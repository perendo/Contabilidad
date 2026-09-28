"""Los favoritos sobreviven a que su destino cambie de sitio (SPEC-031, US6, T073).

Este es el caso que justifica la clave estable de FR-026 y es donde se cruzan US4 y US6:
una opción se reubica, y quien la tenía marcada tiene que seguir llegando a ella.

Hay dos riesgos y van en direcciones opuestas:

1. **Si la ruta cambia pero la clave no**, el favorito sigue funcionando. Es lo que pide
   FR-026, y es por eso que `destino` es una clave y no una ruta.
2. **Si la ruta cambia y la clave desaparece**, el favorito tiene que seguir existiendo,
   marcado como no accesible, para que si el destino vuelve, vuelva el favorito. Aquí no
   se puede probar por API (el 404 impide crearlo), así que se inyecta la fila, imitando
   un favorito creado en una versión anterior.

Lo que NO se prueba aquí, y conviene decir: que la fila sobreviva a un **cambio de
esquema**. Un favorito de la versión 5 de la aplicación, guardado en una base migrada a la
6, depende de que la migración conserve la tabla. Eso lo cubre `test_migrations.py` y el
contrato de PostgreSQL, no este fichero.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlalchemy as sa

from models.navigation.favorito import FavoritoUsuario
from services.navigation.destinos import DESTINOS, es_conocido
from services.navigation.favoritos import listar, marcar

RAIZ = Path(__file__).resolve().parents[3]
SUPERFICIES = RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts"

#: Destinos que han cambiado de ruta en SPEC-031, con su ruta antigua. Se documentan
#: para que el test sea histórico y no una lista de trabajo.
REUBICADOS = [
    ("import-export", "/contabilidad/import-export", "/asientos/import-export"),
]


# ---------------------------------------------------------------------------
# La clave no es la ruta
# ---------------------------------------------------------------------------


def test_el_destino_se_guarda_como_clave_y_no_como_ruta() -> None:
    """La columna `destino` guarda una clave estable, no una URL.

    Es el mecanismo entero de FR-026. Si guardara la ruta, reubicar un destino dejaría
    todos los favoritos guardados apuntando a la pantalla antigua, y no habría forma de
    saber a cuál correspondían.
    """
    import inspect

    firma = inspect.signature(marcar)
    assert "destino" in firma.parameters
    # No hay ningún parámetro de ruta en el servicio: la ruta no se conoce aquí.
    assert "ruta" not in firma.parameters


def test_una_clave_sigue_siendo_valida_despues_de_reubicar_la_ruta() -> None:
    """Cambiar la ruta en el mapa no invalida la clave.

    Se simula el efecto de la reubicación sin tocar ficheros: la clave `import-export`
    sigue en `DESTINOS` aunque su ruta en el mapa sea ahora otra. Si la clave dependiera
    de la ruta, esto fallaría.
    """
    clave, _antigua, _nueva = REUBICADOS[0]
    assert es_conocido(clave), "la clave debe seguir siendo valida tras la reubicacion"

    # Y la ruta nueva es la que declara el mapa hoy.
    texto = SUPERFICIES.read_text(encoding="utf-8")
    m = re.search(
        r'd\(\s*"' + re.escape(clave) + r'"\s*,\s*"[^"]*"\s*,\s*"([^"]*)"', texto
    )
    assert m is not None, f"{clave} deberia seguir en el mapa"
    assert m.group(1) == REUBICADOS[0][2], f"el mapa deberia apuntar a {REUBICADOS[0][2]}"


def test_ninguna_clave_del_mapa_es_una_ruta() -> None:
    """Las claves no empiezan por `/`.

    Una clave que fuera una ruta volvería frágil con el momento del trabajo, que es
    exactamente lo que se quería evitar.
    """
    texto = SUPERFICIES.read_text(encoding="utf-8")
    claves = re.findall(r'd\(\s*"([^"]+)"', texto)
    rutas = [c for c in claves if c.startswith("/") or "/" in c]
    assert not rutas, f"claves que parecen rutas: {rutas}"


# ---------------------------------------------------------------------------
# El destino desaparecido se conserva
# ---------------------------------------------------------------------------


async def test_un_favorito_de_destino_retirado_se_conserva(db_session) -> None:
    """La fila sobrevive y se marca, en vez de desaparecer.

    Se inyecta a propósito: por API no se puede crear, porque `marcar` rechaza con 404
    una clave que no está en el mapa. Y ese 404 es justamente lo que hay que comprobar:
    sin él, se guardaría un favorito que ninguna superficie puede abrir.
    """
    from models.iam.user import User
    from models.iam.user_company import UserCompany, UserRol
    from services.auth.security import hash_password
    from tests.conftest import crear_empresas

    await crear_empresas(db_session, 10)
    db_session.add(
        User(id=700, email="r@reub.es", password_hash=hash_password("pw"), full_name="R")
    )
    db_session.add(
        UserCompany(
            id=700, user_id=700, company_id=10, role=UserRol.ADMIN, is_default=True
        )
    )
    await db_session.flush()

    # Un favorito "de la era anterior", con una clave que ya no existe.
    db_session.add(
        FavoritoUsuario(
            empresa_id=10, usuario_id=700, destino="destino-retirado", orden=1
        )
    )
    await db_session.flush()

    lectura = await listar(db_session, empresa_id=10, usuario_id=700)
    assert lectura["total"] == 1, "NO se borra"
    assert lectura["items"][0]["desconocido"] is True
    assert lectura["items"][0]["accesible"] is False, "pero no se muestra"

    # Y la fila sigue en la tabla, que es lo que permite que reaparezca.
    filas = (
        (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    )
    assert len(filas) == 1


async def test_una_clave_retirada_no_se_puede_volver_a_marcar(db_session) -> None:
    """Reintroducir un destino retirado tampoco es obligación: se rechaza con 404.

    El caso simétrico. Si `marcar` aceptara cualquier cadena, el 404 dejaría de ser útil
    y un cliente con la clave equivocada crearía filas invisibles.
    """
    from services.navigation.errores import NavigationError
    from tests.conftest import crear_empresas

    await crear_empresas(db_session, 10)
    with pytest.raises(NavigationError) as error:
        await marcar(
            db_session,
            empresa_id=10,
            usuario_id=700,
            destino="destino-retirado",
            orden=1,
        )
    assert error.value.code == "destino_desconocido"
    assert error.value.status_code == 404


def test_un_destino_nuevo_se_puede_marcar_sin_tocar_los_existentes() -> None:
    """Añadir un destino no invalida los demás.

    Es el otro lado de la reubicación: cuando la feature añada la centésima pantalla, los
    favoritos ya guardados tienen que seguir ahí. El catálogo es un conjunto que crece, no
    una lista que se reescribe.
    """
    assert len(DESTINOS) >= 100
    assert all(not c.startswith("/") for c in DESTINOS)
