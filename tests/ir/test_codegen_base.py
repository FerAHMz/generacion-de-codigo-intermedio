"""Esqueleto del generador: pipeline de dos pasadas, emisión, etiquetas,
temporales por función y pila de break/continue.

`MiniGen` implementa lo mínimo del contrato (`gen_expr` para literales e
identificadores, `print` y `while` simples) solo para ejercitar la base; la
generación real la aportan los mixins de codegen/."""

import pytest

from compiscript.codegen import CodeGenBase, CodegenError, compile_source
from compiscript.generated.CompiscriptParser import CompiscriptParser as P
from compiscript.ir import Const, Label, Op, Temp, Var
from compiscript.semantic import analyze


class MiniGen(CodeGenBase):

    def gen_expr(self, ctx):
        node = ctx
        while node.getChildCount() == 1 and not isinstance(node, P.IdentifierExprContext):
            node = node.getChild(0)
        if isinstance(node, P.IdentifierExprContext):
            return self.var(self.symbol_of(node))
        text = node.getText()
        return Const(True) if text == "true" else Const(int(text))

    def visitPrintStatement(self, ctx):
        self.emit(Op.PRINT, self.gen_expr(ctx.expression()))

    def visitWhileStatement(self, ctx):
        start, end = self.new_label(), self.new_label()
        self.place(start)
        self.emit_if_false(self.gen_expr(ctx.expression()), end)
        with self.breakable(end, start):
            self.visit(ctx.block())
        self.emit_goto(start)
        self.place(end)

    def visitBreakStatement(self, ctx):
        self.emit_goto(self.break_target())

    def visitBlock(self, ctx):
        for st in ctx.statement():
            self.visit(st)

    def visitFunctionDeclaration(self, ctx):
        with self.function(self.record_of(self.symbol_of(ctx))):
            t = self.new_temp()
            self.emit(Op.ASSIGN, Const(1), None, t)
            self.visit(ctx.block())


def gen(src):
    r = analyze(src)
    assert r.ok, list(r.errors)
    return MiniGen(r)


def test_programa_vacio_genera_main():
    res = compile_source("")
    assert res.ok
    assert res.tac_lines() == ["func_begin main, 0", "func_end main"]
    assert res.program.check() == []


def test_programa_con_error_no_genera_tac():
    res = compile_source('let x: integer = "hola";')
    assert not res.ok and res.program is None
    d = res.to_dict()
    assert d["tac"] == [] and d["errors"][0]["phase"] == "semantic"
    assert "activation_records" in d["symbols"]
    with pytest.raises(CodegenError):
        CodeGenBase(res.analysis)


def test_error_sintactico_no_genera_tac():
    res = compile_source("let = ;")
    assert res.program is None and res.errors[0].phase == "syntax"


def test_emision_y_variables_con_direccion():
    prog = gen("let a: integer = 1; print(a); print(7);").generate()
    assert [str(q) for q in prog] == ["func_begin main, 0", "print a", "print 7", "func_end main"]
    assert prog[1].arg1 == Var("a", "global[0]")


def test_while_break_y_etiquetas_balanceadas():
    prog = gen("while (true) { print(1); break; }").generate()
    assert prog.check() == []
    text = [str(q) for q in prog]
    assert text == ["func_begin main, 0", "L1:", "ifFalse true goto L2", "print 1",
                    "goto L2", "goto L1", "L2:", "func_end main"]


def test_funciones_en_bufer_propio_con_frame_size_final():
    g = gen("function f(n: integer) { print(n); } function h() { print(2); } print(3);")
    prog = g.generate()
    names = [str(q.arg1) for q in prog if q.op == Op.FUNC_BEGIN]
    assert names == ["main", "f", "h"]
    assert prog.check() == []
    f_ar = g.table.record_of("f")
    assert f_ar.temp_count == 1                         # usó t1
    begin_f = next(q for q in prog if q.op == Op.FUNC_BEGIN and str(q.arg1) == "f")
    assert begin_f.arg2 == Const(f_ar.frame_size) == Const(4 + 4 + 4)
    assert [str(q) for q in prog][-4:] == ["func_begin h, 8", "t1 = 1", "print 2", "func_end h"]


def test_temporales_y_emit_binary_reciclan():
    g = gen("")
    with g.function(g.table.main):
        a, b, c = Var("a", "global[0]"), Var("b", "global[4]"), Var("c", "global[8]")
        t = g.emit_binary(Op.ADD, a, b)
        t = g.emit_binary(Op.ADD, t, c)
        assert t == Temp(1) and g.temps.max_live == 1
        g.emit_copy(Var("x", "global[12]"), t)
        assert g.temps.live == 0
        assert [str(q) for q in g.code][1:] == ["t1 = a + b", "t1 = t1 + c", "x = t1"]


