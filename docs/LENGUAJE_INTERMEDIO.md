# Lenguaje intermedio: código de tres direcciones (TAC)

> **Estado:** versión inicial (diseño). Define las instrucciones, convenciones y
> esquemas de traducción que implementa el generador (`compiscript/codegen/`).
> Las secciones marcadas con **(esquema)** describen la traducción que deben
> producir los mixins de generación; cuando estén implementados, los ejemplos se
> reemplazarán por la salida real del compilador.

## 1. Visión general

El compilador trabaja en dos pasadas sobre el mismo árbol de ANTLR:

1. **Análisis semántico** (`compiscript/semantic/`): valida tipos y ámbitos, y
   anota cada nodo con su tipo (`node_types`), su símbolo (`node_symbols`) y el
   entorno que abre (`node_scopes`). Al terminar, `SymbolTable.allocate_storage()`
   asigna direcciones, registros de activación y layouts de clases.
   **Si hay errores, se reportan y no se genera TAC.**
2. **Generación de TAC** (`compiscript/codegen/`): recorre el árbol usando esas
   anotaciones y emite cuádruplos.

```python
from compiscript.codegen import compile_source
res = compile_source(src)       # res.errors, res.program (TACProgram | None)
print(res.program.format())     # TAC numerado
```

## 2. Representación: cuádruplos

Cada instrucción es un `Quad(op, arg1, arg2, result)` (`compiscript/ir/tac.py`).
Los operandos son objetos tipados, no texto:

| Operando | Se imprime | Contenido |
|---|---|---|
| `Temp(n)` | `t1`, `t2`, … | temporal; lo asigna y recicla `TempAllocator` |
| `Var(name, address, hops)` | `x` | variable del fuente; `address` es su dirección (`global[8]`, `fp[+4]`, `fp[-4]`); `hops` = enlaces estáticos a seguir (closures) |
| `Const(value)` | `5`, `2.5`, `"hola"`, `true`, `null` | literal |
| `Label(name)` | `L3`, `fact`, `Perro_hablar` | etiqueta de salto o de función/clase |
| `Field(name, offset)` | — | atributo: se imprime como `[obj + offset]` con el nombre en comentario |

Las variables se imprimen por nombre para que el TAC sea legible; dos variables
homónimas (sombra) se distinguen por su `address`, que es lo que usa el
intérprete. `TACProgram.format()` numera las instrucciones; las etiquetas y
`func_begin`/`func_end` van sin sangría.

## 3. Conjunto de instrucciones

| Forma | `op` | arg1 | arg2 | result | Significado |
|---|---|---|---|---|---|
| `t = a op b` | `+ - * / %` | a | b | t | aritmética (`/` entera si ambos son integer) |
| `t = a relop b` | `< <= > >= == !=` | a | b | t | comparación con valor booleano |
| `t = minus a` | `minus` | a | | t | negación aritmética |
| `t = not a` | `not` | a | | t | negación lógica (solo si se necesita el valor) |
| `x = y` | `=` | y | | x | copia |
| `goto L` | `goto` | | | L | salto incondicional |
| `if a relop b goto L` | `if<`, `if==`, … | a | b | L | salto condicional relacional |
| `if a goto L` | `if` | a | | L | salta si `a` es verdadero |
| `ifFalse a goto L` | `ifFalse` | a | | L | salta si `a` es falso |
| `L:` | `label` | | | L | define una etiqueta |
| `param x` | `param` | x | | | apila un argumento |
| `t = call f, n` | `call` | f | n | t (opcional) | llama con `n` argumentos; `f` es `Label` (directa) o `Temp` (método virtual) |
| `return [x]` | `return` | x? | | | retorna (con o sin valor) |
| `func_begin f, size` | `func_begin` | f | size | | prólogo: reserva `frame_size` bytes |
| `func_end f` | `func_end` | f | | | epílogo |
| `t = a[i]` | `[]` | a | i | t | lectura de arreglo (índice en **elementos**) |
| `a[i] = x` | `[]=` | i | x | a | escritura de arreglo |
| `t = len a` | `len` | a | | t | longitud de un arreglo |
| `t = alloc n` | `alloc` | n | | t | crea un arreglo de `n` elementos |
| `t = new C, size` | `new` | C | size | t | reserva `size` bytes y guarda la vtable de `C` en `[t + 0]` |
| `t = [obj + off]` | `getf` | obj | Field | t | lee un atributo |
| `[obj + off] = x` | `setf` | Field | x | obj | escribe un atributo |
| `t = method obj, m` | `method` | obj | m | t | busca `m` en la vtable del objeto (despacho dinámico) |
| `print x` | `print` | x | | | imprime |
| `t = concat a, b` | `concat` | a | b | t | concatena; convierte a string el operando que no lo sea |
| `t = int_to_float a` | `int_to_float` | a | | t | conversión explícita por promoción |
| `push_handler L` | `push_handler` | | | L | instala el manejador `L` (try) |
| `pop_handler` | `pop_handler` | | | | retira el manejador más reciente |
| `x = exception` | `get_exception` | | | x | mensaje de la excepción capturada |

