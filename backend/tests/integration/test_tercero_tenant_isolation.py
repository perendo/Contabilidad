"""Tests SPEC-008 Foundational (T013): tercero de A invisible desde B."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from services.thirdparty.alta import crear_tercero


async def _empresa(db: AsyncSession, cid: int) -> None:
    from models.iam.company import Company
    from services.acct.seed import seed_default_pgc

    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()
    await seed_default_pgc(db, cid)


async def test_tercero_a_invisible_desde_b(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    creado = await crear_tercero(
        db_session,
        empresa_id=10,
        nif="12345678Z",
        razon_social="Cliente A SL",
        es_cliente=True,
    )
    assert await db_session.scalar(
        select(Tercero).where(Tercero.empresa_id == 10, Tercero.id == creado.id)
    ) is not None
    assert await db_session.scalar(
        select(Tercero).where(Tercero.empresa_id == 20, Tercero.id == creado.id)
    ) is None
    assert await db_session.scalar(
        select(Tercero).where(Tercero.empresa_id == 20, Tercero.nif == "12345678Z")
    ) is None
