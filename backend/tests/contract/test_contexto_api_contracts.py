"""Contrato de `GET /api/v1/contexto` (SPEC-031, US1).

Comprueba la forma de la respuesta, que es lo que el shell consume. Si esto cambia,
el cliente se rompe de una forma que la suite del backend no detectaria, porque
cualquier test de este fichero que pase no garantiza que `ContextZone.tsx` siga
leyendo lo que cree.

Dos invariantes que tambien viven aqui y no en los otros ficheros de la feature:

1. **`empresa_id` no se acepta desde el cliente.** Ni en el path, ni en el query, ni
   en el body. Es la constitution III aplicada a la ruta mas expuesta del proyecto,
   la que se llama en cada carga del shell.
2. **El router esta registrado en la app real.** Un router que solo existe en el
   fixture de tests es un router que no existe.
"""

from __future__ import annotations

from typing import Any

import pytest

RUTA = "/api/v1/contexto"

CLAVES_USUARIO = {"id", "email", "nombre", "rol"}
CLAVES_EMPRESA = {"id", "nombre", "nif", "es_activa"}
CLAVES_EJERCICIO = {
    "ejercicio",
    "estado",
    "es_actual",
    "n_asientos",
    "es_seleccionable",
}
ESTADOS = {"abierto", "con_apertura", "cerrado"}


def _cuerpo(cli) -> dict[str, Any]:
    respuesta = cli.get(RUTA, empresa_id=10)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _detalle(respuesta) -> dict[str, Any]:
    cuerpo = respuesta.json()
    assert isinstance(cuerpo.get("detail"), dict), cuerpo
    return cuerpo["detail"]


def test_la_respuesta_tiene_las_cuatro_claves(navegacion_client) -> None:
    cuerpo = _cuerpo(navegacion_client)
    assert set(cuerpo) == {"usuario", "empresa", "ejercicio_activo", "ejercicios"}


def test_la_forma_de_usuario(navegacion_client) -> None:
    usuario = _cuerpo(navegacion_client)["usuario"]
    assert set(usuario) == CLAVES_USUARIO
    assert isinstance(usuario["id"], int)
    assert isinstance(usuario["email"], str) and "@" in usuario["email"]
    assert usuario["rol"] in {"ADMIN", "ACCOUNTANT", "READ_ONLY"}


def test_la_forma_de_empresa(navegacion_client) -> None:
    empresa = _cuerpo(navegacion_client)["empresa"]
    assert set(empresa) == CLAVES_EMPRESA
    assert empresa["id"] == 10
    assert isinstance(empresa["nombre"], str) and empresa["nombre"]
    assert isinstance(empresa["nif"], str)
    assert empresa["es_activa"] is True


def test_la_forma_de_ejercicio(navegacion_client) -> None:
    for ejercicio in _cuerpo(navegacion_client)["ejercicios"]:
        assert set(ejercicio) == CLAVES_EJERCICIO
        assert isinstance(ejercicio["ejercicio"], int)
        assert ejercicio["estado"] in ESTADOS
        assert isinstance(ejercicio["es_actual"], bool)
        assert isinstance(ejercicio["n_asientos"], int)
        assert isinstance(ejercicio["es_seleccionable"], bool)


def test_ejercicio_activo_esta_en_la_lista(navegacion_client) -> None:
    """Invariante que el cliente da por cierto: el activo esta entre los listados.

    Si no lo estuviera, `ExerciseSwitcher` no tendria forma de marcar la opcion
    vigente, y el usuario veria un selector sin seleccion.
    """
    cuerpo = _cuerpo(navegacion_client)
    listados = {f["ejercicio"] for f in cuerpo["ejercicios"]}
    assert cuerpo["ejercicio_activo"]["ejercicio"] in listados


def test_los_cuatro_estados_son_representables(navegacion_client) -> None:
    """El tipo `EstadoEjercicio` del cliente tiene que coincidir con lo que llega.

    Se comprueba que el servidor nunca emite un estado fuera del contrato. Los tres
    valores estan en el contrato porque la UI distingue abierto, con apertura y
    cerrado; un cuarto valor obligaria a tocar el cliente sin avisar.
    """
    for empresa in (10, 20):
        cuerpo = navegacion_client.client.get(
            RUTA,
            headers={
                "Authorization": f"Bearer {navegacion_client.token_de('admin')}",
                "X-Empresa-Activa": str(empresa),
            },
        ).json()
        for ejercicio in cuerpo["ejercicios"]:
            assert ejercicio["estado"] in ESTADOS


def test_un_ejercicio_cerrado_no_es_seleccionable(navegacion_client) -> None:
    cuerpo = _cuerpo(navegacion_client)
    cerrados = [f for f in cuerpo["ejercicios"] if f["estado"] == "cerrado"]
    assert cerrados, "el fixture siembra 2025 cerrado a proposito"
    for ejercicio in cerrados:
        assert ejercicio["es_seleccionable"] is False


def test_un_ejercicio_abierto_si_es_seleccionable(navegacion_client) -> None:
    cuerpo = _cuerpo(navegacion_client)
    abiertos = [f for f in cuerpo["ejercicios"] if f["estado"] == "abierto"]
    assert abiertos
    for ejercicio in abiertos:
        assert ejercicio["es_seleccionable"] is True