`TACProgram.check()` verifica que el código esté bien formado: cada etiqueta se
define una vez, todo salto apunta a una etiqueta existente y cada `func_begin`
tiene su `func_end`.

## 4. Modelo de memoria y registros de activación

### 4.1 Tamaños

Los tamaños se eligieron pensando en MIPS32 (palabra de 4 bytes):

| Tipo | Bytes | En MIPS |
|---|---|---|
| `integer` | 4 | `lw`/`sw`, registros `$t`/`$s` |
| `float` | 4 | precisión simple, `l.s`/`s.s`, registros `$f` |
| `boolean` | 1 | `lb`/`sb` |
| `string`, arreglos, objetos (referencias) | 4 | dirección en el heap o en `.data` |
| ranura de temporal | 4 | ranura de *spill* |

Cada dato se alinea a su tamaño.

### 4.2 Direcciones

| Dónde se declara | Dirección | Ejemplo |
|---|---|---|
| Nivel superior (incluye bloques/bucles de nivel superior) | área estática | `global[8]` |
| Parámetro | positiva respecto a `fp` | `fp[+4]` |
| Local de una función (bloques anidados aplanados) | negativa respecto a `fp` | `fp[-4]` |
| Atributo de clase | desplazamiento en el objeto | `this[+4]` → `[obj + 4]` |

### 4.3 Registro de activación (campos según su uso)

No hay una lista fija de campos: cada uno se incluye solo si la función lo usa.

```
            ┌──────────────────────────┐
 fp + …     │ parámetros (0 = this)    │  ← los apila el llamador con `param`
 [opcional] │ static link              │  ← la función (o una anidada) lee variables de una externa
 [opcional] │ dirección de retorno     │  ← la función llama a otras (`jal` sobrescribe $ra)
 fp + 0     │ control link (fp previo) │  ← siempre (salvo main): restaurar el fp al retornar
 fp - 4…    │ locales (aplanados)      │
            │ temporales t1…tN         │  (4 B cada uno; en MIPS, ranuras de spill)
            └──────────────────────────┘
frame_size = encabezado + parámetros + locales + 4·temporales
```

| Campo | Se incluye cuando | Para qué |
|---|---|---|
| control link | siempre, excepto en `main` | restaurar el `fp` del llamador al retornar |
| dirección de retorno | la función hace alguna llamada (no es hoja) | guardar `$ra`, que `jal` sobrescribe |
| static link | hay que atravesar el marco para llegar a una variable capturada, o la función llama a otra que necesita static link | closures |
| parámetros, locales | siempre que existan | datos de la función |
| temporales | `max_live > 0` | valores intermedios que no caben en registros |

El static link se decide con las capturas de cada función y un punto fijo sobre
el grafo de llamadas que registra la fase semántica (`FunctionSymbol.calls`).

* El código de nivel superior se genera como la función `main` (nivel 0); sus
  variables viven en el área global y nadie la llama, así que no tiene
  encabezado.
* `level` es la profundidad léxica: `main` = 0, función global = 1, función
  anidada = 2, …
* El número de temporales se conoce al terminar de generar la función: el
  generador guarda `TempAllocator.max_live` en el registro y corrige el
  `frame_size` de `func_begin`.

