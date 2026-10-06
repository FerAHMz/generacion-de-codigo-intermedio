"""Cuádruplos: formato legible de cada instrucción y verificación estructural."""

from compiscript.ir import Const, Field, Label, Op, Quad, TACProgram, Temp, Var

t1, t2 = Temp(1), Temp(2)
a, b = Var("a", "global[0]"), Var("b", "fp[-4]")
L1 = Label("L1")


def test_formato_de_cada_instruccion():
    casos = [
        (Quad(Op.ADD, a, b, t1), "t1 = a + b"),
        (Quad(Op.LT, a, Const(3), t1), "t1 = a < 3"),
        (Quad(Op.NEG, a, None, t1), "t1 = minus a"),
        (Quad(Op.NOT, a, None, t1), "t1 = not a"),
        (Quad(Op.ASSIGN, t1, None, a), "a = t1"),
        (Quad(Op.GOTO, result=L1), "goto L1"),
        (Quad(Op.if_rel("<="), a, b, L1), "if a <= b goto L1"),
        (Quad(Op.IF_FALSE, a, None, L1), "ifFalse a goto L1"),
        (Quad(Op.LABEL, result=L1), "L1:"),
        (Quad(Op.PARAM, a), "param a"),
        (Quad(Op.CALL, Label("f"), Const(2), t1), "t1 = call f, 2"),
        (Quad(Op.CALL, Label("g"), Const(0)), "call g, 0"),
        (Quad(Op.RETURN, a), "return a"),
        (Quad(Op.RETURN), "return"),
        (Quad(Op.FUNC_BEGIN, Label("f"), Const(24)), "func_begin f, 24"),
        (Quad(Op.FUNC_END, Label("f")), "func_end f"),
        (Quad(Op.INDEX_GET, a, t1, t2), "t2 = a[t1]"),
        (Quad(Op.INDEX_SET, t1, Const(7), a), "a[t1] = 7"),
        (Quad(Op.LEN, a, None, t1), "t1 = len a"),
        (Quad(Op.ALLOC, Const(3), None, t1), "t1 = alloc 3"),
        (Quad(Op.NEW, Label("Perro"), Const(12), t1), "t1 = new Perro, 12"),
        (Quad(Op.FIELD_GET, a, Field("edad", 8), t1), "t1 = [a + 8]    # a.edad"),
        (Quad(Op.FIELD_SET, Field("edad", 8), Const(3), a), "[a + 8] = 3    # a.edad"),
        (Quad(Op.METHOD, a, Label("hablar"), t1), "t1 = method a, hablar"),
        (Quad(Op.PRINT, Const("hola")), 'print "hola"'),
        (Quad(Op.CONCAT, Const("n="), a, t1), 't1 = concat "n=", a'),
        (Quad(Op.INT_TO_FLOAT, a, None, t1), "t1 = int_to_float a"),
        (Quad(Op.PUSH_HANDLER, result=L1), "push_handler L1"),
        (Quad(Op.POP_HANDLER), "pop_handler"),
        (Quad(Op.GET_EXCEPTION, result=a), "a = exception"),
    ]
    for quad, esperado in casos:
        assert str(quad) == esperado


def test_constantes():
    assert [str(Const(v)) for v in (1, 2.5, True, False, None, 'di "hola"')] == \
        ["1", "2.5", "true", "false", "null", '"di \\"hola\\""']


def test_var_con_enlace_estatico():
    assert Var("x", "fp[-4]", hops=2).location == "fp^2[-4]"
    assert Var("g", "global[8]", hops=1).location == "global[8]"


def test_relop_invalido():
    import pytest
    with pytest.raises(ValueError):
        Op.if_rel("+")


def test_programa_bien_formado():
    p = TACProgram([
        Quad(Op.FUNC_BEGIN, Label("main"), Const(12)),
        Quad(Op.IF_FALSE, a, None, L1),
        Quad(Op.PRINT, a),
        Quad(Op.LABEL, result=L1),
        Quad(Op.FUNC_END, Label("main")),
    ])
    assert p.check() == []
    assert p.labels() == ["L1"]
    assert p.format().splitlines()[0] == "1  func_begin main, 12"
    assert "    ifFalse a goto L1" in str(p)


def test_programa_mal_formado_reporta_problemas():
    p = TACProgram([
        Quad(Op.FUNC_BEGIN, Label("main"), Const(12)),
        Quad(Op.GOTO, result=Label("L9")),
        Quad(Op.LABEL, result=L1),
        Quad(Op.LABEL, result=L1),
    ])
    problems = p.check()
    assert any("L9" in x for x in problems)
    assert any("duplicada" in x for x in problems)
    assert any("sin func_end" in x for x in problems)


def test_tipo_de_operandos_no_afecta_igualdad():
    from compiscript.types import FLOAT, INTEGER
    assert Temp(1, FLOAT) == Temp(1, INTEGER) == Temp(1)
    assert Temp(1, FLOAT).is_float and not Temp(1).is_float
    assert Var("x", "fp[-4]", 0, FLOAT).is_float
    assert Const(2.5).is_float and not Const(2).is_float
