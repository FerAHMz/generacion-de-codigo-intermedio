"""Catálogo de errores en tiempo de ejecución (compartido por intérprete y MIPS)."""

from compiscript.ir import Op
from compiscript.ir.runtime import MESSAGES, CompiscriptRuntimeError, RuntimeErrorKind, checks_for


def test_instrucciones_que_revisan_errores():
    assert checks_for(Op.INDEX_GET) == [RuntimeErrorKind.NULL_REFERENCE, RuntimeErrorKind.INDEX_OUT_OF_BOUNDS]
    assert checks_for(Op.DIV) == [RuntimeErrorKind.DIVISION_BY_ZERO]
    assert checks_for(Op.FIELD_GET) == [RuntimeErrorKind.NULL_REFERENCE]
    assert checks_for(Op.ADD) == []


def test_mensaje_es_el_valor_del_catch():
    err = CompiscriptRuntimeError(RuntimeErrorKind.DIVISION_BY_ZERO)
    assert str(err) == "división entre cero" and err.kind == RuntimeErrorKind.DIVISION_BY_ZERO
    assert all(MESSAGES.values())
