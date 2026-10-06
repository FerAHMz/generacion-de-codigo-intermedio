"""2. Manejo de ámbito."""

from .helpers import assert_error, assert_ok


def test_resolucion_global_desde_funcion():
    assert_ok("""
        let g: integer = 1;
        function f(): integer { return g + 1; }
    """)


def test_resolucion_local_sobre_global():
    assert_ok("""
        let x: integer = 1;
        function f(): string { let x: string = "local"; return x; }
    """)


def test_variable_no_declarada():
    assert_error("print(y);", "'y' no ha sido declarada")


def test_asignacion_a_no_declarada():
    assert_error("z = 1;", "'z' no ha sido declarada")


def test_redeclaracion_mismo_ambito():
    assert_error("let a: integer = 1; let a: string = \"x\";", "redeclaración", "'a'")


def test_redeclaracion_en_bloque_anidado_permitida():
    assert_ok("let a: integer = 1; { let a: string = \"x\"; }")


def test_variable_de_bloque_no_visible_afuera():
    assert_error("{ let interna: integer = 1; } print(interna);", "'interna' no ha sido declarada")


def test_bloques_anidados_ven_variables_externas():
    assert_ok("let a: integer = 1; { let b: integer = a; { let c: integer = a + b; } }")


def test_nuevo_entorno_por_funcion():
    assert_error("function f() { let v: integer = 1; } print(v);", "'v' no ha sido declarada")


def test_nuevo_entorno_por_clase():
    assert_error("class A { let campo: integer = 1; } print(campo);", "'campo' no ha sido declarada")


def test_parametro_visible_solo_en_su_funcion():
    assert_error("function f(p: integer) {} print(p);", "'p' no ha sido declarada")


def test_uso_antes_de_declaracion_en_inicializador():
    assert_error("let x: integer = x + 1;", "'x' no ha sido declarada")


def test_funcion_y_variable_mismo_nombre():
    assert_error("function f() {} let f: integer = 1;", "redeclaración")


def test_tabla_de_simbolos_registra_entornos():
    from compiscript.semantic import analyze
    result = analyze("let g: integer = 0; function f(a: integer) { let l: integer = a; { let b: integer = 1; } }")
    scopes = {s.path(): s for s in result.table.scopes}
    assert "global" in scopes and "global/f" in scopes and "global/f/block" in scopes
    assert scopes["global/f"].resolve_local("a").kind == "parameter"
    assert scopes["global/f"].resolve_local("l").kind == "variable"
    assert scopes["global/f/block"].resolve("g").scope is result.table.global_scope


def test_uso_de_variable_sin_inicializar():
    assert_error("let x: integer; print(x + 1);", "'x' se usa antes de recibir un valor")


def test_variable_inicializada_por_asignacion_previa():
    assert_ok("let x: integer; x = 1; print(x);")
