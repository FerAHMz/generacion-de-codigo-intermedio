"""Construcción del árbol sintáctico a partir de código fuente Compiscript."""

from dataclasses import dataclass
from typing import Optional

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from .errors import ErrorCollector
from .generated.CompiscriptLexer import CompiscriptLexer
from .generated.CompiscriptParser import CompiscriptParser


class CollectingErrorListener(ErrorListener):
    """Redirige los errores de ANTLR al ErrorCollector en vez de stderr."""

    def __init__(self, collector: ErrorCollector):
        super().__init__()
        self.collector = collector

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        self.collector.syntax(line, column, msg)


@dataclass
class ParseResult:
    tree: CompiscriptParser.ProgramContext
    parser: CompiscriptParser
    tokens: CommonTokenStream
    errors: ErrorCollector

    @property
    def ok(self) -> bool:
        return not self.errors.has_errors


def parse_source(source: str, errors: Optional[ErrorCollector] = None) -> ParseResult:
    """Tokeniza y parsea `source`. Nunca lanza: los errores quedan en `errors`."""
    errors = errors if errors is not None else ErrorCollector()
    listener = CollectingErrorListener(errors)

    lexer = CompiscriptLexer(InputStream(source))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)

    tokens = CommonTokenStream(lexer)
    parser = CompiscriptParser(tokens)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)

    tree = parser.program()
    return ParseResult(tree=tree, parser=parser, tokens=tokens, errors=errors)


def parse_file(path: str, errors: Optional[ErrorCollector] = None) -> ParseResult:
    with open(path, encoding="utf-8") as fh:
        return parse_source(fh.read(), errors)
