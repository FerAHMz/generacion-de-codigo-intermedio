"""Clases: declaración (con hoisting del nombre), herencia, miembros,
constructor, sobreescritura de métodos y el entorno de `this`."""

from __future__ import annotations

from ..generated.CompiscriptParser import CompiscriptParser as P
from ..symbols import ClassSymbol, FunctionSymbol, ScopeKind, SymbolKind
from ..types import ClassType, ERROR, is_error


class ClassesMixin:

    # ---------------------------------------------------------------- hoisting

    def _hoist_classes(self, statements) -> None:
        """Registra el nombre de cada clase del bloque para que pueda usarse como
        tipo antes de su declaración (`let a: Animal` arriba de `class Animal`)."""
        for st in statements:
            if isinstance(st, P.ClassDeclarationContext):
                ident = st.Identifier(0)
                name = ident.getText()
                if name in self.classes:
                    self.error(ident, f"la clase '{name}' ya fue declarada")
                    continue
                sym = ClassSymbol(name, SymbolKind.CLASS, ClassType(name),
                                  ident.getSymbol().line, ident.getSymbol().column, initialized=True)
                if self.declare(sym, ident, "clase"):
                    self.classes[name] = sym
                self.declared_functions[st] = sym
                self.bind(st, sym)

    # ------------------------------------------------------------ declaración

    def visitClassDeclaration(self, ctx: P.ClassDeclarationContext):
        sym = self.declared_functions.get(ctx)
        if not isinstance(sym, ClassSymbol):
            return None  # duplicada: ya se reportó en el hoisting

        parent_ident = ctx.Identifier(1)
        if parent_ident is not None:
            parent_name = parent_ident.getText()
            parent = self.classes.get(parent_name)
            if parent is None:
                self.error(parent_ident, f"la clase padre '{parent_name}' no está definida")
            elif parent is sym or parent.class_type.is_subclass_of(sym.class_type):
                self.error(parent_ident, f"herencia circular: '{sym.name}' no puede heredar de '{parent_name}'")
            else:
                sym.parent = parent
                sym.class_type.parent = parent.class_type

        with self.scoped(ScopeKind.CLASS, owner=sym, ctx=ctx) as scope:
            sym.members = scope
            members = ctx.classMember()
            # 1) firmas de métodos primero: un método puede llamar a otro declarado después.
            for m in members:
                if m.functionDeclaration():
                    self._declare_function(m.functionDeclaration(), SymbolKind.METHOD)
            # 2) atributos (sus inicializadores se evalúan en el entorno de la clase).
            for m in members:
                if m.variableDeclaration():
                    self.visit(m.variableDeclaration())
                elif m.constantDeclaration():
                    self.visit(m.constantDeclaration())
            # 3) cuerpos de los métodos.
            for m in members:
                if m.functionDeclaration():
                    self._check_override(sym, m.functionDeclaration())
                    self.visit(m.functionDeclaration())
        return None

    def _check_override(self, cls: ClassSymbol, fn_ctx: P.FunctionDeclarationContext) -> None:
        method = self.declared_functions.get(fn_ctx)
        if not isinstance(method, FunctionSymbol) or cls.parent is None:
            return
        inherited = cls.parent.lookup_member(method.name)
        if inherited is None:
            return
        if not isinstance(inherited, FunctionSymbol):
            self.error(fn_ctx.Identifier(), f"'{method.name}' es un atributo en la clase padre y no puede "
                                            f"redefinirse como método")
            return
        if method.name == "constructor":
            return  # cada clase puede definir su propio constructor
        same = (len(method.params) == len(inherited.params)
                and all(a.type == b.type for a, b in zip(method.params, inherited.params))
                and method.return_type == inherited.return_type)
        if not same:
            self.error(fn_ctx.Identifier(), f"el método '{method.name}' sobreescribe a '{cls.parent.name}."
                                            f"{method.name}' pero con una firma distinta "
                                            f"({inherited.signature()})")
