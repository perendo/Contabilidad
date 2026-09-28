"""Tests SPEC-013 US2/US3 (T025/T026/T035/T037/T038/T039/T047): flujo completo."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.treasury.conciliacion import ConciliacionEstado
from services.journal.entry_service import asentar, crear_borrador
from services.reconciliation.cierre import CierreError, cerrar_periodo
from services.reconciliation.conciliacion import abrir_conciliacion
from services.reconciliation.cruce import CruceError, confirmar_cruce, deshacer_cruce
from services.reconciliation.importacion import importar_extracto
from services.reconciliation.matching import generar_propuestas
from services.reconciliation.saldos import informe
from tests.conftest import sembrar_empresa_pgc

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


async def _cuentas(db: AsyncSession) -> dict[str, int]:
    filas = (
        await db.scalars(
            select(AccountPlan).where(
                AccountPlan.tenant_id == 10,
                AccountPlan.code.in_(["5720", "4300", "4000"]),
            )
        )
    ).all()
    return {c.code: c.id for c in filas}


async def _apunte(db: AsyncSession, cuentas: dict[str, int], debe: str, haber: str, concepto: str) -> None:
    """Asiento con la 5720 a un lado y 4300/4000 al otro."""
    if Decimal(debe) > 0:
        lineas = [
            {"account_id": cuentas["5720"], "debit": debe, "credit": "0", "detail": concepto},
            {"account_id": cuentas["4000"], "debit": "0", "credit": debe, "detail": concepto},
        ]
    else:
        lineas = [
            {"account_id": cuentas["4300"], "debit": haber, "credit": "0", "detail": concepto},
            {"account_id": cuentas["5720"], "debit": "0", "credit": haber, "detail": concepto},
        ]
    borrador = await crear_borrador(
        db, empresa_id=10, fecha=date(2026, 9, 12), concepto=concepto, lineas=lineas, actor="t"
    )
    await asentar(db, empresa_id=10, entry_id=borrador.id, actor="t")


async def _escenario(db: AsyncSession) -> tuple:
    await sembrar_empresa_pgc(db, 10)
    cuentas = await _cuentas(db)
    extracto = await importar_extracto(
        db, empresa_id=10, file_bytes=(FIXTURES / "extracto_43_19_valido.txt").read_bytes(),
        nombre_fichero="v.txt", actor="t",
    )
    # Apuntes 572 espejo: debe 500, debe 200, haber 1805 → neto 1105 == saldo_final
    await _apunte(db, cuentas, "0", "1805.0000", "ABONO CLIENTE")
    await _apunte(db, cuentas, "500.0000", "0", "TRANSFERENCIA A PROVEEDOR X")
    await _apunte(db, cuentas, "200.0000", "0", "RECIBO DOMICILIADO")
    conc = await abrir_conciliacion(
        db, empresa_id=10, cuenta_id=cuentas["5720"],
        fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30),
        extracto_id=extracto.id, actor="t",
    )
    return conc, cuentas


async def test_flujo_propuestas_cruce_cierre(db_session: AsyncSession) -> None:
    conc, _ = await _escenario(db_session)
    assert conc.saldo_banco == Decimal("1105.0000")
    assert conc.saldo_libros == Decimal("1105.0000")
    assert conc.diferencia == Decimal("0.0000")

    propuestas = await generar_propuestas(db_session, empresa_id=10, conciliacion=conc)
    assert len(propuestas) == 3
    for p in propuestas:
        await confirmar_cruce(
            db_session, empresa_id=10, conciliacion=conc,
            movimiento_id=p.movimiento_id, apunte_id=p.apunte_id, actor="t",
        )
    informe_c = await informe(db_session, 10, conc)
    assert informe_c["diferencia"] == "0.0000"
    assert informe_c["pendientes"]["movimientos_sin_cruzar"] == []

    periodo = await cerrar_periodo(db_session, empresa_id=10, conciliacion=conc, actor="t")
    assert periodo.numero_periodo == 1
    assert periodo.diferencia == Decimal("0.0000")
    assert conc.estado == ConciliacionEstado.cerrada
    with pytest.raises(CruceError) as exc:
        await deshacer_cruce(db_session, empresa_id=10, conciliacion=conc, cruce_id=propuestas[0].id)
    assert exc.value.code == "periodo_archivado"


async def test_cierre_con_pendientes_409(db_session: AsyncSession) -> None:
    await sembrar_empresa_pgc(db_session, 10)
    cuentas = await _cuentas(db_session)
    extracto = await importar_extracto(
        db_session, empresa_id=10,
        file_bytes=(FIXTURES / "extracto_43_19_valido.txt").read_bytes(),
        nombre_fichero="v.txt", actor="t",
    )
    # Solo se registra un apunte → neto libros != banco
    await _apunte(db_session, cuentas, "500.0000", "0", "TRANSFERENCIA A PROVEEDOR X")
    conc = await abrir_conciliacion(
        db_session, empresa_id=10, cuenta_id=cuentas["5720"],
        fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30),
        extracto_id=extracto.id, actor="t",
    )
    assert conc.diferencia != Decimal("0.0000")
    with pytest.raises(CierreError) as exc:
        await cerrar_periodo(db_session, empresa_id=10, conciliacion=conc, actor="t")
    assert exc.value.code == "diferencia_no_cero"
    assert conc.estado == ConciliacionEstado.abierta


async def test_correlatividad_periodos(db_session: AsyncSession) -> None:
    conc, cuentas = await _escenario(db_session)
    p1 = await cerrar_periodo(db_session, empresa_id=10, conciliacion=conc, actor="t")
    assert p1.numero_periodo == 1
    # Segundo período (rango distinto, sin apuntes ni extracto) → diferencia 0 → número 2
    conc2 = await abrir_conciliacion(
        db_session, empresa_id=10, cuenta_id=cuentas["5720"],
        fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 10, 31), actor="t",
    )
    p2 = await cerrar_periodo(db_session, empresa_id=10, conciliacion=conc2, actor="t")
    assert p2.numero_periodo == 2
