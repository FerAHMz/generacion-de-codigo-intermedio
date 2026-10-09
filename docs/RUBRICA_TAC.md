# Cumplimiento de la rúbrica — Proyecto 2 (código intermedio)

Mapa de cada requisito de `README_TAC_GENERATION.md` del curso al código que lo
implementa, a los tests que lo validan y a cómo mostrarlo en la presentación.
Toda la batería corre con `make test`.

Convenciones:

* `ir/x` = `tests/ir/test_x.py`; `tac/x` = `tests/tac/test_x.py`.
* `e2e[caso]` = `tac/e2e::test_programa[caso]`: el programa se compila, el TAC
  se ejecuta con el intérprete y se compara la salida de los `print`.
* En la columna *Demo*, **IDE** = cargar el ejemplo desde *Ejemplos…* y abrir la
  pestaña indicada; **CLI** = `python3 Driver.py <archivo> <opción>`.

## 1. Diseño del código intermedio (25 pts)

| Requisito | Dónde | Tests | Demo |
|---|---|---|---|
| Sintaxis propia de TAC en cuádruplos con operandos tipados | `compiscript/ir/tac.py`, `docs/LENGUAJE_INTERMEDIO.md` §2–3 | `ir/tac::test_formato_de_cada_instruccion`, `test_constantes`, `test_var_con_enlace_estatico`, `test_relop_invalido` | **CLI** `--tac` |
| TAC bien formado (etiquetas únicas, saltos válidos, funciones balanceadas) | `TACProgram.check()` | `ir/tac::test_programa_bien_formado`, `test_programa_mal_formado_reporta_problemas`; `test_examples::test_ejemplo_valido` (todos los ejemplos) | — |
| Esquemas de traducción y supuestos documentados con ejemplos | `docs/LENGUAJE_INTERMEDIO.md` §7–8 | los casos de `tac/e2e` siguen esos esquemas | documento |
| Semántica ejecutable del TAC (lo que significa cada instrucción) | `compiscript/ir/interp.py` | `ir/interp` (23 tests con TAC escrito a mano) | **IDE** botón *Ejecutar TAC*; **CLI** `--run` |
| Errores en tiempo de ejecución para `try/catch` (no hay `throw`) | `compiscript/ir/runtime.py`, LENGUAJE_INTERMEDIO §7.11 | `ir/runtime::test_instrucciones_que_revisan_errores`, `test_mensaje_es_el_valor_del_catch`; `ir/interp::test_indice_fuera_de_rango_dentro_de_try_salta_al_catch`, `test_error_fuera_de_try_termina_con_el_mensaje`, `test_error_en_funcion_llamada_desde_el_try_desapila_sus_marcos`, `test_pop_handler_deja_activo_el_try_externo`, `test_acceso_a_null` | `04_control_de_flujo.cps` → *Salida* |
| Preparación para MIPS (tamaños MIPS32, enteros de 32 bits, registros por tipo) | LENGUAJE_INTERMEDIO §9, `symbols.sizeof` | `ir/registros_activacion::test_tamanos_por_tipo`; `ir/interp::test_enteros_de_32_bits`; `ir/codegen_base::test_temporales_llevan_tipo_para_elegir_registros` | — |

## 2. Generación de TAC desde Compiscript (65 pts)

Cada fila tiene la prueba del **texto** del TAC (generador) y la prueba de que
el TAC **se comporta** como el programa fuente (extremo a extremo).