Volcado de ejemplo (`SymbolTable.format_runtime()`):

```
Registro de activación fact (nivel 1) frame_size = 12
  fp[+8]         param n: integer (4 B)
  fp[+4]         dirección de retorno (4 B)
  fp[+0]         control link (fp anterior) (4 B)

Registro de activación externa_media (nivel 2, static link -> externa) frame_size = 12
  fp[+8]         static link -> externa (4 B)
  fp[+4]         dirección de retorno (4 B)
  fp[+0]         control link (fp anterior) (4 B)
```

### 4.4 Etiquetas

* Funciones globales: su nombre (`fact`). Funciones anidadas: prefijo de la
  externa (`fact_aux`). Métodos: `Clase_metodo` (`Perro_hablar`).
* Si un nombre choca (p. ej. una función llamada `main`), se agrega `_2`, `_3`, …
* Etiquetas de salto: `L1`, `L2`, … únicas en todo el programa.

## 5. Temporales: asignación y reciclaje

El reciclaje se hace en dos niveles.

### 5.1 Al generar: free-list (`compiscript/ir/temps.py`)

`TempAllocator` mantiene una free-list ordenada:

1. `new()` entrega el temporal libre de **menor número**, o crea uno nuevo.
2. Un temporal se libera en cuanto su valor se consume como operando. El
   generador libera los operandos **antes** de pedir el temporal del resultado,
   así `t1 = t1 + c` reutiliza el nombre.
3. El asignador se reinicia al cerrar cada función.

Como siempre se reutiliza el menor libre, los nombres usados son exactamente
`t1 … t{max_live}`: `max_live` es la cantidad de ranuras de temporales del marco.

| `x = a + b + c + d` sin reciclaje | con reciclaje |
|---|---|
| `t1 = a + b` | `t1 = a + b` |
| `t2 = t1 + c` | `t1 = t1 + c` |
| `t3 = t2 + d` | `t1 = t1 + d` |
| `x = t3` | `x = t1` |
| 3 temporales | `max_live = 1` |

`(a + b) * (c + d)` necesita `max_live = 2`: `t1 = a + b`, `t2 = c + d`,
`t1 = t1 * t2`.

### 5.2 Sobre el TAC: vida + linear scan (`compiscript/ir/liveness.py`)

Basado en M. Poletto y V. Sarkar, *Linear Scan Register Allocation*, ACM
TOPLAS 21(5), 1999 (por confirmar con el profesor que es el paper del MIT que
recomendó):

1. **Vida:** análisis de flujo de datos hacia atrás sobre el grafo de flujo de
   cada función (`goto`, saltos condicionales, `return`, y `push_handler` con
   arista al manejador). Solo temporales: las variables viven en memoria.
2. **Valores:** como `t1` se recicla, un mismo nombre contiene valores sin
   relación. Con definiciones que alcanzan se agrupan las definiciones que
   llegan a un mismo uso; cada grupo es un valor con su intervalo
   `[inicio, fin]` en orden lineal. En un bucle, el intervalo se extiende hasta
   el salto de regreso.
3. **Linear scan:** se recorren los intervalos por inicio; los que terminaron
   devuelven su registro; si no hay libre, se derrama (spill) el que termina más
   tarde. Dos intervalos que solo se tocan en un extremo comparten registro
   (`add $t0, $t0, $t1`). Las clases entera y flotante se asignan por separado
   (por eso `Temp` y `Var` llevan su tipo).

| Función | Uso |
|---|---|
| `allocate_registers(prog)` | registro MIPS o ranura de spill de cada aparición de un temporal (`location(pos, t, "use"/"def")`); base de `getReg()` |
| `compact_temps(prog)` | renombra con el mínimo de temporales que permite la vida real (registros ilimitados) |
| `LiveInterval.crosses_call` | el valor está vivo durante un `call`: en MIPS conviene un `$s` (lo preserva el llamado) |

## 6. Convenciones de llamada

**Llamada** `f(a1, …, an)`:

```
param a1
...
param an
t1 = call f, n        # o `call f, n` si es void
```

