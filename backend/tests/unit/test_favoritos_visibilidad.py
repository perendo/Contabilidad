"""Visibilidad de favoritos cuando el acceso cambia (SPEC-031, US4, T072).

FR-024 pide que un favorito que ya no se puede abrir **se conserve**, marcado como no
accesible, en vez de borrarse: si el acceso vuelve, tiene que volver a estar.

QUE SE PUEDE COMPROBAR HOY, Y QUE NO

La mitad de "sin permiso" **no es alcanzable de extremo a extremo con el mapa actual**, y
conviene decirlo en vez de montar un test que lo de por cubierto cuando no lo esta. La
razon es que `destinos.py` fija `PERMISO_POR_DEFECTO = ("acct", "ver")` y ningun destino
lo sobrescribe (lo comprueba `test_destinos_en_sync.py`). Y `GET /favoritos` exige
precisamente `acct:ver`. De ahi sale que un usuario sin ese permiso:

1. no puede ni siquiera leer la lista: responde 403, no una lista con `accesible: false`;
2. y por tanto tampoco puede quitar el favorito que le sobraria.

Que se escondan todos los destinos es coherente: sin `acct:ver` tampoco puede abrir
ninguna pantalla de contabilidad, que es lo que ese permiso significa en este sistema.

El mecanismo de `accesible: false` **si** se prueba, en el sitio donde se puede: el
servicio, con un conjunto de permisos explicito. Eso esta en
`test_destinos_en_sync.py::test_es_accesible_distingue_permiso_de_destino_inexistente`.
Aqui se prueba lo que si ocurre: que perder el acceso no borra nada por el camino, y que
la fila sobrevive para cuando vuelva.
"""

from __future__ import annotations

import sqlalchemy as sa

from models.navigation.favorito import FavoritoUsuario

FAV = "/api/v1/favoritos"
DESTINO = "conciliacion"


def _revocar_acct_ver(navegacion_client, empresa: int, rol_nombre: str) -> None:
    """Quita `acct:ver` a un rol en la matriz, sin tocar el vinculo del usuario.

    Se quita el permiso y no se cambia de rol a proposito: el caso real es "me
    quitaron un permiso", no "me movieron de rol". Con el rol intacto, lo unico que
    cambia para el usuario es lo que puede hacer.
    """
    from models.rbac.matriz_permiso import MatrizPermiso
    from models.rbac.permiso_operacion import PermisoOperacion
    from models.rbac.rol import Rol

    async def _aplicar(session):
        rol = await session.scalar(
            sa.select(Rol).where(
                Rol.empresa_id == empresa, Rol.nombre == rol_nombre
            )
        )
        assert rol is not None, f"no esta el rol {rol_nombre} en la empresa {empresa}"
        permiso = await session.scalar(
            sa.select(PermisoOperacion).where(
                PermisoOperacion.modulo == "acct",
                PermisoOperacion.operacion == "ver",
            )
        )
        assert permiso is not None, "el catalogo deberia tener acct:ver"
        fila = await session.scalar(
            sa.select(MatrizPermiso).where(
                MatrizPermiso.empresa_id == empresa,
                MatrizPermiso.rol_id == rol.id,
                MatrizPermiso.permiso_id == permiso.id,
            )
        )
        assert fila is not None, f"{rol_nombre} deberia tener acct:ver de partida"
        await session.delete(fila)

    navegacion_client.run(navegacion_client.mutar(_aplicar))


def test_sin_el_permiso_de_contexto_la_lista_responde_403(navegacion_client) -> None:
    """El guard responde 403, y no una lista vacia.

    Es la distincion importante: una respuesta 403 es "no puedes saberlo", que es
    honesto. Una lista vacia seria "no tienes favoritos", que es una mentira que el
    cliente no tiene forma de distinguir de la verdad.
    """
    _revocar_acct_ver(navegacion_client, 10, "ACCOUNTANT")
    r = navegacion_client.get(FAV, token_key="accountant")
    assert r.status_code == 403, r.text
    assert "total" not in r.json(), "no es una lista vacia: es un no autorizado"


