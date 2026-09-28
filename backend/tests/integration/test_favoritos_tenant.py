"""Aislamiento de favoritos entre empresas y usuarios (SPEC-031, US4, T038).

Es el Principio V(b) de la constitution aplicado a la unica parte de la feature que
**escribe**. Y tiene una garantia de la que el resto de la feature no necesita
preocuparse: aqui no basta con que el servicio filtre por empresa, porque la FK
compuesta a `user_companies` hace que un favorito sin vinculacion sea **invalido** en
la base, no invisible. Estos tests comprueban las dos capas:

1. El servicio, que filtra por `(empresa_id, usuario_id)` en cada consulta.
2. La base, que no admite un favorito de una empresa a la que el usuario no esta
   vinculado aunque alguien lo inserte a mano.

La segunda es la que importa de verdad: si el filtro del servicio se rompe, la FK
sigue impidiendo el fallo. Y si alguien desactiva las FK, la segunda se rompe y este
fichero lo dice.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from models.navigation.favorito import FavoritoUsuario
from services.auth.security import hash_password
from services.navigation.favoritos import desmarcar, listar, marcar
from tests.conftest import crear_empresas

EMPRESA_A = 10
EMPRESA_B = 20
DESTINO = "vencimientos"


async def _usuario(
    db: AsyncSession,
    uid: int,
    company_id: int,
    rol=UserRol.ACCOUNTANT,
    *,
    nueva: bool = True,
    vinculo_id: int | None = None,
) -> None:
    """Crea el usuario si toca, y su vinculo con una empresa.

    `nueva=False` evita duplicar el `User` cuando el mismo esta en dos empresas: lo
    que cambia es el `UserCompany`, que es por empresa. Por eso `vinculo_id` es
    independiente de `uid`; si coincidieran, el segundo vinculo colisionaria con el
    primero en `uq_user_companies_pair` y en la PK.
    """
    if nueva:
        db.add(
            User(id=uid, email=f"u{uid}@fav.es", password_hash=hash_password("pw"), full_name="U")
        )
    db.add(
        UserCompany(
            id=vinculo_id if vinculo_id is not None else uid,
            user_id=uid,
            company_id=company_id,
            role=rol,
            is_default=company_id == EMPRESA_A,
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# 1. El servicio filtra por empresa
# ---------------------------------------------------------------------------


async def test_los_favoritos_no_cruzan_de_empresa(db_session: AsyncSession) -> None:
    """Un favorito de la empresa A no aparece al listar los de la B."""
    await crear_empresas(db_session, EMPRESA_A, EMPRESA_B)
    await _usuario(db_session, 1, EMPRESA_A)
    await marcar(
        db_session, empresa_id=EMPRESA_A, usuario_id=1, destino=DESTINO, orden=1
    )

    de_a = await listar(db_session, empresa_id=EMPRESA_A, usuario_id=1)
    de_b = await listar(db_session, empresa_id=EMPRESA_B, usuario_id=1)
    assert de_a["total"] == 1
    assert de_b["total"] == 0, "un usuario sin vinculo a B no puede tener favoritos en B"


async def test_cada_usuario_solo_ve_los_suyos(db_session: AsyncSession) -> None:
    """El favorito es por usuario: dos personas en la misma empresa no se ven."""
    await crear_empresas(db_session, EMPRESA_A)
    await _usuario(db_session, 1, EMPRESA_A)
    await _usuario(db_session, 2, EMPRESA_A)
    await marcar(
        db_session, empresa_id=EMPRESA_A, usuario_id=1, destino=DESTINO, orden=1
    )

    uno = await listar(db_session, empresa_id=EMPRESA_A, usuario_id=1)
    otro = await listar(db_session, empresa_id=EMPRESA_A, usuario_id=2)
    assert uno["total"] == 1
    assert otro["total"] == 0, "los favoritos son por usuario, no por empresa"


async def test_desmarcar_no_toca_el_de_otra_empresa(db_session: AsyncSession) -> None:
    """Desmarcar en la empresa B no borra el favorito de la A.

    Es el caso peligroso del servicio: un `DELETE` por `destino` sin filtro de empresa
    habria borrado el favorito de la A al desmarcar desde la B.
    """
    await crear_empresas(db_session, EMPRESA_A, EMPRESA_B)
    await _usuario(db_session, 1, EMPRESA_A)
    await marcar(
        db_session, empresa_id=EMPRESA_A, usuario_id=1, destino=DESTINO, orden=1
    )
    await desmarcar(db_session, empresa_id=EMPRESA_B, usuario_id=1, destino=DESTINO)
    siguen = (
        (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    )
    assert len(siguen) == 1, "el desmarcar en B no puede borrar el favorito de A"
    assert siguen[0].empresa_id == EMPRESA_A


async def test_marcar_en_empresa_sin_vinculo_falla_por_la_fk(
    db_session: AsyncSession,
) -> None:
    """La garantia fuerte: no es "invisible", es **invalido**.

    Se marca un favorito para un usuario que no esta vinculado a esa empresa, y la FK
    compuesta a `user_companies` lo rechaza. Con esto, un fallo del filtro del servicio
    no se convierte en una fuga de datos, porque la base lo impide.
    """
    await crear_empresas(db_session, EMPRESA_A, EMPRESA_B)
    await _usuario(db_session, 1, EMPRESA_A)
    with pytest.raises(IntegrityError):
        await marcar(
            db_session,
            empresa_id=EMPRESA_B,
            usuario_id=1,
            destino=DESTINO,
            orden=1,
        )
        await db_session.flush()


async def test_el_mismo_destino_puede_existir_en_dos_empresas(
    db_session: AsyncSession,
) -> None:
    """El UNIQUE es `(empresa, usuario, destino)`, no `(usuario, destino)`.

    Dos empresas pueden tener favoritos del mismo destino: son conjuntos distintos, y
    el UNIQUE equivocado habria hecho imposible tener favoritos en las dos.
    """
    await crear_empresas(db_session, EMPRESA_A, EMPRESA_B)
    await _usuario(db_session, 1, EMPRESA_A)
    # El mismo usuario en la segunda empresa: no se crea otro `User`, solo otro
    # `UserCompany`, con id propio.
    await _usuario(db_session, 1, EMPRESA_B, nueva=False, vinculo_id=900)
    await marcar(db_session, empresa_id=EMPRESA_A, usuario_id=1, destino=DESTINO, orden=1)
    await marcar(db_session, empresa_id=EMPRESA_B, usuario_id=1, destino=DESTINO, orden=1)
    filas = (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    assert len(filas) == 2
    assert {f.empresa_id for f in filas} == {EMPRESA_A, EMPRESA_B}


async def test_reordenar_no_toca_otros_usuarios(db_session: AsyncSession) -> None:
    """Reordenar los de un usuario no cambia los de otro."""
    from services.navigation.favoritos import reordenar

    await crear_empresas(db_session, EMPRESA_A)
    await _usuario(db_session, 1, EMPRESA_A)
    await _usuario(db_session, 2, EMPRESA_A)
    await marcar(db_session, empresa_id=EMPRESA_A, usuario_id=1, destino="asientos", orden=1)
    await marcar(db_session, empresa_id=EMPRESA_A, usuario_id=1, destino="facturas", orden=2)
    await marcar(db_session, empresa_id=EMPRESA_A, usuario_id=2, destino="asientos", orden=1)

    await reordenar(
        db_session,
        empresa_id=EMPRESA_A,
        usuario_id=1,
        ordenes=["facturas", "asientos"],
    )
    del_otro = await listar(db_session, empresa_id=EMPRESA_A, usuario_id=2)
    assert [f["destino"] for f in del_otro["items"]] == ["asientos"]
