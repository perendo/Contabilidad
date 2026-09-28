"""Tests SPEC-013 Foundational (T011): modelos de conciliación."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from models.treasury.conciliacion import (
    Conciliacion,
    CruceConciliacion,
    CruceOrigen,
    CrucePrioridad,
)
from models.treasury.extracto_bancario import ExtractoBancario
from models.treasury.movimiento_bancario import MovimientoBancario, SignoMovimiento
from models.treasury.periodo_conciliado import PeriodoConciliado


async def _empresa(db: AsyncSession, cid: int = 10) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()


async def _extracto(db: AsyncSession, cid: int = 10, sha: str = "a" * 64) -> ExtractoBancario:
    ex = ExtractoBancario(
        empresa_id=cid, cuenta_id=1, fecha_inicio=date(2026, 9, 1),
        fecha_fin=date(2026, 9, 30), saldo_inicial=Decimal(0), saldo_final=Decimal(100),
        nombre_fichero="x.txt", sha256=sha, n_movimientos=1,
    )
    db.add(ex)
    await db.flush()
    return ex


async def test_sha256_unico_por_empresa(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    await _extracto(db_session, 10)
    ex2 = ExtractoBancario(
        empresa_id=10, cuenta_id=1, fecha_inicio=date(2026, 10, 1),
        fecha_fin=date(2026, 10, 31), saldo_inicial=Decimal(0), saldo_final=Decimal(0),
        nombre_fichero="y.txt", sha256="a" * 64, n_movimientos=0,
    )
    db_session.add(ex2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_sha256_repetido_otra_empresa_ok(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    await _extracto(db_session, 10)
    await _extracto(db_session, 20)
    assert True


async def test_orden_unico_por_extracto(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    ex = await _extracto(db_session)
    for _ in range(2):
        db_session.add(
            MovimientoBancario(
                empresa_id=10, extracto_id=ex.id, orden=1,
                fecha_operacion=date(2026, 9, 10), concepto="X",
                importe=Decimal("10.0000"), signo=SignoMovimiento.D,
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_movimiento_unico_en_cruces(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    ex = await _extracto(db_session)
    mov = MovimientoBancario(
        empresa_id=10, extracto_id=ex.id, orden=1, fecha_operacion=date(2026, 9, 10),
        concepto="X", importe=Decimal("10.0000"), signo=SignoMovimiento.D,
    )
    db_session.add(mov)
    await db_session.flush()
    conc = Conciliacion(
        empresa_id=10, cuenta_id=1, ejercicio=2026,
        fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30),
        saldo_banco=Decimal(0), saldo_libros=Decimal(0), diferencia=Decimal(0),
    )
    db_session.add(conc)
    await db_session.flush()
    for _ in range(2):
        db_session.add(
            CruceConciliacion(
                empresa_id=10, conciliacion_id=conc.id, movimiento_id=mov.id,
                apunte_id=uuid.uuid4(), importe=Decimal("10.0000"), signo="D",
                origen=CruceOrigen.auto, prioridad=CrucePrioridad.candidato,
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_periodo_diferencia_cero_check(db_session: AsyncSession) -> None:
    await _empresa(db_session)
    conc = Conciliacion(
        empresa_id=10, cuenta_id=1, ejercicio=2026,
        fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30),
        saldo_banco=Decimal(0), saldo_libros=Decimal(0), diferencia=Decimal(0),
    )
    db_session.add(conc)
    await db_session.flush()
    db_session.add(
        PeriodoConciliado(
            empresa_id=10, conciliacion_id=conc.id, cuenta_id=1, ejercicio=2026,
            numero_periodo=1, fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30),
            saldo_banco=Decimal(0), saldo_libros=Decimal(0), diferencia=Decimal("1.0000"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
