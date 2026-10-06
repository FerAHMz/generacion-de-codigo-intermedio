"""Tabla de símbolos para la generación de código: tamaños, direcciones,
registros de activación (frame_size, static link) y layout de clases."""

import json

from compiscript.semantic import analyze
from compiscript.symbols import HEADER_SIZE, TEMP_SLOT, Storage, sizeof
from compiscript.types import ArrayType, BOOLEAN, FLOAT, INTEGER, STRING


def table_of(src):
    r = analyze(src)
    assert r.ok, list(r.errors)
    return r.table


def sym(table, name, scope_suffix=""):
    for s in table.scopes:
        if s.path().endswith(scope_suffix) and name in s.symbols:
            return s.symbols[name]
    raise KeyError(name)


def test_tamanos_por_tipo():
    assert sizeof(INTEGER) == 4
    assert sizeof(FLOAT) == 8
    assert sizeof(BOOLEAN) == 1
    assert sizeof(STRING) == 4                 # referencia
    assert sizeof(ArrayType(FLOAT)) == 4       # referencia


def test_globales_con_alineacion():
    t = table_of("let a: integer = 1; let b: boolean = true; let c: float = 2.0; let d: integer = 3;")
    assert [sym(t, n).address for n in "abcd"] == ["global[0]", "global[4]", "global[8]", "global[16]"]
    assert t.globals_size == 20


def test_variables_de_bloques_de_nivel_superior_son_globales():
    t = table_of("let a: integer = 1; { let b: integer = 2; } while (false) { let c: integer = 3; }")
    assert [sym(t, n).storage for n in "abc"] == [Storage.GLOBAL] * 3


def test_parametros_positivos_y_locales_negativos():
    t = table_of("""
    function f(a: integer, b: float, c: boolean): integer {
        let x: integer = 1;
        if (c) { let y: float = b; }
        while (false) { let z: integer = 2; }
        return x;
    }""")
    assert [sym(t, n, "f").address for n in "abc"] == ["fp[+12]", "fp[+16]", "fp[+24]"]
    assert sym(t, "x", "f").address == "fp[-4]"
    assert sym(t, "y").address == "fp[-16]"   # bloque anidado aplanado, alineado a 8
    assert sym(t, "z").address == "fp[-20]"
    ar = sym(t, "f").activation
    assert [p.name for p in ar.params] == ["a", "b", "c"]
    assert [l.name for l in ar.locals] == ["x", "y", "z"]
    assert ar.params_size == 13 and ar.locals_size == 20


def test_frame_size_incluye_encabezado_parametros_locales_y_temporales():
    t = table_of("function f(a: integer): integer { let x: integer = a; return x; }")
    ar = sym(t, "f").activation
    assert ar.frame_size == HEADER_SIZE + 4 + 8      # locales alineados a TEMP_SLOT
    ar.set_temps(3)
    assert ar.frame_size == HEADER_SIZE + 4 + 8 + 3 * TEMP_SLOT
    assert ar.temp_address(1) == "fp[-16]"
    assert ar.temp_address(3) == "fp[-32]"


def test_registro_main_y_etiquetas():
    t = table_of("function f() {} function g() { function h() {} }")
    labels = [ar.label for ar in t.activation_records]
    assert labels == ["main", "f", "g", "g_h"]
    assert t.main.level == 0 and t.main.frame_size == HEADER_SIZE


def test_etiquetas_unicas_si_chocan():
    t = table_of("function main() {} function f() { function g() {} } function f_g() {}")
    labels = {ar.label for ar in t.activation_records}
    assert {"main", "main_2", "f_g", "f_g_2"} <= labels


def test_static_link_y_hops_para_closures():
    t = table_of("""
    function externa(n: integer): integer {
        let acc: integer = 0;
        function media(): integer {
            function interna(): integer { return acc + n; }
            return interna();
        }
        return media();
    }""")
    ext, med, inn = (sym(t, n).activation for n in ("externa", "media", "interna"))
    assert (ext.level, med.level, inn.level) == (1, 2, 3)
    assert inn.parent is med and med.parent is ext and ext.parent is t.main
    acc = sym(t, "acc", "externa")
    assert t.hops(acc, inn) == 2
    assert t.hops(acc, ext) == 0
    g = table_of("let g: integer = 1; function f(): integer { return g; }")
    assert g.hops(sym(g, "g"), sym(g, "f").activation) == 0


def test_metodos_reciben_this_como_parametro_0():
    t = table_of("""
    class A { let v: integer;
      function constructor(x: integer) { this.v = x; }
      function get(): integer { return this.v; } }""")
    ctor = sym(t, "constructor", "A").activation
    assert ctor.label == "A_constructor"
    assert ctor.this is not None and ctor.params[0] is ctor.this
    assert ctor.this.address == "fp[+12]"
    assert sym(t, "x", "constructor").address == "fp[+16]"


def test_layout_con_herencia_atributos_heredados_primero():
    t = table_of("""
    class Animal { let nombre: string; let edad: integer;
      function hablar(): string { return "..."; }
      function info(): string { return this.nombre; } }
    class Perro : Animal { let peso: float;
      function hablar(): string { return "guau"; }
      function correr() {} }""")
    a, p = t.class_layouts["Animal"], t.class_layouts["Perro"]
    assert a.object_size == 12
    assert a.field_offset("nombre") == 4 and a.field_offset("edad") == 8
    assert p.field_offset("nombre") == 4 and p.field_offset("edad") == 8
    assert p.field_offset("peso") == 16                  # alineado a 8
    assert p.object_size == 24
    assert sym(t, "peso").address == "this[+16]"
    # Sobreescritura en la misma ranura; métodos nuevos al final.
    assert a.vtable == [("hablar", "Animal_hablar"), ("info", "Animal_info")]
    assert p.vtable == [("hablar", "Perro_hablar"), ("info", "Animal_info"), ("correr", "Perro_correr")]
    assert p.method_slot("hablar") == a.method_slot("hablar") == 0
    assert sym(t, "Perro").object_size == 24


def test_constructor_heredado():
    t = table_of("""
    class A { let v: integer; function constructor(x: integer) { this.v = x; } }
    class B : A { }""")
    assert t.class_layouts["B"].constructor_label == "A_constructor"


def test_volcado_json_y_texto():
    t = table_of("let g: integer = 1; class A { let v: integer; } function f(x: integer) {}")
    data = json.loads(t.to_json())
    assert set(data) == {"symbols", "globals_size", "activation_records", "classes"}
    assert data["activation_records"][1]["label"] == "f"
    assert data["classes"][0]["fields"][0] == {"name": "v", "offset": 4, "size": 4, "declared_in": "A"}
    texto = t.format_runtime()
    assert "Registro de activación f" in texto and "frame_size" in texto
    assert "Clase A  object_size = 8" in texto
    assert "address" in str(t)


def test_programa_con_errores_no_rompe_la_asignacion():
    r = analyze("let x: integer = \"a\"; function f(): Desconocida { return 1; }")
    assert not r.ok
    r.table.allocate_storage()          # idempotente y tolerante a ERROR
    assert r.table.to_dict()["activation_records"][0]["label"] == "main"
