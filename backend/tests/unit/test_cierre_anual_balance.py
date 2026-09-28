"""Cierre anual completo (SPEC-028 T026 + T027, US2/FR-002).

Verifica que los tres asientos del paquete de cierre (REGULARIZACION, CIERRE y
la apertura de SPEC-009) cuadran exactamente, y que son **inmutables** una vez
publicados: el trigger de SPEC-002 rechaza UPDATE y DELETE (constitucion II).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryTipo,
)
from models.closing.cierre_ejercicio import EstadoCierreEjercicio
from services.closing.cierre_anual import (
    calcular_cierre_saldos,
    calcular_regularizacion,
    generar_cierre_anual,
    obtener_cierre_anual,
)
from services.closing.errores import ClosingError
from services.closing.periodo import meses_cubiertos
from tests.unit import closing_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026
MESES = list(range(1, 13))


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


async def _preparar_ejercicio(session, con_gestion: bool = True) -> None:
    """Ejercicio con un balance patrimonial equilibrado (constitucion I).

    Dataset pensado para que los grupos 1-3 cuadren por si mismos, que es lo
    que exige la apertura de SPEC-009 (`calcular_saldos_patrimoniales`):

    - capital 17.000 -> inmovilizado 17.000
    - inmovilizado 3.000 a proveedor (deuda 3.000)
    - ventas 10.000 a clientes
    - gastos 7.000 contra clientes

    Tras regularizar, 2100 = 20.000 debe y 1110 + 1290 = 20.000 haber: la
    apertura sale balanceada y el resultado es +3.000.
    """
    await soporte.fiscal_year(session, empresa_id=EMPRESA, year=EJERCICIO)
    await soporte.fiscal_year(session, empresa_id=EMPRESA, year=EJERCICIO + 1)
    if con_gestion:
        # El seed de SPEC-001 no crea la 129: el cierre la exige (SPEC-004).
        await soporte.plantar_pyg(session, EMPRESA)
        await soporte.publicar_asiento(
            session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 1, 15),
            lineas=[
                {"cuenta": "1110", "haber": "17000.0000"},
                {"cuenta": "2100", "debe": "17000.0000"},
            ],
            concepto="Aportacion de capital",
        )
        await soporte.publicar_asiento(
            session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 2, 1),
            lineas=[
                {"cuenta": "2100", "debe": "3000.0000"},
                {"cuenta": "4100", "haber": "3000.0000"},
            ],
            concepto="Inmovilizado a proveedor",
        )
        await soporte.publicar_asiento(
            session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 3, 31),
            lineas=[
                {"cuenta": "7000", "haber": "10000.0000"},
                {"cuenta": "4300", "debe": "10000.0000"},
            ],
            concepto="Ventas del ejercicio",
        )
        await soporte.publicar_asiento(
            session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 6, 30),
            lineas=[
                {"cuenta": "6000", "debe": "7000.0000"},
                {"cuenta": "4300", "haber": "7000.0000"},
            ],
            concepto="Gastos del ejercicio",
        )
    await soporte.cerrar_meses(
        session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=MESES
    )



# --- T026 · los tres asientos cuadran --------------------------------------


async def test_la_regularizacion_cuadra_y_saldo_las_gestoras(db_session) -> None:
    await _preparar_ejercicio(db_session)
    lineas, resultado = await calcular_regularizacion(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO
    )
    debe = sum((linea["debe"] for linea in lineas), Decimal(0))
    haber = sum((linea["haber"] for linea in lineas), Decimal(0))
    # Gestion del ejercicio: 7.000 de gastos (6) frente a 10.000 de ingresos (7).
    assert debe == haber == Decimal("17000.0000")
    assert resultado == Decimal("3000.0000")
    por_cuenta: dict[str, tuple[Decimal, Decimal]] = {}
    for linea in lineas:
        d, h = por_cuenta.get(linea["cuenta"], (Decimal(0), Decimal(0)))
        por_cuenta[linea["cuenta"]] = (d + linea["debe"], h + linea["haber"])
    assert por_cuenta["7000"] == (Decimal("10000.0000"), Decimal(0))
    assert por_cuenta["6000"] == (Decimal(0), Decimal("7000.0000"))
    assert por_cuenta["1290"] == (Decimal("7000.0000"), Decimal("10000.0000"))



async def test_el_cierre_de_saldos_cuadra(db_session) -> None:
    """Tras la regularizacion, el cierre de saldos anula todas las cuentas."""
    from models.acct.journal import JournalEntryTipo
    from services.closing.cierre_anual import _publicar

    await _preparar_ejercicio(db_session)
    lineas_reg, _ = await calcular_regularizacion(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO
    )
    await _publicar(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        fecha=date(EJERCICIO, 12, 31),
        concepto="Regularizacion",
        tipo=JournalEntryTipo.REGULARIZACION,
        lineas=lineas_reg,
        actor="test",
    )
    lineas = await calcular_cierre_saldos(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    debe = sum((linea["debe"] for linea in lineas), Decimal(0))
    haber = sum((linea["haber"] for linea in lineas), Decimal(0))
    assert debe == haber == Decimal("23000.0000")
    # Toda cuenta queda con saldo cero tras el asiento de cierre.
    for linea in lineas:
        assert (linea["debe"] > 0) != (linea["haber"] > 0)
    por_cuenta = {linea["cuenta"]: linea for linea in lineas}
    assert por_cuenta["2100"]["debe"] == Decimal("20000.0000")
    assert por_cuenta["1110"]["haber"] == Decimal("17000.0000")
    assert por_cuenta["1290"]["haber"] == Decimal("3000.0000")
    assert por_cuenta["4300"]["debe"] == Decimal("3000.0000")
    assert por_cuenta["4100"]["haber"] == Decimal("3000.0000")


async def test_el_cierre_anual_publica_tres_asientos_balanceados(db_session) -> None:
    await _preparar_ejercicio(db_session)
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    regularizacion = resultado["asiento_regularizacion"]
    cierre = resultado["asiento_cierre"]
    assert regularizacion is not None and regularizacion.tipo is JournalEntryTipo.REGULARIZACION
    assert cierre is not None and cierre.tipo is JournalEntryTipo.CIERRE
    for asiento in (regularizacion, cierre):
        debe, haber = await soporte.saldos_asiento(
            db_session, empresa_id=EMPRESA, asiento_id=asiento.id
        )
        assert debe == haber and debe > 0
        assert asiento.estado is JournalEntryEstado.POSTED
        assert asiento.numero_asiento is not None


async def test_el_cierre_anual_registra_el_resultado_y_las_tres_entradas(db_session) -> None:
    await _preparar_ejercicio(db_session)
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    fila = resultado["cierre"]
    assert fila.estado is EstadoCierreEjercicio.completado
    assert fila.resultado_ejercicio == Decimal("3000.0000")
    assert fila.asiento_regularizacion_id == resultado["asiento_regularizacion"].id
    assert fila.asiento_cierre_id == resultado["asiento_cierre"].id
    assert fila.asiento_apertura_id is not None
    assert fila.fecha_cierre == date(EJERCICIO, 12, 31)
    assert fila.cerrado_por == "test"


async def test_el_cierre_anual_invoca_la_apertura_de_spec_009(db_session) -> None:
    """T033: la apertura del ejercicio siguiente la genera SPEC-009."""
    await _preparar_ejercicio(db_session)
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    apertura_id = resultado["asiento_apertura_id"]
    assert apertura_id is not None
    apertura = await db_session.get(JournalEntry, apertura_id)
    assert apertura is not None
    assert apertura.tipo is JournalEntryTipo.OPENING
    assert apertura.ejercicio == EJERCICIO + 1
    debe, haber = await soporte.saldos_asiento(
        db_session, empresa_id=EMPRESA, asiento_id=apertura.id
    )
    assert debe == haber and debe > 0


async def test_la_apertura_solo_se_genera_si_el_ejercicio_siguiente_existe(db_session) -> None:
    await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO)
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=MESES
    )
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    assert resultado["asiento_apertura_id"] is None


async def test_el_cierre_sin_gestion_no_publica_regularizacion(db_session) -> None:
    await _preparar_ejercicio(db_session, con_gestion=False)
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    assert resultado["asiento_regularizacion"] is None
    assert resultado["asiento_cierre"] is None
    assert resultado["resultado_ejercicio"] == Decimal("0.0000")


async def test_el_cierre_anual_bloquea_el_ejercicio(db_session) -> None:
    await _preparar_ejercicio(db_session)
    await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    from models.acct.fiscal_year import FiscalYear

    fy = await db_session.scalar(
        select(FiscalYear).where(FiscalYear.empresa_id == EMPRESA, FiscalYear.year == EJERCICIO)
    )
    assert fy is not None and fy.is_closed
    assert fy.cierre_entry_id is not None
    assert fy.regularizacion_entry_id is not None


# --- T027 · inmutabilidad de los asientos de cierre ------------------------


@pytest.mark.parametrize("campo", ["regularizacion_id", "cierre_id"])
async def test_los_asientos_de_cierre_rechazan_update(db_session, campo: str) -> None:
    """T027: el trigger `chk_journal_entry_immutable_posted` bloquea el UPDATE."""
    await _preparar_ejercicio(db_session)
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    entrada = resultado["asiento_regularizacion" if campo == "regularizacion_id" else "asiento_cierre"]
    assert entrada is not None
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text("UPDATE journal_entry SET concepto = 'tocada' WHERE id = :id"),
            {"id": entrada.id.hex},
        )
    assert "inmutable" in str(exc.value).lower()
    await db_session.rollback()


@pytest.mark.parametrize("campo", ["regularizacion_id", "cierre_id"])
async def test_los_asientos_de_cierre_rechazan_delete(db_session, campo: str) -> None:
    await _preparar_ejercicio(db_session)
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    entrada = resultado["asiento_regularizacion" if campo == "regularizacion_id" else "asiento_cierre"]
    assert entrada is not None
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text("DELETE FROM journal_entry WHERE id = :id"), {"id": entrada.id.hex}
        )
    assert "inmutable" in str(exc.value).lower()
    await db_session.rollback()


async def test_las_lineas_de_cierre_rechazan_update(db_session) -> None:
    from models.acct.journal import JournalEntryLine

    await _preparar_ejercicio(db_session)
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    entrada = resultado["asiento_cierre"]
    assert entrada is not None
    linea_id = await db_session.scalar(
        select(JournalEntryLine.id).where(JournalEntryLine.journal_entry_id == entrada.id)
    )
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text("UPDATE journal_entry_line SET debe = 1 WHERE id = :id"),
            {"id": linea_id.hex},
        )
    assert "inmutable" in str(exc.value).lower()
    await db_session.rollback()


async def test_el_cierre_registrado_tampoco_se_borra(db_session) -> None:
    await _preparar_ejercicio(db_session)
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("DELETE FROM cierre_ejercicio WHERE id = :id"),
            {"id": resultado["cierre"].id.hex},
        )
    await db_session.rollback()


# --- requisitos del flujo (T028/T029) en la capa de servicio --------------


async def test_el_cierre_anual_exige_todos_los_meses_cerrados(db_session) -> None:
    await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO)
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=list(range(1, 12))
    )
    with pytest.raises(ClosingError) as exc:
        await generar_cierre_anual(
            db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
        )
    assert exc.value.code == "periodos_intermedios_pendientes"
    assert exc.value.status_code == 409
    assert "12" in exc.value.message


async def test_un_trimestre_cerrado_cubre_sus_tres_meses(db_session) -> None:
    await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO)
    for trimestre in (1, 2, 3, 4):
        await soporte.cerrar_meses(
            db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[trimestre], tipo="TRIMESTRE"
        )
    assert await meses_cubiertos(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO) == set(
        range(1, 13)
    )
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    assert resultado["cierre"].estado is EstadoCierreEjercicio.completado


async def test_reintentar_el_cierre_anual_devuelve_409(db_session) -> None:
    await _preparar_ejercicio(db_session)
    await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    with pytest.raises(ClosingError) as exc:
        await generar_cierre_anual(
            db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
        )
    assert exc.value.code == "ejercicio_cerrado"
    assert exc.value.status_code == 409


async def test_el_cierre_anual_de_un_ejercicio_inexistente_devuelve_404(db_session) -> None:
    with pytest.raises(ClosingError) as exc:
        await generar_cierre_anual(
            db_session, empresa_id=EMPRESA, ejercicio=2024, actor="test"
        )
    assert exc.value.status_code == 404


async def test_obtener_cierre_anual_sin_registro_devuelve_404(db_session) -> None:
    with pytest.raises(ClosingError) as exc:
        await obtener_cierre_anual(
            db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO
        )
    assert exc.value.status_code == 404


async def test_el_cierre_anual_no_se_ve_desde_otra_empresa(db_session) -> None:
    await soporte.empresa(db_session, soporte.B)
    await _preparar_ejercicio(db_session)
    await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    with pytest.raises(ClosingError) as exc:
        await obtener_cierre_anual(
            db_session, empresa_id=soporte.B, ejercicio=EJERCICIO
        )
    assert exc.value.status_code == 404


async def test_la_numeracion_de_asientos_es_correlativa(db_session) -> None:
    """Constitucion IV: regularizacion, cierre y apertura llevan numero seguido."""
    await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO)
    await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO + 1)
    await soporte.plantar_pyg(db_session, EMPRESA)
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 11, 5),
        lineas=[
            {"cuenta": "7000", "haber": "1.0000"},
            {"cuenta": "5720", "debe": "1.0000"},
        ],
    )
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=MESES
    )
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test"
    )
    regularizacion = resultado["asiento_regularizacion"]
    cierre = resultado["asiento_cierre"]
    assert regularizacion is not None and cierre is not None
    assert regularizacion.numero_asiento < cierre.numero_asiento
