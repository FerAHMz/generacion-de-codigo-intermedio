"""Análisis de vida de temporales y linear scan (Poletto y Sarkar, 1999)."""

from compiscript.ir import Const, Label, Op, Quad, TACProgram, Temp, Var
from compiscript.ir.liveness import (DEF, USE, allocate_registers, compact_temps, function_ranges,
                                     live_intervals, liveness)
from compiscript.types import FLOAT

a, b, c, d, x = (Var(n, f"global[{4 * i}]") for i, n in enumerate("abcdx"))
t1, t2, t3 = Temp(1), Temp(2), Temp(3)


def fn(*quads, name="main"):
    return TACProgram([Quad(Op.FUNC_BEGIN, Label(name), Const(0)), *quads, Quad(Op.FUNC_END, Label(name))])


def test_rangos_de_funciones():
    p = TACProgram(list(fn(Quad(Op.PRINT, a))) + list(fn(Quad(Op.RETURN), name="f")))
    assert function_ranges(p) == [("main", 0, 2), ("f", 3, 5)]


def test_vida_basica():
    # 1: t1 = a + b ; 2: t2 = c + d ; 3: t1 = t1 * t2 ; 4: x = t1
    p = fn(Quad(Op.ADD, a, b, t1), Quad(Op.ADD, c, d, t2), Quad(Op.MUL, t1, t2, t1), Quad(Op.ASSIGN, t1, None, x))
    lv = liveness(p, 0, len(p) - 1)
    assert lv.live_out[1] == {1}
    assert lv.live_out[2] == {1, 2}
    assert lv.live_in[4] == {1} and lv.live_out[4] == set()


def test_nombre_reciclado_son_valores_distintos():
    # t1 = a + b ; print t1 ; t1 = c + d ; print t1   -> dos valores de t1
    p = fn(Quad(Op.ADD, a, b, t1), Quad(Op.PRINT, t1), Quad(Op.ADD, c, d, t1), Quad(Op.PRINT, t1))
    ivs, occ = live_intervals(p, 0, len(p) - 1)
    assert [(iv.name, iv.start, iv.end) for iv in ivs] == [(1, 1, 2), (1, 3, 4)]
    assert occ[(2, 1, USE)] is ivs[0] and occ[(3, 1, DEF)] is ivs[1]


def test_uso_y_definicion_en_la_misma_instruccion():
    # t1 = a + b ; t1 = t1 + c ; x = t1
    p = fn(Quad(Op.ADD, a, b, t1), Quad(Op.ADD, t1, c, t1), Quad(Op.ASSIGN, t1, None, x))
    ivs, occ = live_intervals(p, 0, len(p) - 1)
    assert len(ivs) == 2
    assert occ[(2, 1, USE)] is not occ[(2, 1, DEF)]
    alloc = allocate_registers(p)
    # se tocan en un extremo: comparten registro, como `add $t0, $t0, $a`
    assert alloc.location(2, t1, USE).location == alloc.location(2, t1, DEF).location == "$t0"


def test_bucle_extiende_el_intervalo_hasta_el_salto_de_regreso():
    # 1: t1 = 0 ; 2: L1: ; 3: if t1 >= a goto L2 ; 4: print t1 ; 5: t1 = t1 + 1 ; 6: goto L1 ; 7: L2:
    L1, L2 = Label("L1"), Label("L2")
    p = fn(Quad(Op.ASSIGN, Const(0), None, t1), Quad(Op.LABEL, result=L1),
           Quad(Op.if_rel(">="), t1, a, L2), Quad(Op.PRINT, t1), Quad(Op.ADD, t1, Const(1), t1),
           Quad(Op.GOTO, result=L1), Quad(Op.LABEL, result=L2))
    ivs, _ = live_intervals(p, 0, len(p) - 1)
    assert len(ivs) == 1                              # el índice es un solo valor
    assert (ivs[0].start, ivs[0].end) == (1, 6)


def test_valor_que_cruza_un_call():
    p = fn(Quad(Op.ADD, a, b, t1), Quad(Op.CALL, Label("f"), Const(0), t2),
           Quad(Op.ADD, t1, t2, t1), Quad(Op.PRINT, t1))
    ivs, _ = live_intervals(p, 0, len(p) - 1)
    crossing = {iv.start: iv.crosses_call for iv in ivs}
    assert crossing[1] is True and crossing[2] is False


def test_linear_scan_derrama_el_que_termina_mas_tarde():
    # tres valores vivos a la vez con solo dos registros
    p = fn(Quad(Op.ASSIGN, a, None, t1), Quad(Op.ASSIGN, b, None, t2), Quad(Op.ASSIGN, c, None, t3),
           Quad(Op.ADD, t2, t3, t2), Quad(Op.PRINT, t2), Quad(Op.PRINT, t1))
    alloc = allocate_registers(p, int_registers=("$t0", "$t1"))
    fa = alloc.functions["main"]
    assert fa.max_pressure == 3 and fa.spill_slots == 1
    spilled = [iv for iv in fa.intervals if iv.spilled]
    assert [iv.name for iv in spilled] == [1]          # t1 vive hasta el final
    assert spilled[0].spill_slot == 0
    assert fa.registers_used() == {"$t0", "$t1"}


def test_clases_de_registro_entero_y_flotante():
    f1 = Temp(1, FLOAT)
    p = fn(Quad(Op.INT_TO_FLOAT, a, None, f1), Quad(Op.ADD, a, b, t2),
           Quad(Op.PRINT, f1), Quad(Op.PRINT, t2))
    alloc = allocate_registers(p)
    assert alloc.location(1, f1, DEF).location == "$f4"
    assert alloc.location(2, t2, DEF).location == "$t0"


def test_handler_es_sucesor_de_push_handler():
    # t1 se usa en el catch: debe estar vivo durante todo el try
    Lc, Le = Label("Lc"), Label("Le")
    p = fn(Quad(Op.ASSIGN, a, None, t1), Quad(Op.PUSH_HANDLER, result=Lc), Quad(Op.PRINT, b),
           Quad(Op.POP_HANDLER), Quad(Op.GOTO, result=Le), Quad(Op.LABEL, result=Lc),
           Quad(Op.PRINT, t1), Quad(Op.LABEL, result=Le))
    lv = liveness(p, 0, len(p) - 1)
    assert 1 in lv.live_out[2]


def test_compact_temps_minimiza_nombres_sin_cambiar_el_programa():
    # El generador pidió t1, t2, t3 sin reciclar; solo dos están vivos a la vez.
    p = fn(Quad(Op.ADD, a, b, t1), Quad(Op.ADD, t1, c, t2), Quad(Op.ADD, t2, d, t3), Quad(Op.ASSIGN, t3, None, x))
    q = compact_temps(p)
    assert [str(i) for i in q][1:-1] == ["t1 = a + b", "t1 = t1 + c", "t1 = t1 + d", "x = t1"]
    assert [str(i) for i in p][1] == "t1 = a + b"      # el original no se modifica
    assert q.check() == []
