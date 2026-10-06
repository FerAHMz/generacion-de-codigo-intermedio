"""Servidor del IDE de Compiscript.

    python3 -m ide.app            # http://localhost:8080 (variable PORT para cambiarlo)

Endpoints:
    GET  /                    interfaz del editor
    POST /api/analyze         {"source": "..."} -> errores, tabla de símbolos, árbol
    POST /api/tree.svg        {"source": "..."} -> imagen SVG del árbol (requiere Graphviz)
    GET  /api/examples        lista de programas de ejemplo
    GET  /api/examples/<name> contenido de un ejemplo
"""

from __future__ import annotations

import os

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from compiscript.semantic import analyze
from compiscript.tree_viz import render_dot, tree_to_dict, tree_to_dot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "ide", "static")
EXAMPLE_DIRS = [os.path.join(ROOT, "examples"), os.path.join(ROOT, "program")]

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
