"""Representación intermedia (TAC en cuádruplos) y utilidades asociadas."""

from .tac import Const, Field, Label, Op, Operand, Quad, TACProgram, Temp, Var
from .temps import TempAllocator

__all__ = ["Const", "Field", "Label", "Op", "Operand", "Quad", "TACProgram",
           "Temp", "TempAllocator", "Var"]
