"""7. Reglas generales: código muerto, expresiones sin sentido, duplicados.
También valida el programa de ejemplo del curso."""

import os

from compiscript.semantic import analyze_file

from .helpers import assert_error, assert_ok

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_codigo_muerto_tras_return():
    assert_error("function f(): integer { return 1; print(2); }", "código muerto")


def test_codigo_muerto_tras_break():
    assert_error("while (true) { break; print(1); }", "código muerto")


def test_codigo_muerto_tras_continue():
    assert_error("while (true) { continue; let x: integer = 1; }", "código muerto")


def test_return_en_rama_no_es_codigo_muerto():
    assert_ok("function f(n: integer): integer { if (n > 0) { return 1; } return 0; }")


def test_multiplicar_funciones():
    assert_error("function f(): integer { return 1; } let x: integer = f * 2;", "no tiene sentido", "función")


def test_sumar_funcion_a_string():
    assert_error('function f() {} let s: string = "a" + f;', "no tiene sentido")


def test_asignar_a_funcion():
    assert_error("function f() {} f = 1;", "no se puede asignar a la función")


def test_imprimir_funcion():
    assert_error("function f() {} print(f);", "no se puede imprimir una función")


def test_declaraciones_duplicadas_de_variable():
    assert_error("let a: integer = 1; let a: integer = 2;", "redeclaración")


def test_parametros_duplicados():
    assert_error("function f(x: integer, x: string) {}", "parámetro duplicado")


def test_asignar_a_resultado_de_llamada():
    assert_error("function f(): integer { return 1; } f() = 2;", "no se puede asignar al resultado de una llamada")


def test_error_sintactico_detiene_semantica():
    from compiscript.semantic import analyze
    r = analyze("let x = ;")
    assert any(e.phase == "syntax" for e in r.errors)
    assert not any(e.phase == "semantic" for e in r.errors)


def test_programa_de_ejemplo_del_curso_es_valido():
    result = analyze_file(os.path.join(ROOT, "program", "program.cps"))
    assert [str(e) for e in result.errors] == []
