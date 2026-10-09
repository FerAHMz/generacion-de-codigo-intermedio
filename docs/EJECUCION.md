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
python3 Driver.py <archivo.cps> [--tac] [--out ARCHIVO] [--runtime] [--run]
                                [--symbols] [--tree] [--lisp] [--dot salida.dot] [--quiet]
```

El Driver compila con las dos pasadas (`compile_file`). Si hay errores
sintácticos o semánticos los reporta y **no genera TAC**: las opciones
`--tac`, `--out`, `--runtime` y `--run` no hacen nada.

| Opción | Efecto |
|---|---|
| (ninguna) | Reporta errores sintácticos y semánticos con línea:columna y, si no hay, cuántas instrucciones de TAC se generaron. |
| `--tac` | Imprime el código intermedio numerado. |
| `--out X.tac` | Guarda el código intermedio numerado en `X.tac`. |
| `--runtime` | Imprime el área global, los registros de activación (encabezado por uso, parámetros, locales y temporales) y el layout de cada clase con su vtable. |
| `--run` | Ejecuta el TAC con el intérprete (`compiscript/ir/interp.py`) e imprime la salida del programa. |
| `--symbols` | Imprime la tabla de símbolos (entorno, nombre, categoría, tipo, línea, tamaño, dirección, etiqueta). |
| `--tree` | Árbol sintáctico indentado con la posición de cada token. |
| `--lisp` | Árbol en notación `(regla hijo ...)` de ANTLR. |
| `--dot X.dot` | Exporta el árbol a Graphviz; si `dot` está instalado también genera `X.svg`. |
| `--quiet` | Omite el resumen final. |

Código de salida: `0` sin errores, `1` con errores de compilación (o un error
en tiempo de ejecución con `--run`), `2` uso incorrecto (p. ej. archivo
inexistente).

Ejemplos:

```
$ python3 Driver.py examples/02_funciones_y_closures.cps --tac --quiet
 1  func_begin main, 4
 2      param "Mundo"
 3      t1 = call saludar, 1
 4      print t1
...
17  func_begin factorial, 20
18      t1 = n
19      if t1 > 1 goto L1
20      return 1
21  L1:
...

$ python3 Driver.py examples/02_funciones_y_closures.cps --run --quiet
Hola Mundo
120
2
4

$ python3 Driver.py examples/02_funciones_y_closures.cps --runtime --quiet
...
Registro de activación crearContador_siguiente (nivel 2, static link -> crearContador) frame_size = 12
  fp[+4]         static link -> crearContador (4 B)
  fp[+0]         control link (fp anterior) (4 B)
  fp[-4]         temporal t1 (4 B)

$ python3 Driver.py examples/err_02_ambitos.cps --tac
[Error semántico] línea 2:6 — la variable 'noExiste' no ha sido declarada
...
✘ 5 error(es) encontrado(s); no se generó código intermedio
```

Con `make`: `make run F=archivo.cps` equivale a `python3 Driver.py archivo.cps`.

### Desde Python

```python
from compiscript.codegen import compile_file
from compiscript.ir.interp import run

res = compile_file("examples/03_clases_y_herencia.cps")
if res.ok:
    print(res.program.format())            # TAC numerado
    print(res.table.format_runtime())      # registros de activación y clases
    print(run(res.program, res.table))     # salida del programa
else:
    for e in res.errors:
        print(e)
```

## IDE

1. `make ide` (o `python3 -m ide.app`) y abrir <http://localhost:8080>.
2. Escribir código en el editor; el análisis y la generación de TAC corren en
   vivo (o con **Compilar** / `Ctrl+Enter`).
3. Pestañas:
   * **Errores**: sintácticos y semánticos; clic para saltar a la línea.
   * **Código intermedio**: el TAC numerado. Si el programa tiene errores queda
     vacío ("no se generó código intermedio").
   * **Registros de activación**: un cuadro por función con su nivel, static
     link, `frame_size`, el encabezado (cada campo con el motivo por el que se
     incluye) y el contenido del marco; después, el layout de cada clase con
     sus atributos, la vtable y el constructor.
   * **Salida**: lo que imprime el programa al ejecutar el TAC con el botón
     **⚙ Ejecutar TAC**. Un error en ejecución sin `try` se muestra en rojo.
   * **Tabla de símbolos** y **Árbol sintáctico** (colapsable, con el tipo de
     cada expresión).
4. **Ejemplos…** carga los programas de `examples/` y `program/`.
5. **Árbol SVG** abre el árbol dibujado con Graphviz (requiere `dot` en el servidor).

El código se conserva en el navegador entre recargas (`localStorage`).

API usada por el IDE (JSON, `{"source": "..."}` en el cuerpo):

| Endpoint | Respuesta |
|---|---|
| `POST /api/analyze` | `ok`, `errors`, `symbols` (filas), `scopes`, `tree` |
| `POST /api/compile` | `ok`, `errors`, `tac` (líneas), `symbols` (`globals_size`, `activation_records`, `classes`, `symbols`) |
| `POST /api/run` | `ok`, `errors`, `output` (líneas impresas), `runtime_error` |

## Tests

```bash
make test            # o: .venv/bin/python -m pytest -q
pytest tests/test_classes.py -v      # un grupo de reglas semánticas
pytest tests/ir tests/tac -v         # código intermedio
```

| Carpeta | Qué prueba |
|---|---|
| `tests/test_*.py` | Análisis semántico, un archivo por grupo de reglas, y `test_examples` (los `examples/NN_*.cps` compilan y los `err_*.cps` fallan en las líneas comentadas). |
| `tests/ir/` | Cuádruplos, temporales, vida y linear scan, errores en ejecución, registros de activación, contrato del generador e intérprete con TAC escrito a mano. |
| `tests/tac/` | Driver (`--tac`, `--out`, `--runtime`, `--run`), IDE (`/api/compile`, `/api/run`) y pruebas de extremo a extremo: programa → TAC → intérprete → salida esperada. |

El mapa requisito → archivo → tests → demo está en
[RUBRICA_TAC.md](RUBRICA_TAC.md).
