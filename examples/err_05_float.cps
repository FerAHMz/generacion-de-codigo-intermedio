// Errores con float
let i: integer = 1.5;             // float no cabe en integer
let f: float = 2.5;
let j: integer = f + 1;           // la suma con float es float
let r = 5.0 % 2;                  // % solo admite integer
let xs: integer[] = [1, 2];
let x: integer = xs[1.0];         // índice float
function doble(n: integer): integer { return n * 2; }
doble(1.5);                       // argumento float en parámetro integer
function e(): integer { return 2.5; }   // retorno float en función integer
let b: float = 1.5 + true;        // aritmética con boolean
