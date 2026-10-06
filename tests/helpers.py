"""Utilidades compartidas por la batería de tests semánticos."""

from typing import List

from compiscript.semantic import analyze


def errors_of(source: str) -> List[str]:
    """Analiza `source` y devuelve los mensajes de error (sintácticos y semánticos)."""
    return [e.message for e in analyze(source).errors]


def assert_ok(source: str) -> None:
    errs = errors_of(source)
    assert errs == [], f"se esperaba un programa válido pero se reportó: {errs}"


def assert_error(source: str, *fragments: str) -> List[str]:
    """Falla si el programa NO produce al menos un error que contenga cada fragmento."""
    errs = errors_of(source)
    assert errs, "se esperaba al menos un error semántico y no se reportó ninguno"
    for frag in fragments:
        assert any(frag in e for e in errs), f"ningún error contiene '{frag}': {errs}"
    return errs
