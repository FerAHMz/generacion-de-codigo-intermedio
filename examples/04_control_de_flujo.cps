// Programa válido: todas las estructuras de control
let notas: integer[] = [90, 85, 100, 40];
let matriz: integer[][] = [[1, 2], [3, 4]];
let i: integer = 0;

if (notas[0] > 60) { print("aprobado"); } else { print("reprobado"); }

while (i < 3) { i = i + 1; }
do { i = i - 1; } while (i > 0);

for (let j: integer = 0; j < 3; j = j + 1) { print(j); }

foreach (n in notas) {
  if (n < 60) { continue; }
  if (n == 100) { break; }
  print(n);
}

switch (i) {
  case 0: print("cero"); break;
  case 1: print("uno");
  default: print("otro");
}

try {
  let peligro: integer = notas[100];
} catch (err) {
  print("Error atrapado: " + err);
}

print(matriz[1][0]);