def test_perder_el_acceso_no_borra_el_favorito(navegacion_client) -> None:
    """La fila sobrevive al 403 del otro usuario.

    Comprueba que no hay ningun efecto colateral: perder el permiso cierra la pantalla
    (correcto) pero no toca los datos de la preferencia (también correcto). Un
    `DELETE` silencioso en algun sitio dejaria al usuario sin favorito y sin aviso al
    volver a recuperarlo.
    """
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)

    async def _leer(session):
        return (
            await session.execute(
                sa.select(FavoritoUsuario).where(
                    FavoritoUsuario.destino == DESTINO
                )
            )
        ).scalars().all()

    antes = navegacion_client.run(navegacion_client.consultar(_leer))
    assert len(antes) == 1

    _revocar_acct_ver(navegacion_client, 10, "ACCOUNTANT")
    assert navegacion_client.get(FAV, token_key="accountant").status_code == 403

    despues = navegacion_client.run(navegacion_client.consultar(_leer))
    assert len(despues) == 1, "el 403 del otro usuario no puede borrar nada"
    assert despues[0].orden == 1, "ni alterar el orden guardado"


def test_el_favorito_sigue_legible_para_quien_mantiene_el_acceso(navegacion_client) -> None:
    """Revocar a un rol no afecta a los favoritos de quien conserva el permiso."""
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)
    _revocar_acct_ver(navegacion_client, 10, "ACCOUNTANT")

    cuerpo = navegacion_client.get(FAV, token_key="admin").json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["accesible"] is True
    assert cuerpo["items"][0]["desconocido"] is False


def test_el_favorito_de_otro_usuario_no_aparece_en_la_lista(navegacion_client) -> None:
    """Un 403 no convierte la lista en un volcado de las preferencias ajenas.

    Comprueba el orden de las dos cosas: primero se autoriza, despues se filtra. Si el
    filtro fuera lo primero, un usuario sin permiso veria los favoritos de la empresa
    antes de que el guard le parase.
    """
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)
    _revocar_acct_ver(navegacion_client, 10, "ACCOUNTANT")

    cuerpo = navegacion_client.get(FAV, token_key="accountant").json()
    assert "items" not in cuerpo, "un 403 no lleva lista, ni propia ni ajena"
    assert "total" not in cuerpo


def test_reconocer_el_favorito_a_otro_usuario_sigue_siendo_imposible(
    navegacion_client,
) -> None:
    """La unicidad es `(empresa, usuario, destino)`, no `(empresa, destino)`.

    Con la uniqueness equivocada, el segundo usuario que marcara el mismo destino
    recibe un error de duplicado en vez de tener su propio favorito. Es un detalle de
    la tabla que se nota en cuanto hay dos personas en la misma empresa.
    """
    navegacion_client.put(f"{FAV}/{DESTINO}", destino=DESTINO, orden=1)
    r = navegacion_client.put(
        f"{FAV}/{DESTINO}", token_key="accountant", destino=DESTINO, orden=1
    )
    assert r.status_code == 201, r.text

    async def _leer(session):
        return (
            await session.execute(sa.select(FavoritoUsuario))
        ).scalars().all()

    filas = navegacion_client.run(navegacion_client.consultar(_leer))
    assert len(filas) == 2, "uno por usuario, en la misma empresa"
    assert {f.usuario_id for f in filas} == {1, 2}


def test_la_lectura_no_puede_devolver_destinos_de_otra_empresa(navegacion_client) -> None:
    """Favoritos por empresa: los de B no aparecen al listar los de A.

    Se comprobaba ya en `test_favoritos_routes.py`, y se repite aqui porque esta es la
    combinacion que mas se repite en uso real: cambiar de empresa y volver.
    """
    navegacion_client.put(
        f"{FAV}/{DESTINO}", empresa_id=10, destino=DESTINO, orden=1
    )
    navegacion_client.put(
        f"{FAV}/asientos", empresa_id=20, destino="asientos", orden=1
    )
    assert navegacion_client.get(FAV, empresa_id=10).json()["total"] == 1
    assert navegacion_client.get(FAV, empresa_id=20).json()["total"] == 1

    async def _leer(session):
        return (
            await session.execute(sa.select(FavoritoUsuario))
        ).scalars().all()

    filas = navegacion_client.run(navegacion_client.consultar(_leer))
    assert {f.empresa_id for f in filas} == {10, 20}
    
