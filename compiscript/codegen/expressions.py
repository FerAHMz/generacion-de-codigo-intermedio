"""Expresiones y destinos de asignación TAC. Autor: Felipe Aguilar."""

from antlr4 import ParserRuleContext

from .base import CodegenError, P
from ..ir.tac import Const, Field, Label, Op, Var
from ..symbols import FunctionSymbol, Storage
from ..types import ArrayType, BOOLEAN, FLOAT, INTEGER, STRING


class ExpressionsGen:
    def gen_expr(self, ctx, expected=None):
        if isinstance(expected, ArrayType):
            node = ctx
            while True:
                if isinstance(node, P.ArrayLiteralContext):
                    return self.visitArrayLiteral(node, expected)
                if isinstance(node, P.TernaryExprContext) and node.expression():
                    return self.visitTernaryExpr(node, expected)
                if isinstance(node, P.PrimaryExprContext) and node.expression():
                    node = node.expression()
                elif node.getChildCount() == 1 and isinstance(node.getChild(0), ParserRuleContext):
                    node = node.getChild(0)
                else:
                    break
        value = self.visit(ctx)
        return self.coerce(value, self.type_of(ctx), expected) if expected is not None else value

    def snapshot(self, value):
        """Conserva una lectura antes de evaluar expresiones con efectos."""
        if isinstance(value, Var):
            saved = self.new_temp(value.type)
            self.emit(Op.ASSIGN, value, result=saved)
            return saved
        return value

    def visitExpression(self, ctx):
        return self.gen_expr(ctx.assignmentExpr())

    def visitExprNoAssign(self, ctx):
        return self.gen_expr(ctx.conditionalExpr())

    def visitPrimaryExpr(self, ctx):
        return self.gen_expr(ctx.literalExpr() or ctx.leftHandSide() or ctx.expression())

    def visitLiteralExpr(self, ctx):
        if ctx.arrayLiteral():
            return self.gen_expr(ctx.arrayLiteral())
        text = ctx.getText()
        if text.startswith('"'):
            return Const(text[1:-1])  # la gramática no interpreta escapes
        if text in ("true", "false", "null"):
            return Const({"true": True, "false": False, "null": None}[text])
        return Const(float(text) if "." in text else int(text))

    def visitArrayLiteral(self, ctx, expected=None):
        kind = expected or self.type_of(ctx)
        result = self.new_temp(kind)
        self.emit(Op.ALLOC, Const(len(ctx.expression())), result=result)
        for index, expr in enumerate(ctx.expression()):
            value = self.gen_expr(expr, kind.element)
            self.emit(Op.INDEX_SET, Const(index), value, result)
            self.release(value)
        return result

    def visitUnaryExpr(self, ctx):
        if ctx.primaryExpr():
            return self.gen_expr(ctx.primaryExpr())
        if ctx.getChild(0).getText() == "!":
            return self._boolean_value(ctx)
        return self.emit_unary(Op.NEG, self.gen_expr(ctx.unaryExpr()), self.type_of(ctx))

    def _binary(self, ctx):
        nodes = list(ctx.getChildren())[::2]
        value, kind = self.gen_expr(nodes[0]), self.type_of(nodes[0])
        for i, node in enumerate(nodes[1:]):
            value = self.snapshot(value)
            right, right_type = self.gen_expr(node), self.type_of(node)
            op = ctx.getChild(2 * i + 1).getText()
            if op == Op.ADD and STRING in (kind, right_type):
                op, result_type = Op.CONCAT, STRING
            else:
                if FLOAT in (kind, right_type) and kind in (INTEGER, FLOAT) and right_type in (INTEGER, FLOAT):
                    value = self.coerce(value, kind, FLOAT)
                    right = self.coerce(right, right_type, FLOAT)
                result_type = BOOLEAN if op in Op.RELOPS else (FLOAT if FLOAT in (kind, right_type) else INTEGER)
            value = self.emit_binary(op, value, right, result_type)
            kind = result_type
        return value

    visitAdditiveExpr = _binary
    visitMultiplicativeExpr = _binary
    visitRelationalExpr = _binary
    visitEqualityExpr = _binary

    def _logical(self, ctx):
        if ctx.getChildCount() == 1:
            return self.gen_expr(ctx.getChild(0))
        return self._boolean_value(ctx)

    visitLogicalAndExpr = _logical
    visitLogicalOrExpr = _logical

    def _boolean_value(self, ctx):
        false, end = self.new_label(), self.new_label()
        self.gen_cond(ctx, None, false)
        result = self.new_temp(BOOLEAN)
        self.emit(Op.ASSIGN, Const(True), result=result)
        self.emit_goto(end)
        self.place(false)
        self.emit(Op.ASSIGN, Const(False), result=result)
        self.place(end)
        return result

    def gen_cond(self, ctx, true_label, false_label):
        # Desenvuelve precedencias sin perder paréntesis ni efectos laterales.
        if isinstance(ctx, P.PrimaryExprContext) and ctx.expression():
            return self.gen_cond(ctx.expression(), true_label, false_label)
        if (not isinstance(ctx, P.LeftHandSideContext) and ctx.getChildCount() == 1
                and isinstance(ctx.getChild(0), ParserRuleContext)):
            return self.gen_cond(ctx.getChild(0), true_label, false_label)
        if isinstance(ctx, P.UnaryExprContext) and ctx.unaryExpr() and ctx.getChild(0).getText() == "!":
            return self.gen_cond(ctx.unaryExpr(), false_label, true_label)
        if isinstance(ctx, (P.LogicalAndExprContext, P.LogicalOrExprContext)):
            is_or = isinstance(ctx, P.LogicalOrExprContext)
            destination = true_label if is_or else false_label
            shortcut = destination or self.new_label()
            nodes = list(ctx.getChildren())[::2]
            for node in nodes[:-1]:
                self.gen_cond(node, shortcut if is_or else None, None if is_or else shortcut)
            self.gen_cond(nodes[-1], true_label, false_label)
            if destination is None:
                self.place(shortcut)
            return
        if ctx.getText() in ("true", "false"):
            target = true_label if ctx.getText() == "true" else false_label
            if target is not None:
                self.emit_goto(target)
            return
        if isinstance(ctx, (P.RelationalExprContext, P.EqualityExprContext)) and ctx.getChildCount() == 3:
            left, right = ctx.getChild(0), ctx.getChild(2)
            a = self.snapshot(self.gen_expr(left))
            b = self.gen_expr(right)
            if FLOAT in (self.type_of(left), self.type_of(right)):
                a = self.coerce(a, self.type_of(left), FLOAT)
                b = self.coerce(b, self.type_of(right), FLOAT)
            op = ctx.getChild(1).getText()
            if true_label is not None:
                self.emit_if_rel(op, a, b, true_label)
                if false_label is not None:
                    self.emit_goto(false_label)
            elif false_label is not None:
                inverse = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "==": "!=", "!=": "=="}
                self.emit_if_rel(inverse[op], a, b, false_label)
            else:
                self.release(a, b)
            return
        value = self.gen_expr(ctx)
        if true_label is not None:
            self.emit_if(value, true_label)
            if false_label is not None:
                self.emit_goto(false_label)
        elif false_label is not None:
            self.emit_if_false(value, false_label)
        else:
            self.release(value)

    def visitTernaryExpr(self, ctx, expected=None):
        branches = ctx.expression()
        if not branches:
            return self.gen_expr(ctx.logicalOrExpr())
        kind = expected or self.type_of(ctx)
        false, end = self.new_label(), self.new_label()
        self.gen_cond(ctx.logicalOrExpr(), None, false)
        result = self.new_temp(kind)
        for i, branch in enumerate(branches):
            value = self.gen_expr(branch, kind)
            self.emit_copy(result, value)
            if i == 0:
                self.emit_goto(end)
                self.place(false)
        self.place(end)
        return result

    def _symbol_target(self, sym):
        if sym.storage == Storage.FIELD:
            return (Op.FIELD_SET, self.this_var(), Field(sym.name, sym.frame_offset), sym.type)
        return (Op.ASSIGN, self.var(sym), None, sym.type)

    def _load(self, target):
        op, base, index, kind = target
        if op == Op.ASSIGN:
            return base
        self.release(base, index)
        result = self.new_temp(kind)
        self.emit(Op.FIELD_GET if op == Op.FIELD_SET else Op.INDEX_GET, base, index, result)
        return result

    def _store(self, target, value):
        op, base, index, _ = target
        if op == Op.ASSIGN:
            self.emit(Op.ASSIGN, value, result=base)
        else:
            self.emit(op, index, value, base)
            self.release(base, index)
        return value  # asignar también es una expresión

    def _lhs(self, ctx, target=False):
        atom = ctx.primaryAtom()
        receiver = None
        if isinstance(atom, P.IdentifierExprContext):
            sym = self.symbol_of(atom)
            if isinstance(sym, FunctionSymbol):
                value = Label(sym.label)
                if sym.owner_class is not None:
                    receiver = self.snapshot(self.this_var())
                    value = self._method(receiver, sym)
            else:
                location = self._symbol_target(sym)
                if target and not ctx.suffixOp():
                    return location
                value = self._load(location)
        else:
            value = self.gen_expr(atom)
            sym = None
        suffixes = ctx.suffixOp()
        for i, suffix in enumerate(suffixes):
            if isinstance(suffix, P.CallExprContext):
                value = self.call_function(sym, value, suffix.arguments(), receiver)
                sym, receiver = None, None
                continue
            value = self.snapshot(value)
            if isinstance(suffix, P.IndexExprContext):
                index = self.snapshot(self.gen_expr(suffix.expression()))
                location = (Op.INDEX_SET, value, index, self.type_of(suffix))
                sym = None
            else:
                sym = self.symbol_of(suffix)
                if isinstance(sym, FunctionSymbol):
                    receiver, value = value, self._method(value, sym)
                    continue
                location = (Op.FIELD_SET, value, Field(sym.name, sym.frame_offset), sym.type)
            if target and i == len(suffixes) - 1:
                return location
            value = self._load(location)
        if target:
            raise CodegenError("destino de asignación no soportado")
        return value

    def visitLeftHandSide(self, ctx):
        return self._lhs(ctx)

    def visitThisExpr(self, ctx):
        return self.this_var()

    def _assign_value(self, target, expr):
        value = self.gen_expr(expr, target[3])
        return self._store(target, value)

    def visitAssignExpr(self, ctx):
        return self._assign_value(self._lhs(ctx.lhs, target=True), ctx.assignmentExpr())

    def visitPropertyAssignExpr(self, ctx):
        sym = self.symbol_of(ctx)
        obj = self.snapshot(self.gen_expr(ctx.lhs))
        return self._assign_value((Op.FIELD_SET, obj, Field(sym.name, sym.frame_offset), sym.type), ctx.assignmentExpr())

    def visitAssignment(self, ctx):
        exprs, sym = ctx.expression(), self.symbol_of(ctx)
        if len(exprs) == 1:
            target = self._symbol_target(sym)
        else:
            obj = self.snapshot(self.gen_expr(exprs[0]))
            target = (Op.FIELD_SET, obj, Field(sym.name, sym.frame_offset), sym.type)
        self.release(self._assign_value(target, exprs[-1]))

    def visitVariableDeclaration(self, ctx):
        if ctx.initializer():
            self.release(self._assign_value(self._symbol_target(self.symbol_of(ctx)), ctx.initializer().expression()))

    def visitConstantDeclaration(self, ctx):
        self.release(self._assign_value(self._symbol_target(self.symbol_of(ctx)), ctx.expression()))

    def visitExpressionStatement(self, ctx):
        self.release(self.gen_expr(ctx.expression()))

    def visitPrintStatement(self, ctx):
        value = self.gen_expr(ctx.expression())
        self.emit(Op.PRINT, value)
        self.release(value)