* El parámetro `i` queda en `fp[+encabezado + offset_i]` del marco del llamado.
* **Static link:** solo se pasa si el llamado lo necesita (§4.3). Lo establece
  la secuencia de llamada: si el llamador está en el nivel `p` y el llamado en el
  nivel `q` (`q ≤ p + 1`), se siguen `p - q + 1` enlaces estáticos desde el marco
  del llamador. No hay instrucción explícita: el nivel de cada función está en
  su registro de activación.
* **Retorno:** `return x` deja el valor en el registro de retorno; `t = call`
  lo recibe. `func_end` equivale a `return` sin valor.
* **Recursión:** cada llamada crea un marco nuevo; no requiere nada especial.

## 7. Esquemas de traducción **(esquema)**

En adelante `E.place` es el operando que devuelve `gen_expr(E)` y
`cond(E, Lt, Lf)` es `gen_cond`: código de saltos que va a `Lt` si `E` es
verdadera y a `Lf` si es falsa; un destino `fall` significa "seguir con la
instrucción siguiente".

### 7.1 Expresiones aritméticas y precedencia

La gramática ya codifica la precedencia; las cadenas `a op b op c` se evalúan de
izquierda a derecha.

```
x = a + b * c - d          t1 = b * c
                           t1 = a + t1
                           t1 = t1 - d
                           x = t1
```

### 7.2 float e `int_to_float`

Donde la semántica promovió `integer → float` se emite la conversión explícita:
operación mixta, asignación/inicialización de un float con un integer, argumento
integer a parámetro float, `return` integer en función float y elementos de un
arreglo float. Una constante entera se convierte en compilación.

```
let f: float = n * 2.5;    t1 = int_to_float n
                           t1 = t1 * 2.5
                           f = t1
let g: float = 3;          g = 3.0
```

### 7.3 Strings

`+` con algún operando string genera `concat` (convierte el otro operando):

```
print("n = " + n);         t1 = concat "n = ", n
                           print t1
```

### 7.4 Booleanos: código de saltos con corto circuito

Se usan **etiquetas heredadas** con fall-through:

| E | `cond(E, Lt, Lf)` |
|---|---|
| `a relop b` | `if a relop b goto Lt` y/o `goto Lf` (si `Lt = fall`: `if a relop' b goto Lf` con el relop invertido: `<`↔`>=`, `<=`↔`>`, `==`↔`!=`) |
| `E1 \|\| E2` | `cond(E1, Lt ó Lnuevo, fall)`; `cond(E2, Lt, Lf)`; `Lnuevo:` si se creó |
| `E1 && E2` | `cond(E1, fall, Lf ó Lnuevo)`; `cond(E2, Lt, Lf)`; `Lnuevo:` si se creó |
| `!E` | `cond(E, Lf, Lt)` |
| `true` / `false` | `goto Lt` / `goto Lf` (o nada si es `fall`) |
| variable booleana `b` | `if b goto Lt` / `ifFalse b goto Lf` |

```
if (a < b && c != d) { print(1); }      if a >= b goto L1
                                        if c == d goto L1
                                        print 1
                                      L1:
```

Si se necesita el **valor** (`let ok = a < b || c;`): una comparación simple
usa `t = a < b`; con `&&`, `||` o `!` se materializa con saltos:

```
    cond(E, fall, Lf)
    t1 = true
    goto Lend
Lf: t1 = false
Lend:
```

### 7.5 if / else

```
if (E) S1 else S2        cond(E, fall, Lelse)
                         S1
                         goto Lend
                       Lelse:
                         S2
                       Lend:
```

### 7.6 while, do-while, for

```
while (E) S              Lcond:                 do S while (E);     Linicio:
                           cond(E, fall, Lend)                        S
                           S                                        Lcont:
                           goto Lcond                                 cond(E, Linicio, fall)
                         Lend:                                      Lend:

for (init; E; upd) S     init
                       Lcond:
                         cond(E, fall, Lend)
                         S
                       Lcont:                   # destino de continue
                         upd
                         goto Lcond
                       Lend:                    # destino de break
```

`continue` en un `while` salta a `Lcond`; en `for`, a `Lcont` (para ejecutar la
actualización).

### 7.7 foreach (índice oculto)

