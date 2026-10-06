"""Sistema de tipos de Compiscript.

Los tipos son objetos inmutables comparables por valor. `ERROR` es un tipo
"veneno": se asigna a expresiones mal formadas para no reportar errores en
cascada (cualquier operación con ERROR es silenciosamente ERROR).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


class Type:
    """Clase base. Cada subtipo define `name` (representación textual)."""

    name: str = "?"

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    def __eq__(self, other) -> bool:
        return isinstance(other, Type) and self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    # Tamaño en "celdas" para fases posteriores (generación de código).
    size: int = 1


@dataclass(frozen=True, eq=False)
class PrimitiveType(Type):
    name: str
    size: int = 1


INTEGER = PrimitiveType("integer")
FLOAT = PrimitiveType("float")
STRING = PrimitiveType("string")
BOOLEAN = PrimitiveType("boolean")
NULL = PrimitiveType("null")
VOID = PrimitiveType("void")     # funciones sin valor de retorno
ERROR = PrimitiveType("<error>")  # tipo veneno

PRIMITIVES = {"integer": INTEGER, "float": FLOAT, "string": STRING, "boolean": BOOLEAN}


@dataclass(frozen=True, eq=False)
class ArrayType(Type):
    element: Type

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"{self.element}[]"

    @property
    def size(self) -> int:  # type: ignore[override]
        return 1  # referencia

    def depth(self) -> int:
        return 1 + (self.element.depth() if isinstance(self.element, ArrayType) else 0)


@dataclass(eq=False)
class ClassType(Type):
    """Tipo nominal de una clase. `parent` se enlaza al resolver la herencia."""

    name: str
    parent: Optional["ClassType"] = None

    @property
    def size(self) -> int:  # type: ignore[override]
        return 1  # referencia

    def is_subclass_of(self, other: "ClassType") -> bool:
        cur: Optional[ClassType] = self
        seen = set()
        while cur is not None and cur.name not in seen:
            if cur.name == other.name:
                return True
            seen.add(cur.name)
            cur = cur.parent
        return False

    def ancestors(self) -> List["ClassType"]:
        out, cur, seen = [], self.parent, {self.name}
        while cur is not None and cur.name not in seen:
            out.append(cur)
            seen.add(cur.name)
            cur = cur.parent
        return out


@dataclass(frozen=True, eq=False)
class FunctionType(Type):
    """Tipo de una función/método usado como valor (p. ej. en expresiones)."""

    params: Tuple[Type, ...]
    returns: Type

    @property
    def name(self) -> str:  # type: ignore[override]
        ps = ", ".join(str(p) for p in self.params)
        return f"({ps}) -> {self.returns}"


# ---------------------------------------------------------------------------
# Predicados y reglas de compatibilidad
# ---------------------------------------------------------------------------

def is_error(t: Optional[Type]) -> bool:
    return t is None or t == ERROR


def is_numeric(t: Type) -> bool:
    return t == INTEGER or t == FLOAT


def numeric_result(a: Type, b: Type) -> Type:
    """Tipo resultante de una operación aritmética entre dos numéricos:
    si alguno es float, el resultado se promueve a float."""
    return FLOAT if FLOAT in (a, b) else INTEGER


def is_reference(t: Type) -> bool:
    return isinstance(t, (ArrayType, ClassType)) or t == STRING


def is_assignable(target: Type, value: Type) -> bool:
    """¿Puede un valor de tipo `value` guardarse en algo de tipo `target`?"""
    if is_error(target) or is_error(value):
        return True  # ya se reportó; evitar cascada
    if target == value:
        return True
    if target == FLOAT and value == INTEGER:
        return True  # promoción implícita integer -> float (nunca al revés)
    if value == NULL:
        return is_reference(target)
    if isinstance(target, ClassType) and isinstance(value, ClassType):
        return value.is_subclass_of(target)
    if isinstance(target, ArrayType) and isinstance(value, ArrayType):
        return is_assignable(target.element, value.element)
    return False


def are_comparable(a: Type, b: Type) -> bool:
    """Compatibilidad para `==` y `!=`."""
    if is_error(a) or is_error(b):
        return True
    if a == b:
        return True
    if is_numeric(a) and is_numeric(b):
        return True
    if a == NULL or b == NULL:
        return is_reference(a) or is_reference(b)
    if isinstance(a, ClassType) and isinstance(b, ClassType):
        return a.is_subclass_of(b) or b.is_subclass_of(a)
    return False


def are_orderable(a: Type, b: Type) -> bool:
    """Compatibilidad para `<`, `<=`, `>`, `>=`: ambos numéricos."""
    if is_error(a) or is_error(b):
        return True
    return is_numeric(a) and is_numeric(b)


def common_type(types: List[Type]) -> Optional[Type]:
    """Tipo común de los elementos de un arreglo literal, o None si no existe."""
    real = [t for t in types if not is_error(t)]
    if not real:
        return ERROR if types else None
    base = real[0]
    for t in real[1:]:
        if is_assignable(base, t):
            continue
        if is_assignable(t, base):
            base = t
            continue
        return None
    return base
