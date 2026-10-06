"""1. Sistema de tipos."""

from .helpers import assert_error, assert_ok


# --- aritmética --------------------------------------------------------------

def test_aritmetica_entera_valida():
    assert_ok("let a: integer = 1 + 2 * 3 - 4 / 2 % 3;")


def test_aritmetica_rechaza_boolean():
    assert_error("let a: integer = 1 + true;", "operador '+'", "boolean")


def test_aritmetica_rechaza_string_en_multiplicacion():
    assert_error('let a: integer = "x" * 2;', "operador '*'")


def test_concatenacion_string_permitida():
    assert_ok('let s: string = "total: " + 5;')


def test_menos_unario_requiere_integer():
    assert_error("let a: integer = -true;", "unario '-'")


# --- lógica ------------------------------------------------------------------

def test_logica_valida():
    assert_ok("let b: boolean = !(true && false) || true;")


def test_and_rechaza_integer():
    assert_error("let b: boolean = 1 && true;", "operador '&&'", "boolean")


def test_not_rechaza_string():
    assert_error('let b: boolean = !"s";', "operador '!'")


# --- comparaciones -----------------------------------------------------------

def test_comparaciones_validas():
    assert_ok("""
        let a: boolean = 1 < 2;
        let b: boolean = "x" == "y";
        let c: boolean = true != false;
    """)


def test_igualdad_tipos_distintos():
    assert_error('let b: boolean = 1 == "1";', "comparar", "integer", "string")


def test_relacional_requiere_integer():
    assert_error('let b: boolean = "a" < "b";', "operador '<'")


def test_null_comparable_con_referencias():
    assert_ok('let s: string = "x"; let b: boolean = s == null;')


# --- asignaciones ------------------------------------------------------------

def test_asignacion_tipo_correcto():
    assert_ok("let a: integer = 1; a = 2;")


def test_asignacion_tipo_incorrecto():
    assert_error('let a: integer = 1; a = "dos";', "asignar", "string", "integer")


def test_inicializacion_tipo_incorrecto():
    assert_error("let s: string = 10;", "inicializar", "string", "integer")


def test_inferencia_de_tipo():
    assert_error('let a = 1; a = "x";', "asignar")


def test_variable_sin_tipo_ni_valor():
    assert_error("let a;", "necesita un tipo o un valor inicial")


# --- constantes --------------------------------------------------------------

def test_const_inicializada_valida():
    assert_ok("const PI: integer = 314;")


def test_const_sin_inicializar_es_error():
    # La gramática exige `= expression`; se reporta como error sintáctico.
    errs = assert_error("const PI: integer;")
    assert errs


def test_const_no_reasignable():
    assert_error("const PI: integer = 3; PI = 4;", "constante 'PI'")


# --- listas ------------------------------------------------------------------

def test_lista_homogenea_valida():
    assert_ok("let xs: integer[] = [1, 2, 3]; let m: integer[][] = [[1], [2, 3]];")


def test_lista_heterogenea_invalida():
    assert_error('let xs = [1, "dos"];', "mismo tipo")


def test_lista_tipo_declarado_incompatible():
    assert_error('let xs: integer[] = ["a"];', "inicializar")


def test_ternario_condicion_boolean():
    assert_error("let a: integer = 1 ? 2 : 3;", "ternario", "boolean")


def test_ternario_ramas_compatibles():
    assert_error('let a: integer = true ? 1 : "x";', "ramas del ternario")


# --- var, null y const inferida ----------------------------------------------

def test_var_funciona_como_let():
    assert_ok('var contador: integer = 0; contador = contador + 1;')
    assert_error('var a: integer = 1; let a: string = "x";', "redeclaración")


def test_const_con_tipo_inferido_sigue_siendo_inmutable():
    assert_error("const MAX = 100; MAX = 200;", "constante 'MAX'")


def test_null_asignable_a_referencias():
    assert_ok('let s: string = null; let xs: integer[] = null; class A {} let a: A = null;')


def test_null_no_asignable_a_primitivos_de_valor():
    assert_error("let n: integer = null;", "inicializar", "null")
    assert_error("let b: boolean = null;", "inicializar", "null")