```
foreach (x in xs) S      t1 = 0                 # índice oculto
                         t2 = len xs
                       Lcond:
                         if t1 >= t2 goto Lend
                         x = xs[t1]
                         S
                       Lcont:
                         t1 = t1 + 1
                         goto Lcond
                       Lend:
```

`t1`/`t2` permanecen vivos durante todo el bucle (no se liberan hasta `Lend`);
como los temporales viven en el marco, sobreviven a llamadas dentro de `S`.

### 7.8 switch (cadena de comparaciones, fallthrough)

```
switch (E) {             t1 = E.place
  case c1: S1            if t1 == c1 goto Lc1
  case c2: S2            if t1 == c2 goto Lc2
  default: S3            goto Ldef               # o Lend si no hay default
}                      Lc1: S1                   # sin break cae al siguiente caso
                       Lc2: S2
                       Ldef: S3
                       Lend:                     # destino de break
```

### 7.9 break / continue

El generador mantiene una pila de destinos (`breakable`): cada bucle registra
`(Lend, Lcont)` y cada `switch` registra `(Lend, —)`. `break` usa el tope;
`continue` busca el bucle más interno, atravesando los `switch`.

### 7.10 Ternario

```
x = E ? A : B            cond(E, fall, Lf)
                         t1 = A.place
                         goto Lend
                       Lf:
                         t1 = B.place
                       Lend:
                         x = t1
```

### 7.11 try / catch

```
try S1 catch (e) S2      push_handler Lcatch
                         S1
                         pop_handler
                         goto Lend
                       Lcatch:
                         e = exception
                         S2
                       Lend:
```

**Supuestos** (catálogo en `compiscript/ir/runtime.py`):

* Compiscript no tiene `throw`: las excepciones son errores en tiempo de
  ejecución que revisan ciertas instrucciones antes de ejecutarse:

  | Error | Mensaje (valor de `e`) | Lo revisan |
  |---|---|---|
  | índice fuera de rango | `"índice fuera de rango"` | `t = a[i]`, `a[i] = x` |
  | acceso a `null` | `"acceso a una referencia null"` | `a[i]`, `len`, `[obj + off]`, `method` |
  | división entre cero | `"división entre cero"` | `/`, `%` |

* `push_handler L` apila el registro (`L`, `fp`, `sp`) del marco actual.
* Ante un error: si no hay manejador, el programa termina imprimiendo el
  mensaje; si hay, se desapila el más reciente, se restauran `fp` y `sp` (esto
  descarta los marcos de las funciones llamadas dentro del try) y se salta a
  `L`; `exception` contiene el mensaje (string).
* Un `break`, `continue` o `return` que sale de uno o más `try` emite un
  `pop_handler` por cada uno antes del salto (`emit_jump_out`, `emit_return`).
* Para la vida de temporales, `push_handler L` tiene arista a `L`: un valor
  que se usa en el catch está vivo durante todo el try.

### 7.12 Arreglos

```
let xs: integer[] = [1, 2, 3];      t1 = alloc 3
                                    t1[0] = 1
                                    t1[1] = 2
                                    t1[2] = 3
                                    xs = t1
print(xs[i]);                       t1 = xs[i]
                                    print t1
xs[0] = 5;                          xs[0] = 5
```

**Supuesto:** el índice es en **elementos**, no en bytes; el arreglo guarda su
longitud (`len`). La traducción a bytes (`base + 4 + 4·i`) se hace en la
generación de MIPS (§9.1). Un índice fuera de rango es un error en
tiempo de ejecución (capturable con try/catch).

### 7.13 Clases y objetos

**Layout:** `[obj + 0]` = puntero a la vtable; después los atributos heredados,
con los mismos offsets que en la clase padre, y luego los propios.

```
Clase Perro : Animal  object_size = 20
  [obj + 0  ] vtable
  [obj + 4  ] nombre (4 B) (heredado)
  [obj + 8  ] edad (4 B) (heredado)
  [obj + 12 ] raza (4 B)
  [obj + 16 ] peso (4 B)
  vtable[0] hablar -> Perro_hablar      # sobreescribe Animal_hablar en la misma ranura
  vtable[1] info -> Animal_info
```

