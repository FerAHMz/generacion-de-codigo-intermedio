"""Modelo de errores compartido por las fases sintáctica y semántica."""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class CompilerError:
    """Un error detectado durante la compilación.

    `phase` es "syntax" o "semantic"; `line`/`column` apuntan al token que
    disparó el error (1-based para línea, 0-based para columna, como ANTLR).
    """

    phase: str
    line: int
    column: int
    message: str

    def __str__(self) -> str:
        tag = "Error sintáctico" if self.phase == "syntax" else "Error semántico"
        return f"[{tag}] línea {self.line}:{self.column} — {self.message}"


@dataclass
class ErrorCollector:
    """Acumula errores sin abortar el análisis, para reportarlos todos juntos."""

    errors: List[CompilerError] = field(default_factory=list)

    def add(self, phase: str, line: int, column: int, message: str) -> CompilerError:
        err = CompilerError(phase, line, column, message)
        self.errors.append(err)
        return err

    def syntax(self, line: int, column: int, message: str) -> CompilerError:
        return self.add("syntax", line, column, message)

    def semantic(self, line: int, column: int, message: str) -> CompilerError:
        return self.add("semantic", line, column, message)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def sorted(self) -> List[CompilerError]:
        return sorted(self.errors, key=lambda e: (e.line, e.column))

    def __iter__(self):
        return iter(self.sorted())

    def __len__(self) -> int:
        return len(self.errors)
