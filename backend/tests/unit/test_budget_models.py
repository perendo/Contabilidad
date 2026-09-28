"""Tests de modelos fundacionales de SPEC-026 (T009).

Cubre: unicidad de la combinacion (empresa, ejercicio, cuenta, centro) con y
sin centro, unicidad correlativa de `numero_periodo`, un solo periodo abierto
por ejercicio, checks de rango y FKs compuestas por `empresa_id`
(constitucion III).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models.acct.account_plan import AccountPlan
from models.budget.desviacion import Desviacion
from models.budget.periodo_seguimiento import EstadoPeriodo, PeriodoSeguimiento
from models.budget.presupuesto import Presupuesto, TipoPresupuesto
from models.costcenters.centro_coste import CentroCoste, CentroEstado, CentroTipo
from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.budget import periodos
from services.budget.utils import c4
from tests.conftest import sembrar_empresa_pgc

EMPRESA = 10
EJERCICIO = 2026


async def _cuenta(db, codigo: str = "6400") -> int:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == EMPRESA, AccountPlan.code == codigo
        )
    )
    assert cuenta is not None, f"falta la cuenta {codigo} en el seed del PGC"
    return int(cuenta.id)


async def _centro(db) -> uuid.UUID:
    centro = CentroCoste(
        empresa_id=EMPRESA,
        codigo="CC-01",
        nombre="Departamento de produccion",
        tipo=CentroTipo.departamento,
        estado=CentroEstado.activo,
    )
    db.add(centro)
    await db.flush()
    return centro.id


def _presupuesto(cuenta_id: int, centro=None, importe="48000.0000") -> Presupuesto:
    return Presupuesto(
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=cuenta_id,
        centro_coste_id=centro,
        importe=c4(Decimal(importe)),
        tipo=TipoPresupuesto.gasto,
    )


def _periodo(numero: int, estado=EstadoPeriodo.abierto) -> PeriodoSeguimiento:
    return PeriodoSeguimiento(
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        numero_periodo=numero,
        fecha_inicio=date(EJERCICIO, 1, 1),
        fecha_fin=date(EJERCICIO, 12, 31),
        estado=estado,
    )


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    """Empresa 10 con PGC sembrado; se crea y se descarta por test."""
    async with db_session_factory() as session:
        session.add(
            Company(company_id=EMPRESA, nif="T00000010", razon_social="Presupuestos SL")
        )
        await session.flush()
        await seed_default_pgc(session, EMPRESA)
        await session.commit()


# --- T005 / FR-005: unicidad de la combinacion ---------------------------


async def test_presupuesto_unico_sin_centro(db_session):
    cuenta_id = await _cuenta(db_session)
    db_session.add(_presupuesto(cuenta_id))
    await db_session.commit()

    db_session.add(_presupuesto(cuenta_id, importe="100.0000"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_presupuesto_unico_con_centro(db_session):
    cuenta_id = await _cuenta(db_session)
    centro = await _centro(db_session)
    db_session.add(_presupuesto(cuenta_id, centro))
    await db_session.commit()

    db_session.add(_presupuesto(cuenta_id, centro, importe="100.0000"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_mismo_importe_entre_ejercicios_no_choca(db_session):
    """El indice es por (empresa, ejercicio, cuenta): otro ejercicio es otra fila."""
    cuenta_id = await _cuenta(db_session)
    db_session.add(_presupuesto(cuenta_id))
    db_session.add(
        Presupuesto(
            empresa_id=EMPRESA,
            ejercicio=2027,
            cuenta_id=cuenta_id,
            importe=c4(Decimal(48000)),
            tipo=TipoPresupuesto.gasto,
        )
    )
    await db_session.commit()

    assert len((await db_session.scalars(select(Presupuesto))).all()) == 2


async def test_cuenta_y_centro_de_otra_empresa_rechazados(db_session):
    """FK compuesta (empresa_id): el centro de la empresa 20 no cuela en la 10."""
    await sembrar_empresa_pgc(db_session, 20, nif="T00000020", razon_social="Otra SL")
    centro_ajeno = CentroCoste(
        empresa_id=20,
        codigo="CC-99",
        nombre="Centro ajeno",
        tipo=CentroTipo.proyecto,
        estado=CentroEstado.activo,
    )
    db_session.add(centro_ajeno)
    await db_session.flush()
    cuenta_id = await _cuenta(db_session)
    db_session.add(_presupuesto(cuenta_id, centro_ajeno.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


# --- T006 / constitucion IV: correlatividad y periodo abierto unico ------


async def test_numero_periodo_correlativo(db_session):
    assert await periodos.proximo_numero_periodo(db_session, EMPRESA, EJERCICIO) == 1
    db_session.add(_periodo(1))
    await db_session.commit()
    assert await periodos.proximo_numero_periodo(db_session, EMPRESA, EJERCICIO) == 2
    db_session.add(_periodo(2, EstadoPeriodo.cerrado))
    await db_session.commit()
    assert await periodos.proximo_numero_periodo(db_session, EMPRESA, EJERCICIO) == 3


async def test_numero_periodo_duplicado_rechazado(db_session):
    db_session.add(_periodo(1))
    await db_session.commit()
    db_session.add(_periodo(1))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_solo_un_periodo_abierto_por_ejercicio(db_session):
    db_session.add(_periodo(1))
    await db_session.commit()
    db_session.add(_periodo(2))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_periodo_cerrado_libera_el_slot(db_session):
    db_session.add(_periodo(1, EstadoPeriodo.cerrado))
    await db_session.commit()
    db_session.add(_periodo(2))
    await db_session.commit()
    assert (
        await db_session.scalar(
            select(PeriodoSeguimiento).where(
                PeriodoSeguimiento.empresa_id == EMPRESA,
                PeriodoSeguimiento.estado == EstadoPeriodo.abierto,
            )
        )
    ) is not None


async def test_rango_de_periodo_invalido(db_session):
    malo = PeriodoSeguimiento(
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        numero_periodo=1,
        fecha_inicio=date(EJERCICIO, 12, 31),
        fecha_fin=date(EJERCICIO, 1, 1),
        estado=EstadoPeriodo.abierto,
    )
    db_session.add(malo)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_numero_periodo_no_positivo(db_session):
    malo = PeriodoSeguimiento(
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        numero_periodo=0,
        fecha_inicio=date(EJERCICIO, 1, 1),
        fecha_fin=date(EJERCICIO, 12, 31),
        estado=EstadoPeriodo.abierto,
    )
    db_session.add(malo)
    with pytest.raises(IntegrityError):
        await db_session.commit()


# --- T007: snapshot de desviaciones --------------------------------------


async def test_snapshot_desviacion_es_append_only(db_session_factory):
    async with db_session_factory() as session:
        cuenta_id = await _cuenta(session)
        periodo = _periodo(1, EstadoPeriodo.cerrado)
        session.add(periodo)
        await session.flush()
        session.add(
            Desviacion(
                empresa_id=EMPRESA,
                periodo_id=periodo.id,
                cuenta_id=cuenta_id,
                importe_presupuestado=c4(Decimal(48000)),
                importe_real=c4(Decimal(45000)),
                desviacion_absoluta=c4(Decimal(-3000)),
                desviacion_relativa=c4(Decimal("-0.0625")),
                sin_presupuesto=False,
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "UPDATE desviacion SET importe_real = '1.0000' "
                    "WHERE empresa_id = :e"
                ),
                {"e": EMPRESA},
            )

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text("DELETE FROM desviacion WHERE empresa_id = :e"), {"e": EMPRESA}
            )


async def test_snapshot_desviacion_unico_por_combinacion(db_session):
    cuenta_id = await _cuenta(db_session)
    periodo = _periodo(1, EstadoPeriodo.cerrado)
    db_session.add(periodo)
    await db_session.flush()
    for _ in range(2):
        db_session.add(
            Desviacion(
                empresa_id=EMPRESA,
                periodo_id=periodo.id,
                cuenta_id=cuenta_id,
                importe_presupuestado=c4(Decimal(0)),
                importe_real=c4(Decimal(0)),
                desviacion_absoluta=c4(Decimal(0)),
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.commit()
