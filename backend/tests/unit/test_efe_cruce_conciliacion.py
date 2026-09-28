"""Cruce del EFE con la conciliacion bancaria (T024, US2/FR-005/D5).

research.md D5: si el ultimo extracto conciliado de una cuenta de tesoreria no
coincide con el `saldo_final` del EFE, el informe se marca `sin_conciliar` como
**aviso** y se puede formular igualmente (no se exige 100 % de coincidencia,
Assumptions de la spec). Sin conciliacion previa no hay diferencia: es ausencia
de dato, no descuadre.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.cashflow.efe import formular_efe, generar_efe
from services.cashflow.errores import CashflowError
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


async def _apertura_y_venta(db) -> None:
    await soporte.plantar_cuenta(
        db, empresa_id=EMPRESA, code="1000", parent="100", name="Capital social"
    )
    await soporte.publicar_asiento(
        db,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 1, 2),
        lineas=[
            {"cuenta": "5720", "debe": "3000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "3000.0000"},
        ],
        concepto="Apertura",
        tipo="OPENING",
    )
    await soporte.publicar_asiento(
        db,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 4, 1),
        lineas=[
            {"cuenta": "5720", "debe": "1000.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "1000.0000"},
        ],
        concepto="Cobro de venta",
    )
    await db.flush()


def _conciliacion(db, **kwargs) -> None:
    from models.treasury.conciliacion import Conciliacion, ConciliacionEstado

    async def _op() -> None:
        cuentas = await soporte.cuentas(db, EMPRESA)
        banco = Decimal(str(kwargs.get("saldo_banco", "0.0000")))
        libros = Decimal(str(kwargs.get("saldo_libros", "0.0000")))
        db.add(
            Conciliacion(
                empresa_id=EMPRESA,
                cuenta_id=cuentas["5720"],
                ejercicio=EJERCICIO,
                fecha_inicio=date(EJERCICIO, 1, 1),
                fecha_fin=kwargs.get("fecha_fin", date(EJERCICIO, 6, 30)),
                saldo_banco=banco,
                saldo_libros=libros,
                diferencia=banco - libros,
                estado=ConciliacionEstado.cerrada,
            )
        )
        await db.flush()

    return _op


async def test_sin_conciliacion_no_hay_diferencia(db_session):
    await _apertura_y_venta(db_session)
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["saldo_conciliacion"] is None
    assert informe["sin_conciliar"] is False
    assert informe["cuadre"] is True


async def test_conciliacion_que_coincide_no_avisa(db_session):
    await _apertura_y_venta(db_session)
    # El saldo final del diario es 4000 (3000 de apertura + 1000 de cobro).
    await _conciliacion(db_session, saldo_banco="4000.0000", saldo_libros="4000.0000")()
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["saldo_final"] == Decimal("4000.0000")
    assert informe["saldo_conciliacion"] == Decimal("4000.0000")
    assert informe["sin_conciliar"] is False


async def test_diferencia_por_movimientos_no_conciliados_avisa_sin_bloquear(db_session):
    await _apertura_y_venta(db_session)
    await _conciliacion(db_session, saldo_banco="3800.0000", saldo_libros="4000.0000")()
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["cuadre"] is True
    assert informe["sin_conciliar"] is True
    assert informe["saldo_conciliacion"] == Decimal("3800.0000")
    assert informe["saldo_final"] == Decimal("4000.0000")

    # El aviso NO bloquea la formulacion (Assumptions de la spec).
    resultado = await formular_efe(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    assert resultado["estado"] == "formulado"
    assert resultado["cuadre"] is True
    assert resultado["sin_conciliar"] is True


async def test_conciliacion_posterior_al_ejercicio_se_ignora(db_session):
    """Solo cruza el extracto anterior al cierre del ejercicio."""
    await _apertura_y_venta(db_session)
    await _conciliacion(
        db_session,
        fecha_fin=date(EJERCICIO + 1, 3, 31),
        saldo_banco="100.0000",
        saldo_libros="4000.0000",
    )()
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["saldo_conciliacion"] is None
    assert informe["sin_conciliar"] is False


async def test_diferencia_sub_euro_no_se_olvida(db_session):
    """Una diferencia de 0.50 entre banco y libros tambien es diferencia.

    La comparacion es en `Decimal` (SC-005): ningun redondeo la enmascara.
    """
    await _apertura_y_venta(db_session)
    await _conciliacion(db_session, saldo_banco="3800.5000", saldo_libros="3801.0000")()
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["cuadre"] is True
    assert informe["saldo_conciliacion"] == Decimal("3800.5000")
    assert informe["sin_conciliar"] is True


def test_diferencia_no_impide_la_lectura_del_efe_por_api(cashflow_client):
    """Escenario 4 del quickstart: `sin_conciliar` viaja en la respuesta."""
    cf = cashflow_client
    cf.plantar(empresa_id=10, code="1000", parent="100", name="Capital social")
    cf.asiento(
        empresa_id=10,
        fecha="2026-01-02",
        lineas=[
            {"cuenta": "5720", "debe": "3000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "3000.0000"},
        ],
        tipo="OPENING",
    )
    cf.asiento(
        empresa_id=10,
        fecha="2026-04-01",
        lineas=[
            {"cuenta": "5720", "debe": "1000.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "1000.0000"},
        ],
    )
    cf.conciliacion(empresa_id=10, saldo_banco="3800.0000", saldo_libros="4000.0000")

    informe = cf.get("/api/v1/tesoreria/efe", ejercicio=2026).json()
    assert informe["saldo_final"] == "4000.0000"
    assert informe["cuadre"] is True
    assert informe["sin_conciliar"] is True
    assert informe["saldo_conciliacion"] == "3800.0000"
    assert informe["formulado"] is False

    formulada = cf.post("/api/v1/tesoreria/efe/formular", {"ejercicio": 2026})
    assert formulada.status_code == 200
    assert formulada.json()["sin_conciliar"] is True


async def test_efe_otro_ejercicio_no_ve_la_conciliacion(db_session):
    await _apertura_y_venta(db_session)
    await _conciliacion(db_session, saldo_banco="1.0000", saldo_libros="2.0000")()
    await db_session.commit()

    anterior = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO - 1)
    assert anterior["saldo_conciliacion"] is None
    assert anterior["sin_conciliar"] is False


async def test_efe_descuadrado_no_se_puede_formular(db_session, monkeypatch):
    """FR-004: si el cuadre falla, 422 y no se persiste snapshot."""
    from sqlalchemy import select

    from models.treasury.efe import InformeEFE

    await _apertura_y_venta(db_session)
    await db_session.commit()

    # Se fuerza un descuadre para probar la rama de negocio del servicio.
    real = generar_efe

    async def _descadrado(*args, **kwargs):
        informe = await real(*args, **kwargs)
        informe["cuadre"] = False
        return informe

    monkeypatch.setattr("services.cashflow.efe.generar_efe", _descadrado)
    with pytest.raises(CashflowError) as exc:
        await formular_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert exc.value.code == "efe_descuadrado"
    assert exc.value.status_code == 422
    assert (await db_session.scalars(select(InformeEFE))).all() == []
