"""1b. Tipo float: literales, promoción integer -> float y restricciones."""

from compiscript.semantic import analyze

from .helpers import assert_error, assert_ok


def test_literal_float_y_declaracion():
    assert_ok("let f: float = 3.14; let g = 2.5;")
    assert analyze("let g = 2.5;").table.global_scope.resolve("g").type.name == "float"


def test_integer_se_promueve_a_float():
    assert_ok("let f: float = 2; let h: float = 1 + 2.5; let k: float = 3 / 2.0;")


def test_float_no_se_asigna_a_integer():
    assert_error("let i: integer = 1.5;", "inicializar", "integer", "float")


def test_aritmetica_mixta_da_float():
    assert_error("let f: float = 1.5; let i: integer = f * 2;", "integer", "float")


def test_menos_unario_conserva_float():
    assert_ok("let f: float = -2.5;")


def test_comparaciones_entre_numericos():
    assert_ok("let b: boolean = 1 < 2.5; let c: boolean = 3 == 3.0; let d: boolean = 2.0 >= 1.0;")


def test_modulo_solo_entero():
    assert_error("let r = 5.0 % 2;", "operador '%'", "integer")


def test_indice_float_invalido():
    assert_error("let xs: integer[] = [1, 2]; let x: integer = xs[1.0];", "índice", "float")


def test_arreglo_mixto_se_promueve_a_float():
    assert_ok("let xs: float[] = [1, 2.5, 3];")
    assert_error("let ys: integer[] = [1, 2.5];", "inicializar")


def test_retorno_float_en_funcion_integer():
    assert_error("function f(): integer { return 2.5; }", "debe retornar integer", "float")


def test_parametro_float_acepta_integer():
    assert_ok("function mitad(x: float): float { return x / 2; } let m: float = mitad(3);")


def test_parametro_integer_rechaza_float():
    assert_error("function doble(x: integer): integer { return x * 2; } doble(1.5);", "argumento 1", "float")


def test_concatenacion_con_float():
    assert_ok('let s: string = "pi = " + 3.14;')


def test_float_con_boolean_es_error():
    assert_error("let f: float = 1.5 + true;", "operador '+'", "boolean")
