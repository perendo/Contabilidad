"""T034: Agregación del informe de costes (SPEC-017 US3).

Clasifica líneas 6xx/7xx de asientos POSTED por centro y calcula totales con
4 decimales (Decimal, nunca float). Solo cuentan asientos POSTED del ejercicio.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from services.costcenters.centros import crear_centro
from services.costcenters.informes import informe_costes
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc


async def _cuenta(db_session, empresa_id, code: str) -> AccountPlan:
    cuenta = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
        )
    )
    assert cuenta is not None
    return cuenta


async def _asiento(db_session, empresa_id, fecha: date, centro_id, debe_code, haber_code, importe: str, imputar_haber: bool = False):
    c1 = await _cuenta(db_session, empresa_id, debe_code)
    c2 = await _cuenta(db_session, empresa_id, haber_code)
    if imputar_haber:
        l1 = {"cuenta": c1.code, "debe": importe, "haber": "0"}
        l2 = {"cuenta": c2.code, "debe": "0", "haber": importe, "centro_coste_id": str(centro_id)}
    else:
        l1 = {"cuenta": c1.code, "debe": importe, "haber": "0", "centro_coste_id": str(centro_id)}
        l2 = {"cuenta": c2.code, "debe": "0", "haber": importe}
    return await crear_asiento_multilinea(
        db_session,
        empresa_id=empresa_id,
        fecha=fecha,
        concepto="Movimiento",
        lineas=[l1, l2],
    )


async def test_agrega_coste_e_ingreso_por_centro(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="AGG", nombre="Agregado", tipo="proyecto")

    # 6000 con Debe 250 (coste)
    await _asiento(db_session, 10, date(2026, 3, 10), centro["id"], "6000", "5720", "250.0000")
    # 7000 con Haber 50 (ingreso) -> imputar la línea de Haber
    await _asiento(db_session, 10, date(2026, 4, 10), centro["id"], "5720", "7000", "50.0000", imputar_haber=True)

    informe = await informe_costes(db_session, empresa_id=10, ejercicio=2026)
    assert informe["n_filas"] == 1
    fila = informe["filas"][0]
    assert fila["codigo"] == "AGG"
    assert fila["directo_debe"] == "250.0000"
    assert fila["directo_haber"] == "50.0000"
    assert fila["subtotal"] == "200.0000"
    assert informe["totales"] == {
        "coste": "250.0000",
        "ingreso": "50.0000",
        "neto": "200.0000",
    }


async def test_solo_cuenta_asientos_posteado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="POS", nombre="Posteado", tipo="proyecto")
    c6000 = await _cuenta(db_session, 10, "6000")
    c570 = await _cuenta(db_session, 10, "5720")

    # Borrador NO cuenta
    await crear_borrador_(db_session, 10, date(2026, 5, 1), c6000, c570, centro["id"])
    # POSTED sí
    await _asiento(db_session, 10, date(2026, 5, 1), centro["id"], "6000", "5720", "100.0000")

    informe = await informe_costes(db_session, empresa_id=10, ejercicio=2026)
    assert informe["totales"]["coste"] == "100.0000"


async def crear_borrador_(db_session, empresa_id, fecha: date, c6000, c570, centro_id):
    from services.journal.entry_service import crear_borrador

    await crear_borrador(
        db_session,
        empresa_id=empresa_id,
        fecha=fecha,
        concepto="Borrador no posteado",
        lineas=[
            {"account_id": c6000.id, "debit": Decimal("999.0000"), "credit": Decimal(0), "centro_coste_id": centro_id},
            {"account_id": c570.id, "debit": Decimal(0), "credit": Decimal("999.0000")},
        ],
    )


async def test_fuera_de_ejercicio_no_cuenta(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="EJE", nombre="2025", tipo="proyecto")
    await _asiento(db_session, 10, date(2025, 12, 31), centro["id"], "6000", "5720", "10.0000")

    informe = await informe_costes(db_session, empresa_id=10, ejercicio=2026)
    assert informe["n_filas"] == 0
    assert informe["totales"]["coste"] == "0.0000"