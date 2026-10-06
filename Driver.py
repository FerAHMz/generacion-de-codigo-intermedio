"""Punto de entrada por línea de comandos.

    python3 Driver.py program.cps                 # parsea + analiza, reporta errores
    python3 Driver.py program.cps --symbols       # además imprime la tabla de símbolos
    python3 Driver.py program.cps --tree          # imprime el árbol sintáctico indentado
    python3 Driver.py program.cps --lisp          # árbol en notación (rule ...) de ANTLR
    python3 Driver.py program.cps --dot out.dot   # exporta el árbol a Graphviz (y SVG si hay `dot`)

Código de salida: 0 sin errores, 1 con errores, 2 uso incorrecto.
"""

import argparse
import sys

from compiscript.semantic import analyze_file
from compiscript.tree_viz import render_dot, tree_to_dot, tree_to_lisp, tree_to_text


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="Driver.py", description="Analizador semántico de Compiscript")
    ap.add_argument("file", help="archivo fuente .cps")
    ap.add_argument("--symbols", action="store_true", help="imprime la tabla de símbolos")
    ap.add_argument("--tree", action="store_true", help="imprime el árbol sintáctico indentado")
    ap.add_argument("--lisp", action="store_true", help="imprime el árbol en notación LISP de ANTLR")
    ap.add_argument("--dot", metavar="ARCHIVO", help="exporta el árbol a un archivo Graphviz .dot")
    ap.add_argument("--quiet", action="store_true", help="no imprime el resumen final")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = analyze_file(args.file)
    except OSError as exc:
        print(f"No se pudo leer '{args.file}': {exc}")
        return 2

    if args.tree:
        print(tree_to_text(result.tree))
    if args.lisp:
        print(tree_to_lisp(result.tree, result.parse.parser))
    if args.dot:
        dot = tree_to_dot(result.tree, result.node_types)
        with open(args.dot, "w", encoding="utf-8") as fh:
            fh.write(dot)
        svg = args.dot.rsplit(".", 1)[0] + ".svg"
        if render_dot(dot, svg):
            print(f"Árbol exportado a {args.dot} y {svg}")
        else:
            print(f"Árbol exportado a {args.dot} (instale Graphviz para generar la imagen)")
    if args.symbols:
        print(result.table)
        print()

    for err in result.errors:
        print(err)

    if not args.quiet:
        n = len(result.errors)
        print("✔ Sin errores" if n == 0 else f"✘ {n} error(es) encontrado(s)")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
