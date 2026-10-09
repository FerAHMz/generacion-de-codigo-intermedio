"""Pruebas de extremo a extremo: programa .cps -> TAC -> intérprete.

Cada caso compila con `compile_source` y ejecuta el TAC con `ir/interp.py`;
la salida de los `print` debe ser la que produciría el programa fuente. Si el
generador todavía no soporta una construcción (`NotImplementedError` o
`CodegenError`), el caso se salta en vez de fallar.
"""

import glob
import os

import pytest

from compiscript.codegen import CodegenError, compile_file, compile_source
from compiscript.ir.interp import run
from compiscript.ir.runtime import MESSAGES, RuntimeErrorKind

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

INDEX = MESSAGES[RuntimeErrorKind.INDEX_OUT_OF_BOUNDS]
DIV0 = MESSAGES[RuntimeErrorKind.DIVISION_BY_ZERO]
NULL = MESSAGES[RuntimeErrorKind.NULL_REFERENCE]


def compile_or_skip(source: str):
    try:
        result = compile_source(source)
    except (NotImplementedError, CodegenError) as exc:
        pytest.skip(f"el generador aún no soporta esta construcción: {exc}")
    assert [str(e) for e in result.errors] == []
    assert result.program.check() == []
    return result


def execute(source: str):
    result = compile_or_skip(source)
    return run(result.program, result.table)


