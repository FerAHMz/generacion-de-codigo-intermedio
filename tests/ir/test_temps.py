"""Asignación y reciclaje de temporales (free-list, menor índice libre)."""

from compiscript.ir import Temp, TempAllocator, Var


def test_reutiliza_el_menor_libre():
    ta = TempAllocator()
    t1, t2, t3 = ta.new(), ta.new(), ta.new()
    assert (t1, t2, t3) == (Temp(1), Temp(2), Temp(3))
    ta.release(t3, t1)
    assert ta.new() == Temp(1)
    assert ta.new() == Temp(3)
    assert ta.new() == Temp(4)


def test_cadena_de_sumas_usa_un_solo_temporal():
    # a + b + c + d: se libera el operando antes de pedir el resultado.
    ta = TempAllocator()
    acc = ta.new()                       # t1 = a + b
    for _ in range(2):                   # t1 = t1 + c ; t1 = t1 + d
        ta.release(acc)
        acc = ta.new()
    assert acc == Temp(1)
    assert ta.max_live <= 2
    assert ta.max_live == 1


def test_expresion_con_dos_ramas_necesita_dos():
    # (a + b) * (c + d)
    ta = TempAllocator()
    left, right = ta.new(), ta.new()
    ta.release(left, right)
    res = ta.new()
    assert res == Temp(1)
    assert ta.max_live == 2


def test_liberar_dos_veces_o_no_temporales_es_inocuo():
    ta = TempAllocator()
    t = ta.new()
    ta.release(t, t, Var("x"))
    ta.release(t)
    assert ta.live == 0
    assert ta.new() == Temp(1)
    assert ta.live == 1


def test_reset_al_cerrar_funcion():
    ta = TempAllocator()
    ta.new(); ta.new()
    ta.reset()
    assert ta.max_live == 0 and ta.live == 0
    assert ta.new() == Temp(1)


def test_nombres_usados_igual_a_max_live():
    ta = TempAllocator()
    ts = [ta.new() for _ in range(3)]
    ta.release(ts[1])
    ta.new(); ta.release(ts[0]); ta.new()
    assert ta.distinct == ta.max_live == 3
