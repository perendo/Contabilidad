"""Cuadre del Estado de Flujos de Efectivo (T023, US2/FR-004/SC-003).

Verifica la identidad contable que sostiene el cuadre (constitucion I):

    saldo_inicial + variacion_neta == saldo_final
    variacion_neta == variacion real de la tesoreria del diario

y que un EFE descuadrado no es formulable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.cashflow.efe import formular_efe, generar_efe
from services.cashflow.errores import CashflowError
from services.cashflow.utils import c4
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


async def _apertura(db, importe: str = "3000.0000") -> None:
    await soporte.plantar_cuenta(
        db, empresa_id=EMPRESA, code="1000", parent="100", name="Capital social"
    )
    await soporte.publicar_asiento(
        db,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 1, 2),
        lineas=[
            {"cuenta": "5720", "debe": importe, "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": importe},
        ],
        concepto="Apertura",
        tipo="OPENING",
    )
    await db.flush()


async def _cobro(db, importe: str = "1000.0000", fecha=None) -> None:
    await soporte.publicar_asiento(
        db,
        empresa_id=EMPRESA,
        fecha=fecha or date(EJERCICIO, 4, 1),
        lineas=[
            {"cuenta": "5720", "debe": importe, "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": importe},
        ],
        concepto="Cobro de venta",
    )
    await db.flush()


async def _pago(db, importe: str = "400.0000", fecha=None) -> None:
    await soporte.publicar_asiento(
        db,
        empresa_id=EMPRESA,
        fecha=fecha or date(EJERCICIO, 5, 1),
        lineas=[
            {"cuenta": "6400", "debe": importe, "haber": "0"},
            {"cuenta": "5720", "debe": "0", "haber": importe},
        ],
        concepto="Pago de nomina",
    )
    await db.flush()


# --- Cuadre (SC-003) ---------------------------------------------------------


async def test_efe_cuadra_sin_movimientos(db_session):
    await _apertura(db_session, "3000.0000")
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["saldo_inicial"] == Decimal("3000.0000")
    assert informe["variacion_neta"] == Decimal("0.0000")
    assert informe["saldo_final"] == Decimal("3000.0000")
    assert informe["cuadre"] is True
    # El asiento de apertura no genera lineas: ya esta en el saldo inicial.
    assert informe["lineas"] == []


async def test_efe_cuadra_con_cobro_y_pago(db_session):
    await _apertura(db_session, "3000.0000")
    await _cobro(db_session, "1000.0000")
    await _pago(db_session, "400.0000")
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["cuadre"] is True
    assert informe["saldo_inicial"] == Decimal("3000.0000")
    # La variacion de la tesoreria real es +1000 -400 = +600.
    assert informe["variacion_neta"] == Decimal("600.0000")
    assert informe["variacion_tesoreria"] == Decimal("600.0000")
    assert informe["saldo_final"] == Decimal("3600.0000")
    # `saldo_inicial + variacion == saldo_final` (FR-004).
    assert informe["saldo_inicial"] + informe["variacion_neta"] == informe["saldo_final"]


async def test_efe_reparte_las_lineas_en_su_bloque(db_session):
    await _apertura(db_session, "3000.0000")
    await _cobro(db_session, "1000.0000")
    await _pago(db_session, "400.0000")
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    por_codigo = {linea["codigo_cuenta"]: linea for linea in informe["lineas"]}
    # 7000 (ingreso) recibe el signo opuesto a su saldo: -(-1000) = +1000.
    assert por_codigo["7000"]["bloque"] == "operativa"
    assert por_codigo["7000"]["importe"] == Decimal("1000.0000")
    # 6400 (gasto, suma 400) aporta -400 de tesoreria.
    assert por_codigo["6400"]["bloque"] == "operativa"
    assert por_codigo["6400"]["importe"] == Decimal("-400.0000")
    # Ninguna linea es una cuenta de tesoreria (derivan los saldos).
    assert "5720" not in por_codigo
    assert "1000" not in por_codigo
    assert informe["totales"]["operativa"] == Decimal("600.0000")
    assert informe["totales"]["inversion"] == Decimal("0.0000")
    assert informe["totales"]["financiacion"] == Decimal("0.0000")


async def test_los_tres_bloques_suman_la_variacion(db_session):
    await _apertura(db_session, "5000.0000")
    # Operativa: venta cobrada.
    await _cobro(db_session, "2000.0000")
    # Inversion: compra de inmovilizado pagada.
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 6, 1),
        lineas=[
            {"cuenta": "2100", "debe": "1200.0000", "haber": "0"},
            {"cuenta": "5720", "debe": "0", "haber": "1200.0000"},
        ],
        concepto="Compra de inmovilizado",
    )
    # Financiacion: devolucion de prestamo a largo plazo.
    await soporte.plantar_cuenta(
        db_session, empresa_id=EMPRESA, code="1600", parent="160", name="Prestamos LP"
    )
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 7, 1),
        lineas=[
            {"cuenta": "5720", "debe": "800.0000", "haber": "0"},
            {"cuenta": "1600", "debe": "0", "haber": "800.0000"},
        ],
        concepto="Devolucion de prestamo",
    )
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["cuadre"] is True
    assert informe["totales"]["operativa"] == Decimal("2000.0000")
    assert informe["totales"]["inversion"] == Decimal("-1200.0000")
    assert informe["totales"]["financiacion"] == Decimal("800.0000")
    assert (
        informe["totales"]["operativa"]
        + informe["totales"]["inversion"]
        + informe["totales"]["financiacion"]
        == informe["variacion_neta"]
    )
    assert informe["saldo_final"] == Decimal("6600.0000")


async def test_importes_con_cuatro_decimales_no_derivan_redondeo(db_session):
    """SC-005: el cuadre se verifica en Decimal, sin deriva por coma flotante."""
    await _apertura(db_session, "1000.0000")
    for indice in range(3):
        await soporte.publicar_asiento(
            db_session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 3, indice + 1),
            lineas=[
                {"cuenta": "7000", "debe": "0", "haber": "0.1000"},
                {"cuenta": "5720", "debe": "0.1000", "haber": "0"},
            ],
            concepto="Cobro con céntimos",
        )
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["variacion_neta"] == Decimal("0.3000")
    assert informe["saldo_final"] == Decimal("1000.3000")
    assert informe["cuadre"] is True
    assert c4(informe["saldo_inicial"] + informe["variacion_neta"]) == informe["saldo_final"]


# --- Formulacion (T026) -----------------------------------------------------


async def test_formular_persiste_el_snapshot(db_session):
    from sqlalchemy import select

    from models.treasury.efe import EstadoInformeEFE, InformeEFE, LineaEFE

    await _apertura(db_session, "3000.0000")
    await _cobro(db_session, "1000.0000")
    await _pago(db_session, "400.0000")
    await db_session.commit()

    resultado = await formular_efe(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    assert resultado["estado"] == EstadoInformeEFE.formulado.value
    assert resultado["cuadre"] is True
    assert resultado["saldo_final"] == Decimal("3600.0000")

    informe = (
        await db_session.scalars(select(InformeEFE))
    ).one()
    assert informe.estado is EstadoInformeEFE.formulado
    assert informe.formulado_por == "test"
    lineas = (await db_session.scalars(select(LineaEFE))).all()
    assert len(lineas) == 2
    assert {l.codigo_cuenta for l in lineas} == {"7000", "6400"}
    assert all(l.empresa_id == EMPRESA for l in lineas)


async def test_formular_dos_veces_devuelve_409(db_session):
    await _apertura(db_session, "1000.0000")
    await db_session.commit()
    await formular_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    with pytest.raises(CashflowError) as exc:
        await formular_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert exc.value.code == "efe_ya_formulado"
    assert exc.value.status_code == 409


async def test_formular_ejercicio_cerrado_devuelve_409(db_session):
    """T044: el EFE no es formulable sobre un ejercicio cerrado (SPEC-004)."""
    from models.acct.fiscal_year import FiscalYear

    await _apertura(db_session, "1000.0000")
    db_session.add(
        FiscalYear(
            empresa_id=EMPRESA,
            year=EJERCICIO,
            date_start=date(EJERCICIO, 1, 1),
            date_end=date(EJERCICIO, 12, 31),
            is_closed=True,
        )
    )
    await db_session.commit()

    with pytest.raises(CashflowError) as exc:
        await formular_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert exc.value.code == "ejercicio_cerrado"
    assert exc.value.status_code == 409


async def test_ejercicio_invalido_rechazado(db_session):
    with pytest.raises(CashflowError) as exc:
        await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=1800)
    assert exc.value.code == "ejercicio_invalido"
    assert exc.value.status_code == 422


# --- Overrides del usuario (research D4) ------------------------------------


async def test_override_reclasifica_una_cuenta(db_session):
    await _apertura(db_session, "3000.0000")
    await _pago(db_session, "400.0000")
    await db_session.commit()

    cuentas = await soporte.cuentas(db_session, EMPRESA)
    informe = await generar_efe(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        clasificaciones=[{"cuenta_id": cuentas["6400"], "bloque": "inversion"}],
    )
    por_codigo = {linea["codigo_cuenta"]: linea for linea in informe["lineas"]}
    assert por_codigo["6400"]["bloque"] == "inversion"
    assert por_codigo["6400"]["override_usuario"] is True
    assert informe["totales"]["inversion"] == Decimal("-400.0000")
    assert informe["totales"]["operativa"] == Decimal("0.0000")
    # El override no altera la suma: el cuadre se mantiene.
    assert informe["cuadre"] is True
    assert informe["variacion_neta"] == Decimal("-400.0000")


async def test_override_persiste_en_el_snapshot(db_session):
    from sqlalchemy import select

    from models.treasury.efe import LineaEFE

    await _apertura(db_session, "3000.0000")
    await _pago(db_session, "400.0000")
    await db_session.commit()
    cuentas = await soporte.cuentas(db_session, EMPRESA)

    await formular_efe(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        clasificaciones=[{"cuenta_id": cuentas["6400"], "bloque": "inversion"}],
    )
    linea = (
        await db_session.scalars(select(LineaEFE).where(LineaEFE.codigo_cuenta == "6400"))
    ).one()
    assert linea.bloque.value == "inversion"
    assert linea.override_usuario is True


async def test_bloque_invalido_rechazado(db_session):
    await _apertura(db_session, "1000.0000")
    await db_session.commit()
    cuentas = await soporte.cuentas(db_session, EMPRESA)
    with pytest.raises(CashflowError) as exc:
        await generar_efe(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            clasificaciones=[{"cuenta_id": cuentas["6400"], "bloque": "operativo"}],
        )
    assert exc.value.code == "bloque_invalido"


async def test_cuenta_sin_movimientos_no_se_puede_reclasificar(db_session):
    await _apertura(db_session, "1000.0000")
    await db_session.commit()
    cuentas = await soporte.cuentas(db_session, EMPRESA)
    with pytest.raises(CashflowError) as exc:
        await generar_efe(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            clasificaciones=[{"cuenta_id": cuentas["7000"], "bloque": "inversion"}],
        )
    assert exc.value.code == "cuenta_no_clasificable"


async def test_cuenta_ajena_rechazada_en_override(db_session):
    """La cuenta debe ser de la empresa activa y tener movimientos."""
    await soporte.empresa(db_session, soporte.B)
    await _apertura(db_session, "1000.0000")
    await db_session.commit()
    cuentas_b = await soporte.cuentas(db_session, soporte.B)
    with pytest.raises(CashflowError) as exc:
        await generar_efe(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            clasificaciones=[{"cuenta_id": cuentas_b["6400"], "bloque": "inversion"}],
        )
    assert exc.value.code == "cuenta_no_clasificable"
