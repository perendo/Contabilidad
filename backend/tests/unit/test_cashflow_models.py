"""Tests de modelos fundacionales de SPEC-027 (T010).

Cubre: constraint de rango y correlatividad de `numero_prevision` (constitucion
IV), FKs compuestas por `empresa_id` en vencimiento y cuenta (constitucion
III), `importe > 0` en `MovimientoPrevision`, la obligatoriedad del motivo de
exclusion, y que `AlertaLiquidez` solo admite saldo proyectado negativo.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models.acct.account_plan import AccountPlan
from models.treasury.alerta_liquidez import (
    AccionSugeridaLiquidez,
    AlertaLiquidez,
    EstadoAlertaLiquidez,
)
from models.treasury.efe import BloqueEFE, InformeEFE, LineaEFE
from models.treasury.movimiento_prevision import (
    FrecuenciaMovimiento,
    MovimientoPrevision,
    OrigenMovimientoPrevision,
    TipoMovimientoPrevision,
)
from models.treasury.prevision import (
    EstadoPrevision,
    GranularidadPrevision,
    PrevisionTesoreria,
)
from services.cashflow.proyeccion import proximo_numero_prevision
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
OTRA = soporte.B
EJERCICIO = 2026


@pytest.fixture(autouse=True)
async def _empresas(db_session_factory):
    async with db_session_factory() as session:
        for empresa_id in (EMPRESA, OTRA):
            await soporte.empresa(session, empresa_id)
        await session.commit()


def _prevision(empresa_id: int = EMPRESA, **kwargs) -> PrevisionTesoreria:
    datos = {
        "empresa_id": empresa_id,
        "numero_prevision": 1,
        "desde_fecha": date(EJERCICIO, 9, 16),
        "hasta_fecha": date(EJERCICIO, 10, 31),
        "granularidad": GranularidadPrevision.dia,
        "saldo_inicial": Decimal("1000.0000"),
        "saldo_final": Decimal("1000.0000"),
        "estado": EstadoPrevision.generada,
    }
    datos.update(kwargs)
    return PrevisionTesoreria(**datos)


def _movimiento(prevision_id: uuid.UUID | None, **kwargs) -> MovimientoPrevision:
    datos: dict[str, object] = {
        "empresa_id": EMPRESA,
        "prevision_id": prevision_id,
        "origen": OrigenMovimientoPrevision.pago_recurrente,
        "tipo": TipoMovimientoPrevision.pago,
        "importe": Decimal("1200.0000"),
        "fecha_prevista": date(EJERCICIO, 10, 1),
        "frecuencia": FrecuenciaMovimiento.unico,
        "incluido": True,
    }
    datos.update(kwargs)
    return MovimientoPrevision(**datos)  # type: ignore[arg-type]


# --- T005: prevision, rango y correlatividad (constitucion IV) --------------


async def test_prevision_rango_de_fechas_valido(db_session):
    db_session.add(_prevision())
    await db_session.commit()
    assert (await db_session.scalars(select(PrevisionTesoreria))).all() != []


async def test_prevision_hasta_antes_de_desde_rechazada(db_session):
    db_session.add(
        _prevision(desde_fecha=date(EJERCICIO, 12, 31), hasta_fecha=date(EJERCICIO, 1, 1))
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_numero_prevision_no_positivo_rechazado(db_session):
    db_session.add(_prevision(numero_prevision=0))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_numero_prevision_correlativo_por_empresa(db_session):
    assert await proximo_numero_prevision(db_session, EMPRESA) == 1
    db_session.add(_prevision(numero_prevision=1))
    await db_session.commit()
    assert await proximo_numero_prevision(db_session, EMPRESA) == 2
    db_session.add(_prevision(numero_prevision=2))
    await db_session.commit()
    assert await proximo_numero_prevision(db_session, EMPRESA) == 3
    # La correlatividad es por empresa: la otra arranca en 1.
    assert await proximo_numero_prevision(db_session, OTRA) == 1


async def test_numero_prevision_duplicado_rechazado(db_session):
    db_session.add(_prevision(numero_prevision=1))
    await db_session.commit()
    db_session.add(_prevision(numero_prevision=1))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_misma_prevision_numero_en_otra_empresa_permitida(db_session):
    db_session.add(_prevision(EMPRESA, numero_prevision=1))
    db_session.add(_prevision(OTRA, numero_prevision=1))
    await db_session.commit()
    assert len((await db_session.scalars(select(PrevisionTesoreria))).all()) == 2


# --- T006: movimiento proyectado -------------------------------------------


async def test_movimiento_importe_no_positivo_rechazado(db_session):
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    db_session.add(_movimiento(prevision.id, importe=Decimal(0)))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_movimiento_importe_negativo_rechazado(db_session):
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    db_session.add(_movimiento(prevision.id, importe=Decimal("-5.0000")))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_movimiento_excluido_exige_motivo(db_session):
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    db_session.add(_movimiento(prevision.id, incluido=False))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_movimiento_incluido_no_admite_motivo(db_session):
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    db_session.add(_movimiento(prevision.id, motivo_exclusion="cobrado"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_movimiento_excluido_con_motivo_se_persiste(db_session):
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    db_session.add(
        _movimiento(
            prevision.id,
            incluido=False,
            motivo_exclusion="sin_fecha",
            fecha_prevista=None,
        )
    )
    await db_session.commit()
    fila = (await db_session.scalars(select(MovimientoPrevision))).one()
    assert fila.motivo_exclusion == "sin_fecha"
    assert fila.incluido is False


async def test_vencimiento_de_otra_empresa_rechazado(db_session):
    """FK compuesta (empresa_id): el vencimiento de la empresa 20 no cuela en la 10."""
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    ajeno = await soporte.vencimiento(
        db_session,
        empresa_id=OTRA,
        fecha_vencimiento=date(EJERCICIO, 10, 1),
        recibo_num="R-OTRA",
    )
    db_session.add(_movimiento(prevision.id, vencimiento_id=ajeno.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_vencimiento_de_la_misma_empresa_se_enlaza(db_session):
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    propio = await soporte.vencimiento(
        db_session,
        empresa_id=EMPRESA,
        fecha_vencimiento=date(EJERCICIO, 10, 1),
        recibo_num="R-PROPIO",
    )
    db_session.add(
        _movimiento(
            prevision.id,
            vencimiento_id=propio.id,
            origen=OrigenMovimientoPrevision.vencimiento,
        )
    )
    await db_session.commit()
    fila = (await db_session.scalars(select(MovimientoPrevision))).one()
    assert fila.vencimiento_id == propio.id


async def test_movimiento_de_otra_prevision_rechazado(db_session):
    prevision_ajena = _prevision(OTRA, numero_prevision=1)
    db_session.add(prevision_ajena)
    await db_session.flush()
    db_session.add(_movimiento(prevision_ajena.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


# --- T007: alerta de liquidez -----------------------------------------------


async def test_alerta_con_saldo_no_negativo_rechazada(db_session):
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    db_session.add(
        AlertaLiquidez(
            empresa_id=EMPRESA,
            prevision_id=prevision.id,
            fecha=date(EJERCICIO, 10, 1),
            saldo_proyectado=Decimal("500.0000"),
            importe_deficit=Decimal("500.0000"),
            estado=EstadoAlertaLiquidez.abierta,
            accion_sugerida=AccionSugeridaLiquidez.reprogramar_pago,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_alerta_deficit_no_positivo_rechazada(db_session):
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    db_session.add(
        AlertaLiquidez(
            empresa_id=EMPRESA,
            prevision_id=prevision.id,
            fecha=date(EJERCICIO, 10, 1),
            saldo_proyectado=Decimal("-500.0000"),
            importe_deficit=Decimal(0),
            estado=EstadoAlertaLiquidez.abierta,
            accion_sugerida=AccionSugeridaLiquidez.incluir_ingreso,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_alerta_unica_por_bucket(db_session):
    prevision = _prevision()
    db_session.add(prevision)
    await db_session.flush()
    for _ in range(2):
        db_session.add(
            AlertaLiquidez(
                empresa_id=EMPRESA,
                prevision_id=prevision.id,
                fecha=date(EJERCICIO, 10, 1),
                saldo_proyectado=Decimal("-100.0000"),
                importe_deficit=Decimal("100.0000"),
                estado=EstadoAlertaLiquidez.abierta,
                accion_sugerida=AccionSugeridaLiquidez.reprogramar_pago,
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_alerta_de_otra_prevision_rechazada(db_session):
    ajena = _prevision(OTRA, numero_prevision=1)
    db_session.add(ajena)
    await db_session.flush()
    db_session.add(
        AlertaLiquidez(
            empresa_id=EMPRESA,
            prevision_id=ajena.id,
            fecha=date(EJERCICIO, 10, 1),
            saldo_proyectado=Decimal("-100.0000"),
            importe_deficit=Decimal("100.0000"),
            estado=EstadoAlertaLiquidez.abierta,
            accion_sugerida=AccionSugeridaLiquidez.reprogramar_pago,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


# --- T008: informe y lineas del EFE -----------------------------------------


async def test_efe_unico_por_empresa_y_ejercicio(db_session):
    db_session.add(InformeEFE(empresa_id=EMPRESA, ejercicio=EJERCICIO))
    await db_session.commit()
    db_session.add(InformeEFE(empresa_id=EMPRESA, ejercicio=EJERCICIO))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_efe_mismo_ejercicio_otra_empresa_permitido(db_session):
    db_session.add(InformeEFE(empresa_id=EMPRESA, ejercicio=EJERCICIO))
    db_session.add(InformeEFE(empresa_id=OTRA, ejercicio=EJERCICIO))
    await db_session.commit()
    assert len((await db_session.scalars(select(InformeEFE))).all()) == 2


async def test_linea_efe_cuenta_unica_por_informe(db_session):
    informe = InformeEFE(empresa_id=EMPRESA, ejercicio=EJERCICIO)
    db_session.add(informe)
    await db_session.flush()
    cuenta = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == EMPRESA, AccountPlan.code == "6400"
        )
    )
    assert cuenta is not None
    for _ in range(2):
        db_session.add(
            LineaEFE(
                empresa_id=EMPRESA,
                informe_id=informe.id,
                bloque=BloqueEFE.operativa,
                cuenta_id=cuenta.id,
                codigo_cuenta="6400",
                importe=Decimal("100.0000"),
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_linea_efe_cuenta_de_otra_empresa_rechazada(db_session):
    informe = InformeEFE(empresa_id=EMPRESA, ejercicio=EJERCICIO)
    db_session.add(informe)
    await db_session.flush()
    cuenta_ajena = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == OTRA, AccountPlan.code == "6400"
        )
    )
    assert cuenta_ajena is not None
    db_session.add(
        LineaEFE(
            empresa_id=EMPRESA,
            informe_id=informe.id,
            bloque=BloqueEFE.operativa,
            cuenta_id=cuenta_ajena.id,
            codigo_cuenta="6400",
            importe=Decimal("100.0000"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_snapshot_efe_formulado_es_append_only(db_session_factory):
    """Constitucion II: el EFE formulado no se actualiza ni se borra."""
    async with db_session_factory() as session:
        session.add(InformeEFE(empresa_id=EMPRESA, ejercicio=EJERCICIO, cuadre=True))
        await session.commit()

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text("UPDATE informe_efe SET cuadre = 0 WHERE empresa_id = :e"),
                {"e": EMPRESA},
            )

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text("DELETE FROM informe_efe WHERE empresa_id = :e"), {"e": EMPRESA}
            )


async def test_company_inexistente_no_soporta_prevision(db_session):
    db_session.add(_prevision(empresa_id=9999, numero_prevision=1))
    with pytest.raises(IntegrityError):
        await db_session.commit()
