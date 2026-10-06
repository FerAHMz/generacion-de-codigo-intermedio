# Compiscript — Análisis Semántico

Proyecto 1 del curso **Construcción de Compiladores** (Universidad del Valle de Guatemala).
Analizador sintáctico y semántico para **Compiscript**, un subset de TypeScript, construido
con **ANTLR 4.13.1** (gramática oficial del curso) y **Python 3**, con tabla de símbolos,
batería de tests e IDE web.

**Integrantes:** Fernando Hernández · Felipe Aguilar · Fernando Rueda

## Ejecución rápida

```bash
make venv                        # crea .venv e instala dependencias
make run F=program/program.cps   # analiza un archivo (.cps)
make test                        # batería de tests (pytest)
make ide                         # IDE web en http://localhost:8080
```

Con el mismo entorno Docker del curso: `make docker-build && make docker-shell`.
Guía completa en [docs/EJECUCION.md](docs/EJECUCION.md).

## Qué valida

| Grupo | Reglas |
|---|---|
| Sistema de tipos | Aritmética con `integer`/`float` (promoción implícita `integer → float`), lógica con `boolean`, comparaciones compatibles, asignaciones e inicializaciones con el tipo declarado, `const` inicializada e inmutable, listas homogéneas, inferencia de tipos. |
| Ámbitos | Resolución local/global, variables no declaradas, redeclaración en el mismo ámbito, visibilidad en bloques anidados, un entorno por función/clase/bloque/bucle, lectura antes de asignar. |
| Funciones | Número y tipo de argumentos (posicional), tipo de retorno, `return` obligatorio y solo dentro de funciones, recursión, funciones anidadas con captura de closures, funciones y parámetros duplicados. |
| Control de flujo | Condiciones `boolean` en `if`/`while`/`do-while`/`for`/ternario, `case` comparables con el `switch`, `foreach` sobre arreglos, `break`/`continue` solo en bucles. |
| Clases | Atributos y métodos existentes (`.`), constructor con argumentos correctos, `this` solo en métodos, herencia (padre existente, sin ciclos), sobreescritura con la misma firma. |
| Listas | Tipo de elementos, índices `integer` y no negativos, indexar solo arreglos. |
| Generales | Código muerto tras `return`/`break`/`continue`, expresiones sin sentido (operar o imprimir funciones), declaraciones duplicadas. |

Los errores se reportan todos juntos con línea y columna; un error no genera
mensajes en cascada.

## Estructura del repositorio

```
program/Compiscript.g4      gramática ANTLR del curso, extendida con float (+ BNF y program.cps)
compiscript/
  generated/                lexer, parser y visitor generados por ANTLR
  parsing.py                construcción del árbol y captura de errores sintácticos
  types.py                  sistema de tipos y compatibilidad
  symbols.py                tabla de símbolos y entornos
  semantic/                 visitor semántico (base, expressions, declarations,
                            functions, control_flow, classes)
  tree_viz.py               árbol en texto / LISP / JSON / Graphviz
Driver.py                   línea de comandos
ide/                        IDE web (Flask + CodeMirror)
tests/                      batería de tests por grupo de reglas
examples/                   programas válidos (NN_*.cps) y con errores (err_*.cps)
docs/                       ARQUITECTURA.md y EJECUCION.md
Dockerfile, commands/, antlr-4.13.1-complete.jar   entorno Docker del curso
```

## Documentación

* [Arquitectura de la implementación](docs/ARQUITECTURA.md)
* [Cómo ejecutar el compilador](docs/EJECUCION.md)
* [Mapa de la rúbrica: regla → tests → demo](docs/RUBRICA_TESTS.md)

## División del trabajo

| Integrante | Porción |
|---|---|
| Fernando Hernández | Configuración del proyecto (Docker/ANTLR/Makefile), integración del parser, sistema de tipos, tabla de símbolos, visualización del árbol, Driver, ejemplos. |
| Felipe Aguilar | Analizador semántico: base del visitor, expresiones, declaraciones, funciones y closures, control de flujo, clases. |
| Fernando Rueda | Batería de tests, IDE web (backend y frontend), documentación y extensión del lenguaje con `float`. |
