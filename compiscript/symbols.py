"""Tabla de símbolos con manejo de entornos (scopes) anidados.

Diseñada para servir a esta fase (análisis semántico) y a las siguientes
(generación de código intermedio): cada símbolo guarda tipo, categoría,
posición en el fuente, tamaño y desplazamiento dentro de su entorno, y cada
entorno conoce a su padre, a sus hijos y al símbolo que lo "posee"
(la función o clase que lo creó).

Para la generación de código intermedio la tabla se completa, después del
análisis semántico, con `SymbolTable.allocate_storage()`:
  * tamaño en bytes de cada símbolo según su tipo (`sizeof`),
  * dirección en tiempo de ejecución (`global[off]`, `fp[+off]`, `fp[-off]`,
    `this[+off]`),
  * etiqueta de cada función/método (`fact`, `Perro_hablar`),
  * un `ActivationRecord` por función (y uno para el código global, `main`),
  * un `ClassLayout` por clase (atributos heredados primero + vtable).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from .types import BOOLEAN, ClassType, FunctionType, Type, VOID


# ---------------------------------------------------------------------------
# Tamaños en bytes
# ---------------------------------------------------------------------------

WORD = 4            # palabra de MIPS: integer, float, referencias y punteros
TEMP_SLOT = WORD    # cada temporal ocupa una palabra (int o float de precisión simple)


def sizeof(t: Optional[Type]) -> int:
    """Bytes que ocupa un valor de tipo `t` en memoria (pensado para MIPS32).
    integer: 4, float: 4 (IEEE 754 de precisión simple, registros $f),
    boolean: 1 (lb/sb); string, arreglos y objetos son referencias de 4 bytes
    (el contenido vive en el heap)."""
    if t == BOOLEAN:
        return 1
    return WORD


def align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


# ---------------------------------------------------------------------------
# Símbolos
# ---------------------------------------------------------------------------

class SymbolKind:
    VARIABLE = "variable"
    CONSTANT = "constant"
    PARAMETER = "parameter"
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    FIELD = "field"


@dataclass
class Symbol:
    name: str
    kind: str
    type: Type
    line: int = 0
    column: int = 0
    scope: Optional["Scope"] = None      # entorno donde fue declarado
    initialized: bool = False
    offset: int = 0                       # desplazamiento dentro del entorno
    captured: bool = False                # variable capturada por un closure
    # --- tiempo de ejecución (lo llena SymbolTable.allocate_storage) ---------
    storage: Optional[str] = None         # Storage.GLOBAL / PARAM / LOCAL / FIELD
    frame_offset: Optional[int] = None    # con signo: + parámetros, - locales
    label: Optional[str] = None           # funciones, métodos y clases

    @property
    def size(self) -> int:
        return sizeof(self.type)

    @property
    def address(self) -> Optional[str]:
        """`global[off]`, `fp[+off]` (parámetro), `fp[-off]` (local) o
        `this[+off]` (atributo). None si el símbolo no ocupa memoria."""
        if self.storage is None or self.frame_offset is None:
            return None
        off = self.frame_offset
        if self.storage == Storage.GLOBAL:
            return f"global[{off}]"
        if self.storage == Storage.FIELD:
            return f"this[+{off}]"
        return f"fp[{'+' if off >= 0 else '-'}{abs(off)}]"

    @property
    def is_callable(self) -> bool:
        return self.kind in (SymbolKind.FUNCTION, SymbolKind.METHOD)

    def __str__(self) -> str:
        return f"{self.kind} {self.name}: {self.type}"


@dataclass
class FunctionSymbol(Symbol):
    params: List[Symbol] = field(default_factory=list)
    return_type: Type = VOID
    body_scope: Optional["Scope"] = None
    captures: List[Symbol] = field(default_factory=list)   # closures
    calls: List["FunctionSymbol"] = field(default_factory=list)  # funciones/métodos que invoca
    has_return: bool = False
    activation: Optional["ActivationRecord"] = None
    owner_class: Optional["ClassSymbol"] = None            # métodos

    def __post_init__(self):
        if not isinstance(self.type, FunctionType):
            self.type = FunctionType(tuple(p.type for p in self.params), self.return_type)

    def refresh_type(self) -> None:
        self.type = FunctionType(tuple(p.type for p in self.params), self.return_type)

    def signature(self) -> str:
        ps = ", ".join(f"{p.name}: {p.type}" for p in self.params)
        return f"{self.name}({ps}): {self.return_type}"


@dataclass
class ClassSymbol(Symbol):
    parent: Optional["ClassSymbol"] = None
    members: Optional["Scope"] = None
    layout: Optional["ClassLayout"] = None

    @property
    def object_size(self) -> int:
        return self.layout.object_size if self.layout else 0

    @property
    def class_type(self) -> ClassType:
        return self.type  # type: ignore[return-value]

    def lookup_member(self, name: str) -> Optional[Symbol]:
        """Busca un atributo/método en la clase y en su cadena de herencia."""
        cur: Optional[ClassSymbol] = self
        seen = set()
        while cur is not None and cur.name not in seen:
            if cur.members is not None:
                sym = cur.members.resolve_local(name)
                if sym is not None:
                    return sym
            seen.add(cur.name)
            cur = cur.parent
        return None

    def constructor(self) -> Optional[FunctionSymbol]:
        sym = self.lookup_member("constructor")
        return sym if isinstance(sym, FunctionSymbol) else None


# ---------------------------------------------------------------------------
# Entornos
# ---------------------------------------------------------------------------

class ScopeKind:
    GLOBAL = "global"
    FUNCTION = "function"
    CLASS = "class"
    BLOCK = "block"
    LOOP = "loop"
    SWITCH = "switch"


class Scope:
    _counter = 0

    def __init__(self, kind: str, parent: Optional["Scope"] = None,
                 owner: Optional[Symbol] = None, name: Optional[str] = None):
        Scope._counter += 1
        self.id = Scope._counter
        self.kind = kind
        self.parent = parent
        self.owner = owner
        self.name = name or (owner.name if owner else kind)
        self.symbols: Dict[str, Symbol] = {}
        self.children: List[Scope] = []
        self._next_offset = 0
        if parent is not None:
            parent.children.append(self)

    # --- declaración / resolución -------------------------------------------------

    def define(self, sym: Symbol) -> bool:
        """Registra `sym`. Devuelve False si ya existía en ESTE entorno."""
        if sym.name in self.symbols:
            return False
        sym.scope = self
        if sym.kind in (SymbolKind.VARIABLE, SymbolKind.CONSTANT,
                        SymbolKind.PARAMETER, SymbolKind.FIELD):
            sym.offset = self._next_offset
            self._next_offset += sym.size
        self.symbols[sym.name] = sym
        return True

    def resolve_local(self, name: str) -> Optional[Symbol]:
        return self.symbols.get(name)

    def resolve(self, name: str) -> Optional[Symbol]:
        """Busca en este entorno y hacia arriba por la cadena de padres."""
        cur: Optional[Scope] = self
        while cur is not None:
            sym = cur.symbols.get(name)
            if sym is not None:
                return sym
            cur = cur.parent
        return None

    # --- consultas sobre el contexto ----------------------------------------------

    def ancestors(self) -> Iterator["Scope"]:
        cur = self
        while cur is not None:
            yield cur
            cur = cur.parent

    def enclosing(self, kind: str) -> Optional["Scope"]:
        for s in self.ancestors():
            if s.kind == kind:
                return s
        return None

    def enclosing_function(self) -> Optional[FunctionSymbol]:
        for s in self.ancestors():
            if s.kind == ScopeKind.FUNCTION and isinstance(s.owner, FunctionSymbol):
                return s.owner
        return None

    def enclosing_class(self) -> Optional[ClassSymbol]:
        for s in self.ancestors():
            if s.kind == ScopeKind.CLASS and isinstance(s.owner, ClassSymbol):
                return s.owner
        return None

    def in_loop(self) -> bool:
        """True si hay un bucle entre este entorno y la función más cercana."""
        for s in self.ancestors():
            if s.kind == ScopeKind.LOOP:
                return True
            if s.kind in (ScopeKind.FUNCTION, ScopeKind.CLASS):
                return False
        return False

    def in_breakable(self) -> bool:
        for s in self.ancestors():
            if s.kind in (ScopeKind.LOOP, ScopeKind.SWITCH):
                return True
            if s.kind in (ScopeKind.FUNCTION, ScopeKind.CLASS):
                return False
        return False

    @property
    def depth(self) -> int:
        return sum(1 for _ in self.ancestors()) - 1

    @property
    def frame_size(self) -> int:
        return self._next_offset

    def path(self) -> str:
        return "/".join(reversed([s.name for s in self.ancestors()]))

    def __repr__(self) -> str:
        return f"<Scope {self.id} {self.kind} '{self.name}' {list(self.symbols)}>"


# ---------------------------------------------------------------------------
# Entornos de ejecución: registros de activación y layout de objetos
# ---------------------------------------------------------------------------

class Storage:
    GLOBAL = "global"   # área estática: variables del código de nivel superior
    PARAM = "param"     # parámetro: fp[+off]
    LOCAL = "local"     # local de la función (bloques anidados aplanados): fp[-off]
    FIELD = "field"     # atributo de objeto: [obj + off]


_DATA_KINDS = (SymbolKind.VARIABLE, SymbolKind.CONSTANT, SymbolKind.PARAMETER, SymbolKind.FIELD)


@dataclass
class ActivationRecord:
    """Marco de una función en la pila. Cada campo del encabezado existe solo
    si la función lo usa (se decide con el grafo de llamadas y las capturas):

        fp + ...        parámetros (el 0 es `this` en los métodos); los apila el llamador
        [static link]   la función, o una anidada en ella, lee variables de una
                        función externa (closures) o llama a una función que lo necesita
        [dir. retorno]  la función llama a otras (no es hoja): `jal` sobrescribe $ra
        fp + 0          control link (fp del llamador), para restaurarlo al retornar
        fp - ...        locales (incluye los de bloques anidados, aplanados)
        ...             temporales (una palabra cada uno; en MIPS, ranuras de spill)

    `main` (código de nivel superior, nivel 0) no tiene encabezado: nadie la
    llama ni retorna a un llamador. `level` es la profundidad léxica (main = 0,
    función global = 1, anidada = 2, ...): para leer una variable capturada se
    siguen `nivel_actual - nivel_dueño` enlaces estáticos.
    """

    HEADER_USES = {
        "control_link": "restaurar el fp del llamador al retornar",
        "return_address": "volver al llamador: la función hace llamadas y jal sobrescribe $ra",
        "static_link": "acceder a variables de funciones externas (closures)",
    }

    name: str
    label: str
    level: int
    function: Optional[FunctionSymbol] = None
    parent: Optional["ActivationRecord"] = None     # destino del static link
    this: Optional[Symbol] = None
    params: List[Symbol] = field(default_factory=list)
    locals: List[Symbol] = field(default_factory=list)
    params_size: int = 0
    locals_size: int = 0
    temp_count: int = 0
    needs_control_link: bool = True
    needs_return_address: bool = True
    needs_static_link: bool = False

    # --- encabezado ---------------------------------------------------------------

    def header(self) -> List[str]:
        """Campos presentes, de fp+0 hacia arriba."""
        out = []
        if self.needs_control_link:
            out.append("control_link")
        if self.needs_return_address:
            out.append("return_address")
        if self.needs_static_link:
            out.append("static_link")
        return out

    @property
    def header_size(self) -> int:
        return WORD * len(self.header())

    def header_offset(self, name: str) -> Optional[int]:
        """Offset (respecto a fp) de un campo del encabezado, o None si no existe."""
        fields = self.header()
        return WORD * fields.index(name) if name in fields else None

    @property
    def params_base(self) -> int:
        return self.header_size

    # --- construcción -------------------------------------------------------------

    def add_param(self, sym: Symbol) -> None:
        off = align(self.params_base + self.params_size, min(sym.size, WORD))
        sym.storage, sym.frame_offset = Storage.PARAM, off
        self.params_size = off + sym.size - self.params_base
        self.params.append(sym)

    def add_local(self, sym: Symbol) -> None:
        end = align(self.locals_size + sym.size, sym.size)
        sym.storage, sym.frame_offset = Storage.LOCAL, -end
        self.locals_size = end
        self.locals.append(sym)

    def set_temps(self, count: int) -> None:
        """Lo llama el generador al cerrar la función con `TempAllocator.max_live`."""
        self.temp_count = count

    # --- consultas ----------------------------------------------------------------

    @property
    def temps_base(self) -> int:
        return align(self.locals_size, WORD)

    def temp_address(self, index: int) -> str:
        """Dirección de la ranura del temporal t{index} (1-based)."""
        return f"fp[-{self.temps_base + index * TEMP_SLOT}]"

    @property
    def temps_size(self) -> int:
        return self.temp_count * TEMP_SLOT

    @property
    def frame_size(self) -> int:
        return self.header_size + align(self.params_size, WORD) + self.temps_base + self.temps_size

    def slots(self) -> List[dict]:
        """Contenido del marco, de direcciones altas a bajas (para el volcado)."""
        out = [{"address": p.address, "content": f"param {p.name}: {p.type}", "size": p.size,
                "use": "argumento"} for p in reversed(self.params)]
        names = {"control_link": "control link (fp anterior)",
                 "return_address": "dirección de retorno",
                 "static_link": "static link" + (f" -> {self.parent.label}" if self.parent else "")}
        for h in reversed(self.header()):
            out.append({"address": f"fp[+{self.header_offset(h)}]", "content": names[h],
                        "size": WORD, "use": self.HEADER_USES[h]})
        out += [{"address": s.address, "content": f"local {s.name}: {s.type}", "size": s.size,
                 "use": "variable local"} for s in self.locals]
        out += [{"address": self.temp_address(i), "content": f"temporal t{i}", "size": TEMP_SLOT,
                 "use": "valor intermedio"} for i in range(1, self.temp_count + 1)]
        return out

    def to_dict(self) -> dict:
        return {
            "name": self.name, "label": self.label, "level": self.level,
            "static_link": self.parent.label if self.parent and self.needs_static_link else None,
            "header": [{"field": h, "offset": self.header_offset(h), "use": self.HEADER_USES[h]}
                       for h in self.header()],
            "params_size": self.params_size, "locals_size": self.locals_size,
            "temps": self.temp_count, "frame_size": self.frame_size,
            "slots": self.slots(),
        }


@dataclass
class ClassLayout:
    """Distribución de un objeto en el heap:

        [obj + 0]   puntero a la tabla de métodos (vtable) de su clase
        [obj + 4]   atributos heredados (mismos offsets que en la clase padre)
        ...         atributos propios

    `vtable` conserva el orden del padre; un método sobreescrito reemplaza
    la etiqueta en la MISMA ranura, por lo que `method_slot` es válido para
    cualquier subclase (despacho dinámico). El constructor no va en la vtable:
    se llama de forma directa después de `new`.
    """

    VTABLE_OFFSET = 0

    name: str
    parent: Optional["ClassLayout"] = None
    fields: List[Tuple[str, int, int, str]] = field(default_factory=list)  # nombre, offset, tamaño, clase dueña
    vtable: List[Tuple[str, str]] = field(default_factory=list)            # (método, etiqueta)
    object_size: int = WORD
    constructor_label: Optional[str] = None

    def field_offset(self, name: str) -> Optional[int]:
        for fname, off, _, _ in self.fields:
            if fname == name:
                return off
        return None

    def method_slot(self, name: str) -> Optional[int]:
        for i, (mname, _) in enumerate(self.vtable):
            if mname == name:
                return i
        return None

    def method_label(self, name: str) -> Optional[str]:
        slot = self.method_slot(name)
        return self.vtable[slot][1] if slot is not None else None

    def to_dict(self) -> dict:
        return {
            "name": self.name, "parent": self.parent.name if self.parent else None,
            "object_size": self.object_size, "constructor": self.constructor_label,
            "fields": [{"name": n, "offset": o, "size": sz, "declared_in": c}
                       for n, o, sz, c in self.fields],
            "vtable": [{"slot": i, "method": m, "label": lab} for i, (m, lab) in enumerate(self.vtable)],
        }


# ---------------------------------------------------------------------------
# Tabla de símbolos
# ---------------------------------------------------------------------------

class SymbolTable:
    """Mantiene el entorno global, el entorno actual y el historial completo."""

    def __init__(self):
        Scope._counter = 0
        self.global_scope = Scope(ScopeKind.GLOBAL, name="global")
        self.current = self.global_scope
        self.scopes: List[Scope] = [self.global_scope]
        # --- entornos de ejecución (allocate_storage) ---
        self.main: Optional[ActivationRecord] = None
        self.activation_records: List[ActivationRecord] = []
        self.class_layouts: Dict[str, ClassLayout] = {}
        self.globals_size = 0
        self._owner: Dict[int, ActivationRecord] = {}   # id(símbolo) -> marco dueño

    # --- navegación ---------------------------------------------------------------

    def push(self, kind: str, owner: Optional[Symbol] = None,
             name: Optional[str] = None) -> Scope:
        scope = Scope(kind, parent=self.current, owner=owner, name=name)
        self.scopes.append(scope)
        self.current = scope
        return scope

    def pop(self) -> Scope:
        finished = self.current
        if finished.parent is None:
            raise RuntimeError("no se puede salir del entorno global")
        self.current = finished.parent
        return finished

    # --- atajos -------------------------------------------------------------------

    def define(self, sym: Symbol) -> bool:
        return self.current.define(sym)

    def resolve(self, name: str) -> Optional[Symbol]:
        return self.current.resolve(name)

    def resolve_local(self, name: str) -> Optional[Symbol]:
        return self.current.resolve_local(name)

    # --- entornos de ejecución ---------------------------------------------------

    def allocate_storage(self) -> "SymbolTable":
        """Asigna direcciones, etiquetas, registros de activación y layouts.

        Se ejecuta una vez terminada la pasada semántica (todos los entornos
        ya existen). Es idempotente y tolera programas con errores (los tipos
        ERROR ocupan una palabra), para que el IDE siempre pueda mostrarla.
        """
        if self.main is not None:
            return self
        used_labels = {"main"}
        self.main = ActivationRecord("main", "main", level=0)
        self.activation_records = [self.main]

        def unique(base: str) -> str:
            label, k = base, 1
            while label in used_labels:
                k += 1
                label = f"{base}_{k}"
            used_labels.add(label)
            return label

        def function_scope(scope: Scope) -> Optional[Scope]:
            """Entorno FUNCTION más cercano (sin cruzar una clase)."""
            for s in scope.ancestors():
                if s.kind == ScopeKind.FUNCTION:
                    return s
                if s.kind == ScopeKind.CLASS:
                    return None
            return None

        # 1) etiquetas de funciones, métodos y clases (en orden del fuente).
        for scope in self.scopes:
            for sym in scope.symbols.values():
                if isinstance(sym, ClassSymbol):
                    sym.label = unique(sym.name)
                elif isinstance(sym, FunctionSymbol):
                    if scope.kind == ScopeKind.CLASS and isinstance(scope.owner, ClassSymbol):
                        sym.owner_class = scope.owner
                        sym.label = unique(f"{scope.owner.name}_{sym.name}")
                    else:
                        outer = scope.enclosing_function()
                        prefix = f"{outer.label}_" if outer is not None and outer.label else ""
                        sym.label = unique(prefix + sym.name)

        # 2) un registro de activación por función (aún sin parámetros).
        records: Dict[int, ActivationRecord] = {}
        for scope in self.scopes:
            if scope.kind == ScopeKind.FUNCTION and isinstance(scope.owner, FunctionSymbol):
                fn = scope.owner
                outer_scope = function_scope(scope.parent) if scope.parent else None
                parent = records.get(outer_scope.id) if outer_scope else self.main
                ar = ActivationRecord(fn.name, fn.label or fn.name, level=parent.level + 1,
                                      function=fn, parent=parent)
                if fn.owner_class is not None:
                    ar.this = Symbol("this", SymbolKind.PARAMETER, fn.owner_class.type,
                                     fn.line, fn.column, scope=scope, initialized=True)
                fn.activation = ar
                records[scope.id] = ar
                self.activation_records.append(ar)

        # 3) qué campos del encabezado usa cada marco.
        self._decide_header(records, function_scope)

        # 4) parámetros, locales y globales.
        for ar in self.activation_records[1:]:
            for prm in ([ar.this] if ar.this else []) + list(ar.function.params):
                ar.add_param(prm)
                self._owner[id(prm)] = ar
        for scope in self.scopes:
            if scope.kind == ScopeKind.CLASS:
                continue   # los atributos se ubican en el layout del objeto
            fscope = function_scope(scope)
            for sym in scope.symbols.values():
                if sym.kind not in _DATA_KINDS or sym.kind == SymbolKind.PARAMETER:
                    continue
                if fscope is None:
                    off = align(self.globals_size, sym.size)
                    sym.storage, sym.frame_offset = Storage.GLOBAL, off
                    self.globals_size = off + sym.size
                    self._owner[id(sym)] = self.main
                else:
                    ar = records[fscope.id]
                    ar.add_local(sym)
                    self._owner[id(sym)] = ar

        # 5) layout de cada clase (el padre primero).
        for scope in self.scopes:
            for sym in scope.symbols.values():
                if isinstance(sym, ClassSymbol):
                    self._layout(sym)
        return self

    def _decide_header(self, records: Dict[int, ActivationRecord], function_scope) -> None:
        """Encabezado por uso:
          * main no tiene encabezado;
          * dirección de retorno solo en funciones que llaman a otras;
          * static link en cada marco que hay que atravesar para llegar a una
            variable capturada, y en el llamador que debe calcular el static link
            de una función que lo necesita (punto fijo sobre el grafo de llamadas).
        """
        self.main.needs_control_link = False
        self.main.needs_return_address = False
        ars = self.activation_records[1:]
        for ar in ars:
            ar.needs_return_address = bool(ar.function.calls)

        def mark(ar: ActivationRecord, hops: int) -> bool:
            changed, cur = False, ar
            for _ in range(hops):
                if cur is None or cur is self.main:
                    break
                if not cur.needs_static_link:
                    cur.needs_static_link = changed = True
                cur = cur.parent
            return changed

        for ar in ars:
            for captured in ar.function.captures:
                owner_scope = function_scope(captured.scope) if captured.scope else None
                owner = records.get(owner_scope.id) if owner_scope else None
                if owner is not None:
                    mark(ar, ar.level - owner.level)
        changed = True
        while changed:
            changed = False
            for ar in ars:
                for callee in ar.function.calls:
                    target = callee.activation
                    if target is not None and target.needs_static_link:
                        # el static link del llamado es el marco de nivel q-1:
                        # desde el llamador (nivel p) se siguen p - q + 1 enlaces.
                        changed |= mark(ar, ar.level - target.level + 1)

    def _layout(self, cls: ClassSymbol) -> ClassLayout:
        if cls.layout is not None:
            return cls.layout
        parent = self._layout(cls.parent) if cls.parent is not None else None
        lay = ClassLayout(cls.name, parent)
        if parent is not None:
            lay.fields = list(parent.fields)
            lay.vtable = list(parent.vtable)
            lay.object_size = parent.object_size
            lay.constructor_label = parent.constructor_label
        cursor = lay.object_size
        members = cls.members.symbols.values() if cls.members else []
        for sym in members:
            if sym.kind in (SymbolKind.FIELD, SymbolKind.CONSTANT):
                off = align(cursor, sym.size)
                sym.storage, sym.frame_offset = Storage.FIELD, off
                lay.fields.append((sym.name, off, sym.size, cls.name))
                cursor = off + sym.size
            elif isinstance(sym, FunctionSymbol):
                if sym.name == "constructor":
                    lay.constructor_label = sym.label
                    continue
                slot = lay.method_slot(sym.name)
                if slot is None:
                    lay.vtable.append((sym.name, sym.label))
                else:
                    lay.vtable[slot] = (sym.name, sym.label)   # sobreescritura
        lay.object_size = align(cursor, WORD)
        cls.layout = lay
        self.class_layouts[cls.name] = lay
        return lay

    def owner_record(self, sym: Symbol) -> Optional[ActivationRecord]:
        """Registro de activación al que pertenece la variable/parámetro `sym`."""
        return self._owner.get(id(sym))

    def hops(self, sym: Symbol, current: ActivationRecord) -> int:
        """Enlaces estáticos a seguir desde `current` para llegar a `sym`
        (0 para globales y para variables del propio marco)."""
        if sym.storage not in (Storage.PARAM, Storage.LOCAL):
            return 0
        owner = self.owner_record(sym)
        return max(0, current.level - owner.level) if owner else 0

    def record_of(self, label: str) -> Optional[ActivationRecord]:
        for ar in self.activation_records:
            if ar.label == label:
                return ar
        return None

    # --- reportes -----------------------------------------------------------------

    def rows(self) -> List[dict]:
        """Vista plana de todos los símbolos, útil para el IDE y la documentación."""
        out = []
        for scope in self.scopes:
            for sym in scope.symbols.values():
                row = {
                    "scope_id": scope.id,
                    "scope": scope.path(),
                    "scope_kind": scope.kind,
                    "name": sym.name,
                    "kind": sym.kind,
                    "type": str(sym.type),
                    "line": sym.line,
                    "column": sym.column,
                    "size": sym.size,
                    "offset": sym.offset,
                    "initialized": sym.initialized,
                    "captured": sym.captured,
                    "address": sym.address or "",
                    "label": sym.label or "",
                    "extra": "",
                }
                if isinstance(sym, FunctionSymbol):
                    row["extra"] = sym.signature()
                    if sym.captures:
                        row["extra"] += " captura: " + ", ".join(c.name for c in sym.captures)
                elif isinstance(sym, ClassSymbol) and sym.parent is not None:
                    row["extra"] = f"hereda de {sym.parent.name}"
                out.append(row)
        return out

    def __str__(self) -> str:
        rows = self.rows()
        if not rows:
            return "(tabla de símbolos vacía)"
        headers = ["scope", "name", "kind", "type", "line", "size", "address", "label", "extra"]
        widths = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in headers}
        line = " | ".join(h.ljust(widths[h]) for h in headers)
        sep = "-+-".join("-" * widths[h] for h in headers)
        body = "\n".join(" | ".join(str(r[h]).ljust(widths[h]) for h in headers) for r in rows)
        return f"{line}\n{sep}\n{body}"

    # --- volcado de entornos de ejecución -----------------------------------------

    def to_dict(self) -> dict:
        """Tabla completa para el IDE y la documentación (serializable a JSON)."""
        self.allocate_storage()
        return {
            "symbols": self.rows(),
            "globals_size": self.globals_size,
            "activation_records": [ar.to_dict() for ar in self.activation_records],
            "classes": [lay.to_dict() for lay in self.class_layouts.values()],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def format_runtime(self) -> str:
        """Volcado de texto de registros de activación y layouts de clases."""
        self.allocate_storage()
        out = [f"Área global: {self.globals_size} bytes"]
        for row in self.rows():
            if row["address"].startswith("global"):
                out.append(f"  {row['address']:<14} {row['name']}: {row['type']}")
        for ar in self.activation_records:
            link = f", static link -> {ar.parent.label}" if ar.needs_static_link else ""
            out.append("")
            out.append(f"Registro de activación {ar.label} (nivel {ar.level}{link}) "
                       f"frame_size = {ar.frame_size}")
            for slot in ar.slots():
                out.append(f"  {slot['address']:<14} {slot['content']} ({slot['size']} B)")
        for lay in self.class_layouts.values():
            parent = f" : {lay.parent.name}" if lay.parent else ""
            out.append("")
            out.append(f"Clase {lay.name}{parent}  object_size = {lay.object_size}")
            out.append(f"  [obj + {ClassLayout.VTABLE_OFFSET:<3}] vtable")
            for name, off, size, owner in lay.fields:
                inh = " (heredado)" if owner != lay.name else ""
                out.append(f"  [obj + {off:<3}] {name} ({size} B){inh}")
            for i, (m, lab) in enumerate(lay.vtable):
                out.append(f"  vtable[{i}] {m} -> {lab}")
            if lay.constructor_label:
                out.append(f"  constructor -> {lay.constructor_label}")
        return "\n".join(out)
