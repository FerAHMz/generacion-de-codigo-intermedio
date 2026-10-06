"""Interfaz entre pasadas: la fase semántica deja anotado, para cada nodo,
el símbolo al que resuelve y el entorno que abre. El generador de TAC
consume estas anotaciones en lugar de volver a resolver nombres."""

from compiscript.generated.CompiscriptParser import CompiscriptParser as P
from compiscript.semantic import analyze
from compiscript.symbols import ScopeKind, SymbolKind


def _nodes(tree, cls):
    out, stack = [], [tree]
    while stack:
        n = stack.pop()
        if isinstance(n, cls):
            out.append(n)
        stack.extend(getattr(n, "children", None) or [])
    return out


def test_identificador_resuelve_al_simbolo_correcto_con_sombra():
    r = analyze("let x: integer = 1; { let x: string = \"a\"; print(x); } print(x);")
    assert r.ok
    ids = _nodes(r.tree, P.IdentifierExprContext)
    syms = {id(r.node_symbols[i]): r.node_symbols[i] for i in ids}
    assert len(syms) == 2                       # el x interno y el x global son distintos
    assert {str(s.type) for s in syms.values()} == {"integer", "string"}


def test_declaracion_queda_ligada_a_su_simbolo():
    r = analyze("let a: integer = 3;")
    decl = _nodes(r.tree, P.VariableDeclarationContext)[0]
    assert r.node_symbols[decl].name == "a"


def test_cada_estructura_registra_su_entorno():
    src = """
    function f(n: integer): integer { return n; }
    class A { let v: integer; }
    let xs: integer[] = [1, 2];
    foreach (e in xs) { print(e); }
    for (let i: integer = 0; i < 2; i = i + 1) { print(i); }
    while (false) { }
    switch (1) { case 1: print(1); default: print(0); }
    try { print(1); } catch (err) { print(err); }
    """
    r = analyze(src)
    assert r.ok, list(r.errors)
    kinds = {type(ctx).__name__: sc.kind for ctx, sc in r.node_scopes.items()}
    assert kinds["FunctionDeclarationContext"] == ScopeKind.FUNCTION
    assert kinds["ClassDeclarationContext"] == ScopeKind.CLASS
    assert kinds["ForeachStatementContext"] == ScopeKind.LOOP
    assert kinds["ForStatementContext"] == ScopeKind.LOOP
    assert kinds["SwitchStatementContext"] == ScopeKind.SWITCH
    assert kinds["SwitchCaseContext"] == ScopeKind.BLOCK
    assert kinds["DefaultCaseContext"] == ScopeKind.BLOCK
    assert kinds["TryCatchStatementContext"] == ScopeKind.BLOCK


def test_acceso_a_miembro_y_new_quedan_ligados():
    r = analyze("class A { let v: integer; } let a: A = new A(); print(a.v);")
    assert r.ok
    access = _nodes(r.tree, P.PropertyAccessExprContext)[0]
    assert r.node_symbols[access].kind == SymbolKind.FIELD
    new = _nodes(r.tree, P.NewExprContext)[0]
    assert r.node_symbols[new].kind == SymbolKind.CLASS
