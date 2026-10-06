"""Asignación y reciclaje de temporales.

Algoritmo (free-list ordenada):

  * `new()` entrega el temporal libre de MENOR número; si no hay ninguno libre,
    crea uno nuevo (`t1`, `t2`, ...).
  * `release(*ops)` devuelve a la free-list los temporales que aparezcan en
    `ops` (los demás operandos se ignoran). El generador lo llama en cuanto
    el valor de un temporal se consumió como operando, y ANTES de pedir el
    temporal del resultado, de modo que `t1 = t1 + c` reutiliza el mismo nombre.
  * `reset()` se invoca al cerrar cada función: los temporales no cruzan
    fronteras de función.

Como siempre se reutiliza el menor libre, los nombres usados en una función
son exactamente t1..t{max_live}; por eso `max_live` es también la cantidad de
ranuras de temporales que necesita el registro de activación.

Ejemplo: `x = a + b + c + d`
    sin reciclaje            con reciclaje
    t1 = a + b               t1 = a + b
    t2 = t1 + c              t1 = t1 + c
    t3 = t2 + d              t1 = t1 + d
    x = t3                   x = t1          (max_live = 1)
"""

from __future__ import annotations

import heapq
from typing import List, Optional, Set

from ..types import Type
from .tac import Operand, Temp


class TempAllocator:

    def __init__(self, first: int = 1):
        self.first = first
        self.reset()

    def reset(self) -> None:
        self._next = self.first
        self._free: List[int] = []     # min-heap de índices libres
        self._live: Set[int] = set()
        self.max_live = 0
        self.allocations = 0           # pedidos totales a new() (para estadísticas)

    # ------------------------------------------------------------------ API

    def new(self, type: Optional[Type] = None) -> Temp:
        if self._free:
            idx = heapq.heappop(self._free)
        else:
            idx = self._next
            self._next += 1
        self._live.add(idx)
        self.allocations += 1
        self.max_live = max(self.max_live, len(self._live))
        return Temp(idx, type)

    def release(self, *operands: Operand) -> None:
        """Libera los temporales entre `operands`. Liberar dos veces el mismo
        temporal (p. ej. `t1 * t1`) o un operando que no es temporal no hace nada."""
        for op in operands:
            if isinstance(op, Temp) and op.index in self._live:
                self._live.remove(op.index)
                heapq.heappush(self._free, op.index)

    def is_live(self, t: Temp) -> bool:
        return t.index in self._live

    @property
    def live(self) -> int:
        return len(self._live)

    @property
    def distinct(self) -> int:
        """Cantidad de nombres distintos usados desde el último reset()."""
        return self._next - self.first
