// Errores en funciones
function suma(a: integer, b: integer): integer { return a + b; }
function suma(x: integer): integer { return x; }   // función duplicada
function sinRetorno(): integer { let k: integer = 1; }   // falta return
function vacia() { return 5; }                     // retorna valor sin tipo declarado
function tipoMal(): string { return 42; }          // tipo de retorno incorrecto
function dup(a: integer, a: integer) {}            // parámetro duplicado

suma(1);                          // faltan argumentos
suma(1, "dos");                   // tipo de argumento incorrecto
let n: integer = 3;
n();                              // no es una función
let r: integer = suma * 2;        // no se puede multiplicar una función
return 1;                         // return fuera de función
