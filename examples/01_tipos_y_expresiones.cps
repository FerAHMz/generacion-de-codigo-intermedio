// Programa válido: tipos, literales, precedencia y operadores
let a: integer = 10;
let b: string = "hola";
let c: boolean = true;
let d = null;

let x = 5 + 3 * 2;                 // integer (11)
let y = !(x < 10 || x > 20);       // boolean
let z = (1 + 2) * 3;               // agrupamiento
let resto: integer = 17 % 5;
let mensaje: string = "x vale " + x;   // concatenación
let mayor: integer = x > z ? x : z;    // ternario
const PI: integer = 314;

print(mensaje);
print(y && c);
