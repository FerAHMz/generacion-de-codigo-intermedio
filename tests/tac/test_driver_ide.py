"""Integración del código intermedio con el Driver (CLI) y el IDE (Flask)."""

import os

import pytest

import Driver
from ide.app import app

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VALIDO = os.path.join(ROOT, "examples", "02_funciones_y_closures.cps")
CON_ERRORES = os.path.join(ROOT, "examples", "err_01_tipos.cps")

PROGRAMA = """
function fact(n: integer): integer { if (n <= 1) { return 1; } return n * fact(n - 1); }
class A { let x: integer = 1; function get(): integer { return this.x; } }
print(fact(5));
print(new A().get());
"""


# ---------------------------------------------------------------------------
# Driver.py
# ---------------------------------------------------------------------------

def test_driver_tac_numerado(capsys):
    assert Driver.main([VALIDO, "--tac", "--quiet"]) == 0
    out = capsys.readouterr().out
    assert " 1  func_begin main" in out
    assert "func_begin factorial" in out and "call factorial, 1" in out


def test_driver_out_guarda_el_tac(tmp_path, capsys):
    destino = tmp_path / "prog.tac"
    assert Driver.main([VALIDO, "--out", str(destino), "--quiet"]) == 0
    texto = destino.read_text(encoding="utf-8")
    assert texto.splitlines()[0].strip().endswith("func_begin main, 4")
    assert "func_end factorial" in texto
    assert str(destino) in capsys.readouterr().out


def test_driver_runtime_muestra_registros_de_activacion(capsys):
    assert Driver.main([VALIDO, "--runtime", "--quiet"]) == 0
    out = capsys.readouterr().out
    assert "Registro de activación factorial (nivel 1)" in out
    assert "static link -> crearContador" in out
    assert "dirección de retorno" in out


def test_driver_run_ejecuta_el_tac(capsys):
    assert Driver.main([VALIDO, "--run", "--quiet"]) == 0
    assert capsys.readouterr().out.split() == ["Hola", "Mundo", "120", "2", "4"]


def test_driver_con_error_semantico_no_imprime_tac(tmp_path, capsys):
    destino = tmp_path / "no.tac"
    assert Driver.main([CON_ERRORES, "--tac", "--out", str(destino), "--runtime", "--run"]) == 1
    out = capsys.readouterr().out
    assert "[Error semántico]" in out
    assert "func_begin" not in out and "Registro de activación" not in out
    assert "no se generó código intermedio" in out
    assert not destino.exists()


def test_driver_error_en_ejecucion_sale_con_1(tmp_path, capsys):
    fuente = tmp_path / "div.cps"
    fuente.write_text('print("a"); print(1 / 0);', encoding="utf-8")
    assert Driver.main([str(fuente), "--run", "--quiet"]) == 1
    assert "división entre cero" in capsys.readouterr().out


def test_driver_archivo_inexistente():
    assert Driver.main([os.path.join(ROOT, "no_existe.cps")]) == 2


# ---------------------------------------------------------------------------
# IDE: /api/compile y /api/run
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_compile_devuelve_tac_y_registros(client):
    data = client.post("/api/compile", json={"source": PROGRAMA}).get_json()
    assert data["ok"] is True and data["errors"] == []
    assert data["tac"][0].startswith("func_begin main")
    assert any("call fact, 1" in ln for ln in data["tac"])
    records = {ar["label"]: ar for ar in data["symbols"]["activation_records"]}
    assert records["main"]["header"] == []
    fact = records["fact"]
    assert [h["field"] for h in fact["header"]] == ["control_link", "return_address"]
    assert all(h["use"] for h in fact["header"])
    assert fact["frame_size"] > 0 and fact["slots"]
    clases = {c["name"]: c for c in data["symbols"]["classes"]}
    assert clases["A"]["vtable"][0]["label"] == "A_get"


def test_api_compile_con_errores_no_tiene_tac(client):
    data = client.post("/api/compile", json={"source": 'let x: integer = "a";'}).get_json()
    assert data["ok"] is False
    assert data["tac"] == []
    assert data["errors"][0]["phase"] == "semantic"
    assert data["errors"][0]["line"] == 1


def test_api_compile_error_sintactico(client):
    data = client.post("/api/compile", json={"source": "let x = ;"}).get_json()
    assert data["tac"] == [] and data["errors"][0]["phase"] == "syntax"


def test_api_analyze_sigue_igual(client):
    data = client.post("/api/analyze", json={"source": 'let x: integer = "a";'}).get_json()
    assert data["ok"] is False and len(data["errors"]) == 1
    assert "symbols" in data and "tree" in data


def test_api_run_ejecuta_el_programa(client):
    data = client.post("/api/run", json={"source": PROGRAMA}).get_json()
    assert data == {"ok": True, "errors": [], "output": ["120", "1"], "runtime_error": None}


def test_api_run_reporta_error_en_ejecucion(client):
    data = client.post("/api/run", json={"source": 'print("a"); let xs: integer[] = [1]; print(xs[4]);'}).get_json()
    assert data["output"] == ["a"]
    assert "índice fuera de rango" in data["runtime_error"]


def test_api_run_no_ejecuta_con_errores(client):
    data = client.post("/api/run", json={"source": "print(y);"}).get_json()
    assert data["ok"] is False and data["output"] == [] and data["errors"]


def test_api_run_bucle_infinito_no_bloquea(client):
    data = client.post("/api/run", json={"source": "while (true) { }"}).get_json()
    assert "límite" in data["runtime_error"]


def test_index_tiene_pestanas_de_tac_y_registros(client):
    html = client.get("/").get_data(as_text=True)
    assert 'data-tab="tac"' in html and 'data-tab="runtime"' in html and 'data-tab="output"' in html
