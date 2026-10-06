"""6. Listas y estructuras de datos."""

from .helpers import assert_error, assert_ok


def test_acceso_valido():
    assert_ok("let xs: integer[] = [1, 2, 3]; let x: integer = xs[0];")


def test_matriz():
    assert_ok("let m: integer[][] = [[1, 2], [3, 4]]; let fila: integer[] = m[0]; let v: integer = m[1][1];")


def test_indice_debe_ser_integer():
    assert_error('let xs: integer[] = [1]; let x: integer = xs["0"];', "índice", "integer")


def test_indice_negativo_literal():
    assert_error("let xs: integer[] = [1]; let x: integer = xs[-1];", "índice inválido")


def test_indexar_no_arreglo():
    assert_error("let n: integer = 1; let x: integer = n[0];", "solo se pueden indexar arreglos")


def test_elemento_tipo_incorrecto_al_extraer():
    assert_error("let xs: integer[] = [1]; let s: string = xs[0];", "inicializar", "string", "integer")


def test_elementos_heterogeneos():
    assert_error("let xs: integer[] = [1, true];", "mismo tipo")


def test_asignar_elemento_tipo_incorrecto():
    assert_error('let xs: integer[] = [1]; xs[0] = "x";', "asignar")


def test_arreglo_vacio_con_tipo_declarado():
    assert_ok("let xs: integer[] = [];")


def test_foreach_tipa_elemento():
    assert_error('let xs: integer[] = [1]; foreach (n in xs) { let s: string = n; }', "inicializar")


def test_funcion_retorna_arreglo():
    assert_ok("function m(n: integer): integer[] { return [n, n * 2]; } let r: integer[] = m(2);")
