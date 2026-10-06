# Cómo ejecutar el compilador

## Requisitos

* **Opción local:** Python 3.9+ y (solo para regenerar el parser) Java 17+.
  Graphviz (`dot`) es opcional para exportar el árbol como imagen.
* **Opción Docker:** Docker o Rancher Desktop (mismo `Dockerfile` del curso).

## Opción local

```bash
make venv                       # crea .venv e instala requirements.txt
make grammar                    # (opcional) regenera compiscript/generated desde la gramática
make run F=program/program.cps  # analiza un archivo
make test                       # corre la batería de tests
make ide                        # levanta el IDE en http://localhost:8080 (make ide PORT=9999 para otro puerto)
```

Sin `make`:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python Driver.py program/program.cps
.venv/bin/python -m pytest -q
.venv/bin/python -m ide.app
```

## Opción Docker

> En macOS el puerto 5000 suele estar ocupado por AirPlay Receiver; por eso el
> IDE usa 8080 por defecto (configurable con `PORT`).

```bash
docker build --rm . -t csp-image
docker run --rm -ti -p 8080:8080 -e PORT=8080 -v "$(pwd)":/app csp-image
# dentro del contenedor (el repo está montado en /app):
antlr -Dlanguage=Python3 -visitor -no-listener -Xexact-output-dir -o compiscript/generated program/Compiscript.g4
python3 Driver.py program/program.cps
python3 -m pytest -q
python3 -m ide.app        # abrir http://localhost:8080 en el navegador del host
```

## Driver (línea de comandos)

```
python3 Driver.py <archivo.cps> [--symbols] [--tree] [--lisp] [--dot salida.dot] [--quiet]
```

| Opción | Efecto |
|---|---|
| (ninguna) | Reporta errores sintácticos y semánticos con línea:columna. |
| `--symbols` | Imprime la tabla de símbolos (entorno, nombre, categoría, tipo, línea, offset). |
| `--tree` | Árbol sintáctico indentado con la posición de cada token. |
| `--lisp` | Árbol en notación `(regla hijo ...)` de ANTLR. |
| `--dot X.dot` | Exporta el árbol a Graphviz; si `dot` está instalado también genera `X.svg`. |
| `--quiet` | Omite el resumen final. |

Código de salida: `0` sin errores, `1` con errores, `2` uso incorrecto.

Ejemplo:

```
$ python3 Driver.py examples/err_02_ambitos.cps
[Error semántico] línea 2:6 — la variable 'noExiste' no ha sido declarada
[Error semántico] línea 4:4 — redeclaración de variable 'x' en el mismo ámbito (declarado antes en línea 3)
...
✘ 5 error(es) encontrado(s)
```

## IDE

1. `make ide` (o `python3 -m ide.app`) y abrir <http://localhost:8080>.
2. Escribir código en el editor; el análisis corre en vivo (o con **Compilar** / `Ctrl+Enter`).
3. Pestañas: **Errores** (clic para saltar a la línea), **Tabla de símbolos** y
   **Árbol sintáctico** (colapsable, muestra el tipo de cada expresión).
4. **Ejemplos…** carga los programas de `examples/` y `program/`.
5. **Árbol SVG** abre el árbol dibujado con Graphviz (requiere `dot` en el servidor).

El código se conserva en el navegador entre recargas (`localStorage`).

## Tests

```bash
make test            # o: .venv/bin/python -m pytest -q
pytest tests/test_classes.py -v      # un grupo de reglas
```

Un archivo por grupo de reglas (`test_types`, `test_scopes`, `test_functions`,
`test_control_flow`, `test_classes`, `test_lists`, `test_general`, `test_float`) más
`test_examples`, que valida que los `examples/NN_*.cps` sean correctos y que los
`examples/err_*.cps` fallen exactamente en las líneas comentadas.
