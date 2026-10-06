// Errores de tipos: cada línea marcada produce un error semántico
let a: integer = "texto";        // inicialización con tipo incorrecto
let b: boolean = 1 + true;       // aritmética con boolean
let c: boolean = !"no";          // lógica con string
let d: boolean = 1 == "1";       // comparación incompatible
let e: boolean = "a" < "b";      // relacional con strings
let f: integer[] = [1, "dos"];   // lista heterogénea
const G: integer = 1;
G = 2;                           // asignación a constante
a = true;                        // asignación con tipo incorrecto
let h;                           // sin tipo ni valor inicial
