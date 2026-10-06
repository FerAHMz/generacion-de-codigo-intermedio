"""Generación de código intermedio (segunda pasada del compilador).

    from compiscript.codegen import compile_source
    result = compile_source(src)
    result.errors     # errores sintácticos/semánticos (si hay, no hay TAC)
    result.program    # TACProgram o None
    result.to_dict()  # {"errors", "tac", "symbols"} — contrato de /api/compile
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..errors import CompilerError, ErrorCollector
from ..ir.tac import TACProgram
from ..semantic import AnalysisResult, analyze
from .base import CodeGenBase, CodegenError, JumpTargets
from .generator import TACGenerator


@dataclass
class CompileResult:
    analysis: AnalysisResult
    program: Optional[TACProgram]

    @property
    def ok(self) -> bool:
        return self.analysis.ok and self.program is not None

    @property
    def errors(self) -> List[CompilerError]:
        return list(self.analysis.errors)

    @property
    def table(self):
        return self.analysis.table

    def tac_lines(self) -> List[str]:
        return self.program.lines() if self.program is not None else []

    def to_dict(self) -> dict:
        return {
            "errors": [{"phase": e.phase, "line": e.line, "column": e.column, "message": e.message}
                       for e in self.errors],
            "tac": self.tac_lines(),
            "symbols": self.table.to_dict(),
        }


def compile_source(source: str, errors: Optional[ErrorCollector] = None) -> CompileResult:
    """Pasada 1 (análisis semántico) y, solo si no hubo errores, pasada 2 (TAC)."""
    analysis = analyze(source, errors)
    if not analysis.ok:
        return CompileResult(analysis, None)
    return CompileResult(analysis, TACGenerator(analysis).generate())


def compile_file(path: str, errors: Optional[ErrorCollector] = None) -> CompileResult:
    with open(path, encoding="utf-8") as fh:
        return compile_source(fh.read(), errors)


__all__ = ["CodeGenBase", "CodegenError", "CompileResult", "JumpTargets", "TACGenerator",
           "compile_file", "compile_source"]
