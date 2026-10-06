# Cumplimiento de la rúbrica — mapa de reglas a tests y demo

Cada regla semántica del enunciado (`README_SEMANTIC_ANALYSIS.md` del curso) tiene
**al menos un caso exitoso y un caso fallido** en la batería (`make test`, 152 tests).
La columna *Demo en el IDE* indica qué archivo cargar desde **Ejemplos…** para
mostrar la regla en vivo durante la presentación.

Convención: los tests viven en `tests/test_<grupo>.py`; los ejemplos `NN_*.cps`
son válidos y los `err_*.cps` fallan exactamente en las líneas comentadas
(garantizado por `tests/test_examples.py`).

## 1. Sistema de tipos (`test_types.py`, `test_float.py`)

| Regla | Caso exitoso | Caso fallido | Demo en el IDE |
|---|---|---|---|
| Aritmética con `integer`/`float` | `test_aritmetica_entera_valida`, `test_integer_se_promueve_a_float`, `test_aritmetica_mixta_da_float` | `test_aritmetica_rechaza_boolean`, `test_aritmetica_rechaza_string_en_multiplicacion`, `test_float_con_boolean_es_error`, `test_modulo_solo_entero` | `01`, `05` / `err_01`, `err_05` |
| Lógicas con `boolean` (`&&`, `\|\|`, `!`) | `test_logica_valida` | `test_and_rechaza_integer`, `test_not_rechaza_string` | `01` / `err_01` |
| Comparaciones compatibles | `test_comparaciones_validas`, `test_null_comparable_con_referencias`, `test_comparaciones_entre_numericos` | `test_igualdad_tipos_distintos`, `test_relacional_requiere_integer` | `01` / `err_01` |
| Asignación según tipo declarado | `test_asignacion_tipo_correcto`, `test_inferencia_de_tipo`, `test_var_funciona_como_let`, `test_null_asignable_a_referencias` | `test_asignacion_tipo_incorrecto`, `test_inicializacion_tipo_incorrecto`, `test_variable_sin_tipo_ni_valor`, `test_null_no_asignable_a_primitivos_de_valor` | `01` / `err_01` |
| `const` inicializada e inmutable | `test_const_inicializada_valida` | `test_const_sin_inicializar_es_error`, `test_const_no_reasignable`, `test_const_con_tipo_inferido_sigue_siendo_inmutable` | `01` / `err_01` |
| Tipos en listas | `test_lista_homogenea_valida` | `test_lista_heterogenea_invalida`, `test_lista_tipo_declarado_incompatible` | `04` / `err_01` |

## 2. Manejo de ámbito (`test_scopes.py`)

| Regla | Caso exitoso | Caso fallido | Demo en el IDE |
|---|---|---|---|
| Resolución local/global | `test_resolucion_global_desde_funcion`, `test_resolucion_local_sobre_global` | — (ver siguientes) | `02` + pestaña *Tabla de símbolos* |
| Variables no declaradas | — | `test_variable_no_declarada`, `test_asignacion_a_no_declarada`, `test_uso_de_variable_sin_inicializar` | `err_02` |
| Redeclaración en el mismo ámbito | `test_redeclaracion_en_bloque_anidado_permitida` | `test_redeclaracion_mismo_ambito`, `test_funcion_y_variable_mismo_nombre` | `err_02` |
| Acceso en bloques anidados | `test_bloques_anidados_ven_variables_externas` | `test_variable_de_bloque_no_visible_afuera`, `test_uso_antes_de_declaracion_en_inicializador` | `err_02` |
| Un entorno por función/clase/bloque | `test_tabla_de_simbolos_registra_entornos` | `test_nuevo_entorno_por_funcion`, `test_nuevo_entorno_por_clase`, `test_parametro_visible_solo_en_su_funcion` | *Tabla de símbolos* (columna Entorno) |

## 3. Funciones y procedimientos (`test_functions.py`)

| Regla | Caso exitoso | Caso fallido | Demo en el IDE |
|---|---|---|---|
| Número y tipo de argumentos (posicional) | `test_llamada_valida`, `test_parametro_float_acepta_integer` | `test_numero_de_argumentos_incorrecto`, `test_tipo_de_argumento_incorrecto`, `test_argumentos_posicionales`, `test_parametro_integer_rechaza_float` | `02` / `err_03` |
| Tipo de retorno | `test_tipo_de_retorno_correcto` | `test_tipo_de_retorno_incorrecto`, `test_return_sin_valor_en_funcion_tipada`, `test_funcion_void_no_retorna_valor`, `test_funcion_tipada_sin_return`, `test_retorno_float_en_funcion_integer` | `err_03` |
| Recursión | `test_recursion`, `test_llamada_a_funcion_declarada_despues` | — | `02` (factorial) |
| Funciones anidadas y closures (captura) | `test_funciones_anidadas_y_closure` (verifica la lista de capturas en la tabla de símbolos) | `test_funcion_anidada_no_visible_afuera` | `02` (crearContador) + *Tabla de símbolos* (columna Detalle: "captura: cuenta") |
| Funciones duplicadas | — | `test_funciones_duplicadas`, `test_parametros_duplicados`, `test_parametro_sin_tipo` | `err_03` |

## 4. Control de flujo (`test_control_flow.py`)

