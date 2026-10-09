"""Saltos, bucles y excepciones TAC. Autor: Felipe Aguilar."""

from .base import P
from ..ir.tac import Const, Op
from ..types import FLOAT, INTEGER


class ControlFlowGen:
    def visitBlock(self, ctx):
        for statement in ctx.statement():
            self.visit(statement)

    def visitIfStatement(self, ctx):
        otherwise, end = self.new_label(), self.new_label()
        self.gen_cond(ctx.expression(), None, otherwise)
        self.visit(ctx.block(0))
        if len(ctx.block()) == 2:
            self.emit_goto(end)
        self.place(otherwise)
        if len(ctx.block()) == 2:
            self.visit(ctx.block(1))
            self.place(end)

    def visitWhileStatement(self, ctx):
        start, end = self.new_label(), self.new_label()
        self.place(start)
        self.gen_cond(ctx.expression(), None, end)
        with self.breakable(end, start):
            self.visit(ctx.block())
        self.emit_goto(start)
        self.place(end)

    def visitDoWhileStatement(self, ctx):
        start, condition, end = self.new_label(), self.new_label(), self.new_label()
        self.place(start)
        with self.breakable(end, condition):
            self.visit(ctx.block())
        self.place(condition)
        self.gen_cond(ctx.expression(), start, None)
        self.place(end)

    def visitForStatement(self, ctx):
        children = list(ctx.getChildren())
        if isinstance(children[2], (P.VariableDeclarationContext, P.AssignmentContext)):
            self.visit(children[2])
        i = 3
        condition = children[i] if isinstance(children[i], P.ExpressionContext) else None
        i += 2 if condition is not None else 1
        update = children[i] if isinstance(children[i], P.ExpressionContext) else None
        start, step, end = self.new_label(), self.new_label(), self.new_label()
        self.place(start)
        if condition is not None:
            self.gen_cond(condition, None, end)
        with self.breakable(end, step):
            self.visit(ctx.block())
        self.place(step)
        if update is not None:
            self.release(self.gen_expr(update))
        self.emit_goto(start)
        self.place(end)

    def visitForeachStatement(self, ctx):
        array = self.snapshot(self.gen_expr(ctx.expression()))
        index, length = self.new_temp(INTEGER), self.new_temp(INTEGER)
        self.emit(Op.ASSIGN, Const(0), result=index)
        self.emit(Op.LEN, array, result=length)
        start, step, end = self.new_label(), self.new_label(), self.new_label()
        self.place(start)
        # Estos tres temporales siguen vivos durante todo el cuerpo.
        self.emit(Op.if_rel(Op.GE), index, length, end)
        self.emit(Op.INDEX_GET, array, index, self.var(self.symbol_of(ctx.Identifier())))
        with self.breakable(end, step):
            self.visit(ctx.block())
        self.place(step)
        self.emit(Op.ADD, index, Const(1), index)
        self.emit_goto(start)
        self.place(end)
        self.release(array, index, length)

    def visitSwitchStatement(self, ctx):
        value = self.snapshot(self.gen_expr(ctx.expression()))
        end = self.new_label()
        cases = [(case, self.new_label()) for case in ctx.switchCase()]
        default = self.new_label() if ctx.defaultCase() else end
        for case, label in cases:
            other = self.gen_expr(case.expression())
            compared = value
            subject_type, case_type = self.type_of(ctx.expression()), self.type_of(case.expression())
            if subject_type == INTEGER and case_type == FLOAT:
                compared = self.new_temp(FLOAT)
                self.emit(Op.INT_TO_FLOAT, value, result=compared)
            elif subject_type == FLOAT and case_type == INTEGER:
                other = self.coerce(other, INTEGER, FLOAT)
            self.emit(Op.if_rel(Op.EQ), compared, other, label)
            if compared is not value:
                self.release(compared)
            self.release(other)
        self.emit_goto(default)
        self.release(value)
        with self.breakable(end):
            for case, label in cases:
                self.place(label)
                self.visitBlock(case)
            if ctx.defaultCase():
                self.place(default)
                self.visitBlock(ctx.defaultCase())
        self.place(end)

    def visitBreakStatement(self, ctx):
        self.emit_jump_out("break")

    def visitContinueStatement(self, ctx):
        self.emit_jump_out("continue")

    def visitTryCatchStatement(self, ctx):
        catch, end = self.new_label(), self.new_label()
        with self.handler(catch):
            self.visit(ctx.block(0))
        self.emit_goto(end)
        self.place(catch)
        self.emit(Op.GET_EXCEPTION, result=self.var(self.symbol_of(ctx.Identifier())))
        self.visit(ctx.block(1))
        self.place(end)
