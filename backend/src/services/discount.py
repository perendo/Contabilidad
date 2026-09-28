"""Early-payment discount: conditions, neto calculation, liquidation asiento.

US2 (FR-005): liquidate a recibo applying the tercero's vigente
CondicionProntoPago (o el override por factura) when payment falls within the
window (fecha_pago - fecha_factura <= plazo_dias). Neto never negative, asiento
balanced with Decimal (constitución I/V): Debe 572 (neto) + 432/662 (descuento)
| Haber 430 (total).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.condicion_pronto_pago import CondicionProntoPago
from models.treasury.recibo_remesa import ReciboEstado, ReciboRemesa
from services import accounting
from services.audit import registrar_auditoria

CUENTA_CLIENTES = "430"
CUENTA_BANCO_DEFECTO = "572"
CUENTA_DESCUENTO_DEFECTO = "432"
CUENTA_DESCUENTO_GASTO = "662"

_PRECISION = Decimal("0.0001")


class LiquidacionError(Exception):
    status_code = 400
    code = "error"


class ReciboLiquidacionNotFoundError(LiquidacionError):
    status_code = 404
    code = "recibo_no_encontrado"


class VencimientoNotFoundError(LiquidacionError):
    status_code = 404
    code = "vencimiento_no_encontrado"


class CondicionOverrideNotFoundError(LiquidacionError):
    status_code = 404
    code = "condicion_no_encontrada"


class LiquidacionEstadoError(LiquidacionError):
    status_code = 409
    code = "liquidacion_estado_no_valido"


class DescuentoInvalidoError(LiquidacionError):
    status_code = 422
    code = "descuento_invalido"


@dataclass(frozen=True)
class DescuentoAplicado:
    neto: Decimal
    descuento: Decimal


@dataclass(frozen=True)
class LiquidacionResult:
    recibo: ReciboRemesa
    neto: Decimal
    descuento: Decimal
    asiento_id: uuid.UUID
    descuento_aplicado: bool


def _cuantizar(importe: Decimal) -> Decimal:
    return importe.quantize(_PRECISION, rounding=ROUND_HALF_UP)


def calcular_descuento(importe: Decimal, porcentaje: Decimal) -> DescuentoAplicado:
    """Neto = importe * (1 - porcentaje/100), always >= 0, 4-decimal precision."""
    importe = Decimal(importe)
    porcentaje = Decimal(porcentaje)
    neto_bruto = importe * (Decimal(100) - porcentaje) / Decimal(100)
    neto = _cuantizar(neto_bruto)
    if neto < Decimal(0):
        raise DescuentoInvalidoError("el descuento supera el importe del recibo")
    descuento = _cuantizar(importe - neto)
    return DescuentoAplicado(neto=neto, descuento=descuento)


def fecha_referencia(vencimiento: Vencimiento) -> date:
    return vencimiento.fecha_factura or vencimiento.fecha_vencimiento


def en_plazo(condicion: CondicionProntoPago, vencimiento: Vencimiento, fecha_pago: date) -> bool:
    return (fecha_pago - fecha_referencia(vencimiento)).days <= condicion.plazo_dias


async def condicion_para_vencimiento(
    session: AsyncSession,
    empresa_id: int,
    vencimiento: Vencimiento,
    *,
    override_condicion_id: uuid.UUID | None = None,
) -> CondicionProntoPago | None:
    if override_condicion_id is not None:
        condicion = await session.scalar(
            select(CondicionProntoPago).where(
                CondicionProntoPago.empresa_id == empresa_id,
                CondicionProntoPago.id == override_condicion_id,
            )
        )
        if condicion is None:
            raise CondicionOverrideNotFoundError("condición no encontrada en la empresa activa")
        return condicion

    vigentes = (
        await session.scalars(
            select(CondicionProntoPago).where(
                CondicionProntoPago.empresa_id == empresa_id,
                CondicionProntoPago.tercero_id == vencimiento.tercero_id,
                CondicionProntoPago.vigente.is_(True),
            )
        )
    ).all()
    por_factura = [
        c
        for c in vigentes
        if c.override_factura_id is not None and c.override_factura_id == vencimiento.factura_id
    ]
    if por_factura:
        return por_factura[0]
    generales = [c for c in vigentes if c.override_factura_id is None]
    return generales[0] if generales else None


async def aplicar_pronto_pago(
    session: AsyncSession,
    empresa_id: int,
    vencimiento: Vencimiento,
    fecha_pago: date,
    *,
    override_condicion_id: uuid.UUID | None = None,
) -> tuple[CondicionProntoPago, DescuentoAplicado] | None:
    """Return (condicion, resultado) when a discount applies, else None."""
    condicion = await condicion_para_vencimiento(
        session, empresa_id, vencimiento, override_condicion_id=override_condicion_id
    )
    if condicion is None:
        return None
    if not en_plazo(condicion, vencimiento, fecha_pago):
        return None
    return condicion, calcular_descuento(vencimiento.importe, condicion.porcentaje)


def _asiento_liquidacion(
    empresa_id: int,
    ejercicio: int,
    fecha: date,
    total: Decimal,
    neto: Decimal,
    descuento: Decimal,
    cuenta_banco: str,
    cuenta_descuento: str,
    concepto: str,
) -> tuple[JournalEntry, list[JournalEntryLine]]:
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=JournalEntryTipo.PRONTO_PAGO,
        concepto=concepto,
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    lineas = [
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=cuenta_banco,
            debe=neto,
            haber=Decimal(0),
            descripcion=None,
        )
    ]
    if descuento > Decimal(0):
        lineas.append(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=asiento.id,
                cuenta=cuenta_descuento,
                debe=descuento,
                haber=Decimal(0),
                descripcion=None,
            )
        )
    lineas.append(
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=CUENTA_CLIENTES,
            debe=Decimal(0),
            haber=total,
            descripcion=None,
        )
    )
    accounting.verificar_balance(lineas)
    return asiento, lineas


async def liquidar_con_descuento(
    session: AsyncSession,
    empresa_id: int,
    recibo_id: uuid.UUID,
    *,
    fecha_pago: date,
    cuenta_banco: str = CUENTA_BANCO_DEFECTO,
    cuenta_descuento: str = CUENTA_DESCUENTO_DEFECTO,
    override_condicion_id: uuid.UUID | None = None,
    usuario: str | None = None,
) -> LiquidacionResult:
    recibo = await session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id,
            ReciboRemesa.id == recibo_id,
        )
    )
    if recibo is None:
        raise ReciboLiquidacionNotFoundError("recibo no encontrado")
    if recibo.estado not in (ReciboEstado.pendiente, ReciboEstado.remesado):
        raise LiquidacionEstadoError(
            f"el recibo no se puede liquidar en estado {recibo.estado.value}"
        )

    vencimiento = await session.scalar(
        select(Vencimiento).where(
            Vencimiento.empresa_id == empresa_id,
            Vencimiento.id == recibo.vencimiento_id,
        )
    )
    if vencimiento is None:
        raise VencimientoNotFoundError("vencimiento no encontrado")

    aplicado = await aplicar_pronto_pago(
        session, empresa_id, vencimiento, fecha_pago,
        override_condicion_id=override_condicion_id,
    )
    if aplicado is not None:
        condicion, descuento_resultado = aplicado
        neto = descuento_resultado.neto
        descuento = descuento_resultado.descuento
        tipo = JournalEntryTipo.PRONTO_PAGO
        concepto = f"Pronto pago recibo {recibo.recibo_num}"
        cuenta_descuento_ok = cuenta_descuento or CUENTA_DESCUENTO_GASTO
        recibo.descuento_id = condicion.id
    else:
        neto = recibo.importe
        descuento = Decimal(0)
        tipo = JournalEntryTipo.COBRO
        cuenta_descuento_ok = CUENTA_DESCUENTO_GASTO
        concepto = f"Liquidación recibo {recibo.recibo_num}"

    asiento, lineas = _asiento_liquidacion(
        empresa_id=empresa_id,
        ejercicio=vencimiento.ejercicio,
        fecha=fecha_pago,
        total=recibo.importe,
        neto=neto,
        descuento=descuento,
        cuenta_banco=cuenta_banco,
        cuenta_descuento=cuenta_descuento_ok,
        concepto=concepto,
    )
    asiento.tipo = tipo
    session.add(asiento)
    for linea in lineas:
        session.add(linea)

    recibo.estado = ReciboEstado.cobrado
    recibo.fecha_cobro = fecha_pago
    recibo.asiento_cobro_id = asiento.id
    vencimiento.estado = EstadoVencimiento.cobrado
    session.add(recibo)
    session.add(vencimiento)

    await registrar_auditoria(
        session,
        empresa_id,
        "LIQUIDAR",
        "recibo_remesa",
        recibo.id,
        {
            "asiento_id": str(asiento.id),
            "importe_total": f"{recibo.importe:f}",
            "importe_neto": f"{neto:f}",
            "descuento": f"{descuento:f}",
            "descuento_aplicado": aplicado is not None,
            "fecha_pago": fecha_pago.isoformat(),
        },
        usuario=usuario,
    )
    await session.flush()
    return LiquidacionResult(
        recibo=recibo,
        neto=neto,
        descuento=descuento,
        asiento_id=asiento.id,
        descuento_aplicado=aplicado is not None,
    )