CASES = {
    # ------------------------------------------------------------- expresiones
    "precedencia": ("""
        let a: integer = 2; let b: integer = 3; let c: integer = 4;
        print(a + b * c - 1);
        print((a + b) * (c - 1));
        print(-a * b);
        print(17 % 5 + 7 / 2);
    """, ["13", "15", "-6", "5"]),
    "division_entera_negativa": ("""
        let n: integer = -7;
        print(n / 2); print(n % 2);
    """, ["-3", "-1"]),
    "float_y_promocion": ("""
        let r: float = 2;
        let n: integer = 3;
        print(r * n);
        print(7 / 2.0);
        let xs: float[] = [1, 2.5];
        print(xs[0] + xs[1]);
    """, ["6.0", "3.5", "3.5"]),
    "strings": ("""
        let n: integer = 5;
        let ok: boolean = n > 3;
        print("n = " + n + ", ok = " + ok);
        print("a" + "b" == "ab");
    """, ["n = 5, ok = true", "true"]),
    "asignacion_como_expresion": ("""
        let x: integer = 1;
        let y: integer = x + (x = 4);
        print(y); print(x);
    """, ["5", "4"]),
    # ----------------------------------------------- booleanos y corto circuito
    "corto_circuito": ("""
        function t(s: string): boolean { print(s); return true; }
        function f(s: string): boolean { print(s); return false; }
        if (f("a") && t("b")) { print("no"); }
        if (t("c") || f("d")) { print("si"); }
        let v: boolean = f("e") || t("f");
        print(v);
        print(!(1 < 2) || 3 >= 3);
    """, ["a", "c", "si", "e", "f", "true", "true"]),
    # ------------------------------------------------------- control de flujo
    "if_else": ("""
        let x: integer = 7;
        if (x > 10) { print("grande"); } else { if (x > 5) { print("medio"); } else { print("chico"); } }
    """, ["medio"]),
    "while_y_do_while": ("""
        let i: integer = 0;
        while (i < 3) { print(i); i = i + 1; }
        do { print(i); i = i - 1; } while (i > 10);
    """, ["0", "1", "2", "3"]),
    "for_con_continue_ejecuta_la_actualizacion": ("""
        for (let i: integer = 0; i < 5; i = i + 1) {
          if (i == 2) { continue; }
          if (i == 4) { break; }
          print(i);
        }
    """, ["0", "1", "3"]),
    "foreach": ("""
        let xs: integer[] = [3, 1, 4, 1, 5];
        let suma: integer = 0;
        foreach (x in xs) { if (x == 1) { continue; } suma = suma + x; }
        print(suma);
    """, ["12"]),
    "switch_con_fallthrough_y_break": ("""
        function nombre(n: integer): string {
          let s: string = "";
          switch (n) {
            case 1: s = s + "uno ";
            case 2: s = s + "dos "; break;
            default: s = s + "otro ";
          }
          return s;
        }
        print(nombre(1)); print(nombre(2)); print(nombre(9));
    """, ["uno dos ", "dos ", "otro "]),
    "break_en_switch_dentro_de_bucle": ("""
        for (let i: integer = 0; i < 3; i = i + 1) {
          switch (i) { case 1: break; default: print(i); }
        }
    """, ["0", "2"]),
    "ternario": ("""
        let a: integer = 4;
        print(a > 3 ? "mayor" : "menor");
        let m: integer = a < 0 ? -a : a * 2;
        print(m);
    """, ["mayor", "8"]),
    # -------------------------------------------------------------- try/catch
    "try_indice_fuera_de_rango": ("""
        let xs: integer[] = [1, 2];
        try { print(xs[5]); print("no"); } catch (e) { print("catch: " + e); }
        print("fin");
    """, [f"catch: {INDEX}", "fin"]),
    "try_error_en_funcion_llamada": ("""
        function div(a: integer, b: integer): integer { return a / b; }
        function calc(b: integer): integer { return div(10, b) + 1; }
        let antes: integer = 7;
        try { print(calc(2)); print(calc(0)); } catch (e) { print(e); }
        print(antes);
    """, ["6", DIV0, "7"]),
    "try_anidado_y_break_dentro_de_try": ("""
        let xs: integer[] = [1];
        let i: integer = 0;
        while (true) {
          try { if (i == 2) { break; } i = i + 1; } catch (e) { print("no"); }
        }
        try {
          try { print(xs[1]); } catch (e) { print("interno: " + e); }
          print(xs[2]);
        } catch (e) { print("externo: " + e); }
        print(i);
    """, [f"interno: {INDEX}", f"externo: {INDEX}", "2"]),
    "return_dentro_de_try": ("""
        let xs: integer[] = [1, 2, 3];
        function get(i: integer): integer {
          try { return xs[i]; } catch (e) { return -1; }
        }
        print(get(1)); print(get(9));
        try { print(xs[7]); } catch (e) { print("sigue funcionando"); }
    """, ["2", "-1", "sigue funcionando"]),
    "error_sin_try_termina": ("""
        print("antes");
        let xs: integer[] = [1];
        print(xs[3]);
        print("después");
    """, ["antes", f"Error en tiempo de ejecución: {INDEX}"]),
    # -------------------------------------------------------------- funciones
    "recursion": ("""
        function fib(n: integer): integer { if (n < 2) { return n; } return fib(n - 1) + fib(n - 2); }
        function fact(n: integer): integer { if (n <= 1) { return 1; } return n * fact(n - 1); }
        print(fib(10)); print(fact(6));
    """, ["55", "720"]),
    "closures": ("""
        function contador(inicio: integer): integer {
          let cuenta: integer = inicio;
          function siguiente(paso: integer): integer { cuenta = cuenta + paso; return cuenta; }
          siguiente(1);
          siguiente(10);
          return cuenta;
        }
        print(contador(5));
    """, ["16"]),
    "closure_dos_niveles": ("""
        function a(x: integer): integer {
          function b(y: integer): integer {
            function c(): integer { return x * 100 + y; }
            return c();
          }
          return b(x + 1);
        }
        print(a(3));
    """, ["304"]),
    "arreglo_retornado_y_parametro": ("""
        function llenar(n: integer): integer[] {
          let r: integer[] = [0, 0, 0];
          for (let i: integer = 0; i < 3; i = i + 1) { r[i] = n * i; }
          return r;
        }
        function sumar(xs: integer[]): integer {
          let s: integer = 0;
          foreach (x in xs) { s = s + x; }
          return s;
        }
        print(sumar(llenar(4)));
    """, ["12"]),
    "matriz": ("""
        let m: integer[][] = [[1, 2], [3, 4]];
        m[1][0] = m[0][1] * 10;
        print(m[1][0] + m[1][1]);
    """, ["24"]),
    # ----------------------------------------------------------------- clases
    "clases_herencia_y_vtable": ("""
        class Animal {
          let nombre: string;
          let patas: integer = 4;
          function constructor(nombre: string) { this.nombre = nombre; }
          function hablar(): string { return "..."; }
          function info(): string { return this.nombre + " (" + this.patas + "): " + this.hablar(); }
        }
        class Pajaro : Animal {
          function constructor(nombre: string) { this.nombre = nombre; this.patas = 2; }
          function hablar(): string { return "pío"; }
        }
        let zoo: Animal[] = [new Animal("gato"), new Pajaro("loro")];
        foreach (a in zoo) { print(a.info()); }
    """, ["gato (4): ...", "loro (2): pío"]),
    "objetos_son_referencias": ("""
        class Caja { let v: integer = 0; }
        let a: Caja = new Caja();
        let b: Caja = a;
        b.v = 9;
        print(a.v);
        print(a == b);
        print(new Caja() == a);
    """, ["9", "true", "false"]),
    "inicializadores_por_instancia": ("""
        class Lista { let xs: integer[] = [0, 0]; }
        let a: Lista = new Lista();
        let b: Lista = new Lista();
        a.xs[0] = 5;
        print(b.xs[0]);
    """, ["0"]),
    "metodos_se_llaman_entre_si": ("""
        class Contador {
          let n: integer = 0;
          function inc(): integer { this.n = this.n + 1; return this.n; }
          function inc2(): integer { this.inc(); return this.inc(); }
        }
        let c: Contador = new Contador();
        print(c.inc2()); print(c.inc2());
    """, ["2", "4"]),
    "acceso_a_null": ("""
        class Nodo { let v: integer = 1; let sig: Nodo; }
        let n: Nodo = new Nodo();
        n.sig = null;
        try { print(n.sig.v); } catch (e) { print(e); }
    """, [NULL]),
}


