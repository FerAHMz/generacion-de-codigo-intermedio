"""Infraestructura común del generador de código intermedio (segunda pasada).

`CodeGenBase` recorre el MISMO árbol que la fase semántica, apoyándose en lo
que esta dejó anotado (`AnalysisResult`):
  * `node_types[ctx]`   tipo de cada expresión (para concat, int_to_float, ...),
  * `node_symbols[ctx]` símbolo al que resuelve cada identificador/declaración,
  * `node_scopes[ctx]`  entorno que abre cada bloque/función/clase/bucle,
  * la tabla de símbolos con direcciones, registros de activación y layouts.

Ofrece a los mixins de generación (expresiones, control de flujo, funciones,
clases):
  * emisión de cuádruplos (`emit`, `emit_binary`, `emit_copy`, saltos, ...),
  * etiquetas únicas (`new_label`, `place`),
  * temporales reciclados por función (`new_temp`, `release`),
  * contexto de función: cada cuerpo se genera en su propio búfer, con su
    propio `TempAllocator`, entre `func_begin`/`func_end` (`function()`),
  * pila de destinos de break/continue (`breakable`, `break_target`,
    `continue_target`) y de manejadores de excepción (`handler`,
    `emit_jump_out`, `emit_return`), que emiten los `pop_handler` necesarios
    cuando un salto abandona uno o más bloques `try`.

Los mixins deben implementar `gen_expr` (valor de una expresión) y
`gen_cond` (código de saltos para una condición).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from antlr4 import ParserRuleContext

from ..generated.CompiscriptParser import CompiscriptParser
from ..generated.CompiscriptVisitor import CompiscriptVisitor
from ..ir.tac import Const, Label, Op, Operand, Quad, TACProgram, Temp, Var
from ..ir.temps import TempAllocator
from ..symbols import ActivationRecord, FunctionSymbol, Scope, Symbol, SymbolTable
from ..types import BOOLEAN, ERROR, FLOAT, INTEGER, Type

P = CompiscriptParser


class CodegenError(Exception):
    """Error interno del generador (el programa ya pasó la fase semántica,
    así que indica un caso no soportado o un bug, no un error del usuario)."""


@dataclass
class JumpTargets:
    """Destinos de `break` y `continue` de la estructura más interna.
    En un `switch` solo hay destino de break (`continue_label=None`)."""

    break_label: Label
    continue_label: Optional[Label] = None
    handlers: int = 0     # manejadores try activos al entrar a la estructura


@dataclass
class _FunctionContext:
    record: ActivationRecord
    code: List[Quad] = field(default_factory=list)
    temps: TempAllocator = field(default_factory=TempAllocator)
    jumps: List[JumpTargets] = field(default_factory=list)
    handlers: int = 0     # push_handler sin su pop_handler en la función actual


class CodeGenBase(CompiscriptVisitor):

    def __init__(self, analysis):
        super().__init__()
        if not analysis.ok:
            raise CodegenError("no se genera código intermedio para un programa con errores")
        self.analysis = analysis
        self.table: SymbolTable = analysis.table.allocate_storage()
        self.node_types: Dict[ParserRuleContext, Type] = analysis.node_types
        self.node_symbols: Dict[object, Symbol] = analysis.node_symbols
        self.node_scopes: Dict[ParserRuleContext, Scope] = analysis.node_scopes
        self._labels = 0
        self._stack: List[_FunctionContext] = []
        self._done: List[List[Quad]] = []     # cuerpos de funciones ya cerradas

    # ============================================================ punto de entrada

    def generate(self) -> TACProgram:
        """Genera el TAC del programa: primero `main` (código de nivel superior),
        luego cada función/método en el orden en que se cerró."""
        with self.function(self.table.main) as main_code:
            self.visit(self.analysis.tree)
        return TACProgram(main_code + [q for body in self._done for q in body])

    def visitProgram(self, ctx: P.ProgramContext):
        for st in ctx.statement():
            self.visit(st)

    def visitStatement(self, ctx: P.StatementContext):
        return self.visit(ctx.getChild(0))

    # ===================================================== contrato de los mixins

    def gen_expr(self, ctx) -> Operand:
        """Genera el código de la expresión `ctx` y devuelve el operando que
        contiene su valor (Const, Var o Temp). Si devuelve un Temp, quien lo
        consume debe liberarlo con `release`."""
        raise NotImplementedError("gen_expr lo implementa el mixin de expresiones")

    def gen_cond(self, ctx, true_label: Optional[Label], false_label: Optional[Label]) -> None:
        """Código de saltos (corto circuito) para la condición `ctx`: salta a
        `true_label` si es verdadera y a `false_label` si es falsa. Un destino
        `None` significa "seguir con la instrucción siguiente" (fall-through)."""
        raise NotImplementedError("gen_cond lo implementa el mixin de expresiones")

    # ================================================================== emisión

    @property
    def _ctx(self) -> _FunctionContext:
        if not self._stack:
            raise CodegenError("no hay una función abierta")
        return self._stack[-1]

    @property
    def code(self) -> List[Quad]:
        """Búfer de la función que se está generando."""
        return self._ctx.code

    @property
    def record(self) -> ActivationRecord:
        """Registro de activación de la función que se está generando."""
        return self._ctx.record

    def emit(self, op: str, arg1: Optional[Operand] = None, arg2: Optional[Operand] = None,
             result: Optional[Operand] = None, comment: str = "") -> Quad:
        quad = Quad(op, arg1, arg2, result, comment)
        self.code.append(quad)
        return quad

    def emit_copy(self, dst: Operand, src: Operand, comment: str = "") -> Quad:
        """`dst = src` y libera `src` si era temporal."""
        self.release(src)
        return self.emit(Op.ASSIGN, src, None, dst, comment)

    def emit_binary(self, op: str, a: Operand, b: Operand, type: Optional[Type] = None) -> Temp:
        """`t = a op b`: libera los operandos ANTES de pedir el resultado, de
        modo que el resultado puede reutilizar el temporal de un operando.
        `type` es el tipo del resultado (por defecto boolean en relacionales y
        float si algún operando es float)."""
        if type is None:
            type = BOOLEAN if op in Op.RELOPS else (FLOAT if a.is_float or b.is_float else None)
        self.release(a, b)
        t = self.new_temp(type)
        self.emit(op, a, b, t)
        return t

    def emit_unary(self, op: str, a: Operand, type: Optional[Type] = None) -> Temp:
        """`t = op a` (minus, not, int_to_float, len)."""
        if type is None:
            type = {Op.INT_TO_FLOAT: FLOAT, Op.NOT: BOOLEAN, Op.LEN: INTEGER}.get(
                op, FLOAT if a.is_float else None)
        self.release(a)
        t = self.new_temp(type)
        self.emit(op, a, None, t)
        return t

    def coerce(self, value: Operand, from_type: Optional[Type], to_type: Optional[Type]) -> Operand:
        """Inserta `int_to_float` donde la semántica promovió integer -> float."""
        if from_type == INTEGER and to_type == FLOAT:
            if isinstance(value, Const) and isinstance(value.value, int):
                return Const(float(value.value))   # se pliega en tiempo de compilación
            return self.emit_unary(Op.INT_TO_FLOAT, value)
        return value

    # ------------------------------------------------------------------ saltos

    def new_label(self) -> Label:
        self._labels += 1
        return Label(f"L{self._labels}")

    def place(self, label: Label) -> Quad:
        """Coloca la etiqueta `label:` en la posición actual."""
        return self.emit(Op.LABEL, result=label)

    def emit_goto(self, label: Label) -> Quad:
        return self.emit(Op.GOTO, result=label)

    def emit_if_rel(self, relop: str, a: Operand, b: Operand, label: Label) -> Quad:
        """`if a relop b goto L` (libera a y b)."""
        self.release(a, b)
        return self.emit(Op.if_rel(relop), a, b, label)

    def emit_if(self, value: Operand, label: Label) -> Quad:
        self.release(value)
        return self.emit(Op.IF, value, None, label)

    def emit_if_false(self, value: Operand, label: Label) -> Quad:
        self.release(value)
        return self.emit(Op.IF_FALSE, value, None, label)

    # -------------------------------------------------------------- temporales

    @property
    def temps(self) -> TempAllocator:
        return self._ctx.temps

    def new_temp(self, type: Optional[Type] = None) -> Temp:
        return self.temps.new(type)

    def release(self, *operands: Optional[Operand]) -> None:
        self.temps.release(*[o for o in operands if o is not None])

    # ============================================================== funciones

    @contextmanager
    def function(self, record: ActivationRecord) -> Iterator[List[Quad]]:
        """Abre el cuerpo de una función:

            with self.function(fn.activation):
                ...  # código del cuerpo

        Emite `func_begin label, frame_size` / `func_end label`, usa un búfer y
        un asignador de temporales propios (el del llamador queda intacto si la
        función está anidada) y, al cerrar, guarda en el registro de activación
        cuántas ranuras de temporales usó y corrige el frame_size de func_begin.
        """
        ctx = _FunctionContext(record)
        self._stack.append(ctx)
        begin = self.emit(Op.FUNC_BEGIN, Label(record.label), Const(record.frame_size))
        try:
            yield ctx.code
        finally:
            self.emit(Op.FUNC_END, Label(record.label))
            record.set_temps(ctx.temps.max_live)
            begin.arg2 = Const(record.frame_size)
            ctx.temps.reset()
            self._stack.pop()
            if record is not self.table.main:
                self._done.append(ctx.code)

    def record_of(self, fn: FunctionSymbol) -> ActivationRecord:
        if fn.activation is None:
            raise CodegenError(f"la función '{fn.name}' no tiene registro de activación")
        return fn.activation

    # =================================================================== bucles

    @contextmanager
    def breakable(self, break_label: Label, continue_label: Optional[Label] = None):
        """Registra los destinos de break/continue mientras se genera el cuerpo
        de un bucle (`continue_label` obligatorio) o de un switch (`None`)."""
        self._ctx.jumps.append(JumpTargets(break_label, continue_label, self._ctx.handlers))
        try:
            yield
        finally:
            self._ctx.jumps.pop()

    def _break_targets(self) -> JumpTargets:
        if not self._ctx.jumps:
            raise CodegenError("'break' fuera de un bucle o switch")
        return self._ctx.jumps[-1]

    def _continue_targets(self) -> JumpTargets:
        for targets in reversed(self._ctx.jumps):
            if targets.continue_label is not None:
                return targets
        raise CodegenError("'continue' fuera de un bucle")

    def break_target(self) -> Label:
        return self._break_targets().break_label

    def continue_target(self) -> Label:
        """Continue salta al bucle más interno, atravesando los switch."""
        return self._continue_targets().continue_label

    # ============================================================ try / catch

    @contextmanager
    def handler(self, catch_label: Label):
        """Cuerpo protegido de un try: `push_handler L` ... `pop_handler`."""
        self.emit(Op.PUSH_HANDLER, result=catch_label)
        self._ctx.handlers += 1
        try:
            yield
        finally:
            self._ctx.handlers -= 1
            self.emit(Op.POP_HANDLER)

    def _pop_handlers(self, down_to: int) -> None:
        for _ in range(self._ctx.handlers - down_to):
            self.emit(Op.POP_HANDLER, comment="salida anticipada del try")

    def emit_jump_out(self, kind: str) -> Quad:
        """`goto` de un break (`kind="break"`) o continue (`"continue"`),
        precedido de un pop_handler por cada try que el salto abandona."""
        targets = self._break_targets() if kind == "break" else self._continue_targets()
        self._pop_handlers(targets.handlers)
        label = targets.break_label if kind == "break" else targets.continue_label
        return self.emit_goto(label)

    def emit_return(self, value: Optional[Operand] = None) -> Quad:
        """`return [x]`, cerrando antes los try abiertos en la función."""
        self._pop_handlers(0)
        self.release(value)
        return self.emit(Op.RETURN, value)

    # ====================================================== anotaciones semánticas

    def type_of(self, ctx) -> Type:
        return self.node_types.get(ctx, ERROR)

    def symbol_of(self, node) -> Symbol:
        sym = self.node_symbols.get(node)
        if sym is None:
            raise CodegenError(f"el nodo '{node.getText()}' no tiene símbolo asociado")
        return sym

    def scope_of(self, ctx) -> Optional[Scope]:
        return self.node_scopes.get(ctx)

    def var(self, sym: Symbol) -> Var:
        """Operando para una variable/parámetro/global, con los saltos de enlace
        estático necesarios si pertenece a una función externa (closure)."""
        if sym.address is None:
            raise CodegenError(f"'{sym.name}' no tiene dirección asignada")
        return Var(sym.name, sym.address, self.table.hops(sym, self.record), sym.type)

    def this_var(self) -> Var:
        this = self.record.this
        if this is None:
            raise CodegenError("'this' fuera de un método")
        return Var("this", this.address, 0, this.type)