| Construcción | Dónde | Tests del TAC | Tests de ejecución | Demo |
|---|---|---|---|---|
| Expresiones aritméticas y precedencia | `codegen/expressions.py` | `ir/codegen_base::test_temporales_reciclados_y_capturas_en_el_tac_publico`, `test_operando_izquierdo_se_conserva_antes_de_asignar_el_derecho` | `e2e[precedencia]`, `e2e[division_entera_negativa]`, `e2e[asignacion_como_expresion]` | `01_tipos_y_expresiones.cps` |
| `float` e `int_to_float` | `expressions.py`, `base.coerce` | `ir/codegen_base::test_coerce_emite_int_to_float`, `test_arreglos_float_promueven_literales_anidados_argumentos_y_retornos` | `e2e[float_y_promocion]`, `tac/e2e::test_ejemplo[05_float.cps]` | `05_float.cps` |
| Strings y `concat` | `expressions.py` | `ir/tac::test_formato_de_cada_instruccion` | `e2e[strings]`, `ir/interp::test_concat_convierte_valores_a_texto` | `02_funciones_y_closures.cps` |
| Booleanos con corto circuito | `expressions.gen_cond` | `ir/codegen_base::test_condiciones_tienen_operandos_booleanos`, `test_corto_circuito_salta_la_llamada` | `e2e[corto_circuito]` | `01_tipos_y_expresiones.cps` |
| `if`/`else`, `while`, `do-while`, `for` | `codegen/control_flow.py` | `ir/codegen_base::test_while_break_y_etiquetas_balanceadas` | `e2e[if_else]`, `e2e[while_y_do_while]`, `e2e[for_con_continue_ejecuta_la_actualizacion]` | `04_control_de_flujo.cps` |
| `foreach` | `control_flow.py` | `test_examples::test_ejemplo_valido[04_control_de_flujo.cps]` | `e2e[foreach]`, `e2e[arreglo_retornado_y_parametro]` | `04_control_de_flujo.cps` |
| `switch` con fallthrough, `break`/`continue` | `control_flow.py`, `base.breakable` | `ir/codegen_base::test_pila_break_continue_atraviesa_switch` | `e2e[switch_con_fallthrough_y_break]`, `e2e[break_en_switch_dentro_de_bucle]`, `tac/e2e::test_program_cps_del_curso` | `program.cps` |
| Ternario | `expressions.visitTernaryExpr` | `test_examples::test_ejemplo_valido[01_tipos_y_expresiones.cps]` | `e2e[ternario]` | `01_tipos_y_expresiones.cps` |
| `try/catch` (`push_handler`/`pop_handler`, salidas anticipadas) | `control_flow.py`, `base.handler` | `ir/codegen_base::test_saltos_que_salen_de_un_try_cierran_manejadores`, `test_salidas_anticipadas_desapilan_handlers` | `e2e[try_indice_fuera_de_rango]`, `e2e[try_error_en_funcion_llamada]`, `e2e[try_anidado_y_break_dentro_de_try]`, `e2e[return_dentro_de_try]`, `e2e[error_sin_try_termina]` | `04_control_de_flujo.cps` → *Salida* |
| Arreglos (literales, índices, matrices) | `expressions.py` | `ir/codegen_base::test_arreglos_float_promueven_literales_anidados_argumentos_y_retornos` | `e2e[matriz]`, `e2e[arreglo_retornado_y_parametro]`, `ir/interp::test_arreglo_alloc_len_lectura_y_escritura`, `test_arreglos_son_referencias` | `04_control_de_flujo.cps` |
| Funciones, `param`/`call`/`return`, recursión | `codegen/functions.py` | `ir/codegen_base::test_funciones_en_bufer_propio_con_frame_size_final`, `test_llamadas_anidadas_no_mezclan_parametros` | `e2e[recursion]`, `ir/interp::test_recursion_fact`, `test_cada_llamada_tiene_sus_temporales` | `02_funciones_y_closures.cps` |
| Closures (static link, `Var.hops`) | `base.var`, `symbols.hops` | `ir/codegen_base::test_var_de_closure_lleva_hops`, `test_closure_de_metodo_captura_el_receptor_implicito` | `e2e[closures]`, `e2e[closure_dos_niveles]`, `ir/interp::test_closure_lee_y_escribe_por_static_link`, `test_static_link_con_recursion_de_la_externa` | `02_funciones_y_closures.cps` |
| Clases: `new`, constructor, atributos, `this`, inicializadores | `codegen/classes.py` | `ir/codegen_base::test_inicializadores_por_instancia_herencia_y_despacho_virtual` | `e2e[inicializadores_por_instancia]`, `e2e[objetos_son_referencias]`, `e2e[metodos_se_llaman_entre_si]`, `e2e[acceso_a_null]` | `03_clases_y_herencia.cps` |
| Herencia y despacho dinámico por vtable | `classes.py` (`method`), `ClassLayout.vtable` | `ir/codegen_base::test_inicializadores_por_instancia_herencia_y_despacho_virtual` | `e2e[clases_herencia_y_vtable]`, `ir/interp::test_objeto_con_metodo_sobreescrito_usa_la_vtable`, `test_objetos_comparan_por_identidad` | `03_clases_y_herencia.cps` |
| Programa del curso completo | todo el generador | `test_examples::test_ejemplo_valido` | `tac/e2e::test_program_cps_del_curso`, `tac/e2e::test_ejemplo[*]` | `program.cps` |
| **Casos fallidos:** con errores no se genera TAC | `codegen.compile_source` | `ir/codegen_base::test_programa_con_error_no_genera_tac`, `test_error_sintactico_no_genera_tac` | `tac/e2e::test_programa_con_error_no_genera_tac`, `tac/e2e::test_ejemplos_con_errores_no_se_ejecutan` | `err_01_tipos.cps` → *Código intermedio* vacío |

### Asignación y reciclaje de temporales

| Requisito | Dónde | Tests | Demo |
|---|---|---|---|
| Reciclaje al generar (free-list, menor libre primero) | `compiscript/ir/temps.py` | `ir/temps::test_reutiliza_el_menor_libre`, `test_cadena_de_sumas_usa_un_solo_temporal`, `test_expresion_con_dos_ramas_necesita_dos`, `test_nombres_usados_igual_a_max_live`, `test_reset_al_cerrar_funcion`; `ir/codegen_base::test_temporales_y_emit_binary_reciclan` | **CLI** `--tac` (`t1 = t1 + …`) |
| Vida de temporales y linear scan (Poletto y Sarkar) | `compiscript/ir/liveness.py` | `ir/liveness::test_vida_basica`, `test_nombre_reciclado_son_valores_distintos`, `test_bucle_extiende_el_intervalo_hasta_el_salto_de_regreso`, `test_valor_que_cruza_un_call`, `test_linear_scan_derrama_el_que_termina_mas_tarde`, `test_clases_de_registro_entero_y_flotante`, `test_handler_es_sucesor_de_push_handler`, `test_compact_temps_minimiza_nombres_sin_cambiar_el_programa` | — |
| Temporales separados por llamada (cada marco tiene los suyos) | `ir/interp.py` | `ir/interp::test_cada_llamada_tiene_sus_temporales` | — |

