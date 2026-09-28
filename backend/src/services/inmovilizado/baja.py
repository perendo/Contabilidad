"""Baja de activos del inmovilizado (SPEC-014 US3).

``dar_de_baja`` calcula la amortización hasta la fecha de baja con el método de
prorrateo RESUELTO en SPEC-014 (mensual = mes de baja completo; dias = cuota del
mes de baja proporcional al día), registra la fila ``BajaActivo`` (VNC,
resultado) y el asiento de baja balanceado (Debe 281 + 572/671 | Haber 21x +
771) vía el motor de SPEC-002/006, todo en la misma transacción ACID.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.inmovilizado.activo import ActivoInmovilizado, EstadoActivo
from models.inmovilizado.baja_activo import BajaActivo, TipoBaja
from models.inmovilizado.plan_amortizacion import EstadoPlan, PlanAmortizacion
from services.audit.writer import audit_escribir
from services.inmovilizado.errores import error
from services.inmovilizado.plan import fraccion_cuota_baja
from services.journal.motor import crear_asiento_multilinea

CUENTA_BANCO_BAJA = "5720"
CUENTA_PERDIDAS_BAJA = "6710"
CUENTA_BENEFICIOS_BAJA = "7710"


def _clave(fila: PlanAmortizacion) -> tuple[int, int]:
    return (fila.ejercicio, fila.periodo)


async def _ejercicio_abierto(db: AsyncSession, empresa_id: int, anio: int) -> None:
    fy = await db.scalar(
        select(FiscalYear).where(FiscalYear.empresa_id == empresa_id, FiscalYear.year == anio)
    )
    if fy is not None and fy.is_closed:
        raise error("ejercicio_cerrado", f"El ejercicio {anio} está cerrado", 409)


def _amortizacion_hasta_baja(
    filas: list[PlanAmortizacion],
    fecha_baja: date,
    prorrateo: str,
) -> tuple[Decimal, Decimal]:
    """Devuelve (amortizacion_hasta_baja, amortizacion_acumulada).

    - ``amortizacion_acumulada``: lo realmente registrado en el plan (POSTED).
    - ``amortizacion_hasta_baja``: lo que debería llevar amortizado a la fecha de
      baja según el prorrateo (los meses previos completos y el mes de baja
      completo en ``mensual`` o proporcional al día en ``dias``).
    """
    posteadas = [f for f in filas if f.estado == EstadoPlan.amortizado]
    clave_baja = (fecha_baja.year, fecha_baja.month)
    pendientes_previa = [f for f in filas if f.estado == EstadoPlan.pendiente and _clave(f) < clave_baja]
    pendiente_baja = next(
        (f for f in filas if f.estado == EstadoPlan.pendiente and _clave(f) == clave_baja),
        None,
    )

    acumulada = posteadas[-1].acumulado if posteadas else Decimal(0)

    parcial_mes = Decimal(0)
    if pendiente_baja is not None:
        if prorrateo == "dias":
            parcial_mes = pendiente_baja.cuota * fraccion_cuota_baja(fecha_baja, "dias")
        else:
            parcial_mes = pendiente_baja.cuota

    hasta_baja = acumulada + sum((p.cuota for p in pendientes_previa), Decimal(0)) + parcial_mes
    return hasta_baja, acumulada


async def _codigo(db: AsyncSession, cuenta_id: int | None) -> str:
    if cuenta_id is None:
        raise error("cuenta_no_encontrada", "El activo no tiene cuenta asociada")
    cuenta = await db.scalar(select(AccountPlan).where(AccountPlan.id == cuenta_id))
    if cuenta is None:
        raise error("cuenta_no_encontrada", "No existe la cuenta asociada al activo")
    return cuenta.code


async def dar_de_baja(
    db: AsyncSession,
    *,
    empresa_id: int,
    activo_id: uuid.UUID,
    fecha_baja: date,
    precio_venta: str | Decimal | None = None,
    tipo: str = "venta",
    actor: str | None = None,
    prorrateo: str = "mensual",
) -> dict:
    activo = await db.scalar(
        select(ActivoInmovilizado).where(
            ActivoInmovilizado.empresa_id == empresa_id,
            ActivoInmovilizado.id == activo_id,
        )
    )
    if activo is None:
        raise error("activo_no_encontrado", "Activo inexistente en la empresa activa", 404)
    if activo.estado == EstadoActivo.dado_de_baja:
        raise error("activo_dado_de_baja", "El activo ya está dado de baja", 409)
    if fecha_baja < activo.fecha_alta:
        raise error("fecha_baja_invalida", "fecha_baja no puede ser anterior a fecha_alta")
    await _ejercicio_abierto(db, empresa_id, fecha_baja.year)

    try:
        tipo_enum = TipoBaja(tipo)
    except ValueError:
        raise error("tipo_baja_invalido", f"Tipo de baja desconocido: {tipo}")
    precio = Decimal(0) if precio_venta is None else Decimal(str(precio_venta))
    if precio < 0:
        raise error("precio_invalido", "precio_venta no puede ser negativo")

    filas = (
        await db.scalars(
            select(PlanAmortizacion)
            .where(
                PlanAmortizacion.empresa_id == empresa_id,
                PlanAmortizacion.activo_id == activo.id,
            )
            .order_by(PlanAmortizacion.ejercicio, PlanAmortizacion.periodo)
        )
    ).all()
    filas = list(filas)

    amort_hasta_baja, amort_acumulada = _amortizacion_hasta_baja(filas, fecha_baja, prorrateo)

    vnc = activo.coste_amortizable - amort_hasta_baja
    resultado = precio - vnc

    cuenta = await _codigo(db, activo.cuenta_id)
    cuenta_acum = await _codigo(db, activo.cuenta_acumulada_id)
    concepto = f"Baja de {activo.numero_activo} ({tipo_enum.value})"

    lineas: list[dict] = [
        {
            "cuenta": cuenta_acum,
            "debe": f"{amort_hasta_baja:0.4f}",
            "haber": "0.0000",
            "detalle": concepto,
        }
    ]
    if tipo_enum == TipoBaja.venta:
        lineas.append(
            {"cuenta": CUENTA_BANCO_BAJA, "debe": f"{precio:0.4f}", "haber": "0.0000", "detalle": concepto}
        )
    if resultado < 0:
        lineas.append(
            {
                "cuenta": CUENTA_PERDIDAS_BAJA,
                "debe": f"{-resultado:0.4f}",
                "haber": "0.0000",
                "detalle": concepto,
            }
        )
    elif resultado > 0:
        lineas.append(
            {
                "cuenta": CUENTA_BENEFICIOS_BAJA,
                "debe": "0.0000",
                "haber": f"{resultado:0.4f}",
                "detalle": concepto,
            }
        )
    lineas.append(
        {
            "cuenta": cuenta,
            "debe": "0.0000",
            "haber": f"{activo.coste_amortizable:0.4f}",
            "detalle": concepto,
        }
    )

    asiento = await crear_asiento_multilinea(
        db,
        empresa_id=empresa_id,
        fecha=fecha_baja,
        concepto=concepto,
        lineas=lineas,
        actor=actor,
    )

    baja = BajaActivo(
        empresa_id=empresa_id,
        activo_id=activo.id,
        fecha_baja=fecha_baja,
        precio_venta=precio,
        amortizacion_hasta_baja=amort_hasta_baja,
        amortizacion_acumulada=amort_acumulada,
        valor_neto_contable=vnc,
        resultado=resultado,
        asiento_id=asiento.id,
        tipo=tipo_enum,
    )
    if baja.id is None:
        baja.id = uuid.uuid4()
    db.add(baja)

    activo.estado = EstadoActivo.dado_de_baja
    activo.fecha_baja = fecha_baja
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="BAJA_ACTIVO",
        entity="baja_activo",
        entity_id=str(baja.id),
        payload={
            "activo_id": str(activo.id),
            "asiento_id": str(asiento.id),
            "fecha_baja": fecha_baja.isoformat(),
            "vnc": f"{vnc:0.4f}",
            "resultado": f"{resultado:0.4f}",
        },
    )
    await db.flush()

    return {
        "baja_id": str(baja.id),
        "activo_id": str(activo.id),
        "fecha_baja": fecha_baja.isoformat(),
        "precio_venta": f"{precio:0.4f}",
        "amortizacion_hasta_baja": f"{amort_hasta_baja:0.4f}",
        "amortizacion_acumulada": f"{amort_acumulada:0.4f}",
        "valor_neto_contable": f"{vnc:0.4f}",
        "resultado": f"{resultado:0.4f}",
        "asiento_id": str(asiento.id),
        "numero_asiento": asiento.numero_asiento,
        "tipo": tipo_enum.value,
    }


__all__ = ["dar_de_baja"]