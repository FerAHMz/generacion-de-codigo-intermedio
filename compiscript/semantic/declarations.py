"""Declaraciones de variables/constantes, asignaciones y sentencias simples."""

from __future__ import annotations

from ..generated.CompiscriptParser import CompiscriptParser as P
from ..symbols import ScopeKind, Symbol, SymbolKind
from ..types import ArrayType, ERROR, FunctionType, NULL, Type, is_assignable, is_error


class DeclarationsMixin:

    # ---------------------------------------------------------- declaraciones

    def _declare_binding(self, ctx, ident, kind: str, type_ctx, init_ctx) -> None:
        name = ident.getText()
        declared = self.resolve_type(type_ctx) if type_ctx is not None else None
        # El inicializador se evalúa ANTES de declarar: `let x = x;` es un error.
        value = self.type_of(init_ctx) if init_ctx is not None else None

        if declared is None and value is None:
            self.error(ident, f"la variable '{name}' necesita un tipo o un valor inicial")
            final: Type = ERROR
        elif declared is None:
            final = self._infer(ident, name, value)
        else:
            final = declared
            if value is not None and not is_error(declared) and not is_error(value):
                if not is_assignable(declared, value) and not self._empty_array_ok(declared, value):
                    self.error(init_ctx, f"no se puede inicializar '{name}' de tipo {declared} "
                                         f"con un valor de tipo {value}")

        if self.table.current.kind == ScopeKind.CLASS:
            kind = SymbolKind.FIELD if kind == SymbolKind.VARIABLE else kind
        sym = Symbol(name, kind, final, ident.getSymbol().line, ident.getSymbol().column,
                     initialized=init_ctx is not None)
        self.declare(sym, ident, "constante" if kind == SymbolKind.CONSTANT else "variable")

    def _infer(self, ident, name: str, value: Type) -> Type:
        if value == ArrayType(NULL):
            return self.error(ident, f"no se puede inferir el tipo de '{name}' a partir de un arreglo vacío; "
                                     f"indique el tipo explícitamente")
        if isinstance(value, FunctionType):
            return self.error(ident, f"no se puede guardar una función en la variable '{name}'")
        return value

    def visitVariableDeclaration(self, ctx: P.VariableDeclarationContext):
        type_ctx = self._type_ctx(ctx.typeAnnotation()) if ctx.typeAnnotation() else None
        init_ctx = ctx.initializer().expression() if ctx.initializer() else None
        self._declare_binding(ctx, ctx.Identifier(), SymbolKind.VARIABLE, type_ctx, init_ctx)

    def visitConstantDeclaration(self, ctx: P.ConstantDeclarationContext):
        type_ctx = self._type_ctx(ctx.typeAnnotation()) if ctx.typeAnnotation() else None
        init_ctx = ctx.expression()
        if init_ctx is None:  # la gramática lo exige, pero se valida por robustez
            self.error(ctx.Identifier(), f"la constante '{ctx.Identifier().getText()}' debe inicializarse al declararse")
        self._declare_binding(ctx, ctx.Identifier(), SymbolKind.CONSTANT, type_ctx, init_ctx)

    # ------------------------------------------------------------ asignación

    def visitAssignment(self, ctx: P.AssignmentContext):
        exprs = ctx.expression()
        if ctx.Identifier() is not None and len(exprs) == 1:
            # Identifier '=' expression ';'
            name = ctx.Identifier().getText()
            value = self.type_of(exprs[0])
            sym = self.table.resolve(name)
            if sym is None:
                return self.error(ctx.Identifier(), f"la variable '{name}' no ha sido declarada")
            self._note_capture(sym)
            return self._check_assignment(ctx, sym.type, sym, value)
        # expression '.' Identifier '=' expression ';'
        value = self.type_of(exprs[1])
        obj_t = self.type_of(exprs[0])
        member = self._lookup_member(ctx.Identifier(), obj_t)
        if member is None:
            return ERROR
        return self._check_assignment(ctx, member.type, member, value)

    # ------------------------------------------------------ sentencias simples

    def visitExpressionStatement(self, ctx: P.ExpressionStatementContext):
        return self.type_of(ctx.expression())

    def visitPrintStatement(self, ctx: P.PrintStatementContext):
        t = self.type_of(ctx.expression())
        if isinstance(t, FunctionType):
            self.error(ctx.expression(), "no se puede imprimir una función; invóquela primero")
        return None
