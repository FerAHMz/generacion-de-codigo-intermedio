// Programa válido: funciones, recursión, funciones anidadas y closures
function saludar(nombre: string): string {
  return "Hola " + nombre;
}

function factorial(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * factorial(n - 1);
}

function crearContador(): integer {
  let cuenta: integer = 0;
  function siguiente(): integer {
    cuenta = cuenta + 1;   // captura `cuenta` del entorno externo
    return cuenta;
  }
  siguiente();
  return siguiente();
}

// Se puede llamar a una función declarada más abajo
function usaDespues(): integer { return declaradaDespues(2); }
function declaradaDespues(k: integer): integer { return k * 2; }

print(saludar("Mundo"));
print(factorial(5));
print(crearContador());
print(usaDespues());
