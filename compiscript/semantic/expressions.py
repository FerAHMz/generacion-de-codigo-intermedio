"""Reglas semánticas para expresiones: tipado, operadores, llamadas, accesos.

Cada método `visitXxx` devuelve el `Type` de la expresión. Cuando una
subexpresión ya falló devuelve `ERROR` y las reglas posteriores no vuelven a
reportar sobre ella (evita errores en cascada).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..generated.CompiscriptParser import CompiscriptParser as P
from ..symbols import (ClassSymbol, FunctionSymbol, ScopeKind, Symbol, SymbolKind)
from ..types import (ArrayType, BOOLEAN, ClassType, ERROR, FLOAT, FunctionType, INTEGER,
                     NULL, STRING, Type, are_comparable, are_orderable,
                     common_type, is_assignable, is_error, is_numeric, numeric_result)


class ExpressionsMixin:

    # ------------------------------------------------------------ envoltorios

    def visitExpression(self, ctx: P.ExpressionContext):
        return self.record(ctx, self.type_of(ctx.assignmentExpr()))

    def visitExprNoAssign(self, ctx: P.ExprNoAssignContext):
        return self.type_of(ctx.conditionalExpr())

    def visitPrimaryExpr(self, ctx: P.PrimaryExprContext):
        if ctx.literalExpr():
            return self.type_of(ctx.literalExpr())
        if ctx.leftHandSide():
            return self.type_of(ctx.leftHandSide())
        return self.type_of(ctx.expression())

    # --------------------------------------------------------------- literales

    def visitLiteralExpr(self, ctx: P.LiteralExprContext):
        if ctx.arrayLiteral():
            return self.type_of(ctx.arrayLiteral())
        if ctx.Literal():
            text = ctx.Literal().getText()
            if text.startswith('"'):
                return STRING
            return FLOAT if "." in text else INTEGER
        text = ctx.getText()
        if text == "null":
            return NULL
        return BOOLEAN  # true / false

    def visitArrayLiteral(self, ctx: P.ArrayLiteralContext):
        elems = [self.type_of(e) for e in ctx.expression()]
        if not elems:
            # `[]` sin contexto: se acepta y toma el tipo del destino al asignar.
            return ArrayType(NULL)
        common = common_type(elems)
        if common is None:
            shown = ", ".join(str(t) for t in elems)
            return self.error(ctx, f"los elementos del arreglo deben ser del mismo tipo (se encontró: {shown})")
        return ArrayType(common)

    # ---------------------------------------------------------------- unarios

    def visitUnaryExpr(self, ctx: P.UnaryExprContext):
        if ctx.primaryExpr():
            return self.type_of(ctx.primaryExpr())
        op = ctx.getChild(0).getText()
        operand = self.type_of(ctx.unaryExpr())
        if is_error(operand):
            return ERROR
        if op == "-":
            if not is_numeric(operand):
                return self.error(ctx, f"el operador unario '-' requiere un operando numérico (integer o float), no {operand}")
            return operand
        if operand != BOOLEAN:
            return self.error(ctx, f"el operador '!' requiere un operando boolean, no {operand}")
        return BOOLEAN

    # --------------------------------------------------------------- binarios

    def _fold_binary(self, ctx, operands, rule) -> Type:
        """Evalúa una cadena `a op b op c` de izquierda a derecha con `rule`."""
        left = self.type_of(operands[0])
        for i, right_ctx in enumerate(operands[1:]):
            op = ctx.getChild(2 * i + 1).getText()
            right = self.type_of(right_ctx)
            left = rule(ctx, op, left, right)
        return left

    def _arith(self, ctx, op, left, right) -> Type:
        if is_error(left) or is_error(right):
            return ERROR
        self._reject_callable(ctx, op, left, right)
        if op == "+" and (left == STRING or right == STRING):
            # Concatenación al estilo TypeScript: "total: " + 5
            if isinstance(left, FunctionType) or isinstance(right, FunctionType):
                return ERROR
            return STRING
        if is_numeric(left) and is_numeric(right):
            if op == "%" and FLOAT in (left, right):
                return self.error(ctx, f"el operador '%' solo admite operandos integer, no {left} y {right}")
            return numeric_result(left, right)
        return self.error(ctx, f"el operador '{op}' requiere operandos numéricos (integer o float), no {left} y {right}")

    def _logic(self, ctx, op, left, right) -> Type:
        if is_error(left) or is_error(right):
            return ERROR
        if left == BOOLEAN and right == BOOLEAN:
            return BOOLEAN
        return self.error(ctx, f"el operador '{op}' requiere operandos boolean, no {left} y {right}")

    def _equality(self, ctx, op, left, right) -> Type:
        if is_error(left) or is_error(right):
            return ERROR
        self._reject_callable(ctx, op, left, right)
        if not are_comparable(left, right):
            return self.error(ctx, f"no se pueden comparar con '{op}' valores de tipo {left} y {right}")
        return BOOLEAN

    def _relational(self, ctx, op, left, right) -> Type:
        if is_error(left) or is_error(right):
            return ERROR
        if not are_orderable(left, right):
            return self.error(ctx, f"el operador '{op}' requiere operandos numéricos (integer o float), no {left} y {right}")
        return BOOLEAN

    def _reject_callable(self, ctx, op, left, right) -> None:
        for t in (left, right):
            if isinstance(t, FunctionType):
                self.error(ctx, f"la expresión no tiene sentido: no se puede aplicar '{op}' a una función")

    def visitAdditiveExpr(self, ctx: P.AdditiveExprContext):
        return self._fold_binary(ctx, ctx.multiplicativeExpr(), self._arith)

    def visitMultiplicativeExpr(self, ctx: P.MultiplicativeExprContext):
        return self._fold_binary(ctx, ctx.unaryExpr(), self._arith)

    def visitRelationalExpr(self, ctx: P.RelationalExprContext):
        return self._fold_binary(ctx, ctx.additiveExpr(), self._relational)

    def visitEqualityExpr(self, ctx: P.EqualityExprContext):
        return self._fold_binary(ctx, ctx.relationalExpr(), self._equality)

    def visitLogicalAndExpr(self, ctx: P.LogicalAndExprContext):
        return self._fold_binary(ctx, ctx.equalityExpr(), self._logic)

    def visitLogicalOrExpr(self, ctx: P.LogicalOrExprContext):
        return self._fold_binary(ctx, ctx.logicalAndExpr(), self._logic)

    def visitTernaryExpr(self, ctx: P.TernaryExprContext):
        cond = self.type_of(ctx.logicalOrExpr())
        branches = ctx.expression()
        if not branches:
            return cond
        if not is_error(cond) and cond != BOOLEAN:
            self.error(ctx, f"la condición del operador ternario debe ser boolean, no {cond}")
        then_t = self.type_of(branches[0])
        else_t = self.type_of(branches[1])
        if is_error(then_t) or is_error(else_t):
            return ERROR
        common = common_type([then_t, else_t])
        if common is None:
            return self.error(ctx, f"las ramas del ternario deben tener tipos compatibles, no {then_t} y {else_t}")
        return common

    # ------------------------------------------------------------- asignación

    def visitAssignExpr(self, ctx: P.AssignExprContext):
        value = self.type_of(ctx.assignmentExpr())
        target_t, target_sym = self._lhs_target(ctx.lhs)
        return self._check_assignment(ctx, target_t, target_sym, value)

    def visitPropertyAssignExpr(self, ctx: P.PropertyAssignExprContext):
        value = self.type_of(ctx.assignmentExpr())
        obj_t, _ = self._walk_lhs(ctx.lhs)
        member = self.bind(ctx, self._lookup_member(ctx.Identifier(), obj_t))
        if member is None:
            return ERROR
        return self._check_assignment(ctx, member.type, member, value)

    def _lhs_target(self, lhs: P.LeftHandSideContext) -> Tuple[Type, Optional[Symbol]]:
        """Tipo y símbolo (si lo hay) del destino de una asignación `lhs = ...`."""
        suffixes = lhs.suffixOp()
        if suffixes and isinstance(suffixes[-1], P.CallExprContext):
            self._walk_lhs(lhs)
            return self.error(lhs, "no se puede asignar al resultado de una llamada"), None
        if isinstance(lhs.primaryAtom(), (P.NewExprContext, P.ThisExprContext)) and not suffixes:
            self._walk_lhs(lhs)
            return self.error(lhs, "el destino de la asignación no es una variable"), None
        return self._walk_lhs(lhs)

    def _check_assignment(self, ctx, target_t: Type, target_sym: Optional[Symbol], value: Type) -> Type:
        if target_sym is not None and target_sym.kind == SymbolKind.CONSTANT:
            return self.error(ctx, f"no se puede asignar a la constante '{target_sym.name}'")
        if target_sym is not None and target_sym.is_callable:
            return self.error(ctx, f"no se puede asignar a la función '{target_sym.name}'")
        if target_sym is not None and target_sym.kind == SymbolKind.CLASS:
            return self.error(ctx, f"no se puede asignar a la clase '{target_sym.name}'")
        if is_error(target_t) or is_error(value):
            return ERROR
        if not is_assignable(target_t, value) and not self._empty_array_ok(target_t, value):
            return self.error(ctx, f"no se puede asignar un valor de tipo {value} a un destino de tipo {target_t}")
        if target_sym is not None:
            target_sym.initialized = True
        return target_t

    @staticmethod
    def _empty_array_ok(target: Type, value: Type) -> bool:
        return isinstance(target, ArrayType) and value == ArrayType(NULL)

    # ------------------------------------------------- lado izquierdo / sufijos

    def visitLeftHandSide(self, ctx: P.LeftHandSideContext):
        t, _ = self._walk_lhs(ctx)
        return t

    def _walk_lhs(self, ctx: P.LeftHandSideContext) -> Tuple[Type, Optional[Symbol]]:
        """Recorre `atom (sufijo)*` llevando el tipo y el símbolo actual."""
        atom = ctx.primaryAtom()
        t, sym = self._atom(atom)
        for suffix in ctx.suffixOp():
            if isinstance(suffix, P.CallExprContext):
                t, sym = self._call(suffix, t, sym), None
            elif isinstance(suffix, P.IndexExprContext):
                t, sym = self._index(suffix, t), None
            else:  # PropertyAccessExpr
                member = self.bind(suffix, self._lookup_member(suffix.Identifier(), t))
                t, sym = (member.type, member) if member else (ERROR, None)
            self.record(suffix, t)
        return self.record(ctx, t), sym

    def _atom(self, atom) -> Tuple[Type, Optional[Symbol]]:
        if isinstance(atom, P.IdentifierExprContext):
            return self._identifier(atom)
        if isinstance(atom, P.ThisExprContext):
            return self.visitThisExpr(atom), None
        return self.visitNewExpr(atom), None

    def _identifier(self, atom: P.IdentifierExprContext) -> Tuple[Type, Optional[Symbol]]:
        name = atom.Identifier().getText()
        sym = self.bind(atom, self.table.resolve(name))
        if sym is None:
            return self.error(atom, f"la variable '{name}' no ha sido declarada"), None
        self._note_capture(sym)
        if sym.kind == SymbolKind.VARIABLE and not sym.initialized and not sym.captured:
            # Lectura de una variable declarada sin valor y sin asignación previa.
            self.error(atom, f"la variable '{name}' se usa antes de recibir un valor")
        return self.record(atom, sym.type), sym

    def _note_capture(self, sym: Symbol) -> None:
        """Marca variables de un entorno de función externo como capturadas (closures)."""
        if sym.kind not in (SymbolKind.VARIABLE, SymbolKind.CONSTANT, SymbolKind.PARAMETER):
            return
        owner_fn = sym.scope.enclosing_function() if sym.scope else None
        current_fn = self.table.current.enclosing_function()
        if owner_fn is not None and current_fn is not None and owner_fn is not current_fn:
            sym.captured = True
            if sym not in current_fn.captures:
                current_fn.captures.append(sym)

    def _note_call(self, callee: FunctionSymbol) -> None:
        """Registra que la función actual llama a `callee` (grafo de llamadas que
        usa la tabla para decidir qué marcos necesitan static link y $ra)."""
        current_fn = self.table.current.enclosing_function()
        if current_fn is not None and all(c is not callee for c in current_fn.calls):
            current_fn.calls.append(callee)

    def visitIdentifierExpr(self, ctx: P.IdentifierExprContext):
        return self._identifier(ctx)[0]

    def visitThisExpr(self, ctx: P.ThisExprContext):
        cls = self.table.current.enclosing_class()
        fn = self.table.current.enclosing_function()
        if cls is None or fn is None or fn.kind != SymbolKind.METHOD:
            return self.error(ctx, "'this' solo puede usarse dentro de un método de una clase")
        return self.record(ctx, cls.class_type)

    def visitNewExpr(self, ctx: P.NewExprContext):
        name = ctx.Identifier().getText()
        args = self._arguments(ctx.arguments())
        cls = self.bind(ctx, self.classes.get(name))
        if cls is None:
            return self.error(ctx, f"la clase '{name}' no está definida")
        ctor = cls.constructor()
        if ctor is None:
            if args:
                self.error(ctx, f"la clase '{name}' no define constructor, pero se le pasaron {len(args)} argumentos")
        else:
            self._check_arguments(ctx, f"constructor de '{name}'", ctor, args)
            self._note_call(ctor)
        return self.record(ctx, cls.class_type)

    # ---------------------------------------------------------------- llamadas

    def _arguments(self, args_ctx) -> List[Tuple[Type, object]]:
        if args_ctx is None:
            return []
        return [(self.type_of(e), e) for e in args_ctx.expression()]

    def _check_arguments(self, ctx, label: str, fn: FunctionSymbol, args) -> None:
        if len(args) != len(fn.params):
            self.error(ctx, f"{label} espera {len(fn.params)} argumento(s) pero recibió {len(args)}")
            return
        for i, (param, (arg_t, arg_ctx)) in enumerate(zip(fn.params, args), start=1):
            if not is_assignable(param.type, arg_t) and not self._empty_array_ok(param.type, arg_t):
                self.error(arg_ctx, f"argumento {i} de {label}: se esperaba {param.type} pero se recibió {arg_t}")

    def _call(self, suffix: P.CallExprContext, callee_t: Type, callee: Optional[Symbol]) -> Type:
        args = self._arguments(suffix.arguments())
        if is_error(callee_t):
            return ERROR
        if isinstance(callee, FunctionSymbol):
            self._check_arguments(suffix, f"'{callee.name}'", callee, args)
            self._note_call(callee)
            return callee.return_type
        if isinstance(callee_t, FunctionType):
            if len(args) != len(callee_t.params):
                return self.error(suffix, f"la función espera {len(callee_t.params)} argumento(s) pero recibió {len(args)}")
            for i, (pt, (at, actx)) in enumerate(zip(callee_t.params, args), start=1):
                if not is_assignable(pt, at):
                    self.error(actx, f"argumento {i}: se esperaba {pt} pero se recibió {at}")
            return callee_t.returns
        what = f"'{callee.name}'" if callee else "la expresión"
        return self.error(suffix, f"{what} no es una función y no puede invocarse (tipo {callee_t})")

    # ------------------------------------------------------- índices y miembros

    def _index(self, suffix: P.IndexExprContext, base_t: Type) -> Type:
        index_t = self.type_of(suffix.expression())
        if is_error(base_t):
            return ERROR
        if not isinstance(base_t, ArrayType):
            return self.error(suffix, f"solo se pueden indexar arreglos, no un valor de tipo {base_t}")
        if not is_error(index_t) and index_t != INTEGER:
            self.error(suffix.expression(), f"el índice de un arreglo debe ser integer, no {index_t}")
        text = suffix.expression().getText()
        if text.startswith("-") and text[1:].isdigit():
            self.error(suffix.expression(), f"índice inválido: {text} (los índices deben ser >= 0)")
        return base_t.element

    def _lookup_member(self, ident, obj_t: Type) -> Optional[Symbol]:
        name = ident.getText()
        if is_error(obj_t):
            return None
        if not isinstance(obj_t, ClassType):
            self.error(ident, f"no se puede acceder a '.{name}' en un valor de tipo {obj_t}")
            return None
        cls = self.classes.get(obj_t.name)
        member = cls.lookup_member(name) if cls else None
        if member is None:
            self.error(ident, f"la clase '{obj_t.name}' no tiene un atributo o método llamado '{name}'")
            return None
        return member