**Creación** (`new` + llamada directa al constructor, propio o heredado):

```
let p: Perro = new Perro("Fido");   t1 = new Perro, 20
                                    param t1
                                    call $init_Perro, 1       # atributos por instancia
                                    param t1                 # this
                                    param "Fido"
                                    call Animal_constructor, 2
                                    p = t1
```

**Atributos** (`this` es el parámetro 0 de cada método):

```
this.nombre = n;                    [this + 4] = n           # this.nombre
print(p.edad);                      t1 = [p + 8]             # p.edad
                                    print t1
```

**Métodos — decisión: despacho dinámico por vtable.** Una variable de tipo
`Animal` puede contener un `Perro`, y `hablar` está sobreescrito; con
resolución estática se llamaría al método equivocado. Por eso:

```
print(a.hablar());                  t1 = method a, hablar    # vtable de a, ranura de "hablar"
                                    param a
                                    t2 = call t1, 1
                                    print t2
```

La ranura de cada método es la misma en toda la jerarquía
(`ClassLayout.method_slot`). El constructor no está en la vtable: siempre se
llama de forma directa.

**Inicializadores por instancia — implementación de Felipe Aguilar.** Cada clase
tiene una función interna `$init_Clase($this)`, fuera de la vtable. Primero llama
al inicializador del padre y luego evalúa sus atributos y constantes en orden
de declaración. Esto ocurre en cada `new`, antes de evaluar los argumentos y
llamar al constructor propio o heredado. Declarar una clase no ejecuta sus
inicializadores. Los atributos sin inicializador no generan asignaciones.

Los inicializadores conservan el ámbito léxico de la clase, pueden leer atributos
anteriores por su nombre y crean arreglos independientes para cada instancia.
Una función interna, en vez de expandir el código en cada `new`, permite que un
inicializador contenga otro `new` de su misma clase sin recursión del compilador.
Estas funciones se registran en la tabla; después se recalculan direcciones y
encabezados según sus llamadas y capturas, antes de emitir TAC. El prefijo `$`
evita colisiones porque no es válido en identificadores de Compiscript.

### 7.14 Funciones, recursión y closures

```
function fact(n: integer): integer {     func_begin fact, 16
  if (n <= 1) { return 1; }                if n > 1 goto L1
  return n * fact(n - 1);                  return 1
}                                        L1:
                                           t1 = n - 1
                                           param t1
                                           t1 = call fact, 1
                                           t1 = n * t1
                                           return t1
                                         func_end fact
```

**Closures — decisión: enlace estático (static link).** Las funciones anidadas
acceden a variables de funciones externas siguiendo `hops` enlaces estáticos
(`Var.hops`, dirección `fp^k[off]`). Es suficiente porque en Compiscript una
función no puede guardarse en una variable ni retornarse como valor (la fase
semántica lo rechaza): una función anidada nunca sobrevive al marco que la
contiene, así que no hace falta copiar las capturas al heap.

```
function externa(n: integer): integer {
  function interna(): integer { return n + 1; }     # n: fp^1[+8]
  return interna();
}
```

## 8. Supuestos generales

* El TAC solo se genera para programas sin errores sintácticos ni semánticos.
* Los operandos y argumentos se evalúan de izquierda a derecha. Una lectura de
  variable se copia a un temporal si debe sobrevivir a otra expresión. Por
  ejemplo, `x + (x = 4)` conserva el valor anterior de `x`.
* Los argumentos se calculan antes de emitir el grupo `param ... call`; así las
  llamadas anidadas no mezclan sus parámetros. El receptor y los valores vivos
  durante una llamada permanecen en el marco del llamador.
* El tipo esperado se propaga a los arreglos literales, incluso anidados y en
  ternarios: `let xs: float[] = [1]` almacena `1.0`. Los arreglos ya existentes
  conservan su referencia; no se copian al asignarlos.
* `/` entre integers trunca hacia cero; `%` solo existe entre integers.
* `==`/`!=` entre strings compara contenido; entre objetos/arreglos, identidad.
* Las variables declaradas sin valor inicial no generan código (la semántica
  impide leerlas antes de asignarlas).
