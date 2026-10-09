"""Funciones, argumentos y enlaces estáticos. Autor: Felipe Aguilar."""

from ..ir.tac import Const, Op
from ..types import VOID


class FunctionsGen:
    def visitFunctionDeclaration(self, ctx):
        with self.function(self.record_of(self.symbol_of(ctx))):
            self.visit(ctx.block())

    def call_function(self, fn, callee, args_ctx, receiver=None):
        # Evaluar primero evita mezclar parámetros de llamadas anidadas.
        values = [receiver] if receiver is not None else []
        expressions = args_ctx.expression() if args_ctx else []
        for expr, param in zip(expressions, fn.params):
            value = self.gen_expr(expr, param.type)
            values.append(self.snapshot(value))
        for value in values:
            self.emit(Op.PARAM, value)
        self.release(*values, callee)
        result = self.new_temp(fn.return_type) if fn.return_type != VOID else None
        self.emit(Op.CALL, callee, Const(len(values)), result)
        return result

    def visitReturnStatement(self, ctx):
        value = None
        if ctx.expression():
            value = self.gen_expr(ctx.expression(), self.record.function.return_type)
        self.emit_return(value)
