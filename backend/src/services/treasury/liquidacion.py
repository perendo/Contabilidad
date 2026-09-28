"""Liquidación de anticipos (SPEC-022 US1/US2): aplicación contra facturas.

Al aplicar un anticipo contra facturas se crea una ``LiquidacionAnticipo`` por
cada aplicación con su propio asiento balanceado (Debe 430/410 | Haber 438/407
según cliente/proveedor), se valida que la suma aplicada no supere el
``saldo_pendiente`` (FR-003: el exceso permanece como saldo a favor del
tercero) y se actualiza el saldo y el estado del anticipo de forma atómica.

Multi-tenant estricto (constitución III): la empresa activa se pasa como
parámetro y toda consulta/escritura filtra por ella.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.invoice.factura import Factura
from models.treasury.anticipo import Anticipo, EstadoAnticipo, TipoAnticipo
from models.treasury.liquidacion_anticipo import LiquidacionAnticipo
from services.accounting import verificar_balance
from services.audit import registrar_auditoria
from services.treasury.common import (
    CUENTA_ACREEDORES_SERVICIOS,
    CUENTA_CLIENTES,
    TesoreriaError,
    ejercicio_abierto,
)


class AplicacionAnticipo(BaseModel):
    factura_id: uuid.UUID
    importe_aplicado: str = Field(pattern=r"^\d+(\.\d{1,4})?$")


class LiquidacionError(TesoreriaError):
    pass


def _cuantizar(valor: Decimal | str) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.0000"))


def _nuevo_estado(saldo: Decimal, importe: Decimal) -> EstadoAnticipo:
    if saldo <= 0:
        return EstadoAnticipo.totalmente_aplicado
    if saldo < importe:
        return EstadoAnticipo.parcialmente_aplicado
    return EstadoAnticipo.pendiente


def _asiento_aplicacion(
    *,
    empresa_id: int,
    ejercicio: int,
    fecha: date,
    importe: Decimal,
    tipo: TipoAnticipo,
    cuenta_anticipo: str,
    concepto: str,
) -> tuple[JournalEntry, list[JournalEntryLine]]:
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=JournalEntryTipo.COBRO if tipo == TipoAnticipo.CLIENTE else JournalEntryTipo.GENERAL,
        concepto=concepto,
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    debe_cuenta = (
        CUENTA_CLIENTES
        if tipo == TipoAnticipo.CLIENTE
        else CUENTA_ACREEDORES_SERVICIOS
    )
    lineas = [
        JournalEntryLine(
            empresa_id=empresa_id, journal_entry_id=asiento.id,
            cuenta=debe_cuenta, debe=importe, haber=Decimal(0),
        ),
        JournalEntryLine(
            empresa_id=empresa_id, journal_entry_id=asiento.id,
            cuenta=cuenta_anticipo, debe=Decimal(0), haber=importe,
        ),
    ]
    verificar_balance(lineas)
    return asiento, lineas


async def _persistir_asiento(
    db: AsyncSession,
    asiento: JournalEntry,
    lineas: list[JournalEntryLine],
) -> None:
    db.add(asiento)
    await db.flush()
    for linea in lineas:
        db.add(linea)
    await db.flush()


async def liquidar_anticipo(
    db: AsyncSession,
    *,
    empresa_id: int,
    anticipo_id: uuid.UUID,
    aplicaciones: list[AplicacionAnticipo],
    fecha_aplicacion: date,
    actor: str | None = None,
) -> dict:
    if not aplicaciones:
        raise LiquidacionError("sin_aplicaciones", 422, "Debe indicar al menos una aplicación")
    anticipo = await db.scalar(
        select(Anticipo).where(
            Anticipo.empresa_id == empresa_id, Anticipo.id == anticipo_id
        )
    )
    if anticipo is None:
        raise LiquidacionError("anticipo_no_encontrado", 404, "Anticipo inexistente")
    await ejercicio_abierto(db, empresa_id, fecha_aplicacion, LiquidacionError)

    aplicaciones_d: list[tuple[Decimal, Factura]] = []
    total_aplicar = Decimal("0.0000")
    for aplicacion in aplicaciones:
        if aplicacion.importe_aplicado is not None:
            importe_d = _cuantizar(aplicacion.importe_aplicado)
            if importe_d <= 0:
                raise LiquidacionError(
                    "importe_invalido", 422, "El importe aplicado debe ser > 0"
                )
        else:
            continue
        factura = await db.scalar(
            select(Factura).where(
                Factura.empresa_id == empresa_id, Factura.id == aplicacion.factura_id
            )
        )
        if factura is None:
            raise LiquidacionError(
                "factura_no_encontrada", 422, "Factura inexistente para la empresa activa"
            )
        if factura.tercero_id != anticipo.tercero_id:
            raise LiquidacionError(
                "factura_tercero_distinto",
                422,
                "La factura no pertenece al tercero del anticipo",
            )
        aplicaciones_d.append((importe_d, factura))
        if importe_d > anticipo.saldo_pendiente:
            raise LiquidacionError(
                "importe_supera_saldo",
                422,
                f"El importe {importe_d} supera el saldo pendiente {anticipo.saldo_pendiente}",
            )
        total_aplicar += importe_d
        if total_aplicar > anticipo.saldo_pendiente:
            raise LiquidacionError(
                "saldo_insuficiente",
                409,
                f"El total aplicado {total_aplicar} supera el saldo pendiente {anticipo.saldo_pendiente}",
            )

    liquidaciones = []
    for importe_d, factura in aplicaciones_d:
        asiento, lineas = _asiento_aplicacion(
            empresa_id=empresa_id,
            ejercicio=fecha_aplicacion.year,
            fecha=fecha_aplicacion,
importe=importe_d,
                tipo=anticipo.tipo,
                cuenta_anticipo=anticipo.cuenta_contable,
                concepto=f"Liquidación anticipo {anticipo.concepto}",
        )
        await _persistir_asiento(db, asiento, lineas)
        liquidacion = LiquidacionAnticipo(
            empresa_id=empresa_id,
            anticipo_id=anticipo.id,
            factura_id=factura.id,
            fecha_aplicacion=fecha_aplicacion,
            importe_aplicado=importe_d,
            asiento_id=asiento.id,
            created_by=actor,
        )
        db.add(liquidacion)
        await db.flush()
        liquidaciones.append(liquidacion)

    anticipo.saldo_pendiente -= total_aplicar
    anticipo.estado = _nuevo_estado(anticipo.saldo_pendiente, anticipo.importe)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        operacion="LIQUIDAR_ANTICIPO",
        entidad="anticipo",
        entidad_id=anticipo.id,
        payload={
            "fecha_aplicacion": fecha_aplicacion.isoformat(),
            "total_aplicado": f"{total_aplicar:0.4f}",
            "saldo_pendiente": f"{anticipo.saldo_pendiente:0.4f}",
            "n_liquidaciones": len(liquidaciones),
        },
    )
    await db.flush()
    return {
        "anticipo_id": anticipo.id,
        "saldo_pendiente": f"{anticipo.saldo_pendiente:0.4f}",
        "liquidaciones_creadas": len(liquidaciones),
    }


async def listar_liquidaciones(
    db: AsyncSession, *, empresa_id: int, anticipo_id: uuid.UUID
) -> list[dict]:
    anticipo = await db.scalar(
        select(Anticipo).where(
            Anticipo.empresa_id == empresa_id, Anticipo.id == anticipo_id
        )
    )
    if anticipo is None:
        raise LiquidacionError("anticipo_no_encontrado", 404, "Anticipo inexistente")
    liquidaciones = (
        await db.scalars(
            select(LiquidacionAnticipo)
            .where(
                LiquidacionAnticipo.empresa_id == empresa_id,
                LiquidacionAnticipo.anticipo_id == anticipo_id,
            )
            .order_by(LiquidacionAnticipo.fecha_aplicacion)
        )
    ).all()
    return [
        {
            "id": l.id,
            "factura_id": l.factura_id,
            "fecha_aplicacion": l.fecha_aplicacion.isoformat(),
            "importe_aplicado": f"{l.importe_aplicado:0.4f}",
            "asiento_id": l.asiento_id,
        }
        for l in liquidaciones
    ]