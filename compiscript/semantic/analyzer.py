"""Ensambla los mixins en el analizador semántico y expone `analyze()`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from antlr4 import ParserRuleContext

from ..errors import ErrorCollector
from ..parsing import ParseResult, parse_file, parse_source
from ..symbols import Scope, Symbol, SymbolTable
from ..types import Type
from .base import BaseAnalyzer
from .classes import ClassesMixin
from .control_flow import ControlFlowMixin
from .declarations import DeclarationsMixin
from .expressions import ExpressionsMixin
from .functions import FunctionsMixin


class SemanticAnalyzer(ClassesMixin, ControlFlowMixin, FunctionsMixin, DeclarationsMixin, ExpressionsMixin, BaseAnalyzer):
    """Visitor que aplica todas las reglas semánticas de Compiscript."""


@dataclass
class AnalysisResult:
    parse: ParseResult
    table: SymbolTable
    errors: ErrorCollector
    node_types: Dict[ParserRuleContext, Type]
    # Anotaciones para la segunda pasada (generación de código intermedio).
    node_symbols: Dict[object, Symbol] = field(default_factory=dict)
    node_scopes: Dict[ParserRuleContext, Scope] = field(default_factory=dict)

    @property
    def tree(self):
        return self.parse.tree

    @property
    def ok(self) -> bool:
        return not self.errors.has_errors


def analyze(source: str, errors: Optional[ErrorCollector] = None) -> AnalysisResult:
    """Parsea y analiza semánticamente `source`. Si hay errores sintácticos, no
    se ejecuta la fase semántica (el árbol estaría incompleto)."""
    errors = errors if errors is not None else ErrorCollector()
    parsed = parse_source(source, errors)
    analyzer = SemanticAnalyzer(errors)
    if parsed.ok:
        analyzer.visit(parsed.tree)
    return AnalysisResult(parsed, analyzer.table, errors, analyzer.node_types,
                          analyzer.node_symbols, analyzer.node_scopes)


def analyze_file(path: str, errors: Optional[ErrorCollector] = None) -> AnalysisResult:
    with open(path, encoding="utf-8") as fh:
        return analyze(fh.read(), errors)