def test_coerce_emite_int_to_float():
    from compiscript.types import FLOAT, INTEGER
    g = gen("")
    with g.function(g.table.main):
        assert g.coerce(Const(2), INTEGER, FLOAT) == Const(2.0)
        t = g.coerce(Var("n", "global[0]"), INTEGER, FLOAT)
        assert str(g.code[-1]) == f"{t} = int_to_float n"
        assert g.coerce(Var("x"), FLOAT, FLOAT) == Var("x")


def test_pila_break_continue_atraviesa_switch():
    g = gen("")
    with g.function(g.table.main):
        lb, lc, ls = Label("Lb"), Label("Lc"), Label("Ls")
        with pytest.raises(CodegenError):
            g.break_target()
        with g.breakable(lb, lc):
            with g.breakable(ls):          # switch dentro del bucle
                assert g.break_target() == ls
                assert g.continue_target() == lc
            assert g.break_target() == lb
        with pytest.raises(CodegenError):
            g.continue_target()


def test_saltos_que_salen_de_un_try_cierran_manejadores():
    g = gen("")
    with g.function(g.table.main):
        fin, cont, catch = Label("Lfin"), Label("Lcont"), Label("Lcatch")
        with g.breakable(fin, cont):
            with g.handler(catch):
                g.emit_jump_out("break")
                with g.handler(catch):
                    g.emit_jump_out("continue")
                    g.emit_return(Const(1))
        text = [str(q) for q in g.code][1:]
    assert text == [
        "push_handler Lcatch",
        "pop_handler    # salida anticipada del try", "goto Lfin",
        "push_handler Lcatch",
        "pop_handler    # salida anticipada del try", "pop_handler    # salida anticipada del try",
        "goto Lcont",
        "pop_handler    # salida anticipada del try", "pop_handler    # salida anticipada del try",
        "return 1",
        "pop_handler", "pop_handler",
    ]


def test_var_de_closure_lleva_hops():
    g = gen("function f(n: integer) { function h() { print(n); } }")
    n = g.table.record_of("f").params[0]
    h = g.table.record_of("f_h")
    with g.function(h):
        v = g.var(n)
        assert v.hops == 1 and v.location == "fp^1[+4]"


def test_contrato_de_mixins_pendiente():
    g = CodeGenBase(analyze("print(1);"))
    with pytest.raises(NotImplementedError):
        g.gen_expr(None)
    with pytest.raises(NotImplementedError):
        g.gen_cond(None, None, None)


def test_temporales_llevan_tipo_para_elegir_registros():
    from compiscript.types import BOOLEAN, FLOAT, INTEGER
    g = gen("let n: integer = 1; let f: float = 2.0;")
    with g.function(g.table.main):
        n, f = g.var(g.table.global_scope.symbols["n"]), g.var(g.table.global_scope.symbols["f"])
        assert n.type == INTEGER and f.is_float
        assert g.emit_binary(Op.MUL, f, Const(2.0)).is_float
        assert g.emit_binary(Op.LT, n, Const(3)).type == BOOLEAN
        assert g.coerce(n, INTEGER, FLOAT).is_float


# Contratos públicos del generador completo — Felipe Aguilar.
def compiled(source):
    result = compile_source(source)
    assert result.ok, [str(e) for e in result.errors]
    assert result.program.check() == []
    return result


@pytest.mark.parametrize("condition", ["ok", "!ok", "ok && !ok", "ok || !ok", "(ok)"])
def test_condiciones_tienen_operandos_booleanos(condition):
    result = compiled(f"let ok = true; if ({condition}) {{ print(1); }}")
    branches = [q for q in result.program if q.op in (Op.IF, Op.IF_FALSE)]
    assert branches
    assert all(isinstance(q.arg1, (Var, Temp, Const)) for q in branches)


@pytest.mark.parametrize("expression, shortcut", [("false && f()", False), ("true || f()", True)])
def test_corto_circuito_salta_la_llamada(expression, shortcut):
    result = compiled(f"function f(): boolean {{ return true; }} print({expression});")
    code = result.program.quads
    call = next(i for i, q in enumerate(code) if q.op == Op.CALL)
    jump = next(q for q in code[:call] if q.op == Op.GOTO)
    destination = next(i for i, q in enumerate(code) if q.op == Op.LABEL and q.result == jump.result)
    assert destination > call
    assert any(q.op == Op.ASSIGN and q.arg1 == Const(shortcut) for q in code[destination:])