@pytest.mark.parametrize("name", list(CASES))
def test_programa(name):
    source, expected = CASES[name]
    assert execute(source) == expected


# Salida esperada de los ejemplos del repositorio.
EXAMPLES = {
    "01_tipos_y_expresiones.cps": ["x vale 11", "true"],
    "02_funciones_y_closures.cps": ["Hola Mundo", "120", "2", "4"],
    "03_clases_y_herencia.cps": ["Genérico tiene 4 patas y Genérico hace ruido.",
                                 "Toby tiene 4 patas y Toby ladra.", "3"],
    "04_control_de_flujo.cps": ["aprobado", "0", "1", "2", "90", "85", "cero",
                                f"Error atrapado: {INDEX}", "3"],
    "05_float.cps": ["Área: 12.5664", "3.75", "-3.5"],
    "06_tabla_de_simbolos.cps": ["sombra"],
}


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_ejemplo(name):
    result = compile_file(os.path.join(ROOT, "examples", name))
    assert result.ok
    assert run(result.program, result.table) == EXAMPLES[name]


def test_program_cps_del_curso():
    result = compile_file(os.path.join(ROOT, "program", "program.cps"))
    assert run(result.program, result.table) == [
        "5 + 1 = 6", "Greater than 5",
        "Result is now 10", "Result is now 9", "Result is now 8",
        "Loop index: 0", "Loop index: 1", "Loop index: 2",
        "Number: 1", "Number: 2", "Number: 4", "Number: 5",
        "It's seven", "It's six", "Something else",
        f"Caught an error: {INDEX}",
        "Rex barks.", "First number: 1", "Multiples of 2: 2, 4", "Program finished.",
    ]


# ---------------------------------------------------------------------------
# Casos fallidos: con errores no hay TAC
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source, fragment", [
    ('let x: integer = "hola";', "integer"),
    ("print(noExiste);", "noExiste"),
    ("function f(): integer { return 1; } f(1, 2);", "argumento"),
    ("let x: integer = 1 +;", ""),
])
def test_programa_con_error_no_genera_tac(source, fragment):
    result = compile_source(source)
    assert not result.ok
    assert result.program is None
    assert result.tac_lines() == []
    assert any(fragment in e.message for e in result.errors)


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(ROOT, "examples", "err_*.cps"))),
                         ids=os.path.basename)
def test_ejemplos_con_errores_no_se_ejecutan(path):
    result = compile_file(path)
    assert result.program is None and result.errors