## 3. Tabla de símbolos con nuevas adiciones (10 pts)

| Requisito | Dónde | Tests | Demo |
|---|---|---|---|
| Direcciones (globales, parámetros, locales, atributos) y alineación | `symbols.allocate_storage` | `ir/registros_activacion::test_globales_con_alineacion`, `test_variables_de_bloques_de_nivel_superior_son_globales`, `test_parametros_positivos_y_locales_negativos` | **IDE** *Registros de activación* |
| Registros de activación con campos según su uso | `ActivationRecord` | `ir/registros_activacion::test_encabezado_por_uso`, `test_frame_size_incluye_encabezado_parametros_locales_y_temporales`, `test_registro_main_y_etiquetas`, `test_llamador_de_funcion_con_static_link_tambien_lo_necesita` | **IDE** *Registros de activación*; **CLI** `--runtime` |
| Static link y `hops` para closures | `symbols.hops` | `ir/registros_activacion::test_static_link_y_hops_para_closures`; `ir/interp::test_closure_lee_y_escribe_por_static_link` | `02_funciones_y_closures.cps` (`crearContador_siguiente`) |
| Etiquetas únicas de funciones, métodos y clases | `allocate_storage` | `ir/registros_activacion::test_etiquetas_unicas_si_chocan` | **CLI** `--symbols` |
| Layout de objetos y vtable, `this` como parámetro 0 | `ClassLayout` | `ir/registros_activacion::test_layout_con_herencia_atributos_heredados_primero`, `test_metodos_reciben_this_como_parametro_0`, `test_constructor_heredado` | `03_clases_y_herencia.cps` |
| Anotaciones de la pasada 1 para la pasada 2 | `semantic/`, `AnalysisResult` | `ir/anotaciones_semanticas` (5 tests) | — |
| Volcado JSON/texto (IDE y CLI) | `SymbolTable.to_dict`, `format_runtime` | `ir/registros_activacion::test_volcado_json_y_texto`, `test_programa_con_errores_no_rompe_la_asignacion`; `tac/driver_ide::test_api_compile_devuelve_tac_y_registros`, `test_driver_runtime_muestra_registros_de_activacion` | **IDE** / **CLI** `--runtime` |

## 4. IDE, CLI y documentación (requisitos sin puntaje propio)

| Requisito | Dónde | Tests |
|---|---|---|
| IDE para escribir y compilar código | `ide/app.py` (`/api/compile`, `/api/run`), `ide/static/` | `tac/driver_ide::test_api_compile_devuelve_tac_y_registros`, `test_api_compile_con_errores_no_tiene_tac`, `test_api_compile_error_sintactico`, `test_api_analyze_sigue_igual`, `test_api_run_ejecuta_el_programa`, `test_api_run_reporta_error_en_ejecucion`, `test_api_run_no_ejecuta_con_errores`, `test_api_run_bucle_infinito_no_bloquea`, `test_index_tiene_pestanas_de_tac_y_registros` |
| CLI con TAC | `Driver.py` | `tac/driver_ide::test_driver_tac_numerado`, `test_driver_out_guarda_el_tac`, `test_driver_run_ejecuta_el_tac`, `test_driver_con_error_semantico_no_imprime_tac`, `test_driver_error_en_ejecucion_sale_con_1`, `test_driver_archivo_inexistente` |
| Documentación de arquitectura | `docs/ARQUITECTURA.md` | — |
| Documentación de ejecución | `docs/EJECUCION.md` | — |
| Documentación del lenguaje intermedio | `docs/LENGUAJE_INTERMEDIO.md` | — |

## Guion sugerido para la demo

1. `make test` (toda la batería en verde).
2. IDE con `program.cps`: pestaña *Código intermedio* (TAC numerado), luego
   *Registros de activación* (encabezado por uso de `factorial`, static link de
   las funciones anidadas, vtable de `Dog`), luego *Ejecutar TAC*.
3. `02_funciones_y_closures.cps`: closure con static link (`fp^1[...]`) y su
   salida.
4. `03_clases_y_herencia.cps`: `new`, `$init_Animal`, `method t1, describir` y
   la salida `Toby ... ladra.` (despacho dinámico).
5. `04_control_de_flujo.cps`: `push_handler`/`pop_handler` y el catch en la
   salida.
6. `err_01_tipos.cps`: errores semánticos y la pestaña de TAC vacía.
