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
    assert res.tac_lines() == ["func_begin main, 12", "func_end main"]
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
    assert [str(q) for q in prog] == ["func_begin main, 12", "print a", "print 7", "func_end main"]
    assert prog[1].arg1 == Var("a", "global[0]")


def test_while_break_y_etiquetas_balanceadas():
    prog = gen("while (true) { print(1); break; }").generate()
    assert prog.check() == []
    text = [str(q) for q in prog]
    assert text == ["func_begin main, 12", "L1:", "ifFalse true goto L2", "print 1",
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
    assert begin_f.arg2 == Const(f_ar.frame_size) == Const(12 + 4 + 8)
    assert [str(q) for q in prog][-4:] == ["func_begin h, 20", "t1 = 1", "print 2", "func_end h"]


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
        assert v.hops == 1 and v.location == "fp^1[+12]"


def test_contrato_de_mixins_pendiente():
    g = CodeGenBase(analyze("print(1);"))
    with pytest.raises(NotImplementedError):
        g.gen_expr(None)
    with pytest.raises(NotImplementedError):
        g.gen_cond(None, None, None)