def test_operando_izquierdo_se_conserva_antes_de_asignar_el_derecho():
    result = compiled("let x=1; print(x + (x=4));")
    code = result.program.quads
    saved = next(q for q in code if q.op == Op.ASSIGN and isinstance(q.arg1, Var))
    mutation = next(q for q in code if q.op == Op.ASSIGN and q.arg1 == Const(4))
    addition = next(q for q in code if q.op == Op.ADD)
    assert code.index(saved) < code.index(mutation) < code.index(addition)
    assert addition.arg1 == saved.result


def test_llamadas_anidadas_no_mezclan_parametros():
    result = compiled("function f(a:integer,b:integer):integer{return a+b;} print(f(1,f(2,3)));")
    pending = []
    groups = []
    for q in result.program:
        if q.op == Op.PARAM:
            pending.append(q.arg1)
        if q.op == Op.CALL:
            assert len(pending) == q.arg2.value
            groups.append(pending)
            pending = []
    assert groups[0] == [Const(2), Const(3)]
    assert groups[1][0] == Const(1) and isinstance(groups[1][1], Temp)


def test_arreglos_float_promueven_literales_anidados_argumentos_y_retornos():
    result = compiled('''
        function f(a:float[]):float[] { return [3]; }
        let xs:float[][] = [[1], [2]];
        let ys = f([4]);
    ''')
    values = [q.arg2.value for q in result.program
              if q.op == Op.INDEX_SET and isinstance(q.arg2, Const)]
    assert sorted(values) == [1.0, 2.0, 3.0, 4.0]
    assert all(type(v) is float for v in values)


def test_temporales_reciclados_y_capturas_en_el_tac_publico():
    result = compiled('''
        function f(n:integer):integer {
            function g():integer { return n+1+2+3; }
            return g();
        }
        print(f(4));
    ''')
    captured = [o for q in result.program for o in q.operands() if isinstance(o, Var) and o.name == "n"]
    assert captured and all(o.hops == 1 for o in captured)
    inner = next(ar for ar in result.table.activation_records if ar.name == "g")
    assert inner.temp_count == 1
    assert inner.needs_static_link


def test_inicializadores_por_instancia_herencia_y_despacho_virtual():
    result = compiled('''
        class A { let x=1; function constructor() {} function f():integer{return this.x;} }
        class B:A { let y=2; function f():integer{return this.y;} }
        let a:A=new B(); let b=new B(); print(a.f());
    ''')
    bodies = {}
    for q in result.program:
        if q.op == Op.FUNC_BEGIN:
            body = bodies[q.arg1.name] = []
        else:
            body.append(q)
    main = bodies["main"]
    calls = [q for q in main if q.op == Op.CALL and isinstance(q.arg1, Label)]
    constructor = result.table.class_layouts["B"].constructor_label
    assert [q.arg1.name for q in calls[1::2]] == [constructor, constructor]
    assert calls[0].arg1 == calls[2].arg1
    derived_init = bodies[calls[0].arg1.name]
    parent_call = next(q for q in derived_init if q.op == Op.CALL)
    own_field = next(q for q in derived_init if q.op == Op.FIELD_SET)
    assert derived_init.index(parent_call) < derived_init.index(own_field)
    assert any(q.op == Op.FIELD_SET for q in bodies[parent_call.arg1.name])
    assert not any(q.op == Op.FIELD_SET for q in main)
    assert any(q.op == Op.METHOD and q.arg2 == Label("f") for q in main)
    assert result.table.class_layouts["A"].method_label("f") != result.table.class_layouts["B"].method_label("f")


def test_closure_de_metodo_captura_el_receptor_implicito():
    result = compiled('''
        class A {
            let x=3;
            function f():integer {
                function g():integer { return x; }
                return g();
            }
        }
        print(new A().f());
    ''')
    reads = [q for q in result.program if q.op == Op.FIELD_GET]
    assert len(reads) == 1 and reads[0].arg1.hops == 1
    closure = next(ar for ar in result.table.activation_records if ar.name == "g")
    assert closure.needs_static_link


@pytest.mark.parametrize("statement", ["break;", "continue;", "return;"])
def test_salidas_anticipadas_desapilan_handlers(statement):
    result = compiled(f"function f() {{ while(true) {{ try {{ {statement} }} catch(e) {{ print(e); }} }} }} f();")
    code = result.program.quads
    first_pop = next(i for i, q in enumerate(code) if q.op == Op.POP_HANDLER)
    assert code[first_pop-1].op == Op.PUSH_HANDLER
    assert code[first_pop+1].op == (Op.RETURN if statement == "return;" else Op.GOTO)
