// Errores de control de flujo, clases y listas
if (1) { print("no boolean"); }
while ("si") { }
break;                            // fuera de bucle
continue;                         // fuera de bucle

class Animal {
  let nombre: string;
  function constructor(n: string) { this.nombre = n; }
  function hablar(): string { return this.nombre; }
}
class Gato : Felino { }           // padre inexistente
class Perro : Animal {
  function hablar(): integer { return 1; }   // firma distinta al método heredado
}

let a: Animal = new Animal();     // constructor sin argumentos
print(a.edad);                    // atributo inexistente
a.nombre = 5;                     // tipo incorrecto en propiedad
a.hablar(1);                      // argumentos de más
this.nombre = "x";                // this fuera de clase

let xs: integer[] = [1, 2, 3];
let s: string = xs["0"];          // índice no entero
let t: integer = xs[-1];          // índice negativo
let u: integer = a[0];            // indexar un objeto
foreach (v in 5) { }              // iterar algo que no es arreglo

function f(): integer {
  return 1;
  print("nunca");                 // código muerto
}
