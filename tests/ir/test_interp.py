"""Intérprete de TAC (`compiscript/ir/interp.py`) con TAC escrito a mano.

Estos tests no usan el generador: construyen los cuádruplos directamente y
toman de la tabla de símbolos solo los registros de activación y layouts
(direcciones de parámetros, nivel léxico y vtables).
"""

import pytest

from compiscript.ir.interp import InterpreterError, run
from compiscript.ir.runtime import MESSAGES, RuntimeErrorKind
from compiscript.ir.tac import Const, Field, Label, Op, Quad, TACProgram, Temp, Var
from compiscript.semantic import analyze


def table_for(source: str = ""):
    """Tabla con direcciones y registros de activación de `source`."""
    result = analyze(source)
    assert result.ok, [str(e) for e in result.errors]
    return result.table.allocate_storage()


def param_var(table, label: str, i: int = 0) -> Var:
    sym = table.record_of(label).params[i]
    return Var(sym.name, sym.address)


def main(*body: Quad) -> list:
    return [Quad(Op.FUNC_BEGIN, Label("main"), Const(0)), *body, Quad(Op.FUNC_END, Label("main"))]


def func(label: str, *body: Quad) -> list:
    return [Quad(Op.FUNC_BEGIN, Label(label), Const(0)), *body, Quad(Op.FUNC_END, Label(label))]


def program(*parts: list) -> TACProgram:
    prog = TACProgram([q for part in parts for q in part])
    assert prog.check() == []
    return prog


t1, t2, t3 = Temp(1), Temp(2), Temp(3)
X, Y = Var("x", "global[0]"), Var("y", "global[4]")
L1, L2 = Label("L1"), Label("L2")


def label(L):
    return Quad(Op.LABEL, result=L)


def pr(x):
    return Quad(Op.PRINT, x)


# ---------------------------------------------------------------------------
# Aritmética, memoria y saltos
# ---------------------------------------------------------------------------

def test_aritmetica_con_temporales_y_variables():
    prog = program(main(
        Quad(Op.ASSIGN, Const(2), None, X),             # x = 2
        Quad(Op.MUL, X, Const(3), t1),                  # t1 = x * 3
        Quad(Op.ADD, Const(1), t1, t1),                 # t1 = 1 + t1
        Quad(Op.ASSIGN, t1, None, Y),                   # y = t1
        pr(Y),
        Quad(Op.NEG, Y, None, t1),
        pr(t1),
    ))
    assert run(prog, table_for()) == ["7", "-7"]


@pytest.mark.parametrize("a, b, cociente, resto", [
    (7, 2, 3, 1), (-7, 2, -3, -1), (7, -2, -3, 1), (-7, -2, 3, -1),
])
def test_division_entera_trunca_hacia_cero(a, b, cociente, resto):
    prog = program(main(
        Quad(Op.DIV, Const(a), Const(b), t1), pr(t1),
        Quad(Op.MOD, Const(a), Const(b), t1), pr(t1),
    ))
    assert run(prog, table_for()) == [str(cociente), str(resto)]


def test_division_float_e_int_to_float():
    prog = program(main(
        Quad(Op.INT_TO_FLOAT, Const(7), None, t1),
        Quad(Op.DIV, t1, Const(2.0), t1),
        pr(t1),
    ))
    assert run(prog, table_for()) == ["3.5"]


def test_enteros_de_32_bits():
    prog = program(main(Quad(Op.ADD, Const(2**31 - 1), Const(1), t1), pr(t1)))
    assert run(prog, table_for()) == [str(-2**31)]


def test_concat_convierte_valores_a_texto():
    prog = program(main(
        Quad(Op.CONCAT, Const("n = "), Const(5), t1),
        Quad(Op.CONCAT, t1, Const(True), t1),
        Quad(Op.CONCAT, t1, Const(None), t1),
        pr(t1),
    ))
    assert run(prog, table_for()) == ["n = 5truenull"]


def test_saltos_condicionales_y_bucle():
    # x = 0; while (x < 3) { print x; x = x + 1; }
    prog = program(main(
        Quad(Op.ASSIGN, Const(0), None, X),
        label(L1),
        Quad(Op.if_rel(Op.GE), X, Const(3), L2),
        pr(X),
        Quad(Op.ADD, X, Const(1), t1),
        Quad(Op.ASSIGN, t1, None, X),
        Quad(Op.GOTO, result=L1),
        label(L2),
    ))
    assert run(prog, table_for()) == ["0", "1", "2"]


