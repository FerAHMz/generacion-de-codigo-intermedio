"""Los programas de `examples/` sirven de demostración y de prueba de integración:
los `NN_*.cps` deben ser válidos y los `err_*.cps` deben producir errores en
cada línea marcada con un comentario."""

import glob
import os
import re

import pytest

from compiscript.codegen import compile_file, compile_source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = sorted(glob.glob(os.path.join(ROOT, "examples", "*.cps")))
VALID = [p for p in EXAMPLES if not os.path.basename(p).startswith("err_")]
INVALID = [p for p in EXAMPLES if os.path.basename(p).startswith("err_")]


@pytest.mark.parametrize("path", VALID, ids=os.path.basename)
def test_ejemplo_valido(path):
    result = compile_file(path)
    assert [str(e) for e in result.errors] == []
    assert result.ok
    assert result.program.check() == []


@pytest.mark.parametrize("path", INVALID, ids=os.path.basename)
def test_ejemplo_con_errores(path):
    result = compile_file(path)
    assert not result.ok
    assert result.program is None
    error_lines = {e.line for e in result.errors}
    with open(path, encoding="utf-8") as fh:
        for number, text in enumerate(fh, start=1):
            code = text.split("//")[0].strip()
            if code and re.search(r"//\s*\S", text) and not text.lstrip().startswith("//"):
                # Línea con código y comentario explicativo => debe tener error.
                assert number in error_lines, f"línea {number} de {os.path.basename(path)} sin error: {text.strip()}"


def test_documentacion_tac_coincide_con_el_compilador():
    path = os.path.join(ROOT, "docs", "LENGUAJE_INTERMEDIO.md")
    with open(path, encoding="utf-8") as fh:
        document = fh.read()
    pairs = re.findall(r"```cps\n(.*?)\n```\s+```tac\n(.*?)\n```", document, re.DOTALL)
    assert pairs, "La documentación debe incluir ejemplos reproducibles de TAC"
    assert len(pairs) == document.count("```cps\n") == document.count("```tac\n")
    for source, expected in pairs:
        result = compile_source(source)
        assert result.ok, [str(error) for error in result.errors]
        assert result.program.check() == []
        assert result.program.format(numbered=False) == expected, f"TAC desactualizado para:\n{source}"
