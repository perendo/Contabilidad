"""El cliente y `GET /permisos/mis-permisos` hablan el mismo idioma (SPEC-031, US1).

Este fichero existe por un bug real y silencioso. `SessionContext` pedia los permisos
como `string[]` y los traducía con `String(p).split(":")`, pero la respuesta real de
SPEC-015 es una lista de objetos `{modulo, operacion}`. La consecuencia era:

    String({modulo: "acct", operacion: "ver"})  ->  "[object Object]"
    "[object Object]".split(":")                ->  ["[object", " Object]"]

Un par que no coincide con ningun permiso. Y como el panel oculta todo destino cuyo
permiso no este en la lista, con la llamada **exitosa** el shell se quedaba sin ningun
destino visible. El unico sintoma era una aplicacion con la barra de contexto y nada
mas, en produccion, sin error en consola y con las puertas de `tsc` y ESLint en verde.

Lo que se comprueba aqui es que la forma que el cliente declara coincide con la que el
servidor produce. Es una comparacion de contrato entre dos languages distintos, y por eso
es un test de texto y no de tipos.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
CONTEXTO = RAIZ / "frontend" / "src" / "components" / "navigation" / "SessionContext.tsx"
MATRIZ = RAIZ / "backend" / "src" / "services" / "security" / "matriz.py"
SUPERFICIES = RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts"


@pytest.fixture(scope="module")
def contexto_ts() -> str:
    return CONTEXTO.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def matriz_py() -> str:
    return MATRIZ.read_text(encoding="utf-8")


def test_el_servidor_devuelve_objetos_modulo_operacion(matriz_py: str) -> None:
    """Se fija la forma real del servidor.

    Si esta afirmacion falla, el servidor cambio y el cliente tendra que cambiar con
    el. Se lee el `return` de `mis_permisos` en vez de fiarse de la memoria.
    """
    i = matriz_py.index("async def mis_permisos")
    cuerpo = matriz_py[i : i + 900]
    assert '"modulo": f["modulo"]' in cuerpo
    assert '"operacion": f["operacion"]' in cuerpo


def test_el_cliente_tipa_la_forma_real(contexto_ts: str) -> None:
    """`permisos` se tipa como la lista de objetos que el servidor produce.

    El fallo original fue una tipacion que no describia la respuesta. Con la forma
    correcta declarada, `String(p).split(":")` deja de compilar conceptualmente y el
    normalizador tiene que existir.
    """
    assert "interface PermisoCrudo" in contexto_ts
    assert re.search(r"interface PermisoCrudo\s*\{[^}]*modulo:\s*string", contexto_ts)
    assert re.search(r"interface PermisoCrudo\s*\{[^}]*operacion:\s*string", contexto_ts)


def test_el_cliente_no_traduce_objetos_con_String(contexto_ts: str) -> None:
    """El fallo exacto: `String(p).split(":")` sobre un objeto.

    Se busca la expresion, no el comentario que explica por que no debe usarse, igual
    que en el test de la barra de favoritos.
    """
    codigo = re.sub(r"/\*.*?\*/", "", contexto_ts, flags=re.DOTALL)
    codigo = re.sub(r"//[^\n]*", "", codigo)
    assert "String(p)" not in codigo
    assert not re.search(r"String\s*\(\s*\w+\s*\)\.split\(", codigo)


def test_el_normalizador_acepta_las_tres_formas(contexto_ts: str) -> None:
    """Objetos (la forma real), `"modulo:operacion"` y `["modulo", "operacion"]`."""
    i = contexto_ts.index("function normalizarPermiso")
    cuerpo = contexto_ts[i : i + 2000]
    assert 'typeof p === "string"' in cuerpo
    assert "Array.isArray(p)" in cuerpo
    assert 'typeof p === "object"' in cuerpo
    # El operador de modulo no se inventa: sale de la respuesta.
    assert "p.modulo" in cuerpo


def test_una_entrada_irrecuperable_se_descarta_y_no_filtra(contexto_ts: str) -> None:
    """Un permiso que no se puede leer se descarta; nunca se convierte en un par vacio.

    Es la parte sutil. Devolver `[["", ""]]` seria mas estricto que devolver `[]`, y
    "sin permisos" significa "sin restricciones" mientras que un par falso significa
    "oculto": un dato ilegible terminaria cerrando el panel en lugar de abrirlo.
    """
    i = contexto_ts.index("function normalizarPermiso")
    cuerpo = contexto_ts[i : i + 2000]
    assert "return []" in cuerpo, "las entradas irrecuperables se descartan"
    # Los tres caminos que no pueden leerse (string sin modulo, array sin modulo, valor
    # que no es ninguno de los tres) devuelven lista vacia, nunca un par inventado.
    assert cuerpo.count("return []") == 3, (
        f"se esperaban 3 descartes y hay {cuerpo.count('return []')}"
    )


def test_un_fallo_al_pedir_los_permisos_no_cierra_la_navegacion(contexto_ts: str) -> None:
    """Ante un error, la lista queda vacia, que el panel lee como "sin restricciones"."""
    i = contexto_ts.index("/api/v1/permisos/mis-permisos")
    rama_error = contexto_ts[i : i + 500]
    assert "catch" in rama_error
    assert "setPermisos([])" in rama_error


def test_el_filtro_trata_lista_vacia_como_sin_restricciones() -> None:
    """La lista vacia tiene que significar "todo permitido", no "nada permitido".

    Es el otro extremo del mismo bug, y por eso se fija aqui y no en el test de
    `SessionContext`: `[]` es el estado inicial y tambien el resultado de un fallo al
    pedir la matriz. Con un `permisos === undefined` desnudo, el panel nascia vacio y se
    quedaba vacio para siempre si la llamada fallaba. El criterio va ahora en un solo
    sitio, `sinRestricciones`, y estos componentes lo usan.
    """
    superficies = (RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts").read_text(
        encoding="utf-8"
    )
    i = superficies.index("export function sinRestricciones")
    cuerpo = superficies[i : i + 400]
    assert "permisos === undefined" in cuerpo
    assert "permisos.length === 0" in cuerpo, "la lista vacia tambien es 'sin informacion'"
    # Type guard: es lo que permite `sinRestricciones(p) || p.some(...)` estrechar.
    assert "permisos is undefined" in cuerpo

    for componente in ("SurfacePanel.tsx", "FavoritesBar.tsx", "DestinationRail.tsx", "MobileNav.tsx"):
        texto = (RAIZ / "frontend" / "src" / "components" / "navigation" / componente).read_text(
            encoding="utf-8"
        )
        assert "sinRestricciones(permisos)" in texto, (
            f"{componente} debe usar el helper, no su propio criterio"
        )
        assert "permisos === undefined" not in texto, (
            f"{componente} tiene el criterio duplicado y se puede quedar viejo"
        )


def test_los_destinos_declaran_el_mismo_uso_de_permiso() -> None:
    """El par `(modulo, operacion)` del cliente y el `Permiso` de `surfaces.ts` encajan."""
    texto = SUPERFICIES.read_text(encoding="utf-8")
    assert re.search(r"export type Permiso = readonly \[string, string\]", texto)
    assert re.search(r'ACCESO_CONTEXTO: Permiso = \["[a-z]+", "[a-z]+"\]', texto)
