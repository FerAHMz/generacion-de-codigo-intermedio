"""Intérprete de TAC: ejecuta un `TACProgram` y devuelve lo que imprime.

Sirve para validar el código intermedio de extremo a extremo (el TAC generado
debe producir la misma salida que el programa fuente) y como referencia de la
semántica que tendrá que respetar la fase de MIPS.

    from compiscript.codegen import compile_source
    from compiscript.ir.interp import run
    res = compile_source(src)
    salida = run(res.program, res.table)      # List[str], una línea por print

Modelo de ejecución (docs/LENGUAJE_INTERMEDIO.md §4, §6 y §7.11):
  * Memoria por dirección: `global[off]` en el área global y `fp[±off]` en el
    marco actual; una `Var` con `hops > 0` sigue esa cantidad de static links.
  * Un marco por llamada, con su registro de activación (`table.record_of`),
    sus temporales, el control link (marco llamador) y el static link (marco
    de nivel léxico q-1, siguiendo p - q + 1 enlaces desde el llamador).
  * Heap: arreglos (`alloc`, `len`, `[]`, `[]=`) y objetos (`new` guarda la
    clase; `method` busca la etiqueta en `table.class_layouts[...].vtable`).
  * Excepciones con `ir/runtime.py`: antes de ejecutar una instrucción se
    revisa `checks_for(op)`; si falla se salta al manejador más reciente
    (`push_handler`) descartando los marcos llamados dentro del try. Sin
    manejador, el programa termina y la última línea de salida es el error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..symbols import ActivationRecord, ClassLayout, SymbolTable
from .runtime import CompiscriptRuntimeError, RuntimeErrorKind, checks_for
from .tac import Const, Field, Label, Op, Operand, Quad, TACProgram, Temp, Var

DEFAULT_MAX_STEPS = 1_000_000
INT_BITS = 32


class InterpreterError(Exception):
    """TAC mal formado o ejecución que no termina (no es un error de Compiscript)."""


# ---------------------------------------------------------------------------
# Valores del heap
# ---------------------------------------------------------------------------

class ArrayValue:
    """Arreglo en el heap. Se compara por identidad, como una referencia."""

    def __init__(self, size: int):
        self.items: List[object] = [None] * size

    def __len__(self) -> int:
        return len(self.items)


class ObjectValue:
    """Objeto en el heap: su clase (para la vtable) y atributos por offset."""

    def __init__(self, class_name: str, size: int = 0):
        self.class_name = class_name
        self.size = size
        self.fields: Dict[int, object] = {}


def to_text(value: object) -> str:
    """Cómo se ve un valor con `print` y `concat`."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, ArrayValue):
        return "[" + ", ".join(to_text(x) for x in value.items) + "]"
    if isinstance(value, ObjectValue):
        return f"<{value.class_name}>"
    if isinstance(value, Label):
        return value.name
    return str(value)


def _wrap(n: int) -> int:
    """Aritmética entera de 32 bits con complemento a dos, como en MIPS."""
    n &= (1 << INT_BITS) - 1
    return n - (1 << INT_BITS) if n >= 1 << (INT_BITS - 1) else n


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


# ---------------------------------------------------------------------------
# Marcos y manejadores
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    record: ActivationRecord
    control: Optional["Frame"] = None        # marco del llamador
    static: Optional["Frame"] = None         # marco de la función que lo contiene
    return_pc: int = 0
    result: Optional[Operand] = None         # temporal que recibe el valor de retorno
    memory: Dict[str, object] = field(default_factory=dict)   # "fp[+8]" -> valor
    temps: Dict[int, object] = field(default_factory=dict)

    @property
    def level(self) -> int:
        return self.record.level


@dataclass
class Handler:
    label: Label
    depth: int          # cantidad de marcos en la pila al hacer push_handler
    params: int         # argumentos apilados en ese momento


# ---------------------------------------------------------------------------
# Intérprete
# ---------------------------------------------------------------------------

