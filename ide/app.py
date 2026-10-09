"""Servidor del IDE de Compiscript.

    python3 -m ide.app            # http://localhost:8080 (variable PORT para cambiarlo)

Endpoints:
    GET  /                    interfaz del editor
    POST /api/analyze         {"source": "..."} -> errores, tabla de símbolos, árbol
    POST /api/compile         {"source": "..."} -> errores, TAC y registros de activación
    POST /api/run             {"source": "..."} -> salida del TAC ejecutado con el intérprete
    POST /api/tree.svg        {"source": "..."} -> imagen SVG del árbol (requiere Graphviz)
    GET  /api/examples        lista de programas de ejemplo
    GET  /api/examples/<name> contenido de un ejemplo
"""

from __future__ import annotations

import os

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from compiscript.codegen import compile_source
from compiscript.ir.interp import Interpreter, InterpreterError
from compiscript.semantic import analyze
from compiscript.tree_viz import render_dot, tree_to_dict, tree_to_dot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "ide", "static")
EXAMPLE_DIRS = [os.path.join(ROOT, "examples"), os.path.join(ROOT, "program")]
RUN_MAX_STEPS = 200_000   # evita que un bucle infinito bloquee el servidor

app = Flask(__name__, static_folder=STATIC, static_url_path="/static")


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.post("/api/analyze")
def api_analyze():
    payload = request.get_json(silent=True) or {}
    source = payload.get("source", "")
    result = analyze(source)
    return jsonify({
        "ok": result.ok,
        "errors": [
            {"phase": e.phase, "line": e.line, "column": e.column, "message": e.message}
            for e in result.errors
        ],
        "symbols": result.table.rows(),
        "scopes": [
            {"id": s.id, "kind": s.kind, "name": s.name, "path": s.path(),
             "parent": s.parent.id if s.parent else None, "symbols": len(s.symbols)}
            for s in result.table.scopes
        ],
        "tree": tree_to_dict(result.tree, result.node_types),
    })


@app.post("/api/compile")
def api_compile():
    """Contrato: `CompileResult.to_dict()` -> {"errors", "tac", "symbols"}.
    Con errores, `tac` queda vacío."""
    payload = request.get_json(silent=True) or {}
    result = compile_source(payload.get("source", ""))
    return jsonify({"ok": result.ok, **result.to_dict()})


@app.post("/api/run")
def api_run():
    """Compila y ejecuta el TAC con el intérprete (`compiscript/ir/interp.py`)."""
    payload = request.get_json(silent=True) or {}
    result = compile_source(payload.get("source", ""))
    body = {"ok": result.ok, "errors": result.to_dict()["errors"], "output": [], "runtime_error": None}
    if result.ok:
        interp = Interpreter(result.program, result.table, max_steps=RUN_MAX_STEPS)
        try:
            body["output"] = interp.run()
        except InterpreterError as exc:
            body["output"] = interp.output
            body["runtime_error"] = str(exc)
        if interp.error is not None:
            # el intérprete deja el mensaje como última línea; el IDE lo resalta aparte
            body["output"], body["runtime_error"] = interp.output[:-1], interp.output[-1]
    return jsonify(body)


@app.post("/api/tree.svg")
def api_tree_svg():
    payload = request.get_json(silent=True) or {}
    result = analyze(payload.get("source", ""))
    dot = tree_to_dot(result.tree, result.node_types)
    tmp = os.path.join(ROOT, "out")
    os.makedirs(tmp, exist_ok=True)
    path = os.path.join(tmp, "tree.svg")
    if not render_dot(dot, path):
        return jsonify({"error": "Graphviz (dot) no está instalado en el servidor"}), 501
    with open(path, encoding="utf-8") as fh:
        return Response(fh.read(), mimetype="image/svg+xml")


def _examples() -> dict:
    found = {}
    for d in EXAMPLE_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".cps") and name not in found:
                found[name] = os.path.join(d, name)
    return found


@app.get("/api/examples")
def api_examples():
    return jsonify(sorted(_examples().keys()))


@app.get("/api/examples/<name>")
def api_example(name: str):
    path = _examples().get(name)
    if path is None:
        abort(404)
    with open(path, encoding="utf-8") as fh:
        return Response(fh.read(), mimetype="text/plain; charset=utf-8")


def main():
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")


if __name__ == "__main__":
    main()
