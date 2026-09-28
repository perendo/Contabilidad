"""La barra de favoritos respeta el contrato de API (SPEC-031, US4, T044/T072).

No hay runner de tests en el frontend, asi que se comprueba lo que de verdad puede
diverge: el verbo y la ruta de cada llamada, y la forma de la respuesta. Un componente
que llame a `POST /favoritos/{d}/desmarcar` compila, pasa `tsc`, pasa ESLint y rompe en
produccion con un 404: por eso hace falta un test que lo diga.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
BARRA = RAIZ / "frontend" / "src" / "components" / "navigation" / "FavoritesBar.tsx"
CLIENT = RAIZ / "frontend" / "src" / "services" / "client.ts"


@pytest.fixture(scope="module")
def barra() -> str:
    return BARRA.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def verbs_client() -> set[str]:
    texto = CLIENT.read_text(encoding="utf-8")
    return set(re.findall(r"export (?:async )?function (\w+)", texto))


def test_desmarcar_usa_delete_y_la_ruta_del_contrato(barra: str) -> None:
    """`DELETE /api/v1/favoritos/{destino}`, no un POST a un sublenguaje de acciones.

    El fallo que evita: escribir `post(.../desmarcar)`. Compila, pasa los tipos, pasa
    ESLint y devuelve 404 en el servidor, porque no existe esa ruta. Es el modo de fallo
    mas caro de esta feature: invisible hasta que alguien pulsa el boton.
    """
    assert "remove(" in barra, "desmarcar debe usar el verbo DELETE del cliente"
    # Se buscan las LLAMADAS, no la palabra: el comentario que explica por que no se
    # usa `/desmarcar` contiene esa cadena y haria fallar el test.
    llamadas = re.findall(r"(?:get|post|put|patch|remove)[\(<][^)\n]*", barra)
    assert not any("/desmarcar" in c for c in llamadas), "no existe esa ruta"
    assert re.search(r"remove\(\s*`/api/v1/favoritos/\$\{destino\}`\s*\)", barra), (
        "la ruta debe ser /api/v1/favoritos/{destino}"
    )


def test_leer_usa_get_sobre_la_raiz(barra: str) -> None:
    assert 'get<RespuestaFavoritos>("/api/v1/favoritos")' in barra


def test_no_usa_put_ni_patch_para_desmarcar(barra: str) -> None:
    """`PUT` marca y `PATCH` reordena. Desmarcar no es ninguna de las dos cosas.

    Confusion tipica al reutilizar un cliente: llamar a `put` para "actualizar" el
    favorito, cuando `PUT` lo crearia de nuevo.
    """
    cuerpo = barra[barra.index("const desmarcar") : barra.index("if (datos === null)")]
    assert "put(" not in cuerpo
    assert "patch(" not in cuerpo
    assert "post(" not in cuerpo


def test_el_verbatim_usa_el_tamano_de_respuesta_del_servidor(barra: str) -> None:
    """La cuenta de "N guardados, M visibles" sale de la respuesta, no de un contador local.

    Un `MAXIMO_VISIBLES` en el cliente es un segundo numero que puede quedar viejo
    respecto al servidor, y la interfaz avisaria de mas o de menos. Aqui no hay: se
    comparan `total` y `visibles` tal cual llegan.
    """
    assert "datos.total > datos.visibles" in barra
    assert "{datos.total} guardados, {datos.visibles} visibles" in barra


def test_un_favorito_no_disponible_se_ofrece_para_retirar(barra: str) -> None:
    """FR-024: se conserva, se avisa y se puede quitar. Ocultarlo sin mas no basta.

    Un favorito cuya ruta se movio sigue en el servidor. Si el cliente lo oculta y no
    ofrece nada, el usuario tiene un favorito que no puede ver ni quitar: el servidor lo
    conserva y el usuario no puede limpiarlo.
    """
    assert "retiradobles" in barra, "debe separar los que ya no se pueden abrir"
    assert "Retirar" in barra, "debe ofrecer la accion de retirarlos"
    assert "line-through" in barra, "deben verse tachados, no simplemente ausentes"


def test_sin_favoritos_utilizables_y_sin_retirables_no_hay_seccion(barra: str) -> None:
    """FR-027: sin favoritos no hay seccion. Ni un hueco vacio."""
    assert "if (utilizables.length === 0 && retiradobles.length === 0) return null;" in barra


def test_un_fallo_al_leer_no_rompe_la_pagina(barra: str) -> None:
    """La barra es aditiva: si `/favoritos` falla, la pagina sigue siendo la pagina."""
    assert "catch" in barra
    assert "setDatos(null)" in barra


def test_no_hay_una_ruta_de_desplegar_inventada(barra: str) -> None:
    """La lectura llega recortada a 5 y no hay endpoint que devuelva el resto.

    Un boton de "mostrar mas" que llamara a una ruta inexistente seria otro 404
    silencioso. Aqui el aviso es texto, que es lo que el contrato permite.
    """
    assert "/favoritos/todos" not in barra
    assert "desplegados" not in barra, "no hay nada que desplegar: la lista ya viene recortada"


def test_el_verb_existe_de_verdad_en_el_cliente(barra: str, verbs_client: set[str]) -> None:
    """El verbo que usa la barra existe en `services/client.ts`.

    Se comprueba contra el cliente real y no contra una constante duplicada aqui, para
    que renombrar `remove` en el cliente rompa este test en vez de romper la barra.
    """
    usados = set(re.findall(r"\b(get|post|put|patch|remove)\s*[<(]", barra))
    assert usados, "no se ha detectado ninguna llamada al cliente"
    assert usados <= verbs_client, f"verbos inexistentes: {usados - verbs_client}"
