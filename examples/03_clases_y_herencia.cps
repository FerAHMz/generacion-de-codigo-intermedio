// Programa válido: clases, constructor, this, herencia y sobreescritura
class Animal {
  let nombre: string;
  let patas: integer = 4;

  function constructor(nombre: string) {
    this.nombre = nombre;
  }

  function hablar(): string {
    return this.nombre + " hace ruido.";
  }

  function describir(): string {
    return this.nombre + " tiene " + this.patas + " patas y " + this.hablar();
  }
}

class Perro : Animal {
  function hablar(): string {
    return this.nombre + " ladra.";
  }
}

let animal: Animal = new Animal("Genérico");
let perro: Perro = new Perro("Toby");
let otro: Animal = new Perro("Rex");     // una subclase es asignable a la superclase

print(animal.describir());
print(perro.describir());
perro.patas = 3;
print(perro.patas);
