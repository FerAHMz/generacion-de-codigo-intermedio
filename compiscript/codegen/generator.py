"""Generador TAC de Compiscript. Implementación: Felipe Aguilar."""

from __future__ import annotations

from .base import CodeGenBase
from .classes import ClassesGen
from .control_flow import ControlFlowGen
from .expressions import ExpressionsGen
from .functions import FunctionsGen


class TACGenerator(ClassesGen, ControlFlowGen, FunctionsGen, ExpressionsGen, CodeGenBase):
    """Visitor que traduce un programa Compiscript ya validado a TAC."""
