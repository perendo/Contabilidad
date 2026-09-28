"""Aislamiento multi-tenant de los modelos de SPEC-026 (T010, constitucion III).

Presupuesto y periodo creados en la empresa 10 no son visibles desde ninguna
consulta de la empresa 20, y la combinacion contable de la empresa 20 no puede
apuntarse al presupuesto de la 10 (FK compuesta por `empresa_id`).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from models.acct.account_plan import AccountPlan
from models.budget.periodo_seguimiento import EstadoPeriodo, PeriodoSeguimiento
from models.budget.presupuesto import Presupuesto, TipoPresupuesto
from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.budget.utils import c4

A = 10
B = 20


async def _empresa(db, empresa_id: int) -> None:
    db.add(
        Company(company_id=empresa_id, nif=f"T{empresa_id:08d}", razon_social=f"E{empresa_id} SL")
    )
    await db.flush()
    await seed_default_pgc(db, empresa_id)


async def _cuenta(db, empresa_id: int, codigo: str = "6400") -> int:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == codigo
        )
    )
    assert cuenta is not None
    return int(cuenta.id)


async def _sembrar(db) -> tuple[int, int, uuid.UUID]:
    await _empresa(db, A)
    await _empresa(db, B)
    cuenta_a = await _cuenta(db, A)
    cuenta_b = await _cuenta(db, B)
    periodo_a = PeriodoSeguimiento(
        empresa_id=A,
        ejercicio=2026,
        numero_periodo=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        estado=EstadoPeriodo.abierto,
    )
    db.add(periodo_a)
    db.add(
        Presupuesto(
            empresa_id=A,
            ejercicio=2026,
            cuenta_id=cuenta_a,
            periodo_id=periodo_a.id,
            importe=c4(Decimal(48000)),
            tipo=TipoPresupuesto.gasto,
        )
    )
    await db.commit()
    return cuenta_a, cuenta_b, periodo_a.id


async def test_presupuesto_de_A_no_aparece_en_B(db_session):
    _, _, _ = await _sembrar(db_session)

    visibles_b = (
        await db_session.scalars(
            select(Presupuesto).where(Presupuesto.empresa_id == B)
        )
    ).all()
    assert visibles_b == []

    total_b = await db_session.scalar(
        select(func.count()).select_from(Presupuesto).where(Presupuesto.empresa_id == B)
    )
    assert int(total_b or 0) == 0


async def test_periodo_de_A_no_aparece_en_B(db_session):
    _, _, _ = await _sembrar(db_session)

    periodos_b = (
        await db_session.scalars(
            select(PeriodoSeguimiento).where(PeriodoSeguimiento.empresa_id == B)
        )
    ).all()
    assert periodos_b == []


async def test_correlativo_de_periodo_es_independiente_por_empresa(db_session):
    await _sembrar(db_session)

    from services.budget import periodos

    assert await periodos.proximo_numero_periodo(db_session, A, 2026) == 2
    assert await periodos.proximo_numero_periodo(db_session, B, 2026) == 1


async def test_presupuesto_en_B_con_cuenta_de_A_rechazado(db_session):
    cuenta_a, cuenta_b, periodo_a = await _sembrar(db_session)

    db_session.add(
        Presupuesto(
            empresa_id=B,
            ejercicio=2026,
            cuenta_id=cuenta_a,  # cuenta de la empresa A
            importe=c4(Decimal(10)),
            tipo=TipoPresupuesto.gasto,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()

    assert cuenta_b != cuenta_a
    assert periodo_a is not None


async def test_misma_combinacion_puede_existir_en_ambas_empresas(db_session):
    """El indice parcial es por empresa: 6400 en A y en B no colisionan."""
    await _sembrar(db_session)
    cuenta_b = await _cuenta(db_session, B)
    db_session.add(
        Presupuesto(
            empresa_id=B,
            ejercicio=2026,
            cuenta_id=cuenta_b,
            importe=c4(Decimal(1000)),
            tipo=TipoPresupuesto.gasto,
        )
    )
    await db_session.commit()

    total = await db_session.scalar(select(func.count()).select_from(Presupuesto))
    assert int(total or 0) == 2
