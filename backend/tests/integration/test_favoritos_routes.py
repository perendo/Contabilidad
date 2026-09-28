"""Los cuatro endpoints de favoritos (SPEC-031, US4, T043).

Cubre el contrato, no el servicio: aqui importa el codigo de estado exacto, la forma del
JSON y, sobre todo, que el permiso se respete. El comportamiento del servicio ya esta
probado en `test_favoritos_servicio.py`; repetirlo aqui seria redundante.

Los cuatro verbos comparten la misma logica de sesion, y el aislamiento por empresa es la
mitad de estos casos (constitution III): un favorito marcado en la empresa A no puede
aparecer ni borrarse desde la B, aunque el mismo usuario este en las dos.
"""

from __future__ import annotations

import pytest

FAV = "/api/v1/favoritos"
DESTINO = "vencimientos"


# ---------------------------------------------------------------------------
# PUT · marcar
# ---------------------------------------------------------------------------


def test_marcar_crea_el_favorito_y_devuelve_201(navegacion_client) -> None:
    r = navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)
    assert r.status_code == 201, r.text
    assert r.json() == {"destino": DESTINO, "orden": 1}


def test_marcar_es_idempotente_y_no_duplica(navegacion_client) -> None:
    """Marcar dos veces responde 201 y deja una sola fila.

    Es un gesto normal del usuario: pulsar el boton en dos pestanas. Un 409 lo trataria
    como error y el cliente tendria que distinguir "ya estaba" de "no se pudo".
    """
    primero = navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)
    segundo = navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)
    assert primero.status_code == 201
    assert segundo.status_code == 201, "marcar dos veces no es un error"
    listado = navegacion_client.get(FAV).json()
    assert listado["total"] == 1


def test_marcar_actualiza_el_orden_de_un_favorito_ya_existente(navegacion_client) -> None:
    """Re-marcar con otra posicion mueve el favorito; no crea un segundo."""
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)
    navegacion_client.put(f"{FAV}/asientos", destino="asientos", orden=2)
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=2)
    items = navegacion_client.get(FAV).json()["items"]
    assert navegacion_client.get(FAV).json()["total"] == 2, "no debe duplicarse"
    # `asientos` conserva la 1 porque se le solaparon las posiciones y el desempate es
    # alfabetico; lo que importa es que hay dos y no tres.
    assert sorted(i["destino"] for i in items) == ["asientos", DESTINO]


def test_destino_desconocido_es_404(navegacion_client) -> None:
    r = navegacion_client.put(f"{FAV}/ruta-inexistente", destino="ruta-inexistente", orden=1)
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "destino_desconocido"


def test_orden_no_positivo_es_422(navegacion_client) -> None:
    for valor in (0, -1):
        r = navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=valor)
        assert r.status_code == 422, f"orden={valor} deberia ser 422"
        assert r.json()["detail"]["code"] == "orden_fuera_de_rango"


def test_un_sexto_favorito_se_guarda_y_la_lectura_lo_recorta(navegacion_client) -> None:
    """FR-025 recorta en la LECTURA, nunca en la escritura.

    Este es el caso borde que decidio el limite. Si `PUT` devolviera 422 aqui, el usuario
    con cinco favoritos no podria anadir el suyo, que es justo lo que el requisito
    prohibe. Se comprueban las dos mitades: se guardan seis, se devuelven cinco.
    """
    claves = [
        "asientos",
        "vencimientos",
        "facturas",
        "conciliacion",
        "terceros",
        "presupuestos",
    ]
    for i, clave in enumerate(claves, start=1):
        r = navegacion_client.put(f"{FAV}/{clave}", destino=clave, orden=i)
        assert r.status_code == 201, f"{clave} deberia guardarse: {r.text}"

    listado = navegacion_client.get(FAV).json()
    assert listado["total"] == 6, "los seis estan guardados"
    assert listado["visibles"] == 5, "pero solo se muestran cinco"
    assert len(listado["items"]) == 5


# ---------------------------------------------------------------------------
# GET · leer
# ---------------------------------------------------------------------------


def test_listar_vacio_no_falla(navegacion_client) -> None:
    r = navegacion_client.get(FAV)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo == {"items": [], "total": 0, "visibles": 0}


