"""Errores en tiempo de ejecución: lo que un `try/catch` puede capturar.

Compiscript no tiene `throw`; las únicas excepciones son errores que detecta
el código generado al ejecutar ciertas instrucciones. Este módulo es la fuente
única de esos errores para el intérprete de TAC y para la generación de MIPS
(cada mensaje irá como `.asciiz` en `.data`).

Modelo de manejo (ver docs/LENGUAJE_INTERMEDIO.md §7.11):
  * `push_handler L` apila el registro (L, fp, sp) del marco actual.
  * Una instrucción que falla busca el manejador más reciente: si no hay,
    el programa termina imprimiendo el mensaje; si hay, se desapila, se
    restauran fp y sp, y se salta a L con el mensaje como valor de `exception`.
  * `pop_handler` desapila el manejador al salir normalmente del try.
"""

from __future__ import annotations

from typing import Dict, List

from .tac import Op


class RuntimeErrorKind:
    INDEX_OUT_OF_BOUNDS = "index_out_of_bounds"
    NULL_REFERENCE = "null_reference"
    DIVISION_BY_ZERO = "division_by_zero"


MESSAGES: Dict[str, str] = {
    RuntimeErrorKind.INDEX_OUT_OF_BOUNDS: "índice fuera de rango",
    RuntimeErrorKind.NULL_REFERENCE: "acceso a una referencia null",
    RuntimeErrorKind.DIVISION_BY_ZERO: "división entre cero",
}

# Qué revisa cada instrucción antes de ejecutarse.
CHECKS: Dict[str, List[str]] = {
    Op.INDEX_GET: [RuntimeErrorKind.NULL_REFERENCE, RuntimeErrorKind.INDEX_OUT_OF_BOUNDS],
    Op.INDEX_SET: [RuntimeErrorKind.NULL_REFERENCE, RuntimeErrorKind.INDEX_OUT_OF_BOUNDS],
    Op.LEN: [RuntimeErrorKind.NULL_REFERENCE],
    Op.FIELD_GET: [RuntimeErrorKind.NULL_REFERENCE],
    Op.FIELD_SET: [RuntimeErrorKind.NULL_REFERENCE],
    Op.METHOD: [RuntimeErrorKind.NULL_REFERENCE],
    Op.DIV: [RuntimeErrorKind.DIVISION_BY_ZERO],
    Op.MOD: [RuntimeErrorKind.DIVISION_BY_ZERO],
}


class CompiscriptRuntimeError(Exception):
    """Excepción de Compiscript en ejecución; `str()` es el mensaje que recibe
    la variable del catch."""

    def __init__(self, kind: str):
        super().__init__(MESSAGES[kind])
        self.kind = kind


def checks_for(op: str) -> List[str]:
    """Errores que puede lanzar la instrucción `op` (vacío si ninguno)."""
    return list(CHECKS.get(op, []))
