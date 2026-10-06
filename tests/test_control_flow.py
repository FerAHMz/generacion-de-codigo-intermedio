"""4. Control de flujo."""

from .helpers import assert_error, assert_ok


def test_if_boolean():
    assert_ok("let x: integer = 5; if (x > 1) { print(x); } else { print(0); }")


def test_if_no_boolean():
    assert_error("if (1) {}", "condición de 'if'", "boolean")


def test_while_no_boolean():
    assert_error('while ("s") {}', "condición de 'while'")


def test_do_while_no_boolean():
    assert_error("let x: integer = 1; do { x = x - 1; } while (x);", "condición de 'do-while'")


def test_for_valido():
    assert_ok("for (let i: integer = 0; i < 3; i = i + 1) { print(i); }")


def test_for_condicion_no_boolean():
    assert_error("for (let i: integer = 0; i; i = i + 1) {}", "condición de 'for'")


def test_for_variable_local_al_bucle():
    assert_error("for (let i: integer = 0; i < 3; i = i + 1) {} print(i);", "'i' no ha sido declarada")


def test_switch_valido():
    assert_ok("""
        let x: integer = 1;
        switch (x) { case 1: print("uno"); break; case 2: print("dos"); default: print("otro"); }
    """)


def test_switch_case_tipo_incompatible():
    assert_error('let x: integer = 1; switch (x) { case "a": print(1); }', "'case'", "no es comparable")


def test_break_dentro_de_bucle():
    assert_ok("while (true) { break; }")


def test_continue_dentro_de_bucle():
    assert_ok("let xs: integer[] = [1]; foreach (n in xs) { if (n < 60) { continue; } }")


def test_break_fuera_de_bucle():
    assert_error("break;", "'break' solo puede usarse")


def test_continue_fuera_de_bucle():
    assert_error("continue;", "'continue' solo puede usarse")


def test_continue_en_switch_sin_bucle():
    assert_error("let x: integer = 1; switch (x) { case 1: continue; }", "'continue' solo puede usarse")


def test_break_en_funcion_dentro_de_bucle_es_error():
    # El bucle está fuera de la función: no aplica al cuerpo de f.
    assert_error("while (true) { function f() { break; } }", "'break' solo puede usarse")


def test_try_catch_declara_variable_de_error():
    assert_ok('try { let r: integer = 1; } catch (err) { print("Error: " + err); }')


def test_variable_de_catch_no_visible_afuera():
    assert_error("try {} catch (err) {} print(err);", "'err' no ha sido declarada")


def test_do_while_valido():
    assert_ok("let x: integer = 3; do { x = x - 1; } while (x > 0);")


def test_condiciones_boolean_en_todas_las_estructuras():
    assert_ok("""
        let x: integer = 5;
        if (x > 0) {}
        while (x > 0) { x = x - 1; }
        do { x = x + 1; } while (x < 5);
        for (let i: integer = 0; i < 2; i = i + 1) {}
        let t: integer = x > 3 ? 1 : 0;
    """)