def test_if_e_iffalse_con_booleanos():
    prog = program(main(
        Quad(Op.LT, Const(1), Const(2), t1),             # t1 = true
        Quad(Op.IF_FALSE, t1, None, L1),
        pr(Const("si")),
        label(L1),
        Quad(Op.NOT, t1, None, t1),
        Quad(Op.IF, t1, None, L2),
        pr(Const("no salta")),
        label(L2),
    ))
    assert run(prog, table_for()) == ["si", "no salta"]


def test_igualdad_de_strings_por_contenido():
    prog = program(main(
        Quad(Op.CONCAT, Const("ab"), Const("c"), t1),
        Quad(Op.EQ, t1, Const("abc"), t1),
        pr(t1),
    ))
    assert run(prog, table_for()) == ["true"]


def test_limite_de_pasos():
    prog = program(main(label(L1), Quad(Op.GOTO, result=L1)))
    with pytest.raises(InterpreterError):
        run(prog, table_for(), max_steps=1000)


# ---------------------------------------------------------------------------
# Funciones: param/call/return, recursión y static link
# ---------------------------------------------------------------------------

FACT = "function fact(n: integer): integer { return n; }"


def fact_program(table, arg: int) -> TACProgram:
    n = param_var(table, "fact")
    return program(
        main(Quad(Op.PARAM, Const(arg)), Quad(Op.CALL, Label("fact"), Const(1), t1), pr(t1)),
        func("fact",
             Quad(Op.if_rel(Op.GT), n, Const(1), L1),
             Quad(Op.RETURN, Const(1)),
             label(L1),
             Quad(Op.SUB, n, Const(1), t1),
             Quad(Op.PARAM, t1),
             Quad(Op.CALL, Label("fact"), Const(1), t1),
             Quad(Op.MUL, n, t1, t1),
             Quad(Op.RETURN, t1)),
    )


def test_recursion_fact():
    table = table_for(FACT)
    assert run(fact_program(table, 5), table) == ["120"]
    assert run(fact_program(table, 10), table) == ["3628800"]


def test_cada_llamada_tiene_sus_temporales():
    # t1 del llamador sobrevive a la llamada aunque el llamado también use t1.
    table = table_for("function f(): integer { return 1; }")
    prog = program(
        main(Quad(Op.ASSIGN, Const(10), None, t1),
             Quad(Op.CALL, Label("f"), Const(0), t2),
             Quad(Op.ADD, t1, t2, t1),
             pr(t1)),
        func("f", Quad(Op.ASSIGN, Const(99), None, t1), Quad(Op.RETURN, Const(5))),
    )
    assert run(prog, table) == ["15"]


def test_funcion_void_termina_en_func_end():
    table = table_for("function f(s: string) { print(s); }")
    s = param_var(table, "f")
    prog = program(
        main(Quad(Op.PARAM, Const("hola")), Quad(Op.CALL, Label("f"), Const(1)), pr(Const("fin"))),
        func("f", pr(s)),
    )
    assert run(prog, table) == ["hola", "fin"]


def test_closure_lee_y_escribe_por_static_link():
    src = """
    function externa(n: integer): integer {
      function interna(): integer { n = n + 1; return n; }
      interna();
      return interna();
    }
    """
    table = table_for(src)
    n_sym = table.record_of("externa").params[0]
    n_here = Var("n", n_sym.address)
    n_outer = Var("n", n_sym.address, hops=1)
    prog = program(
        main(Quad(Op.PARAM, Const(10)), Quad(Op.CALL, Label("externa"), Const(1), t1), pr(t1)),
        func("externa",
             Quad(Op.CALL, Label("externa_interna"), Const(0), t1),
             Quad(Op.CALL, Label("externa_interna"), Const(0), t1),
             pr(n_here),
             Quad(Op.RETURN, t1)),
        func("externa_interna",
             Quad(Op.ADD, n_outer, Const(1), t1),
             Quad(Op.ASSIGN, t1, None, n_outer),
             Quad(Op.RETURN, n_outer)),
    )
    assert run(prog, table) == ["12", "12"]