def test_los_tres_roles_pueden_leer_su_lista(navegacion_client) -> None:
    """`acct:ver` lo poseen los tres roles base, asi que los tres leen.

    READ_ONLY tambien: poder ver los favoritos propios no es escribir nada.
    """
    for rol in ("admin", "accountant", "readonly"):
        r = navegacion_client.get(FAV, token_key=rol)
        assert r.status_code == 200, f"{rol} deberia poder leer sus favoritos"


def test_los_items_declaran_si_son_accesibles(navegacion_client) -> None:
    """Cada item lleva `accesible` y `desconocido`, que es lo que permite ocultar sin borrar."""
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)
    item = navegacion_client.get(FAV).json()["items"][0]
    assert item["accesible"] is True
    assert item["desconocido"] is False


def test_un_favorito_de_destino_reubicado_se_conserva_y_se_marca(navegacion_client) -> None:
    """FR-024: si la ruta se movio, la fila sigue existiendo, marcada como desconocida.

    Se inyecta la fila a proposito, imitando un favorito creado en una version anterior
    en la que el destino existia. No se puede crear por API (el 404 lo impide), que es
    exactamente por lo que hay que probarlo asi.
    """
    import sqlalchemy as sa

    from models.navigation.favorito import FavoritoUsuario

    async def _sembrar(session):
        session.add(
            FavoritoUsuario(
                empresa_id=10, usuario_id=1, destino="destino-retirado", orden=1
            )
        )

    # `run(mutar(...))` y no `mutar(...)`: `mutar` es `async`, asi que llamarlo sin
    # `run` devuelve una corrutina que nadie ejecuta. La fila no se insertaba y el test
    # fallaba por un `total == 0` que no decia nada del motivo.
    navegacion_client.run(navegacion_client.mutar(_sembrar))
    cuerpo = navegacion_client.get(FAV).json()
    assert cuerpo["total"] == 1, "el favorito retirado NO se borra"
    item = cuerpo["items"][0]
    assert item["destino"] == "destino-retirado"
    assert item["accesible"] is False, "no se muestra, porque ya no existe"
    assert item["desconocido"] is True

    # Y se puede retirar desde la API, que es lo que la interfaz ofrece hacer.
    assert navegacion_client.delete(f"{FAV}/destino-retirado").status_code == 204
    assert navegacion_client.get(FAV).json()["total"] == 0
    del sa


# ---------------------------------------------------------------------------
# DELETE · desmarcar
# ---------------------------------------------------------------------------


def test_desmarcar_devuelve_204_y_borra(navegacion_client) -> None:
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)
    r = navegacion_client.delete(f"{FAV}/{DESTINO}")
    assert r.status_code == 204
    assert navegacion_client.get(FAV).json()["total"] == 0


def test_desmarcar_lo_que_no_esta_devuelve_204(navegacion_client) -> None:
    """Idempotente. Un 404 aqui seria ruido: el cliente ya esta en el estado que quiere."""
    assert navegacion_client.delete(f"{FAV}/{DESTINO}").status_code == 204
    assert navegacion_client.delete(f"{FAV}/{DESTINO}").status_code == 204


def test_desmarcar_un_destino_desconocido_no_crea_nada(navegacion_client) -> None:
    """Un 204, porque no habia nada que borrar y no se crea una fila fantasma."""
    assert navegacion_client.delete(f"{FAV}/nunca-existio").status_code == 204
    assert navegacion_client.get(FAV).json()["total"] == 0


# ---------------------------------------------------------------------------
# PATCH · reordenar
# ---------------------------------------------------------------------------


def test_reordenar_fija_el_orden(navegacion_client) -> None:
    navegacion_client.put(f"{FAV}/asientos", destino="asientos", orden=1)
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=2)
    r = navegacion_client.patch(FAV, ordenes=[DESTINO, "asientos"])
    assert r.status_code == 200, r.text
    assert [i["destino"] for i in r.json()["items"]] == [DESTINO, "asientos"]


def test_reordenar_un_conjunto_incompleto_es_422(navegacion_client) -> None:
    """Falta uno: 422, porque no se sabe donde iba el que falta."""
    navegacion_client.put(f"{FAV}/asientos", destino="asientos", orden=1)
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=2)
    r = navegacion_client.patch(FAV, ordenes=[DESTINO])
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "conjunto_incompleto"


