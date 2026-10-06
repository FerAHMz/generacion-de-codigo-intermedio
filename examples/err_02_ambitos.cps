// Errores de ámbito
print(noExiste);                 // variable no declarada
let x: integer = 1;
let x: string = "dos";           // redeclaración en el mismo ámbito
{
  let interna: integer = 5;
}
print(interna);                  // fuera del bloque donde se declaró
function f(p: integer) {
  let p: string = "x";           // redeclara el parámetro
}
print(p);                        // parámetro no visible afuera