* Las variables de bloques de nivel superior se ubican en el área global; las de
  bloques dentro de funciones se aplanan en el marco de la función (sin reutilizar
  el espacio de bloques hermanos, para simplificar).

## 9. Preparación para la generación de MIPS

La fase siguiente traduce este TAC a MIPS32 y lo ejecuta en un simulador
(MARS o SPIM). Estas decisiones ya están tomadas en el TAC y la tabla de
símbolos para que esa traducción sea directa.

### 9.1 Memoria

| Segmento | Contenido | Origen en el compilador |
|---|---|---|
| `.data` | variables globales (`global[off]` → `globals + off`), literales string (`.asciiz`), mensajes de error, vtables (`.word Clase_metodo, …`) | `SymbolTable.globals_size`, `ClassLayout.vtable`, `runtime.MESSAGES` |
| pila | un marco por llamada, direccionado con `$fp` | `ActivationRecord` |
| heap | objetos (`new C, size`) y arreglos (`alloc n`), con `sbrk` (syscall 9) | `ClassLayout.object_size` |

* Los tamaños de §4.1 ya son de MIPS32: todo cabe en una palabra, `float` es de
  precisión simple y `boolean` usa `lb`/`sb`.
* **Arreglos:** `[base]` guarda la longitud y los elementos empiezan en
  `base + 4`, una palabra cada uno. `t = a[i]` se traduce a: revisar `null`,
  revisar `0 ≤ i < len`, dirección `a + 4 + 4·i`.
* **Objetos:** `[obj + 0]` apunta a la vtable de su clase; `t = method obj, m`
  es `lw` de la vtable más `lw` de la ranura `ClassLayout.method_slot(m)` y
  `call t, n` es `jalr`.

### 9.2 Secuencias de llamada y retorno

| Paso | MIPS |
|---|---|
| `param x` (llamador) | al primer `param` se reservan `4·n` bytes en la pila; cada argumento se guarda en su offset, con el parámetro 0 en la dirección más baja (junto al encabezado), para que quede en `fp[+encabezado + off]` del llamado |
| static link (llamador, solo si el llamado lo necesita) | seguir `p - q + 1` enlaces desde `$fp` y apilarlo |
| `call f, n` | `jal f`; al volver, `addi $sp, $sp, 4·(n + static link)`; el resultado está en `$v0` (`$f0` si es float) |
| `func_begin f, size` (prólogo) | guardar `$ra` si la función no es hoja, guardar el `$fp` anterior (control link), `$fp = $sp`, reservar locales y spill (`size`) |
| `return x` / `func_end f` (epílogo) | valor a `$v0`/`$f0`, `$sp = $fp`, restaurar `$fp` y `$ra`, `jr $ra` |
| `main` | sin encabezado; termina con `li $v0, 10` / `syscall` |

### 9.3 Asignación de registros: `getReg()`

`getReg()` se basa en `allocate_registers()` (§5.2):

* Temporales enteros → `$t0–$t9` y `$s0–$s7`; flotantes → `$f4–$f11`, `$f16–$f31`.
  Quedan reservados `$at`, `$v0–$v1`, `$a0–$a3`, `$k0–$k1`, `$gp`, `$sp`, `$fp`,
  `$ra`, `$f0` y `$f12–$f14`.
* Un temporal derramado vive en su ranura de spill del marco; se carga en un
  registro de trabajo antes de usarlo y se guarda después de definirlo.
* Valores con `crosses_call`: preferir `$s` (los preserva el llamado) o guardar
  los `$t` vivos antes del `jal` y restaurarlos después.
* Las variables del programa no ocupan registros entre instrucciones: se leen
  con `lw`/`l.s`/`lb` desde su dirección y se escriben con `sw`/`s.s`/`sb`.

### 9.4 Excepciones en MIPS

* Pila de manejadores en memoria: cada `push_handler L` guarda (`L`, `$fp`,
  `$sp`).
* Las revisiones de §7.11 saltan a una rutina común `__raise` con el mensaje en
  `$a0`: si la pila de manejadores está vacía, imprime el mensaje y termina;
  si no, desapila, restaura `$fp`/`$sp` y salta a `L` con el mensaje en `$v0`
  (`e = exception` lo copia de ahí).
