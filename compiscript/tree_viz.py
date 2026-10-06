"""Representaciones del árbol sintáctico: texto indentado, notación LISP,
estructura JSON (para el IDE) y Graphviz DOT (para exportar a imagen)."""

from __future__ import annotations

import shutil
import subprocess
from typing import Dict, List, Optional

from antlr4 import ParserRuleContext
from antlr4.tree.Tree import TerminalNode
from antlr4.tree.Trees import Trees

from .generated.CompiscriptParser import CompiscriptParser
from .types import Type


def _rule_name(node: ParserRuleContext) -> str:
    return CompiscriptParser.ruleNames[node.getRuleIndex()]


def _label(node) -> str:
    if isinstance(node, TerminalNode):
        text = node.getText()
        return "EOF" if text == "<EOF>" else text
    return _rule_name(node)


# ---------------------------------------------------------------------- texto

def tree_to_lisp(tree, parser: CompiscriptParser) -> str:
    """Notación (rule (child ...)) de ANTLR."""
    return Trees.toStringTree(tree, None, parser)


def tree_to_text(tree, indent: str = "  ") -> str:
    """Árbol indentado, una línea por nodo, con la posición de los tokens."""
    lines: List[str] = []

    def walk(node, depth: int):
        if isinstance(node, TerminalNode):
            tok = node.getSymbol()
            lines.append(f"{indent * depth}'{_label(node)}'  @{tok.line}:{tok.column}")
            return
        lines.append(f"{indent * depth}{_rule_name(node)}")
        for child in node.getChildren():
            walk(child, depth + 1)

    walk(tree, 0)
    return "\n".join(lines)


# ----------------------------------------------------------------------- JSON

def tree_to_dict(tree, node_types: Optional[Dict[ParserRuleContext, Type]] = None,
                 collapse: bool = True) -> dict:
    """Estructura anidada serializable. Con `collapse=True` se omiten las cadenas
    de reglas con un único hijo (expression -> assignmentExpr -> ...) para que
    el árbol dibujado sea legible; el nodo conserva el tipo calculado si existe."""
    node_types = node_types or {}

    def walk(node):
        if isinstance(node, TerminalNode):
            tok = node.getSymbol()
            return {"name": _label(node), "kind": "token", "line": tok.line, "column": tok.column}
        children = list(node.getChildren())
        t = node_types.get(node)
        if collapse and len(children) == 1 and not isinstance(children[0], TerminalNode):
            inner = walk(children[0])
            if t is not None and "type" not in inner:
                inner["type"] = str(t)
            return inner
        out = {"name": _rule_name(node), "kind": "rule",
               "line": node.start.line if node.start else 0,
               "children": [walk(c) for c in children]}
        if t is not None:
            out["type"] = str(t)
        return out

    return walk(tree)


# ------------------------------------------------------------------------ DOT

def tree_to_dot(tree, node_types: Optional[Dict[ParserRuleContext, Type]] = None,
                collapse: bool = True) -> str:
    data = tree_to_dict(tree, node_types, collapse)
    lines = ["digraph Compiscript {", "  node [fontname=\"Helvetica\", fontsize=10];",
             "  rankdir=TB;"]
    counter = [0]

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def walk(node) -> int:
        nid = counter[0]
        counter[0] += 1
        if node["kind"] == "token":
            lines.append(f'  n{nid} [label="{esc(node["name"])}", shape=box, style=filled, fillcolor="#e8f5e9"];')
        else:
            label = esc(node["name"]) + (f"\\n: {esc(node['type'])}" if node.get("type") else "")
            lines.append(f'  n{nid} [label="{label}", shape=ellipse];')
            for child in node.get("children", []):
                cid = walk(child)
                lines.append(f"  n{nid} -> n{cid};")
        return nid

    walk(data)
    lines.append("}")
    return "\n".join(lines)


def render_dot(dot_source: str, output_path: str, fmt: str = "svg") -> bool:
    """Genera una imagen con Graphviz si `dot` está instalado. Devuelve True si tuvo éxito."""
    exe = shutil.which("dot")
    if exe is None:
        return False
    subprocess.run([exe, f"-T{fmt}", "-o", output_path], input=dot_source.encode("utf-8"), check=True)
    return True
