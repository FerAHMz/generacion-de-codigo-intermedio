"""Funciones: declaración (con hoisting), parámetros, closures y `return`."""

from __future__ import annotations

from ..generated.CompiscriptParser import CompiscriptParser as P
from ..symbols import FunctionSymbol, ScopeKind, Symbol, SymbolKind
from ..types import ERROR, VOID, is_assignable, is_error


class FunctionsMixin:

    # ---------------------------------------------------------------- hoisting

    def _hoist_functions(self, statements) -> None:
        for st in statements:
            if isinstance(st, P.FunctionDeclarationContext):
                self._declare_function(st, SymbolKind.FUNCTION)

    def _declare_function(self, ctx: P.FunctionDeclarationContext, kind: str) -> FunctionSymbol:
        """Crea el símbolo de la función (firma) y lo registra en el entorno actual."""
        ident = ctx.Identifier()
        name = ident.getText()
        params = []
        seen = set()
        if ctx.parameters():
            for p_ctx in ctx.parameters().parameter():
                p_ident = p_ctx.Identifier()
                p_name = p_ident.getText()
                p_type_ctx = self._type_ctx(p_ctx)
                if p_type_ctx is None:
                    p_type = self.error(p_ident, f"el parámetro '{p_name}' de '{name}' debe declarar su tipo")
                else:
                    p_type = self.resolve_type(p_type_ctx)
                if p_name in seen:
                    self.error(p_ident, f"parámetro duplicado '{p_name}' en la función '{name}'")
                seen.add(p_name)
                params.append(Symbol(p_name, SymbolKind.PARAMETER, p_type,
                                     p_ident.getSymbol().line, p_ident.getSymbol().column,
                                     initialized=True))
        ret_ctx = self._type_ctx(ctx)
        ret_type = self.resolve_type(ret_ctx) if ret_ctx is not None else VOID
        if kind == SymbolKind.METHOD and name == "constructor" and ret_ctx is not None:
            self.error(ret_ctx, "el constructor no puede declarar tipo de retorno")
            ret_type = VOID

        sym = FunctionSymbol(name, kind, None, ident.getSymbol().line, ident.getSymbol().column,
                             params=params, return_type=ret_type, initialized=True)
        self.declare(sym, ident, "método" if kind == SymbolKind.METHOD else "función")
        self.declared_functions[ctx] = sym
        return sym

    # ------------------------------------------------------------ declaración

    def visitFunctionDeclaration(self, ctx: P.FunctionDeclarationContext):
        sym = self.declared_functions.get(ctx)
        if sym is None:  # no fue pre-declarada (p. ej. anidada en un lugar inesperado)
            sym = self._declare_function(ctx, SymbolKind.FUNCTION)

        with self.scoped(ScopeKind.FUNCTION, owner=sym, ctx=ctx) as scope:
            sym.body_scope = scope
            for p in sym.params:
                scope.define(p)   # duplicados ya reportados en la firma
            # El cuerpo comparte entorno con los parámetros: `let x` con param `x` es redeclaración.
            self.visit_statements(ctx.block().statement())

        if sym.return_type != VOID and not is_error(sym.return_type) and not sym.has_return:
            self.error(ctx.Identifier(), f"la función '{sym.name}' declara retornar {sym.return_type} "
                                         f"pero no tiene ninguna sentencia return con valor")
        return None

    # ------------------------------------------------------------------ return

    def visitReturnStatement(self, ctx: P.ReturnStatementContext):
        fn = self.table.current.enclosing_function()
        value = self.type_of(ctx.expression()) if ctx.expression() else None

        if fn is None:
            return self.error(ctx, "'return' solo puede usarse dentro de una función")

        is_ctor = fn.kind == SymbolKind.METHOD and fn.name == "constructor"
        if value is None:
            if fn.return_type != VOID and not is_error(fn.return_type):
                self.error(ctx, f"la función '{fn.name}' debe retornar un valor de tipo {fn.return_type}")
            return None

        fn.has_return = True
        if is_ctor:
            return self.error(ctx, "el constructor no puede retornar un valor")
        if fn.return_type == VOID:
            return self.error(ctx, f"la función '{fn.name}' no declara tipo de retorno y no puede retornar un valor")
        if not is_error(value) and not is_assignable(fn.return_type, value) \
                and not self._empty_array_ok(fn.return_type, value):
            self.error(ctx.expression(), f"la función '{fn.name}' debe retornar {fn.return_type}, "
                                         f"pero retorna {value}")
        return None
