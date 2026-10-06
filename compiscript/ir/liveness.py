"""Análisis de vida de temporales y asignación por *linear scan*.

Implementa el modelo de M. Poletto y V. Sarkar, "Linear Scan Register
Allocation", ACM TOPLAS 21(5), 1999 (MIT Laboratory for Computer Science /
IBM), sobre el TAC de cada función:

1. **Vida (liveness)**: análisis de flujo de datos hacia atrás sobre el grafo
   de flujo a nivel de instrucción (`goto`, saltos condicionales,
   `push_handler` -> manejador, `return`). Solo se analizan temporales: las
   variables del programa viven en memoria (global / marco / objeto).
2. **Valores (webs)**: el generador recicla nombres (`t1` puede contener
   valores sin relación entre sí). Con definiciones que alcanzan
   (*reaching definitions*) se agrupan las definiciones que llegan a un mismo
   uso; cada grupo es un valor con su propio intervalo de vida
   `[primera, última]` posición en la que está vivo, en orden lineal.
3. **Linear scan**: se recorren los intervalos por inicio; los que ya
   terminaron liberan su registro; si no hay registro libre se derrama
   (*spill*) el intervalo que termina más tarde. Hay dos clases de registros
   (enteros y flotantes) que se asignan por separado.

Usos:
  * `allocate_registers(program)` -> `RegisterAllocation`: ubicación (registro
    MIPS o ranura de spill) de cada aparición de cada temporal. Es la base de
    `getReg()` en la generación de MIPS.
  * `compact_temps(program)` -> TAC con los temporales renombrados con el
    mínimo de nombres que permite la vida real de los valores (registros
    ilimitados). Sirve para verificar el reciclaje hecho al generar.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .tac import Label, Op, Quad, TACProgram, Temp

# Registros MIPS disponibles para temporales. Se reservan $at, $v0-$v1
# (retorno/syscalls), $a0-$a3 (argumentos), $k0-$k1, $gp, $sp, $fp, $ra;
# $f0 (retorno float) y $f12-$f14 (argumentos float).
INT_REGISTERS: Tuple[str, ...] = tuple(f"$t{i}" for i in range(10)) + tuple(f"$s{i}" for i in range(8))
FLOAT_REGISTERS: Tuple[str, ...] = tuple(f"$f{i}" for i in (*range(4, 12), *range(16, 32)))

USE, DEF = "use", "def"

_NO_DEF = {Op.LABEL, Op.GOTO, Op.IF, Op.IF_FALSE, Op.PARAM, Op.RETURN, Op.FUNC_BEGIN,
           Op.FUNC_END, Op.PRINT, Op.INDEX_SET, Op.FIELD_SET, Op.PUSH_HANDLER, Op.POP_HANDLER}


# ---------------------------------------------------------------------------
# Usos y definiciones
# ---------------------------------------------------------------------------

def defined_temp(q: Quad) -> Optional[Temp]:
    """Temporal que escribe la instrucción, si lo hay."""
    if q.op in _NO_DEF or Op.relop_of(q.op) is not None:
        return None
    return q.result if isinstance(q.result, Temp) else None


def used_temps(q: Quad) -> List[Temp]:
    """Temporales que lee la instrucción (en `a[i] = x` y `[obj + off] = x`
    el `result` es la base, que también se lee)."""
    ops = [q.arg1, q.arg2]
    if q.op in (Op.INDEX_SET, Op.FIELD_SET):
        ops.append(q.result)
    return [o for o in ops if isinstance(o, Temp)]


# ---------------------------------------------------------------------------
# Funciones y grafo de flujo
# ---------------------------------------------------------------------------

def function_ranges(program: TACProgram) -> List[Tuple[str, int, int]]:
    """(etiqueta, índice de func_begin, índice de func_end) de cada función."""
    out, start, name = [], None, None
    for i, q in enumerate(program):
        if q.op == Op.FUNC_BEGIN:
            start, name = i, str(q.arg1)
        elif q.op == Op.FUNC_END and start is not None:
            out.append((name, start, i))
            start = None
    return out


def _successors(quads: Sequence[Quad], lo: int, hi: int) -> Dict[int, List[int]]:
    labels = {q.result.name: i for i, q in enumerate(quads[lo:hi + 1], start=lo)
              if q.is_label and isinstance(q.result, Label)}
    succ: Dict[int, List[int]] = {}
    for i in range(lo, hi + 1):
        q = quads[i]
        nxt = [i + 1] if i < hi else []
        tgt = labels.get(q.result.name) if isinstance(q.result, Label) and Op.is_jump(q.op) else None
        if q.op == Op.GOTO:
            succ[i] = [tgt] if tgt is not None else []
        elif q.op in (Op.RETURN, Op.FUNC_END):
            succ[i] = []
        elif Op.is_jump(q.op):   # condicionales y push_handler: destino + siguiente
            succ[i] = nxt + ([tgt] if tgt is not None else [])
        else:
            succ[i] = nxt
    return succ


@dataclass
class Liveness:
    live_in: Dict[int, Set[int]]     # índice de instrucción -> temporales vivos antes
    live_out: Dict[int, Set[int]]    # ... vivos después


def liveness(program: TACProgram, lo: int, hi: int) -> Liveness:
    """Vida de temporales (por índice) en las instrucciones lo..hi."""
    quads = program.quads
    succ = _successors(quads, lo, hi)
    use = {i: {t.index for t in used_temps(quads[i])} for i in range(lo, hi + 1)}
    dfn = {i: ({d.index} if (d := defined_temp(quads[i])) else set()) for i in range(lo, hi + 1)}
    live_in = {i: set() for i in range(lo, hi + 1)}
    live_out = {i: set() for i in range(lo, hi + 1)}
    changed = True
    while changed:
        changed = False
        for i in range(hi, lo - 1, -1):
            out = set().union(*(live_in[s] for s in succ[i])) if succ[i] else set()
            inn = use[i] | (out - dfn[i])
            if out != live_out[i] or inn != live_in[i]:
                live_out[i], live_in[i] = out, inn
                changed = True
    return Liveness(live_in, live_out)


def _reaching(program: TACProgram, lo: int, hi: int) -> Dict[int, Dict[int, Set[int]]]:
    """Definiciones que alcanzan cada instrucción: idx -> {temp: {posiciones}}."""
    quads = program.quads
    succ = _successors(quads, lo, hi)
    preds: Dict[int, List[int]] = {i: [] for i in range(lo, hi + 1)}
    for i, ss in succ.items():
        for s in ss:
            preds[s].append(i)
    r_in: Dict[int, Dict[int, Set[int]]] = {i: {} for i in range(lo, hi + 1)}
    r_out: Dict[int, Dict[int, Set[int]]] = {i: {} for i in range(lo, hi + 1)}
    changed = True
    while changed:
        changed = False
        for i in range(lo, hi + 1):
            inn: Dict[int, Set[int]] = {}
            for p in preds[i]:
                for t, ds in r_out[p].items():
                    inn.setdefault(t, set()).update(ds)
            out = {t: set(ds) for t, ds in inn.items()}
            d = defined_temp(quads[i])
            if d is not None:
                out[d.index] = {i}
            if inn != r_in[i] or out != r_out[i]:
                r_in[i], r_out[i] = inn, out
                changed = True
    return r_in


# ---------------------------------------------------------------------------
# Intervalos de vida
# ---------------------------------------------------------------------------

@dataclass
class LiveInterval:
    """Un valor (web) de un temporal y el tramo lineal en el que está vivo."""

    function: str
    name: int                       # índice del temporal en el TAC original
    start: int
    end: int
    is_float: bool = False
    crosses_call: bool = False      # vivo durante un `call`: en MIPS conviene $s (callee-saved)
    location: Optional[str] = None  # registro asignado, o None si está derramado
    spill_slot: Optional[int] = None
    occurrences: List[int] = field(default_factory=list)

    @property
    def spilled(self) -> bool:
        return self.location is None


class _UnionFind:
    def __init__(self):
        self.parent: Dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, items: Iterable[int]) -> None:
        items = list(items)
        for other in items[1:]:
            self.parent[self.find(other)] = self.find(items[0])


def live_intervals(program: TACProgram, lo: int, hi: int, function: str = ""
                   ) -> Tuple[List[LiveInterval], Dict[Tuple[int, int, str], LiveInterval]]:
    """Intervalos de vida de los valores de temporales en lo..hi.

    Devuelve la lista de intervalos y un mapa (posición, índice de temporal,
    "use" | "def") -> intervalo para cada aparición de un temporal. El rol es
    necesario: en `t1 = t1 + c` el t1 leído y el escrito son valores distintos."""
    quads = program.quads
    live = liveness(program, lo, hi)
    reach = _reaching(program, lo, hi)
    uf = _UnionFind()

    # 1) agrupar definiciones que llegan a una misma posición en la que el temporal está vivo.
    for i in range(lo, hi + 1):
        d = defined_temp(quads[i])
        if d is not None:
            uf.find(i)
        for t in live.live_in[i]:
            defs = reach[i].get(t, set())
            if defs:
                uf.union(defs)

    # 2) posiciones de cada valor.
    spans: Dict[int, List[int]] = {}
    names: Dict[int, int] = {}
    floats: Dict[int, bool] = {}
    occ: Dict[Tuple[int, int, str], int] = {}

    def touch(root: int, pos: int, temp: int, is_float: bool = False) -> None:
        spans.setdefault(root, []).append(pos)
        names[root] = temp
        floats[root] = floats.get(root, False) or is_float

    for i in range(lo, hi + 1):
        q = quads[i]
        for t in live.live_in[i]:
            defs = reach[i].get(t, set())
            if defs:
                touch(uf.find(next(iter(defs))), i, t)
        for u in used_temps(q):
            defs = reach[i].get(u.index, set())
            if defs:
                root = uf.find(next(iter(defs)))
                touch(root, i, u.index, u.is_float)
                occ[(i, u.index, USE)] = root
        d = defined_temp(q)
        if d is not None:
            root = uf.find(i)
            touch(root, i, d.index, d.is_float)
            occ[(i, d.index, DEF)] = root

    calls = [i for i in range(lo, hi + 1) if quads[i].op == Op.CALL]
    by_root: Dict[int, LiveInterval] = {}
    for root, positions in spans.items():
        start, end = min(positions), max(positions)
        by_root[root] = LiveInterval(function, names[root], start, end, floats[root],
                                     any(start < c < end for c in calls))
    for key, root in occ.items():
        by_root[root].occurrences.append(key[0])
    intervals = sorted(by_root.values(), key=lambda iv: (iv.start, iv.end))
    return intervals, {key: by_root[root] for key, root in occ.items()}


# ---------------------------------------------------------------------------
# Linear scan
# ---------------------------------------------------------------------------

def linear_scan(intervals: List[LiveInterval], registers: Sequence[str]) -> int:
    """Asigna `registers` a `intervals` (ya ordenados por inicio) con el
    algoritmo de Poletto y Sarkar. Los derramados reciben `spill_slot`.
    Devuelve la cantidad de ranuras de spill usadas.

    Dos intervalos que solo se tocan en un extremo (`t1` se usa por última vez
    en la instrucción que define `t2`) pueden compartir registro, como en
    `add $t0, $t0, $t1`."""
    order = {r: k for k, r in enumerate(registers)}
    free = list(range(len(registers)))  # min-heap: se usa siempre el registro libre de menor índice
    active: List[LiveInterval] = []     # ordenados por fin
    spills = 0
    for iv in intervals:
        for old in list(active):        # expirar los que terminaron
            if old.end > iv.start:
                break
            active.remove(old)
            heapq.heappush(free, order[old.location])
        if free:
            iv.location = registers[heapq.heappop(free)]
            active.append(iv)
        else:
            victim = active[-1]
            if victim.end > iv.end:     # derramar el que termina más tarde
                iv.location, victim.location = victim.location, None
                victim.spill_slot, spills = spills, spills + 1
                active.remove(victim)
                active.append(iv)
            else:
                iv.spill_slot, spills = spills, spills + 1
        active.sort(key=lambda x: x.end)
    return spills


@dataclass
class FunctionAllocation:
    function: str
    intervals: List[LiveInterval]
    spill_slots: int
    occurrences: Dict[Tuple[int, int, str], LiveInterval]

    @property
    def max_pressure(self) -> int:
        """Máximo de valores vivos a la vez (cota inferior de registros sin spill)."""
        events = sorted([(iv.start, 1) for iv in self.intervals] +
                        [(iv.end, -1) for iv in self.intervals], key=lambda e: (e[0], e[1]))
        cur = best = 0
        for _, delta in events:
            cur += delta
            best = max(best, cur)
        return best

    def registers_used(self) -> Set[str]:
        return {iv.location for iv in self.intervals if iv.location}


@dataclass
class RegisterAllocation:
    functions: Dict[str, FunctionAllocation]

    def location(self, position: int, temp: Temp, role: str = USE) -> LiveInterval:
        """Intervalo (con su registro o ranura de spill) de la aparición de
        `temp` en la instrucción `position` del programa; `role` es "use" para
        los operandos leídos y "def" para el resultado escrito."""
        for fa in self.functions.values():
            iv = fa.occurrences.get((position, temp.index, role))
            if iv is not None:
                return iv
        raise KeyError(f"t{temp.index} ({role}) no aparece en la instrucción {position}")


def allocate_registers(program: TACProgram, int_registers: Sequence[str] = INT_REGISTERS,
                       float_registers: Sequence[str] = FLOAT_REGISTERS) -> RegisterAllocation:
    """Linear scan por función, con clases de registro entero y flotante."""
    out: Dict[str, FunctionAllocation] = {}
    for name, lo, hi in function_ranges(program):
        intervals, occ = live_intervals(program, lo, hi, name)
        ints = [iv for iv in intervals if not iv.is_float]
        flts = [iv for iv in intervals if iv.is_float]
        spills = linear_scan(ints, int_registers)
        fspills = linear_scan(flts, float_registers)
        for iv in flts:
            if iv.spill_slot is not None:
                iv.spill_slot += spills
        out[name] = FunctionAllocation(name, intervals, spills + fspills, occ)
    return RegisterAllocation(out)


def compact_temps(program: TACProgram) -> TACProgram:
    """Renombra los temporales de cada función con el mínimo de nombres que
    permite la vida real de sus valores (linear scan con registros ilimitados).
    El programa resultante es equivalente al original."""
    quads = [Quad(q.op, q.arg1, q.arg2, q.result, q.comment) for q in program]
    for name, lo, hi in function_ranges(program):
        intervals, occ = live_intervals(program, lo, hi, name)
        linear_scan(intervals, [str(i) for i in range(1, len(intervals) + 1)])
        for (pos, idx, role), iv in occ.items():
            q = quads[pos]
            new_idx = int(iv.location)
            if role == DEF:
                attrs = ("result",)
            else:
                attrs = ("arg1", "arg2") + (("result",) if q.op in (Op.INDEX_SET, Op.FIELD_SET) else ())
            for attr in attrs:
                val = getattr(program.quads[pos], attr)
                if isinstance(val, Temp) and val.index == idx:
                    setattr(q, attr, Temp(new_idx, val.type))
    return TACProgram(quads)
