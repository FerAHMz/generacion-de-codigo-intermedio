"""5. Clases y objetos."""

from .helpers import assert_error, assert_ok

ANIMAL = """
class Animal {
  let nombre: string;
  function constructor(nombre: string) { this.nombre = nombre; }
  function hablar(): string { return this.nombre + " hace ruido."; }
}
"""


def test_clase_y_acceso_a_miembros():
    assert_ok(ANIMAL + 'let a: Animal = new Animal("Toby"); print(a.nombre); print(a.hablar());')


def test_atributo_inexistente():
    assert_error(ANIMAL + 'let a: Animal = new Animal("x"); print(a.edad);', "no tiene un atributo o método llamado 'edad'")


def test_metodo_inexistente():
    assert_error(ANIMAL + 'let a: Animal = new Animal("x"); a.correr();', "no tiene un atributo o método llamado 'correr'")


def test_asignacion_a_propiedad_tipo_incorrecto():
    assert_error(ANIMAL + 'let a: Animal = new Animal("x"); a.nombre = 5;', "asignar", "integer", "string")


def test_constructor_argumentos_incorrectos():
    assert_error(ANIMAL + "let a: Animal = new Animal();", "constructor de 'Animal'", "espera 1")


def test_constructor_tipo_de_argumento():
    assert_error(ANIMAL + "let a: Animal = new Animal(42);", "constructor de 'Animal'", "string")


def test_clase_sin_constructor_no_acepta_argumentos():
    assert_error("class Vacia {} let v: Vacia = new Vacia(1);", "no define constructor")


def test_herencia_hereda_miembros():
    assert_ok(ANIMAL + """
        class Perro : Animal { function ladrar(): string { return this.nombre + " ladra."; } }
        let p: Perro = new Perro("Rex"); print(p.hablar()); print(p.ladrar());
    """)


def test_subclase_asignable_a_superclase():
    assert_ok(ANIMAL + 'class Perro : Animal {} let a: Animal = new Perro("Rex");')


def test_superclase_no_asignable_a_subclase():
    assert_error(ANIMAL + 'class Perro : Animal {} let p: Perro = new Animal("Rex");', "inicializar")


def test_sobreescritura_misma_firma():
    assert_ok(ANIMAL + 'class Perro : Animal { function hablar(): string { return "guau"; } }')


def test_sobreescritura_firma_distinta():
    assert_error(ANIMAL + "class Perro : Animal { function hablar(): integer { return 1; } }", "firma distinta")


def test_clase_padre_inexistente():
    assert_error("class Perro : Animal {}", "clase padre 'Animal' no está definida")


def test_clase_duplicada():
    assert_error("class A {} class A {}", "clase 'A' ya fue declarada")


def test_this_fuera_de_clase():
    assert_error("this.x = 1;", "'this' solo puede usarse")


def test_this_en_funcion_libre():
    assert_error("function f() { print(this); }", "'this' solo puede usarse")


def test_this_en_metodo_valido():
    assert_ok("class C { let v: integer = 1; function get(): integer { return this.v; } }")


def test_metodos_se_llaman_entre_si_sin_importar_orden():
    assert_ok("class C { function a(): integer { return this.b(); } function b(): integer { return 1; } }")


def test_acceso_punto_en_no_objeto():
    assert_error("let x: integer = 1; print(x.algo);", "no se puede acceder a '.algo'")


def test_tipo_de_clase_no_definido():
    assert_error("let a: Fantasma;", "tipo 'Fantasma' no está definido")


def test_clase_usada_como_tipo_antes_de_declararse():
    assert_ok("let a: Animal = new Animal(); class Animal {}")
