"""Representación intermedia: código de tres direcciones en cuádruplos.

Cada instrucción es un `Quad(op, arg1, arg2, result)`; los operandos son
objetos tipados (`Temp`, `Var`, `Const`, `Label`, `Field`) y no cadenas, para
que el intérprete y las fases siguientes no tengan que volver a parsear texto.
`str(quad)` produce la forma legible documentada en docs/LENGUAJE_INTERMEDIO.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Union


# ---------------------------------------------------------------------------
# Operandos
# ---------------------------------------------------------------------------

class Operand:
    """Clase base de los operandos de un cuádruplo."""


@dataclass(frozen=True)
class Temp(Operand):
    """Temporal `tN`. Lo crea y recicla `ir.temps.TempAllocator`."""

    index: int

    def __str__(self) -> str:
        return f"t{self.index}"


@dataclass(frozen=True)
class Var(Operand):
    """Variable del programa fuente.

    `name` es el identificador (para leer el TAC) y `address` su dirección
    en tiempo de ejecución, tomada de la tabla de símbolos:
    `global[off]`, `fp[+off]` (parámetro) o `fp[-off]` (local).
    `hops` es la cantidad de enlaces estáticos que hay que seguir desde el
    marco actual para llegar al marco dueño de la variable (0 = marco propio;
    solo es > 0 para variables capturadas por funciones anidadas).
    Dos variables con el mismo nombre (sombra) se distinguen por `address`.
    """

    name: str
    address: str = ""
    hops: int = 0

    def __str__(self) -> str:
        return self.name

    @property
    def location(self) -> str:
        """Dirección completa, incluyendo el acceso por enlace estático."""
        if self.hops and self.address.startswith("fp"):
            return f"fp^{self.hops}" + self.address[2:]
        return self.address


@dataclass(frozen=True)
class Const(Operand):
    """Literal: integer, float, string, boolean o null (`value=None`)."""

    value: Union[int, float, str, bool, None]

    def __str__(self) -> str:
        v = self.value
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return repr(v) if isinstance(v, float) else str(v)


@dataclass(frozen=True)
class Label(Operand):
    """Etiqueta de salto (`L3`) o de función/método/clase (`fact`, `Perro_hablar`)."""

    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Field(Operand):
    """Atributo de un objeto: nombre (para leer) + desplazamiento en bytes."""

    name: str
    offset: int

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Códigos de operación
# ---------------------------------------------------------------------------

class Op:
    # Aritméticas y relacionales con resultado en un valor: t = a op b
    ADD, SUB, MUL, DIV, MOD = "+", "-", "*", "/", "%"
    LT, LE, GT, GE, EQ, NE = "<", "<=", ">", ">=", "==", "!="
    # Unarias: t = op a
    NEG = "minus"        # negación aritmética
    NOT = "not"          # negación lógica (solo cuando se necesita el valor)
    # Copia
    ASSIGN = "="
    # Saltos
    LABEL = "label"
    GOTO = "goto"
    IF = "if"            # if a goto L          (a booleano)
    IF_FALSE = "ifFalse" # ifFalse a goto L
    # if a relop b goto L  -> op = "if<", "if==", ...  (ver Op.if_rel)
    # Funciones
    FUNC_BEGIN = "func_begin"
    FUNC_END = "func_end"
    PARAM = "param"
    CALL = "call"        # t = call f, n   (f: Label directo o Temp de un `method`)
    RETURN = "return"
    # Arreglos
    INDEX_GET = "[]"     # t = a[i]
    INDEX_SET = "[]="    # a[i] = x
    LEN = "len"          # t = len a
    ALLOC = "alloc"      # t = alloc n     (arreglo de n elementos)
    # Objetos
    NEW = "new"          # t = new C, size (reserva + puntero a la vtable de C)
    FIELD_GET = "getf"   # t = [obj + off]
    FIELD_SET = "setf"   # [obj + off] = x
    METHOD = "method"    # t = method obj, nombre   (despacho dinámico por vtable)
    # Varios
    PRINT = "print"
    CONCAT = "concat"    # t = concat a, b   (convierte a string lo que no lo sea)
    INT_TO_FLOAT = "int_to_float"
    # Excepciones (try/catch)
    PUSH_HANDLER = "push_handler"
    POP_HANDLER = "pop_handler"
    GET_EXCEPTION = "get_exception"   # x = exception

    BINARY = {ADD, SUB, MUL, DIV, MOD, LT, LE, GT, GE, EQ, NE}
    RELOPS = {LT, LE, GT, GE, EQ, NE}
    UNARY = {NEG, NOT, INT_TO_FLOAT, LEN}

    @staticmethod
    def if_rel(relop: str) -> str:
        if relop not in Op.RELOPS:
            raise ValueError(f"operador relacional inválido: {relop}")
        return "if" + relop

    @staticmethod
    def relop_of(op: str) -> Optional[str]:
        """Devuelve el relop de un salto condicional `if<` / `if==`..., o None."""
        if op.startswith("if") and op[2:] in Op.RELOPS:
            return op[2:]
        return None

    @staticmethod
    def is_jump(op: str) -> bool:
        return op in (Op.GOTO, Op.IF, Op.IF_FALSE, Op.PUSH_HANDLER) or Op.relop_of(op) is not None


# ---------------------------------------------------------------------------
# Cuádruplo
# ---------------------------------------------------------------------------

@dataclass
class Quad:
    op: str
    arg1: Optional[Operand] = None
    arg2: Optional[Operand] = None
    result: Optional[Operand] = None
    comment: str = ""

    # ------------------------------------------------------------- consultas

    @property
    def is_label(self) -> bool:
        return self.op == Op.LABEL

    @property
    def target(self) -> Optional[Label]:
        """Etiqueta destino si la instrucción es un salto."""
        if Op.is_jump(self.op):
            return self.result if isinstance(self.result, Label) else None
        return None

    def operands(self) -> List[Operand]:
        return [x for x in (self.arg1, self.arg2, self.result) if x is not None]

    def temps(self) -> List[Temp]:
        return [x for x in self.operands() if isinstance(x, Temp)]

    # --------------------------------------------------------------- formato

    def text(self) -> str:
        op, a, b, r = self.op, self.arg1, self.arg2, self.result
        if op in Op.BINARY:
            return f"{r} = {a} {op} {b}"
        relop = Op.relop_of(op)
        if relop is not None:
            return f"if {a} {relop} {b} goto {r}"
        simple = {
            Op.ASSIGN: lambda: f"{r} = {a}",
            Op.NEG: lambda: f"{r} = minus {a}",
            Op.NOT: lambda: f"{r} = not {a}",
            Op.LABEL: lambda: f"{r}:",
            Op.GOTO: lambda: f"goto {r}",
            Op.IF: lambda: f"if {a} goto {r}",
            Op.IF_FALSE: lambda: f"ifFalse {a} goto {r}",
            Op.FUNC_BEGIN: lambda: f"func_begin {a}, {b}",
            Op.FUNC_END: lambda: f"func_end {a}",
            Op.PARAM: lambda: f"param {a}",
            Op.CALL: lambda: f"{r} = call {a}, {b}" if r is not None else f"call {a}, {b}",
            Op.RETURN: lambda: f"return {a}" if a is not None else "return",
            Op.INDEX_GET: lambda: f"{r} = {a}[{b}]",
            Op.INDEX_SET: lambda: f"{r}[{a}] = {b}",
            Op.LEN: lambda: f"{r} = len {a}",
            Op.ALLOC: lambda: f"{r} = alloc {a}",
            Op.NEW: lambda: f"{r} = new {a}, {b}",
            Op.FIELD_GET: lambda: f"{r} = [{a} + {_off(b)}]",
            Op.FIELD_SET: lambda: f"[{r} + {_off(a)}] = {b}",
            Op.METHOD: lambda: f"{r} = method {a}, {b}",
            Op.PRINT: lambda: f"print {a}",
            Op.CONCAT: lambda: f"{r} = concat {a}, {b}",
            Op.INT_TO_FLOAT: lambda: f"{r} = int_to_float {a}",
            Op.PUSH_HANDLER: lambda: f"push_handler {r}",
            Op.POP_HANDLER: lambda: "pop_handler",
            Op.GET_EXCEPTION: lambda: f"{r} = exception",
        }
        fmt = simple.get(op)
        if fmt is None:
            parts = ", ".join(str(x) for x in (a, b) if x is not None)
            return f"{r} = {op} {parts}" if r is not None else f"{op} {parts}"
        return fmt()

    def __str__(self) -> str:
        auto = _field_comment(self)
        note = "; ".join(x for x in (auto, self.comment) if x)
        return f"{self.text()}    # {note}" if note else self.text()


def _off(x: Optional[Operand]) -> str:
    return str(x.offset) if isinstance(x, Field) else str(x)


def _field_comment(q: Quad) -> str:
    if q.op == Op.FIELD_GET and isinstance(q.arg2, Field):
        return f"{q.arg1}.{q.arg2.name}"
    if q.op == Op.FIELD_SET and isinstance(q.arg1, Field):
        return f"{q.result}.{q.arg1.name}"
    return ""


# ---------------------------------------------------------------------------
# Programa
# ---------------------------------------------------------------------------

class TACProgram:
    """Secuencia de cuádruplos con utilidades de formato y verificación."""

    def __init__(self, quads: Optional[Iterable[Quad]] = None):
        self.quads: List[Quad] = list(quads or [])

    def __iter__(self):
        return iter(self.quads)

    def __len__(self) -> int:
        return len(self.quads)

    def __getitem__(self, i):
        return self.quads[i]

    def lines(self) -> List[str]:
        """Instrucciones como texto; las etiquetas van sin sangría."""
        return [str(q) if q.is_label or q.op in (Op.FUNC_BEGIN, Op.FUNC_END) else "    " + str(q)
                for q in self.quads]

    def format(self, numbered: bool = True) -> str:
        lines = self.lines()
        if not numbered:
            return "\n".join(lines)
        width = len(str(len(lines)))
        return "\n".join(f"{i:>{width}}  {ln}" for i, ln in enumerate(lines, start=1))

    def __str__(self) -> str:
        return self.format(numbered=False)

    # ----------------------------------------------------------- verificación

    def labels(self) -> List[str]:
        return [q.result.name for q in self.quads if q.is_label and isinstance(q.result, Label)]

    def check(self) -> List[str]:
        """Propiedades estructurales que todo TAC generado debe cumplir:
        etiquetas definidas una sola vez, todo salto apunta a una etiqueta
        existente y cada func_begin tiene su func_end. Devuelve la lista de
        problemas (vacía si el programa está bien formado)."""
        problems: List[str] = []
        defined = self.labels()
        seen = set()
        for name in defined:
            if name in seen:
                problems.append(f"etiqueta duplicada: {name}")
            seen.add(name)
        for i, q in enumerate(self.quads, start=1):
            t = q.target
            if t is not None and t.name not in seen:
                problems.append(f"instrucción {i}: salto a etiqueta inexistente {t.name}")
        open_fn: Optional[str] = None
        for i, q in enumerate(self.quads, start=1):
            if q.op == Op.FUNC_BEGIN:
                if open_fn is not None:
                    problems.append(f"instrucción {i}: func_begin {q.arg1} dentro de {open_fn}")
                open_fn = str(q.arg1)
            elif q.op == Op.FUNC_END:
                if open_fn != str(q.arg1):
                    problems.append(f"instrucción {i}: func_end {q.arg1} sin func_begin")
                open_fn = None
        if open_fn is not None:
            problems.append(f"func_begin {open_fn} sin func_end")
        return problems