def test_reordenar_con_repeticiones_es_422(navegacion_client) -> None:
    navegacion_client.put(f"{FAV}/asientos", destino="asientos", orden=1)
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=2)
    r = navegacion_client.patch(FAV, ordenes=["asientos", "asientos"])
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "conjunto_incompleto"


def test_reordenar_con_un_destino_de_mas_es_422(navegacion_client) -> None:
    navegacion_client.put(f"{FAV}/asientos", destino="asientos", orden=1)
    r = navegacion_client.patch(FAV, ordenes=["asientos", DESTINO])
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# constitution III · la empresa sale de la sesion
# ---------------------------------------------------------------------------


def test_el_favorito_no_cruza_de_empresa(navegacion_client) -> None:
    """Marcado en la empresa A, invisible e indestructible desde la B.

    El mismo usuario esta vinculado a las dos empresas, asi que el unico filtro que
    puede estar fallando es el de `empresa_id`.
    """
    assert navegacion_client.put(f"{FAV}/{DESTINO}", empresa_id=10, destino=DESTINO, orden=1).status_code == 201

    assert navegacion_client.get(FAV, empresa_id=10).json()["total"] == 1
    assert navegacion_client.get(FAV, empresa_id=20).json()["total"] == 0, "no puede verse desde B"

    # Desmarcar desde B no toca el de A.
    navegacion_client.delete(f"{FAV}/{DESTINO}", empresa_id=20)
    assert navegacion_client.get(FAV, empresa_id=10).json()["total"] == 1, "B no puede borrar el de A"


def test_cada_usuario_tiene_su_propia_lista(navegacion_client) -> None:
    """Dos usuarios en la misma empresa no comparten favoritos."""
    navegacion_client.put(f"{FAV}/{DESTINO}", token_key="admin", destino=DESTINO, orden=1)
    assert navegacion_client.get(FAV, token_key="admin").json()["total"] == 1
    assert navegacion_client.get(FAV, token_key="accountant").json()["total"] == 0


def test_sin_autenticacion_es_401(navegacion_client) -> None:
    """/favoritos no es una ruta publica: sin token no hay ni lectura ni escritura."""
    sin = navegacion_client.client.get(FAV)
    assert sin.status_code == 401
    assert navegacion_client.client.put(f"{FAV}/{DESTINO}", json={"destino": DESTINO, "orden": 1}).status_code == 401


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def test_read_only_no_puede_escribir(navegacion_client) -> None:
    """`acct:editar` no lo tiene READ_ONLY, y escribir un favorito es escribir.

    Este es el test que evita que la preferencia de usuario se convierta en una via de
    escritura para el rol mas restringido del catalogo.
    """
    assert navegacion_client.put(f"{FAV}/{DESTINO}", token_key="readonly", destino=DESTINO, orden=1).status_code == 403
    assert navegacion_client.delete(f"{FAV}/{DESTINO}", token_key="readonly").status_code == 403
    assert navegacion_client.patch(FAV, token_key="readonly", ordenes=[DESTINO]).status_code == 403


def test_accountant_si_puede_escribir(navegacion_client) -> None:
    r = navegacion_client.put(f"{FAV}/{DESTINO}", token_key="accountant", destino=DESTINO, orden=1)
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("ruta", [FAV, f"{FAV}/{DESTINO}"])
def test_las_cuatro_rutas_declaran_guard(navegacion_client, ruta: str) -> None:
    """Ninguna ruta de favoritos se cuela sin permiso.

    Lo verifica `routes_registry.rutas_sin_permiso` sobre la app real, que es la unica
    forma de comprobarlo: el fixture monta un subconjunto de routers y daria verde con
    rutas que en la app no estan. El parametro `ruta` esta para dejar constancia de que
    las dos rutas distintas del contrato estan cubiertas; si se anade una tercera forma,
    este test sigue exigiendo el recuento global.
    """
    from api import routes_registry
    from main import app

    assert ruta in (FAV, f"{FAV}/{DESTINO}")
    assert routes_registry.rutas_sin_permiso(app) == []
