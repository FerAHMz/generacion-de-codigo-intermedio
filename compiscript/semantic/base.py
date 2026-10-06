"""Infraestructura común del analizador semántico.

`BaseAnalyzer` extiende el visitor generado por ANTLR con:
  * la tabla de símbolos y el colector de errores,
  * utilidades para reportar errores con posición,
  * resolución de anotaciones de tipo (`integer[]`, `Animal`, ...),
  * el recorrido de listas de sentencias con detección de código muerto.

Las reglas concretas viven en mixins (expressions, declarations, functions,
control_flow, classes) que se combinan en `analyzer.SemanticAnalyzer`.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from antlr4 import ParserRuleContext
from antlr4.tree.Tree import TerminalNode

from ..errors import ErrorCollector
from ..generated.CompiscriptParser import CompiscriptParser
from ..generated.CompiscriptVisitor import CompiscriptVisitor
from ..symbols import ClassSymbol, Scope, ScopeKind, Symbol, SymbolKind, SymbolTable
from ..types import ArrayType, ClassType, ERROR, PRIMITIVES, Type

P = CompiscriptParser

# Sentencias que terminan el flujo: lo que venga después en el mismo bloque es código muerto.
_TERMINATORS = (P.ReturnStatementContext, P.BreakStatementContext, P.ContinueStatementContext)


class BaseAnalyzer(CompiscriptVisitor):

    def __init__(self, errors: Optional[ErrorCollector] = None):
        super().__init__()
        self.errors = errors if errors is not None else ErrorCollector()
        self.table = SymbolTable()
        self.classes: Dict[str, ClassSymbol] = {}
        # Tipo calculado para cada nodo de expresión (lo consume el IDE).
        self.node_types: Dict[ParserRuleContext, Type] = {}
        # Símbolo de función asociado a cada declaración (pre-declaración/hoisting).
        self.declared_functions: Dict[ParserRuleContext, Symbol] = {}
        # Interfaz con la generación de código (segunda pasada): símbolo al que
        # resuelve cada identificador/declaración y entorno que abre cada nodo.
        self.node_symbols: Dict[object, Symbol] = {}
        self.node_scopes: Dict[ParserRuleContext, Scope] = {}

    # ------------------------------------------------------------------ errores

    def error(self, ctx, message: str) -> Type:
        """Registra un error semántico en la posición de `ctx` y devuelve ERROR."""
        if isinstance(ctx, TerminalNode):
            tok = ctx.getSymbol()
        elif isinstance(ctx, ParserRuleContext):
            tok = ctx.start
        else:
            tok = ctx
        line = getattr(tok, "line", 0)
        col = getattr(tok, "column", 0)
        self.errors.semantic(line, col, message)
        return ERROR

    # -------------------------------------------------------------------- tipos

    @staticmethod
    def _type_ctx(ctx):
        """Accesor robusto: el target Python renombra la regla `type` a `type_`."""
        getter = getattr(ctx, "type_", None) or getattr(ctx, "type", None)
        return getter() if callable(getter) else None

    def resolve_type(self, type_ctx) -> Type:
        """Convierte un nodo `type` de la gramática en un objeto Type."""
        if type_ctx is None:
            return ERROR
        base_ctx = type_ctx.baseType()
        name = base_ctx.getText()
        if name in PRIMITIVES:
            base: Type = PRIMITIVES[name]
        else:
            cls = self.classes.get(name)
            if cls is None:
                return self.error(base_ctx, f"el tipo '{name}' no está definido")
            base = cls.class_type
        depth = (type_ctx.getChildCount() - 1) // 2   # cada '[' ']' suma 2 hijos
        for _ in range(depth):
            base = ArrayType(base)
        return base

    def record(self, ctx, t: Type) -> Type:
        self.node_types[ctx] = t
        return t

    def type_of(self, ctx) -> Type:
        """Visita una expresión y garantiza que devuelva un Type."""
        if ctx is None:
            return ERROR
        t = self.visit(ctx)
        if not isinstance(t, Type):
            t = ERROR
        return self.record(ctx, t)

    # ---------------------------------------------------------------- entornos

    def scoped(self, kind: str, owner: Optional[Symbol] = None, name: Optional[str] = None,
               ctx: Optional[ParserRuleContext] = None):
        """Context manager: `with self.scoped(ScopeKind.BLOCK, ctx=ctx): ...`

        Si se pasa `ctx`, el entorno creado queda registrado en `node_scopes[ctx]`
        para que el generador de código lo recupere sin volver a resolver nombres."""
        return _ScopeGuard(self.table, kind, owner, name, ctx, self.node_scopes)

    def bind(self, node, sym: Optional[Symbol]) -> Optional[Symbol]:
        """Asocia un nodo del árbol con el símbolo al que resuelve."""
        if sym is not None:
            self.node_symbols[node] = sym
        return sym

    def declare(self, sym: Symbol, ctx, what: Optional[str] = None) -> bool:
        """Define `sym` en el entorno actual, reportando redeclaraciones."""
        if not self.table.define(sym):
            previous = self.table.resolve_local(sym.name)
            label = what or sym.kind
            where = f" (declarado antes en línea {previous.line})" if previous and previous.line else ""
            self.error(ctx, f"redeclaración de {label} '{sym.name}' en el mismo ámbito{where}")
            return False
        return True

    # -------------------------------------------------------------- sentencias

    def visit_statements(self, statements: List[ParserRuleContext]) -> None:
        """Recorre una lista de sentencias y marca las inalcanzables."""
        self.hoist(statements)
        dead_reported = False
        terminated = False
        for st in statements:
            if terminated and not dead_reported:
                self.error(st, "código muerto: la sentencia nunca se ejecuta "
                               "(está después de return/break/continue)")
                dead_reported = True
            self.visit(st)
            inner = st.getChild(0) if isinstance(st, P.StatementContext) else st
            if isinstance(inner, _TERMINATORS):
                terminated = True

    def hoist(self, statements: List[ParserRuleContext]) -> None:
        """Pre-declara clases y funciones del bloque para permitir referencias
        adelantadas (una función puede llamar a otra declarada más abajo)."""
        inner = [st.getChild(0) if isinstance(st, P.StatementContext) else st for st in statements]
        self._hoist_classes(inner)
        self._hoist_functions(inner)

    def _hoist_classes(self, statements) -> None:   # lo implementa ClassesMixin
        pass

    def _hoist_functions(self, statements) -> None: # lo implementa FunctionsMixin
        pass

    # Los bloques crean su propio entorno.
    def visitBlock(self, ctx: P.BlockContext):
        with self.scoped(ScopeKind.BLOCK, ctx=ctx):
            self.visit_statements(ctx.statement())

    def visitProgram(self, ctx: P.ProgramContext):
        self.visit_statements(ctx.statement())
        return self.table

    # Un `statement` es solo un envoltorio: delega al hijo concreto.
    def visitStatement(self, ctx: P.StatementContext):
        return self.visit(ctx.getChild(0))


class _ScopeGuard:
    def __init__(self, table: SymbolTable, kind, owner, name, ctx=None, registry=None):
        self.table, self.kind, self.owner, self.name = table, kind, owner, name
        self.ctx, self.registry = ctx, registry
        self.scope = None

    def __enter__(self):
        self.scope = self.table.push(self.kind, self.owner, self.name)
        if self.ctx is not None and self.registry is not None:
            self.registry[self.ctx] = self.scope
        return self.scope

    def __exit__(self, *exc):
        self.table.pop()
        return False
