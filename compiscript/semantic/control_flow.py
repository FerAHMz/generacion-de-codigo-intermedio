"""Control de flujo: condiciones booleanas, bucles, switch, try/catch,
`break`/`continue` y los entornos que cada estructura introduce."""

from __future__ import annotations

from ..generated.CompiscriptParser import CompiscriptParser as P
from ..symbols import ScopeKind, Symbol, SymbolKind
from ..types import ArrayType, BOOLEAN, ERROR, STRING, are_comparable, is_error


class ControlFlowMixin:

    def _condition(self, expr_ctx, construct: str) -> None:
        t = self.type_of(expr_ctx)
        if not is_error(t) and t != BOOLEAN:
            self.error(expr_ctx, f"la condición de '{construct}' debe ser boolean, no {t}")

    def _loop_body(self, block_ctx) -> None:
        """Cuerpo de un bucle: entorno LOOP (habilita break/continue)."""
        with self.scoped(ScopeKind.LOOP):
            self.visit_statements(block_ctx.statement())

    # ------------------------------------------------------------ condicionales

    def visitIfStatement(self, ctx: P.IfStatementContext):
        self._condition(ctx.expression(), "if")
        for block in ctx.block():
            self.visit(block)

    # ----------------------------------------------------------------- bucles

    def visitWhileStatement(self, ctx: P.WhileStatementContext):
        self._condition(ctx.expression(), "while")
        self._loop_body(ctx.block())

    def visitDoWhileStatement(self, ctx: P.DoWhileStatementContext):
        self._loop_body(ctx.block())
        self._condition(ctx.expression(), "do-while")

    def visitForStatement(self, ctx: P.ForStatementContext):
        # for '(' (variableDeclaration | assignment | ';') expression? ';' expression? ')' block
        # Se localizan condición y actualización por posición respecto a los ';'.
        with self.scoped(ScopeKind.LOOP, name="for"):
            children = list(ctx.getChildren())
            i = 2  # después de 'for' '('
            init = children[i]
            if isinstance(init, (P.VariableDeclarationContext, P.AssignmentContext)):
                self.visit(init)
            i += 1  # salta init (o el ';' vacío)
            cond = children[i] if isinstance(children[i], P.ExpressionContext) else None
            if cond is not None:
                self._condition(cond, "for")
                i += 1
            i += 1  # ';'
            update = children[i] if isinstance(children[i], P.ExpressionContext) else None
            if update is not None:
                self.type_of(update)
            self.visit_statements(ctx.block().statement())

    def visitForeachStatement(self, ctx: P.ForeachStatementContext):
        iterable = self.type_of(ctx.expression())
        ident = ctx.Identifier()
        if is_error(iterable):
            elem = ERROR
        elif not isinstance(iterable, ArrayType):
            elem = self.error(ctx.expression(), f"'foreach' requiere iterar un arreglo, no un valor de tipo {iterable}")
        else:
            elem = iterable.element
        with self.scoped(ScopeKind.LOOP, name="foreach") as scope:
            scope.define(Symbol(ident.getText(), SymbolKind.VARIABLE, elem,
                                ident.getSymbol().line, ident.getSymbol().column, initialized=True))
            self.visit_statements(ctx.block().statement())

    # ----------------------------------------------------------------- switch

    def visitSwitchStatement(self, ctx: P.SwitchStatementContext):
        subject = self.type_of(ctx.expression())
        with self.scoped(ScopeKind.SWITCH):
            for case in ctx.switchCase():
                case_t = self.type_of(case.expression())
                if not is_error(subject) and not is_error(case_t) and not are_comparable(subject, case_t):
                    self.error(case.expression(), f"el 'case' de tipo {case_t} no es comparable con el "
                                                  f"valor del switch de tipo {subject}")
                with self.scoped(ScopeKind.BLOCK, name="case"):
                    self.visit_statements(case.statement())
            if ctx.defaultCase():
                with self.scoped(ScopeKind.BLOCK, name="default"):
                    self.visit_statements(ctx.defaultCase().statement())

    # -------------------------------------------------------------- try/catch

    def visitTryCatchStatement(self, ctx: P.TryCatchStatementContext):
        self.visit(ctx.block(0))
        ident = ctx.Identifier()
        with self.scoped(ScopeKind.BLOCK, name="catch") as scope:
            # El error capturado se modela como string (mensaje).
            scope.define(Symbol(ident.getText(), SymbolKind.VARIABLE, STRING,
                                ident.getSymbol().line, ident.getSymbol().column, initialized=True))
            self.visit_statements(ctx.block(1).statement())

    # -------------------------------------------------------- break / continue

    def visitBreakStatement(self, ctx: P.BreakStatementContext):
        if not self.table.current.in_breakable():
            self.error(ctx, "'break' solo puede usarse dentro de un bucle o un switch")

    def visitContinueStatement(self, ctx: P.ContinueStatementContext):
        if not self.table.current.in_loop():
            self.error(ctx, "'continue' solo puede usarse dentro de un bucle")
