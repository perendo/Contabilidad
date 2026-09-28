"""Tests SPEC-008 US1 (T014/T015/T016/T017/T018): alta de tercero."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.ar.tercero import Tercero
from models.ar.tercero_subcuenta import TerceroSubcuenta
from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.thirdparty.alta import TerceroError, crear_tercero


async def _empresa(db: AsyncSession, cid: int = 10) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()
    await seed_default_pgc(db, cid)


async def test_alta_crea_dos_subcuentas_y_normaliza_nif(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    tercero = await crear_tercero(
        db_session,
        empresa_id=10,
        nif=" 12345678-z ",
        razon_social="Cliente A SL",
        es_cliente=True,
        es_proveedor=True,
    )
    assert tercero.nif == "12345678Z"
    subcuentas = (
        await db_session.scalars(
            select(TerceroSubcuenta).where(TerceroSubcuenta.tercero_id == tercero.id)
        )
    ).all()
    assert {s.tipo.value for s in subcuentas} == {"CLIENTE", "PROVEEDOR"}
    codigos = {s.cuenta_codigo for s in subcuentas}
    assert any(c.startswith("430") for c in codigos)
    assert any(c.startswith("410") for c in codigos)


async def test_nif_duplicado_misma_empresa_y_aislado_entre_empresas(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    await crear_tercero(
        db_session, empresa_id=10, nif="12345678Z", razon_social="Uno", es_cliente=True
    )
    with pytest.raises(TerceroError) as exc:
        await crear_tercero(
            db_session, empresa_id=10, nif="12345678Z", razon_social="Dos", es_cliente=True
        )
    assert exc.value.code == "nif_duplicado"
    otro = await crear_tercero(
        db_session, empresa_id=20, nif="12345678Z", razon_social="Otra", es_cliente=True
    )
    assert otro.id is not None


async def test_nif_invalido_no_crea_nada(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    with pytest.raises(TerceroError) as exc:
        await crear_tercero(
            db_session, empresa_id=10, nif="12345678A", razon_social="X", es_cliente=True
        )
    assert exc.value.code == "nif_invalido"
    assert (await db_session.scalars(select(Tercero))).all() == []
    assert (await db_session.scalars(select(TerceroSubcuenta))).all() == []


async def test_iban_valido_se_guarda_e_invalido_rechazado(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    tercero = await crear_tercero(
        db_session, empresa_id=10, nif="12345678Z", razon_social="Con IBAN",
        es_cliente=True, iban="ES9121000418450200051332",
    )
    assert tercero.iban == "ES9121000418450200051332"
    with pytest.raises(TerceroError) as exc:
        await crear_tercero(
            db_session, empresa_id=10, nif="87654321X", razon_social="Mal IBAN",
            es_cliente=True, iban="ES0000000000000000000000",
        )
    assert exc.value.code == "iban_invalido"
    sin_iban = await crear_tercero(
        db_session, empresa_id=10, nif="87654321X", razon_social="Sin IBAN", es_cliente=True
    )
    assert sin_iban.iban is None


async def test_subcuenta_en_plan_clase_4(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    tercero = await crear_tercero(
        db_session, empresa_id=10, nif="12345678Z", razon_social="C", es_cliente=True
    )
    subcuenta = await db_session.scalar(
        select(TerceroSubcuenta).where(TerceroSubcuenta.tercero_id == tercero.id)
    )
    assert subcuenta is not None
    cuenta = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == 10, AccountPlan.code == subcuenta.cuenta_codigo
        )
    )
    assert cuenta is not None
    assert cuenta.code.startswith("4")
    assert cuenta.is_selectable is True


async def test_rol_requerido(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    with pytest.raises(TerceroError) as exc:
        await crear_tercero(
            db_session, empresa_id=10, nif="12345678Z", razon_social="Sin rol"
        )
    assert exc.value.code == "rol_requerido"
