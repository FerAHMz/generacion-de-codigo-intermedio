// Programa válido: tipo float y promoción integer -> float
const PI: float = 3.1416;
let radio: float = 2;                 // un integer se promueve a float
let area: float = PI * radio * radio;
let mitad: float = 7 / 2.0;
let entero: integer = 7 / 2;          // división entera
let mayor: boolean = area > 10;       // comparación entre numéricos
let lista: float[] = [1, 2.5, 3];     // el arreglo se promueve a float[]

function promedio(a: float, b: float): float {
  return (a + b) / 2;
}

print("Área: " + area);
print(promedio(3, 4.5));
print(-mitad);