| Regla | Caso exitoso | Caso fallido | Demo en el IDE |
|---|---|---|---|
| Condiciones `boolean` en `if`/`while`/`do-while`/`for`/ternario | `test_if_boolean`, `test_for_valido`, `test_do_while_valido`, `test_condiciones_boolean_en_todas_las_estructuras` | `test_if_no_boolean`, `test_while_no_boolean`, `test_do_while_no_boolean`, `test_for_condicion_no_boolean`, `test_ternario_condicion_boolean` | `04` / `err_04` |
| `switch` con `case` comparables | `test_switch_valido` | `test_switch_case_tipo_incompatible` | `04` |
| `break`/`continue` solo en bucles | `test_break_dentro_de_bucle`, `test_continue_dentro_de_bucle` | `test_break_fuera_de_bucle`, `test_continue_fuera_de_bucle`, `test_continue_en_switch_sin_bucle`, `test_break_en_funcion_dentro_de_bucle_es_error` | `err_04` |
| `return` dentro de una función | `test_return_dentro_de_bucle_en_funcion` | `test_return_fuera_de_funcion` (en `test_functions.py`) | `err_03` |

## 5. Clases y objetos (`test_classes.py`)

| Regla | Caso exitoso | Caso fallido | Demo en el IDE |
|---|---|---|---|
| Existencia de atributos/métodos (`.`) | `test_clase_y_acceso_a_miembros`, `test_herencia_hereda_miembros` | `test_atributo_inexistente`, `test_metodo_inexistente`, `test_acceso_punto_en_no_objeto` | `03` / `err_04` |
| Constructor llamado correctamente | `test_clase_y_acceso_a_miembros` (`new` con argumentos) | `test_constructor_argumentos_incorrectos`, `test_constructor_tipo_de_argumento`, `test_clase_sin_constructor_no_acepta_argumentos` | `err_04` |
| `this` en su ámbito | `test_this_en_metodo_valido` | `test_this_fuera_de_clase`, `test_this_en_funcion_libre` | `err_04` |
| Extra: herencia y sobreescritura | `test_subclase_asignable_a_superclase`, `test_sobreescritura_misma_firma`, `test_metodos_se_llaman_entre_si_sin_importar_orden` | `test_superclase_no_asignable_a_subclase`, `test_sobreescritura_firma_distinta`, `test_clase_padre_inexistente`, `test_clase_duplicada` | `03` |

## 6. Listas y estructuras (`test_lists.py`)

| Regla | Caso exitoso | Caso fallido | Demo en el IDE |
|---|---|---|---|
| Tipo de elementos | `test_acceso_valido`, `test_matriz`, `test_foreach_tipa_elemento` (implícito), `test_arreglo_mixto_se_promueve_a_float` | `test_elementos_heterogeneos`, `test_elemento_tipo_incorrecto_al_extraer`, `test_asignar_elemento_tipo_incorrecto` | `04` / `err_04` |
| Validación de índices | `test_acceso_valido`, `test_funcion_retorna_arreglo` | `test_indice_debe_ser_integer`, `test_indice_negativo_literal`, `test_indexar_no_arreglo`, `test_indice_float_invalido` | `err_04`, `err_05` |

## 7. Generales (`test_general.py`)

| Regla | Caso exitoso | Caso fallido | Demo en el IDE |
|---|---|---|---|
| Código muerto | `test_return_en_rama_no_es_codigo_muerto` | `test_codigo_muerto_tras_return`, `test_codigo_muerto_tras_break`, `test_codigo_muerto_tras_continue` | `err_04` (final) |
| Expresiones con sentido semántico | — | `test_multiplicar_funciones`, `test_sumar_funcion_a_string`, `test_imprimir_funcion`, `test_asignar_a_funcion`, `test_asignar_a_resultado_de_llamada` | `err_03` |
| Declaraciones duplicadas | — | `test_declaraciones_duplicadas_de_variable`, `test_parametros_duplicados` | `err_02`, `err_03` |

## Integración

* `test_programa_de_ejemplo_del_curso_es_valido`: `program/program.cps` (el del
  profesor) compila sin errores.
* `test_examples.py`: todos los `examples/NN_*.cps` son válidos y cada línea
  comentada de los `examples/err_*.cps` produce su error (así los ejemplos que
  se muestran en el IDE están siempre sincronizados con el analizador).
* `test_error_sintactico_detiene_semantica`: los errores sintácticos se reportan
  y no disparan falsos errores semánticos.

## Guion sugerido para el video

1. `make test` → 152 tests en verde; abrir `tests/` y mostrar que hay un archivo
   por grupo de reglas de la rúbrica, cada uno con casos exitosos y fallidos.
2. `.venv/bin/python -m pytest tests/test_classes.py -v` → nombres de los casos
   legibles como especificación.
3. `make ide` → cargar `03_clases_y_herencia.cps` (válido: árbol + tabla de
   símbolos con herencia) y luego `err_04_control_y_clases.cps` (cada línea
   marcada con su error).
4. En vivo: romper una línea (p. ej. `let x: integer = "hola";`) y mostrar el
   error instantáneo; corregirla y mostrar ✔ sin errores.
5. Botón **Árbol SVG** para la representación visual exigida por el enunciado.
