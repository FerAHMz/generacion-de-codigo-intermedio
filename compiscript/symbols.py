"""Tabla de símbolos con manejo de entornos (scopes) anidados.

Diseñada para servir a esta fase (análisis semántico) y a las siguientes
(generación de código intermedio): cada símbolo guarda tipo, categoría,
posición en el fuente, tamaño y desplazamiento dentro de su entorno, y cada
entorno conoce a su padre, a sus hijos y al símbolo que lo "posee"
(la función o clase que lo creó).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from .types import ClassType, FunctionType, Type, VOID


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

    @property
    def size(self) -> int:
        return getattr(self.type, "size", 1)

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
    has_return: bool = False

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
# Tabla de símbolos
# ---------------------------------------------------------------------------

class SymbolTable:
    """Mantiene el entorno global, el entorno actual y el historial completo."""

    def __init__(self):
        Scope._counter = 0
        self.global_scope = Scope(ScopeKind.GLOBAL, name="global")
        self.current = self.global_scope
        self.scopes: List[Scope] = [self.global_scope]

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
        headers = ["scope", "name", "kind", "type", "line", "offset", "size", "extra"]
        widths = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in headers}
        line = " | ".join(h.ljust(widths[h]) for h in headers)
        sep = "-+-".join("-" * widths[h] for h in headers)
        body = "\n".join(" | ".join(str(r[h]).ljust(widths[h]) for h in headers) for r in rows)
        return f"{line}\n{sep}\n{body}"
