"""Cobros y pagos de vencimientos (SPEC-011 US1/US2).

Cada cobro/pago genera su propio asiento balanceado (constitución I) y
actualiza el acumulado del vencimiento en Decimal; los parciales nunca
superan el importe y el vencimiento se salda al igualarlo.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.treasury.cobro_pago import CobroPago
from services.accounting import verificar_balance
from services.audit.writer import audit_escribir

CUENTA_CLIENTES = "430"
CUENTA_PROVEEDORES = "400"
CUENTA_BANCO = "572"
CUENTA_CAJA = "570"


class CobroPagoError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def _ejercicio_abierto(db: AsyncSession, empresa_id: int, fecha: date) -> None:
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == fecha.year
        )
    )
    if fy is not None and fy.is_closed:
        raise CobroPagoError("ejercicio_cerrado", f"El ejercicio {fecha.year} está cerrado")


async def _siguiente_operacion(db: AsyncSession, empresa_id: int, ejercicio: int) -> int:
    ultimo = await db.scalar(
        select(func.max(CobroPago.numero_operacion)).where(
            CobroPago.empresa_id == empresa_id, CobroPago.ejercicio == ejercicio
        )
    )
    return (ultimo or 0) + 1


def _asiento(
    *,
    empresa_id: int,
    ejercicio: int,
    fecha: date,
    importe: Decimal,
    tipo: TipoVencimiento,
    cuenta_tesoreria: str,
    concepto: str,
) -> tuple[JournalEntry, list[JournalEntryLine]]:
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=JournalEntryTipo.COBRO if tipo == TipoVencimiento.cobro else JournalEntryTipo.GENERAL,
        concepto=concepto,
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    if tipo == TipoVencimiento.cobro:
        debe_cuenta, haber_cuenta = cuenta_tesoreria, CUENTA_CLIENTES
    else:
        debe_cuenta, haber_cuenta = CUENTA_PROVEEDORES, cuenta_tesoreria
    lineas = [
        JournalEntryLine(
            empresa_id=empresa_id, journal_entry_id=asiento.id,
            cuenta=debe_cuenta, debe=importe, haber=Decimal(0),
        ),
        JournalEntryLine(
            empresa_id=empresa_id, journal_entry_id=asiento.id,
            cuenta=haber_cuenta, debe=Decimal(0), haber=importe,
        ),
    ]
    verificar_balance(lineas)
    return asiento, lineas


async def registrar_operacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    vencimiento_id: uuid.UUID,
    fecha: date,
    importe: str,
    cuenta_tesoreria: str | None = None,
    actor: str | None = None,
) -> CobroPago:
    """Register a total or partial collection/payment and update the vencimiento."""
    vencimiento = await db.scalar(
        select(Vencimiento).where(
            Vencimiento.empresa_id == empresa_id, Vencimiento.id == vencimiento_id
        )
    )
    if vencimiento is None:
        raise CobroPagoError("vencimiento_no_encontrado", "Vencimiento inexistente")
    if vencimiento.estado == EstadoVencimiento.cobrado:
        raise CobroPagoError("vencimiento_saldado", "El vencimiento ya está saldado")
    if vencimiento.estado == EstadoVencimiento.remesado:
        raise CobroPagoError(
            "vencimiento_remesado", "El vencimiento está en una remesa emitida"
        )
    if vencimiento.estado == EstadoVencimiento.cedido:
        raise CobroPagoError(
            "vencimiento_cedido", "El vencimiento está cedido a una entidad financiera"
        )
    await _ejercicio_abierto(db, empresa_id, fecha)

    importe_d = Decimal(str(importe)).quantize(Decimal("0.0000"))
    if importe_d <= 0:
        raise CobroPagoError("importe_invalido", "El importe debe ser > 0")
    if importe_d > vencimiento.saldo_pendiente:
        raise CobroPagoError(
            "exceso_importe",
            f"El importe {importe_d} supera el saldo pendiente {vencimiento.saldo_pendiente}",
        )

    cuenta = cuenta_tesoreria or CUENTA_BANCO
    asiento, lineas = _asiento(
        empresa_id=empresa_id,
        ejercicio=fecha.year,
        fecha=fecha,
        importe=importe_d,
        tipo=vencimiento.tipo,
        cuenta_tesoreria=cuenta,
        concepto=f"{'Cobro' if vencimiento.tipo == TipoVencimiento.cobro else 'Pago'} {vencimiento.recibo_num}",
    )
    db.add(asiento)
    await db.flush()
    for linea in lineas:
        db.add(linea)
    await db.flush()

    vencimiento.acumulado += importe_d
    vencimiento.estado = (
        EstadoVencimiento.cobrado
        if vencimiento.acumulado >= vencimiento.importe
        else EstadoVencimiento.parcial
    )
    operacion = CobroPago(
        empresa_id=empresa_id,
        numero_operacion=await _siguiente_operacion(db, empresa_id, fecha.year),
        ejercicio=fecha.year,
        vencimiento_id=vencimiento.id,
        fecha=fecha,
        importe=importe_d,
        cuenta_tesoreria=cuenta,
        journal_entry_id=asiento.id,
        created_by=actor,
    )
    db.add(operacion)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="REGISTRAR_COBRO_PAGO",
        entity="cobro_pago",
        entity_id=str(operacion.id),
        payload={"importe": f"{importe_d:0.4f}", "estado": vencimiento.estado.value},
    )
    await db.flush()
    return operacion


async def registrar_cobro(
    db: AsyncSession, *, empresa_id: int, vencimiento_id: uuid.UUID, fecha: date,
    importe: str, cuenta_tesoreria: str | None = None, actor: str | None = None,
) -> CobroPago:
    return await registrar_operacion(
        db, empresa_id=empresa_id, vencimiento_id=vencimiento_id, fecha=fecha,
        importe=importe, cuenta_tesoreria=cuenta_tesoreria, actor=actor,
    )


async def registrar_pago(
    db: AsyncSession, *, empresa_id: int, vencimiento_id: uuid.UUID, fecha: date,
    importe: str, cuenta_tesoreria: str | None = None, actor: str | None = None,
) -> CobroPago:
    return await registrar_operacion(
        db, empresa_id=empresa_id, vencimiento_id=vencimiento_id, fecha=fecha,
        importe=importe, cuenta_tesoreria=cuenta_tesoreria, actor=actor,
    )