def test_el_ejercicio_activo_si_es_seleccionable(navegacion_client) -> None:
    """El activo por definicion se puede usar. Si no, el shell esta mudo."""
    activo = _cuerpo(navegacion_client)["ejercicio_activo"]
    assert activo["es_seleccionable"] is True


@pytest.mark.parametrize(
    ("cabecera", "codigo"),
    [
        ("no-es-un-ano", "ejercicio_invalido"),
        ("25", "ejercicio_invalido"),
        ("1899", "ejercicio_invalido"),
        ("3000", "ejercicio_invalido"),
        ("1999", "ejercicio_no_pertenece_a_empresa"),
    ],
)
def test_cabecera_de_ejercicio_mal_formada(
    navegacion_client, cabecera: str, codigo: str
) -> None:
    """Un valor presente pero invalido es 422 con codigo, no un silencio.

    Se distingue "no has enviado nada" (legitimo, el servidor resuelve) de "has
    enviado basura" (error del cliente), porque no merecen la misma respuesta.
    """
    respuesta = navegacion_client.get(RUTA, empresa_id=10, ejercicio=cabecera)
    assert respuesta.status_code == 422
    assert _detalle(respuesta)["code"] == codigo


def test_sin_cabecera_de_ejercicio_resuelve_el_actual(navegacion_client) -> None:
    """La cabecera es opcional: sin ella, el servidor decide.

    Es lo que permite que el primer render de la aplicacion no tenga que esperar a
    un ejercicio que todavia no ha elegido nadie.
    """
    respuesta = navegacion_client.get(RUTA, empresa_id=10)
    assert respuesta.status_code == 200
    assert respuesta.json()["ejercicio_activo"]["ejercicio"] == 2026


def test_cabecera_vacia_se_trata_como_ausente(navegacion_client) -> None:
    respuesta = navegacion_client.get(RUTA, empresa_id=10, ejercicio="")
    assert respuesta.status_code == 200


def test_cabecera_con_espacios_se_tolera(navegacion_client) -> None:
    """Un espacio alrededor no es un error: los proxies HTTP los anaden."""
    respuesta = navegacion_client.get(RUTA, empresa_id=10, ejercicio=" 2026 ")
    assert respuesta.status_code == 200
    assert respuesta.json()["ejercicio_activo"]["ejercicio"] == 2026


# ---------------------------------------------------------------------------
# constitution III: empresa_id nunca viene del cliente
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "param",
    ["empresa_id", "empresa", "company_id", "tenant_id"],
)
def test_el_cliente_no_puede_elegir_la_empresa_por_query(
    navegacion_client, param: str
) -> None:
    """Un `?empresa_id=` en la URL no cambia la empresa del contexto.

    La empresa sale de `X-Empresa-Activa`, que se valida contra la sesion. Un
    parametro con el mismo nombre en la query es un parametro mas que el backend
    ignora, y esta prueba lo fija: ignorarlo debe seguir siendo asi cuando alguien
    lo anada por error.

    Se llama a `client.get` con la query a mano en vez de usar el helper del
    fixture, porque el helper ya reserva `empresa_id` para la cabecera y no puede
    llevar a la vez el valor de la cabecera y el de la query.
    """
    cabeceras = {
        "Authorization": f"Bearer {navegacion_client.token_de('admin')}",
        "X-Empresa-Activa": "10",
    }
    respuesta = navegacion_client.client.get(
        RUTA, headers=cabeceras, params={param: 20}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["empresa"]["id"] == 10


def test_sin_cabecera_de_empresa_no_hay_contexto(navegacion_client) -> None:
    """La empresa es obligatoria. Sin ella, 403.

    A diferencia del ejercicio, aqui no hay valor por defecto razonable: una empresa
    sin cabecera no tiene sobre que resolver nada.
    """
    respuesta = navegacion_client.client.get(
        RUTA, headers={"Authorization": f"Bearer {navegacion_client.token_de('admin')}"}
    )
    assert respuesta.status_code == 403


# ---------------------------------------------------------------------------
# El router existe en la app real
# ---------------------------------------------------------------------------


def test_el_router_esta_registrado_en_la_app() -> None:
    """Un router que solo vive en el fixture de tests es un router que no existe."""
    from fastapi.routing import APIRoute

    from api.routes_registry import _iter_api_routes, rutas_sin_permiso
    from main import app

    paths = [
        r.path
        for r in _iter_api_routes(list(app.routes))
        if isinstance(r, APIRoute)
    ]
    assert RUTA in paths
    # El guard de SPEC-015: toda ruta con permiso. Este endpoint no puede eximirse.
    assert rutas_sin_permiso(app) == []


def test_la_ruta_no_colisiona_con_ninguna_otra() -> None:
    """Mismo metodo y mismo path que otra ruta seria un sombreado silencioso."""
    from collections import Counter

    from fastapi.routing import APIRoute

    from api.routes_registry import _iter_api_routes
    from main import app

    pares = [
        (metodo, ruta.path)
        for ruta in _iter_api_routes(list(app.routes))
        if isinstance(ruta, APIRoute)
        for metodo in (sorted(ruta.methods) if ruta.methods else [])
        if metodo not in ("HEAD", "OPTIONS")
    ]
    repetidos = [par for par, n in Counter(pares).items() if n > 1]
    assert repetidos == []