class Interpreter:
    def __init__(self, program: TACProgram, table: SymbolTable,
                 max_steps: int = DEFAULT_MAX_STEPS,
                 on_print: Optional[Callable[[str], None]] = None):
        self.program = program
        self.quads: List[Quad] = list(program)
        self.table = table
        self.max_steps = max_steps
        self.on_print = on_print
        self.output: List[str] = []
        self.error: Optional[CompiscriptRuntimeError] = None   # error no capturado
        self.steps = 0
        self.globals: Dict[str, object] = {}
        self.frames: List[Frame] = []
        self.params: List[object] = []
        self.handlers: List[Handler] = []
        self.exception: Optional[str] = None
        self.labels: Dict[str, int] = {}
        self.functions: Dict[str, int] = {}
        for i, q in enumerate(self.quads):
            if q.op == Op.LABEL:
                self.labels[q.result.name] = i
            elif q.op == Op.FUNC_BEGIN:
                self.functions[str(q.arg1)] = i

    # ================================================================ ejecución

    def run(self) -> List[str]:
        if not self.quads:
            return self.output
        start = self.functions.get(self.table.main.label if self.table.main else "main", 0)
        self.frames = [Frame(self._record("main"))]
        pc = start + 1
        while self.frames:
            if pc >= len(self.quads):
                raise InterpreterError("la ejecución salió del final del programa")
            self.steps += 1
            if self.steps > self.max_steps:
                raise InterpreterError(f"se superó el límite de {self.max_steps} instrucciones")
            quad = self.quads[pc]
            try:
                pc = self.step(quad, pc)
            except CompiscriptRuntimeError as exc:
                pc = self.raise_error(exc)
        return self.output

    def step(self, q: Quad, pc: int) -> int:
        """Ejecuta una instrucción y devuelve el índice de la siguiente."""
        op = q.op
        self.check(q)
        if op in Op.BINARY:
            self.store(q.result, self.binary(op, self.load(q.arg1), self.load(q.arg2)))
        elif Op.relop_of(op) is not None:
            if self.binary(Op.relop_of(op), self.load(q.arg1), self.load(q.arg2)):
                return self.jump(q.result)
        elif op == Op.ASSIGN:
            self.store(q.result, self.load(q.arg1))
        elif op == Op.NEG:
            v = self.load(q.arg1)
            self.store(q.result, _wrap(-v) if _is_int(v) else -v)
        elif op == Op.NOT:
            self.store(q.result, not self.load(q.arg1))
        elif op == Op.INT_TO_FLOAT:
            self.store(q.result, float(self.load(q.arg1)))
        elif op == Op.CONCAT:
            self.store(q.result, to_text(self.load(q.arg1)) + to_text(self.load(q.arg2)))
        elif op == Op.PRINT:
            self.print(to_text(self.load(q.arg1)))
        elif op == Op.LABEL or op == Op.FUNC_BEGIN:
            pass
        elif op == Op.GOTO:
            return self.jump(q.result)
        elif op == Op.IF:
            if self.load(q.arg1):
                return self.jump(q.result)
        elif op == Op.IF_FALSE:
            if not self.load(q.arg1):
                return self.jump(q.result)
        # --- funciones
        elif op == Op.PARAM:
            self.params.append(self.load(q.arg1))
        elif op == Op.CALL:
            return self.call(q, pc)
        elif op == Op.RETURN:
            return self.ret(self.load(q.arg1) if q.arg1 is not None else None)
        elif op == Op.FUNC_END:
            return self.ret(None)
        # --- arreglos
        elif op == Op.ALLOC:
            n = self.load(q.arg1)
            if not _is_int(n) or n < 0:
                raise InterpreterError(f"tamaño de arreglo inválido: {n!r}")
            self.store(q.result, ArrayValue(n))
        elif op == Op.LEN:
            self.store(q.result, len(self.load(q.arg1)))
        elif op == Op.INDEX_GET:
            self.store(q.result, self.load(q.arg1).items[self.load(q.arg2)])
        elif op == Op.INDEX_SET:
            self.load(q.result).items[self.load(q.arg1)] = self.load(q.arg2)
        # --- objetos
        elif op == Op.NEW:
            size = self.load(q.arg2) if q.arg2 is not None else 0
            self.store(q.result, ObjectValue(self._layout_name(q.arg1), size))
        elif op == Op.FIELD_GET:
            self.store(q.result, self.load(q.arg1).fields.get(self._offset(q.arg2)))
        elif op == Op.FIELD_SET:
            self.load(q.result).fields[self._offset(q.arg1)] = self.load(q.arg2)
        elif op == Op.METHOD:
            self.store(q.result, Label(self.dispatch(self.load(q.arg1), q.arg2)))
        # --- excepciones
        elif op == Op.PUSH_HANDLER:
            self.handlers.append(Handler(q.result, len(self.frames), len(self.params)))
        elif op == Op.POP_HANDLER:
            if not self.handlers:
                raise InterpreterError("pop_handler sin manejador activo")
            self.handlers.pop()
        elif op == Op.GET_EXCEPTION:
            self.store(q.result, self.exception)
        else:
            raise InterpreterError(f"instrucción desconocida: {q.text()}")
        return pc + 1

    # ======================================================== errores en ejecución

    def check(self, q: Quad) -> None:
        """Revisiones de `runtime.checks_for(op)` antes de ejecutar `q`."""
        for kind in checks_for(q.op):
            if kind == RuntimeErrorKind.DIVISION_BY_ZERO:
                if self.load(q.arg2) == 0:
                    raise CompiscriptRuntimeError(kind)
            elif kind == RuntimeErrorKind.NULL_REFERENCE:
                ref = q.result if q.op in (Op.INDEX_SET, Op.FIELD_SET) else q.arg1
                if self.load(ref) is None:
                    raise CompiscriptRuntimeError(kind)
            elif kind == RuntimeErrorKind.INDEX_OUT_OF_BOUNDS:
                array, index = ((q.result, q.arg1) if q.op == Op.INDEX_SET else (q.arg1, q.arg2))
                i = self.load(index)
                if not 0 <= i < len(self.load(array)):
                    raise CompiscriptRuntimeError(kind)

    def raise_error(self, exc: CompiscriptRuntimeError) -> int:
        """Salta al manejador más reciente o termina el programa."""
        if not self.handlers:
            self.error = exc
            self.print(f"Error en tiempo de ejecución: {exc}")
            self.frames.clear()
            return len(self.quads)
        h = self.handlers.pop()
        del self.frames[h.depth:]      # descarta los marcos llamados dentro del try
        del self.params[h.params:]
        self.exception = str(exc)
        return self.jump(h.label)

    # ================================================================ llamadas

    def call(self, q: Quad, pc: int) -> int:
        target = self.load(q.arg1) if isinstance(q.arg1, Temp) else q.arg1
        label = target.name if isinstance(target, Label) else str(target)
        if label not in self.functions:
            raise InterpreterError(f"llamada a una función inexistente: {label}")
        n = self.load(q.arg2) if q.arg2 is not None else 0
        args = self.params[len(self.params) - n:] if n else []
        del self.params[len(self.params) - n:]
        record = self._record(label)
        if len(args) != len(record.params):
            raise InterpreterError(f"{label} espera {len(record.params)} argumento(s) y recibió {len(args)}")
        caller = self.frames[-1]
        static = caller
        for _ in range(caller.level - record.level + 1):
            static = static.static
        frame = Frame(record, control=caller, static=static, return_pc=pc + 1, result=q.result)
        for sym, value in zip(record.params, args):
            frame.memory[sym.address] = value
        self.frames.append(frame)
        return self.functions[label] + 1

    def ret(self, value: object) -> int:
        frame = self.frames.pop()
        if not self.frames:          # fin de main
            return len(self.quads)
        if frame.result is not None:
            self.store(frame.result, value)
        return frame.return_pc

    def dispatch(self, obj: ObjectValue, method: Operand) -> str:
        layout = self._layout(obj.class_name)
        name = method.name if isinstance(method, Label) else str(method)
        label = layout.method_label(name)
        if label is None:
            raise InterpreterError(f"la clase {obj.class_name} no tiene el método {name}")
        return label

    # ================================================================ memoria

    def frame_for(self, var: Var) -> Frame:
        frame = self.frames[-1]
        for _ in range(var.hops):
            if frame.static is None:
                raise InterpreterError(f"static link inexistente al leer {var.name}")
            frame = frame.static
        return frame

    def load(self, operand: Optional[Operand]) -> object:
        if isinstance(operand, Const):
            return operand.value
        if isinstance(operand, Temp):
            temps = self.frames[-1].temps
            if operand.index not in temps:
                raise InterpreterError(f"lectura de {operand} sin valor")
            return temps[operand.index]
        if isinstance(operand, Var):
            if operand.address.startswith("global"):
                return self.globals.get(operand.address)
            return self.frame_for(operand).memory.get(operand.address)
        if isinstance(operand, Label):
            return operand
        raise InterpreterError(f"operando no se puede leer: {operand!r}")

    def store(self, operand: Optional[Operand], value: object) -> None:
        if isinstance(operand, Temp):
            self.frames[-1].temps[operand.index] = value
        elif isinstance(operand, Var):
            if operand.address.startswith("global"):
                self.globals[operand.address] = value
            else:
                self.frame_for(operand).memory[operand.address] = value
        else:
            raise InterpreterError(f"destino inválido: {operand!r}")

    # ============================================================== aritmética

    @staticmethod
    def binary(op: str, a: object, b: object) -> object:
        if op in (Op.EQ, Op.NE):
            same = a is b if isinstance(a, (ArrayValue, ObjectValue)) or isinstance(
                b, (ArrayValue, ObjectValue)) else a == b
            return same if op == Op.EQ else not same
        if op == Op.LT:
            return a < b
        if op == Op.LE:
            return a <= b
        if op == Op.GT:
            return a > b
        if op == Op.GE:
            return a >= b
        ints = _is_int(a) and _is_int(b)
        if op == Op.ADD:
            r = a + b
        elif op == Op.SUB:
            r = a - b
        elif op == Op.MUL:
            r = a * b
        elif op == Op.DIV:
            if ints:     # división entera que trunca hacia cero
                q = abs(a) // abs(b)
                r = q if (a >= 0) == (b >= 0) else -q
            else:
                r = a / b
        elif op == Op.MOD:
            r = abs(a) % abs(b) * (1 if a >= 0 else -1) if ints else a - b * int(a / b)
        else:
            raise InterpreterError(f"operador desconocido: {op}")
        return _wrap(r) if ints else r

    # ================================================================ utilidades

    def print(self, text: str) -> None:
        self.output.append(text)
        if self.on_print is not None:
            self.on_print(text)

    def jump(self, label: Operand) -> int:
        name = label.name if isinstance(label, Label) else str(label)
        if name not in self.labels:
            raise InterpreterError(f"salto a etiqueta inexistente: {name}")
        return self.labels[name]

    def _record(self, label: str) -> ActivationRecord:
        record = self.table.record_of(label)
        if record is None:
            raise InterpreterError(f"no hay registro de activación para {label}")
        return record

    def _layout(self, name: str) -> ClassLayout:
        layout = self.table.class_layouts.get(name)
        if layout is None:
            raise InterpreterError(f"clase desconocida: {name}")
        return layout

    def _layout_name(self, cls: Operand) -> str:
        """`new C` usa la etiqueta de la clase; normalmente coincide con su nombre,
        salvo que choque con otra etiqueta (`C_2`)."""
        name = cls.name if isinstance(cls, Label) else str(cls)
        if name in self.table.class_layouts:
            return name
        base = name.rsplit("_", 1)[0]
        if base in self.table.class_layouts:
            return base
        raise InterpreterError(f"clase desconocida: {name}")

    @staticmethod
    def _offset(f: Optional[Operand]) -> int:
        if isinstance(f, Field):
            return f.offset
        if isinstance(f, Const):
            return int(f.value)
        raise InterpreterError(f"desplazamiento inválido: {f!r}")


def run(program: TACProgram, table: SymbolTable, max_steps: int = DEFAULT_MAX_STEPS,
        on_print: Optional[Callable[[str], None]] = None) -> List[str]:
    """Ejecuta `program` y devuelve las líneas impresas. Un error en tiempo de
    ejecución sin try termina el programa y queda como última línea."""
    return Interpreter(program, table, max_steps, on_print).run()


__all__ = ["ArrayValue", "Interpreter", "InterpreterError", "ObjectValue", "run", "to_text"]
