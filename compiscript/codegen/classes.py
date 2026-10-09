"""Objetos, despacho virtual e inicialización por instancia. Felipe Aguilar."""

from antlr4 import ParserRuleContext

from .base import P
from ..ir.tac import Const, Label, Op
from ..symbols import ClassSymbol, FunctionSymbol, Scope, ScopeKind, Symbol, SymbolKind
from ..types import VOID


class ClassesGen:
    def __init__(self, analysis):
        self._initializers = {}
        self._class_nodes = {
            sym.name: node for node, sym in analysis.node_symbols.items()
            if isinstance(node, P.ClassDeclarationContext) and isinstance(sym, ClassSymbol)
        }
        if analysis.ok and self._class_nodes:
            self._prepare_initializers(analysis)
        super().__init__(analysis)

    def _prepare_initializers(self, analysis):
        """Una función interna por clase evita expandir recursivamente `new`.

        Se registra antes de reasignar memoria para que las llamadas y capturas
        de los inicializadores también participen en los encabezados del marco.
        No se agrega a la vtable ni modifica el constructor del usuario.
        """
        table = analysis.table
        for name, node in self._class_nodes.items():
            cls = analysis.node_symbols[node]
            existing = cls.scope.resolve_local(f"$init_{name}")
            if existing is not None:
                self._initializers[name] = existing
                continue
            receiver = Symbol("$this", SymbolKind.PARAMETER, cls.type, initialized=True)
            fn = FunctionSymbol(f"$init_{name}", SymbolKind.FUNCTION, None,
                                params=[receiver], return_type=VOID, initialized=True)
            cls.scope.define(fn)  # '$' no puede aparecer en identificadores fuente
            scope = Scope(ScopeKind.FUNCTION, cls.scope, owner=fn)
            scope.define(receiver)
            table.scopes.append(scope)
            fn.body_scope = scope
            self._initializers[name] = fn

        def note(node, fn):
            if isinstance(node, P.FunctionDeclarationContext):
                fn = analysis.node_symbols[node]
            if isinstance(node, P.ClassDeclarationContext):
                cls = analysis.node_symbols[node]
                for member in node.classMember():
                    note(member.getChild(0), self._initializers[cls.name])
                return
            sym = analysis.node_symbols.get(node)
            if fn is not None:
                callees = []
                if isinstance(sym, FunctionSymbol) and not isinstance(node, P.FunctionDeclarationContext):
                    callees.append(sym)
                if isinstance(node, P.NewExprContext):
                    callees.append(self._initializers[sym.name])
                    if sym.constructor():
                        callees.append(sym.constructor())
                for callee in callees:
                    if all(existing is not callee for existing in fn.calls):
                        fn.calls.append(callee)
                if sym is not None and sym.scope is not None and sym.kind in (
                    SymbolKind.VARIABLE, SymbolKind.CONSTANT, SymbolKind.PARAMETER
                ) and sym.scope.kind != ScopeKind.CLASS:
                    owner = sym.scope.enclosing_function()
                    if owner is not None and owner is not fn and all(s is not sym for s in fn.captures):
                        fn.captures.append(sym)
                implicit = isinstance(node, P.IdentifierExprContext) or (
                    isinstance(node, P.AssignmentContext) and len(node.expression()) == 1)
                if (implicit and sym is not None and sym.scope.kind == ScopeKind.CLASS
                        and fn.kind != SymbolKind.METHOD
                        and not any(fn is init for init in self._initializers.values())):
                    owner = fn.scope.enclosing_function()
                    while owner is not None and owner.kind != SymbolKind.METHOD:
                        owner = owner.scope.enclosing_function()
                    if owner is not None:
                        # allocate_storage decide capturas por el entorno dueño;
                        # this_var usará el parámetro con su dirección recalculada.
                        receiver = owner.activation.this
                        if all(s.name != "this" or s.scope is not receiver.scope for s in fn.captures):
                            fn.captures.append(receiver)
            for child in node.getChildren():
                if isinstance(child, ParserRuleContext):
                    note(child, fn)

        note(analysis.tree, None)
        for name, node in self._class_nodes.items():
            cls = analysis.node_symbols[node]
            if cls.parent:
                parent = self._initializers[cls.parent.name]
                calls = self._initializers[name].calls
                if all(callee is not parent for callee in calls):
                    calls.append(parent)
            cls.layout = None
        # analyze() ya asignó memoria. Las funciones internas cambian el grafo
        # de llamadas: reconstruir antes de emitir cualquier operando Var.
        table.main = None
        table.class_layouts.clear()
        table.globals_size = 0
        table.allocate_storage()

    def this_var(self):
        record = self.record
        while record is not None:
            if record.this is not None:
                return self.var(record.this)
            if any(record.function is fn for fn in self._initializers.values()):
                return self.var(record.function.params[0])
            record = record.parent
        return super().this_var()

    def _method(self, receiver, method):
        if method.name == "constructor":
            return Label(method.label)
        result = self.new_temp(method.type)
        self.emit(Op.METHOD, receiver, Label(method.name), result)
        return result

    def visitClassDeclaration(self, ctx):
        cls = self.symbol_of(ctx)
        with self.function(self.record_of(self._initializers[cls.name])):
            if cls.parent:
                self.emit(Op.PARAM, self.this_var())
                self.emit(Op.CALL, Label(self._initializers[cls.parent.name].label), Const(1))
            for member in ctx.classMember():
                declaration = member.variableDeclaration() or member.constantDeclaration()
                if declaration is not None:
                    self.visit(declaration)
        for member in ctx.classMember():
            if member.functionDeclaration():
                self.visit(member.functionDeclaration())

    def visitNewExpr(self, ctx):
        cls = self.symbol_of(ctx)
        obj = self.new_temp(cls.type)
        self.emit(Op.NEW, Label(cls.label), Const(cls.object_size), obj)
        self.emit(Op.PARAM, obj)
        self.emit(Op.CALL, Label(self._initializers[cls.name].label), Const(1))
        ctor = cls.constructor()
        if ctor is not None:
            # La referencia original permanece viva después del constructor.
            receiver = self.new_temp(cls.type)
            self.emit(Op.ASSIGN, obj, result=receiver)
            self.call_function(ctor, Label(ctor.label), ctx.arguments(), receiver)
        return obj