def test_static_link_con_recursion_de_la_externa():
    # En cada activación de `externa` la anidada ve el n de SU marco externo.
    src = """
    function externa(n: integer): integer {
      function interna(): integer { return n; }
      if (n > 0) { return externa(n - 1) + interna(); }
      return 0;
    }
    """
    table = table_for(src)
    n_sym = table.record_of("externa").params[0]
    n = Var("n", n_sym.address)
    prog = program(
        main(Quad(Op.PARAM, Const(3)), Quad(Op.CALL, Label("externa"), Const(1), t1), pr(t1)),
        func("externa",
             Quad(Op.if_rel(Op.LE), n, Const(0), L1),
             Quad(Op.SUB, n, Const(1), t1),
             Quad(Op.PARAM, t1),
             Quad(Op.CALL, Label("externa"), Const(1), t1),
             Quad(Op.CALL, Label("externa_interna"), Const(0), t2),
             Quad(Op.ADD, t1, t2, t1),
             Quad(Op.RETURN, t1),
             label(L1),
             Quad(Op.RETURN, Const(0))),
        func("externa_interna", Quad(Op.RETURN, Var("n", n_sym.address, hops=1))),
    )
    assert run(prog, table) == ["6"]          # 3 + 2 + 1


# ---------------------------------------------------------------------------
# Arreglos y objetos
# ---------------------------------------------------------------------------

def test_arreglo_alloc_len_lectura_y_escritura():
    prog = program(main(
        Quad(Op.ALLOC, Const(3), None, t1),
        Quad(Op.INDEX_SET, Const(0), Const(10), t1),
        Quad(Op.INDEX_SET, Const(1), Const(20), t1),
        Quad(Op.INDEX_SET, Const(2), Const(30), t1),
        Quad(Op.ASSIGN, t1, None, X),
        Quad(Op.INDEX_GET, X, Const(1), t1), pr(t1),
        Quad(Op.LEN, X, None, t1), pr(t1),
        pr(X),
    ))
    assert run(prog, table_for()) == ["20", "3", "[10, 20, 30]"]


def test_arreglos_son_referencias():
    prog = program(main(
        Quad(Op.ALLOC, Const(1), None, t1),
        Quad(Op.INDEX_SET, Const(0), Const(1), t1),
        Quad(Op.ASSIGN, t1, None, X),
        Quad(Op.ASSIGN, X, None, Y),                     # y = x (misma referencia)
        Quad(Op.INDEX_SET, Const(0), Const(2), Y),
        Quad(Op.INDEX_GET, X, Const(0), t1), pr(t1),
        Quad(Op.EQ, X, Y, t1), pr(t1),
    ))
    assert run(prog, table_for()) == ["2", "true"]


CLASES = """
class Animal {
  let nombre: string;
  function hablar(): string { return ""; }
  function presentarse(): string { return ""; }
}
class Perro : Animal {
  function hablar(): string { return ""; }
}
"""


def test_objeto_con_metodo_sobreescrito_usa_la_vtable():
    table = table_for(CLASES)
    off = table.class_layouts["Animal"].field_offset("nombre")
    nombre = Field("nombre", off)
    this_a = param_var(table, "Animal_presentarse")
    this_p = param_var(table, "Perro_hablar")
    prog = program(
        main(
            Quad(Op.NEW, Label("Perro"), Const(8), t1),          # t1 = new Perro
            Quad(Op.FIELD_SET, nombre, Const("Toby"), t1),
            Quad(Op.ASSIGN, t1, None, X),                        # Animal x = perro
            Quad(Op.METHOD, X, Label("presentarse"), t2),
            Quad(Op.PARAM, X),
            Quad(Op.CALL, t2, Const(1), t1),
            pr(t1),
            Quad(Op.NEW, Label("Animal"), Const(8), t1),
            Quad(Op.FIELD_SET, nombre, Const("Genérico"), t1),
            Quad(Op.METHOD, t1, Label("presentarse"), t2),
            Quad(Op.PARAM, t1),
            Quad(Op.CALL, t2, Const(1), t1),
            pr(t1)),
        func("Animal_hablar", Quad(Op.RETURN, Const("hace ruido"))),
        func("Animal_presentarse",                                # this.nombre + " " + this.hablar()
             Quad(Op.FIELD_GET, this_a, nombre, t1),
             Quad(Op.CONCAT, t1, Const(" "), t1),
             Quad(Op.METHOD, this_a, Label("hablar"), t2),
             Quad(Op.PARAM, this_a),
             Quad(Op.CALL, t2, Const(1), t2),
             Quad(Op.CONCAT, t1, t2, t1),
             Quad(Op.RETURN, t1)),
        func("Perro_hablar",
             Quad(Op.FIELD_GET, this_p, nombre, t1),
             Quad(Op.RETURN, Const("ladra"))),
    )
    assert run(prog, table) == ["Toby ladra", "Genérico hace ruido"]


