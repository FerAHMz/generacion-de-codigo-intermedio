"""3. Funciones y procedimientos."""

from compiscript.semantic import analyze

from .helpers import assert_error, assert_ok


def test_llamada_valida():
    assert_ok("function suma(a: integer, b: integer): integer { return a + b; } let r: integer = suma(1, 2);")


def test_numero_de_argumentos_incorrecto():
    assert_error("function f(a: integer) {} f();", "espera 1 argumento(s) pero recibió 0")


def test_tipo_de_argumento_incorrecto():
    assert_error('function f(a: integer) {} f("x");', "argumento 1", "integer", "string")


def test_argumentos_posicionales():
    assert_error('function f(a: integer, b: string) {} f("x", 1);', "argumento 1")


def test_tipo_de_retorno_correcto():
    assert_ok('function nombre(): string { return "ok"; }')


def test_tipo_de_retorno_incorrecto():
    assert_error("function f(): integer { return \"x\"; }", "debe retornar integer", "string")


def test_return_sin_valor_en_funcion_tipada():
    assert_error("function f(): integer { return; }", "debe retornar un valor")


def test_funcion_void_no_retorna_valor():
    assert_error("function f() { return 1; }", "no declara tipo de retorno")


def test_funcion_tipada_sin_return():
    assert_error("function f(): integer { let x: integer = 1; }", "no tiene ninguna sentencia return")


def test_recursion():
    assert_ok("""
        function factorial(n: integer): integer {
          if (n <= 1) { return 1; }
          return n * factorial(n - 1);
        }
    """)


def test_llamada_a_funcion_declarada_despues():
    assert_ok("function a(): integer { return b(); } function b(): integer { return 1; }")


def test_funciones_anidadas_y_closure():
    src = """
        function crearContador(): integer {
          let cuenta: integer = 0;
          function siguiente(): integer { cuenta = cuenta + 1; return cuenta; }
          return siguiente();
        }
    """
    assert_ok(src)
    result = analyze(src)
    inner = [s for s in result.table.scopes if s.name == "crearContador"][0].resolve_local("siguiente")
    assert [c.name for c in inner.captures] == ["cuenta"]
    assert inner.captures[0].captured is True


def test_funcion_anidada_no_visible_afuera():
    assert_error("function f() { function g() {} } g();", "'g' no ha sido declarada")


def test_funciones_duplicadas():
    assert_error("function f() {} function f() {}", "redeclaración de función 'f'")


def test_parametros_duplicados():
    assert_error("function f(a: integer, a: integer) {}", "parámetro duplicado 'a'")


def test_parametro_sin_tipo():
    assert_error("function f(a) {}", "debe declarar su tipo")


def test_llamar_a_no_funcion():
    assert_error("let x: integer = 1; x();", "no es una función")


def test_return_fuera_de_funcion():
    assert_error("return 1;", "'return' solo puede usarse dentro de una función")


def test_return_dentro_de_bucle_en_funcion():
    assert_ok("function f(): integer { while (true) { return 1; } return 0; }")
