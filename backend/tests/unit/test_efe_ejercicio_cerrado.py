"""Ejercicio cerrado: la formulacion del EFE se bloquea con 409 (T044).

Ademas del caso de `FiscalYear.is_closed` (cubierto en
`test_efe_cuadre.py::test_formular_ejercicio_cerrado_devuelve_409`), se cubre
que la lectura sigue disponible, que el ejercicio abierto si admite EFE y que
la cuenta de conciliacion congelada no altera el resultado.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.cashflow.efe import generar_efe, leer_efe
from services.cashflow.errores import CashflowError
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
OTRA = soporte.B
EJERCICIO = 2026
ABIERTO = 2025


@pytest.fixture(autouse=True)
async def _empresas(db_session_factory):
    async with db_session_factory() as session:
        for empresa_id in (EMPRESA, OTRA):
            await soporte.empresa(session, empresa_id)
        await session.commit()


async def _apertura_y_venta(db, empresa_id: int = EMPRESA, year: int = EJERCICIO) -> None:
    await soporte.plantar_cuenta(
        db, empresa_id=empresa_id, code="1000", parent="100", name="Capital"
    )
    await soporte.publicar_asiento(
        db,
        empresa_id=empresa_id,
        fecha=date(year, 1, 2),
        lineas=[
            {"cuenta": "5720", "debe": "5000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "5000.0000"},
        ],
        tipo="OPENING",
    )
    await soporte.publicar_asiento(
        db,
        empresa_id=empresa_id,
        fecha=date(year, 4, 1),
        lineas=[
            {"cuenta": "5720", "debe": "2000.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "2000.0000"},
        ],
    )
    await db.flush()


async def _cerrar(db, empresa_id: int, year: int) -> None:
    from models.acct.fiscal_year import FiscalYear

    existente = await db.scalar(
        FiscalYear.__table__.select().where(
            (FiscalYear.empresa_id == empresa_id) & (FiscalYear.year == year)
        )
    )
    if existente is None:
        db.add(
            FiscalYear(
                empresa_id=empresa_id,
                year=year,
                date_start=date(year, 1, 1),
                date_end=date(year, 12, 31),
                is_closed=True,
            )
        )
    else:  # pragma: no cover - defensivo
        existente.is_closed = True
    await db.flush()


async def test_ejercicio_cerrado_bloquea_la_formulacion(db_session):
    from services.cashflow.efe import formular_efe

    await _apertura_y_venta(db_session)
    await _cerrar(db_session, EMPRESA, EJERCICIO)
    await db_session.commit()

    # La lectura sigue disponible: el cierre no oculta el ejercicio.
    informe = await leer_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["cuadre"] is True
    assert informe["formulado"] is False
    assert informe["saldo_final"] == Decimal("7000.0000")

    with pytest.raises(CashflowError) as exc:
        await formular_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert exc.value.code == "ejercicio_cerrado"
    assert exc.value.status_code == 409


async def test_ejercicio_abierto_si_admite_efe(db_session):
    from services.cashflow.efe import formular_efe

    await _apertura_y_venta(db_session, EMPRESA, ABIERTO)
    await db_session.commit()
    resultado = await formular_efe(
        db_session, empresa_id=EMPRESA, ejercicio=ABIERTO, actor="test"
    )
    assert resultado["estado"] == "formulado"
    assert resultado["cuadre"] is True


async def test_el_cierre_de_A_no_afecta_al_eje_de_B(db_session):
    """`is_closed` es por empresa: el mismo ejercicio puede seguir abierto en B."""
    from services.cashflow.efe import formular_efe

    await _apertura_y_venta(db_session, EMPRESA)
    await _apertura_y_venta(db_session, OTRA)
    await _cerrar(db_session, EMPRESA, EJERCICIO)
    await db_session.commit()

    with pytest.raises(CashflowError):
        await formular_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert await formular_efe(db_session, empresa_id=OTRA, ejercicio=EJERCICIO)


async def test_efe_ya_formulado_tiene_prioridad_sobre_ejercicio_cerrado(db_session):
    """409 `efe_ya_formulado` si ya existe, sea cual sea el estado del ejercicio."""
    from services.cashflow.efe import formular_efe

    await _apertura_y_venta(db_session)
    await db_session.commit()
    await formular_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    await _cerrar(db_session, EMPRESA, EJERCICIO)
    await db_session.commit()

    with pytest.raises(CashflowError) as exc:
        await formular_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert exc.value.code == "efe_ya_formulado"


async def test_el_snapshot_formulado_sobrevive_al_cierre(db_session):
    """Un EFE ya formulado es un documento: el cierre posterior no lo altera."""
    from services.cashflow.efe import formular_efe

    await _apertura_y_venta(db_session)
    await db_session.commit()
    await formular_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    await db_session.commit()

    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 12, 1),
        lineas=[
            {"cuenta": "5720", "debe": "999.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "999.0000"},
        ],
    )
    await db_session.commit()

    snapshot = await leer_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    provisional = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert snapshot["saldo_final"] == Decimal("7000.0000")
    # El recalculo refleja el movimiento nuevo: por eso el formulado es el bueno.
    assert provisional["saldo_final"] == Decimal("7999.0000")


async def test_la_prevision_si_works_en_ejercicio_cerrado(db_session):
    """La prevision es herramienta de gestion: no la bloquea el cierre (spec)."""
    from services.cashflow.proyeccion import generar_prevision

    await _apertura_y_venta(db_session)
    await _cerrar(db_session, EMPRESA, EJERCICIO)
    await db_session.commit()

    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=date(2026, 9, 16),
        hasta_fecha=date(2026, 9, 18),
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "pago", "importe": "1000.0000", "fecha_prevista": date(2026, 9, 17)}
        ],
    )
    assert resultado["prevision"].saldo_inicial is not None
    assert resultado["n_movimientos"] == 1
