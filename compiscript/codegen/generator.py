"""Ensambla el generador de TAC a partir de los mixins de generación.

Pendiente (Felipe Aguilar, ver docs/PLAN_TRABAJO.md): agregar los mixins
`ExpressionsGen`, `ControlFlowGen`, `FunctionsGen` y `ClassesGen` delante de
`CodeGenBase`, igual que `SemanticAnalyzer` combina los mixins semánticos:

    class TACGenerator(ClassesGen, ControlFlowGen, FunctionsGen, ExpressionsGen, CodeGenBase):
        ...
"""

from __future__ import annotations

from .base import CodeGenBase


class TACGenerator(CodeGenBase):
    """Visitor que traduce un programa Compiscript ya validado a TAC."""
