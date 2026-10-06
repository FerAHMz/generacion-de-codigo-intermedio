// Demo de la tabla de símbolos: entornos, sombras, closures y herencia
let global: integer = 10;

function crearContador(): integer {
  let cuenta: integer = 0;
  function siguiente(): integer {
    cuenta = cuenta + 1;
    return cuenta;
  }
  return siguiente();
}

class Animal {
  let nombre: string;
  function constructor(n: string) { this.nombre = n; }
  function hablar(): string { return this.nombre; }
}
class Perro : Animal {}

let p: Perro = new Perro("Rex");
{
  let global: string = "sombra";
  print(global);
}