def test_objetos_comparan_por_identidad():
    table = table_for(CLASES)
    prog = program(main(
        Quad(Op.NEW, Label("Animal"), Const(8), t1),
        Quad(Op.NEW, Label("Animal"), Const(8), t2),
        Quad(Op.EQ, t1, t2, t3), pr(t3),
        Quad(Op.NE, t1, Const(None), t3), pr(t3),
    ))
    assert run(prog, table) == ["false", "true"]


# ---------------------------------------------------------------------------
# Excepciones (R2)
# ---------------------------------------------------------------------------

E = Var("e", "global[8]")


def test_indice_fuera_de_rango_dentro_de_try_salta_al_catch():
    prog = program(main(
        Quad(Op.ALLOC, Const(2), None, t1),
        Quad(Op.PUSH_HANDLER, result=L1),
        Quad(Op.INDEX_GET, t1, Const(5), t2),
        pr(Const("no llega")),
        Quad(Op.POP_HANDLER),
        Quad(Op.GOTO, result=L2),
        label(L1),
        Quad(Op.GET_EXCEPTION, result=E),
        Quad(Op.CONCAT, Const("atrapado: "), E, t1),
        pr(t1),
        label(L2),
        pr(Const("sigue")),
    ))
    assert run(prog, table_for()) == ["atrapado: índice fuera de rango", "sigue"]


def test_error_fuera_de_try_termina_con_el_mensaje():
    prog = program(main(
        pr(Const("antes")),
        Quad(Op.ALLOC, Const(1), None, t1),
        Quad(Op.INDEX_SET, Const(-1), Const(0), t1),
        pr(Const("después")),
    ))
    out = run(prog, table_for())
    assert out[0] == "antes"
    assert len(out) == 2 and "índice fuera de rango" in out[1]


def test_error_en_funcion_llamada_desde_el_try_desapila_sus_marcos():
    table = table_for("function f(d: integer): integer { return d; } function g(d: integer): integer { return d; }")
    d_f, d_g = param_var(table, "f"), param_var(table, "g")
    prog = program(
        main(
            Quad(Op.ASSIGN, Const(7), None, t1),             # valor vivo en main
            Quad(Op.PUSH_HANDLER, result=L1),
            Quad(Op.PARAM, Const(0)),
            Quad(Op.CALL, Label("f"), Const(1), t2),
            Quad(Op.POP_HANDLER),
            Quad(Op.GOTO, result=L2),
            label(L1),
            Quad(Op.GET_EXCEPTION, result=E),
            pr(E),
            pr(t1),                                         # el marco de main sigue intacto
            label(L2),
            Quad(Op.PARAM, Const(4)),                        # la pila de param quedó limpia
            Quad(Op.CALL, Label("g"), Const(1), t2),
            pr(t2)),
        func("f", Quad(Op.PARAM, d_f), Quad(Op.CALL, Label("g"), Const(1), t1), Quad(Op.RETURN, t1)),
        func("g", Quad(Op.PARAM, Const(99)),                  # param pendiente al fallar
             Quad(Op.DIV, Const(10), d_g, t1), Quad(Op.RETURN, t1)),
    )
    assert run(prog, table) == [MESSAGES[RuntimeErrorKind.DIVISION_BY_ZERO], "7", "2"]


def test_pop_handler_deja_activo_el_try_externo():
    prog = program(main(
        Quad(Op.PUSH_HANDLER, result=L1),                    # try externo
        Quad(Op.PUSH_HANDLER, result=L2),                    # try interno
        Quad(Op.POP_HANDLER),                                # sale del interno sin error
        Quad(Op.MOD, Const(1), Const(0), t1),                # error -> catch externo
        label(L2),
        pr(Const("catch interno")),
        label(L1),
        Quad(Op.GET_EXCEPTION, result=E),
        pr(E),
    ))
    assert run(prog, table_for()) == [MESSAGES[RuntimeErrorKind.DIVISION_BY_ZERO]]


def test_acceso_a_null():
    table = table_for(CLASES)
    prog = program(main(
        Quad(Op.ASSIGN, Const(None), None, X),
        Quad(Op.PUSH_HANDLER, result=L1),
        Quad(Op.FIELD_GET, X, Field("nombre", 4), t1),
        Quad(Op.POP_HANDLER),
        label(L1),
        Quad(Op.GET_EXCEPTION, result=E),
        pr(E),
        Quad(Op.LEN, X, None, t1),
    ))
    null = MESSAGES[RuntimeErrorKind.NULL_REFERENCE]
    assert run(prog, table) == [null, f"Error en tiempo de ejecución: {null}"]
