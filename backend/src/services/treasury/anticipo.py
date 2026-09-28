"""Anticipos (SPEC-022 US1/US2): cobros/pagos por anticipado (438/407).

Un anticipo de cliente se cobra registrando el asiento Debe 572 | Haber 438;
un anticipo a proveedor se paga registrando Debe 407/408 | Haber 572. Ambos
se registran con ``saldo_pendiente = importe`` y se aplican luego contra
facturas vía ``LiquidacionAnticipo`` (constitución I: asientos siempre
balanceados; multi-tenancy estricto: la empresa activa se pasa como parámetro
y nunca proviene del cliente).

Un solo servicio unificado por parámetro ``tipo`` (research D9): reutilizar
``registrar_anticipo`` con ``tipo=PROVEEDOR``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.tercero import Tercero
from models.treasury.anticipo import Anticipo, EstadoAnticipo, TipoAnticipo
from models.treasury.liquidacion_anticipo import LiquidacionAnticipo
from services.accounting import verificar_balance
from services.audit import registrar_auditoria
from services.treasury.common import (
    CUENTA_ANTICIPOS_CLIENTES,
    CUENTA_ANTICIPOS_PROVEEDORES,
    CUENTA_BANCO,
    TesoreriaError,
    ejercicio_abierto,
)


class AnticipoError(TesoreriaError):
    pass


def _cuantizar(valor: Decimal | str) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.0000"))


def _cuenta_contable(tipo: TipoAnticipo, cuenta: str | None) -> str:
    if tipo == TipoAnticipo.CLIENTE:
        return CUENTA_ANTICIPOS_CLIENTES
    if cuenta in (CUENTA_ANTICIPOS_PROVEEDORES, "408"):
        return str(cuenta)
    return CUENTA_ANTICIPOS_PROVEEDORES


def _asiento_anticipo(
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
    if tipo == TipoAnticipo.CLIENTE:
        lineas = [
            JournalEntryLine(
                empresa_id=empresa_id, journal_entry_id=asiento.id,
                cuenta=CUENTA_BANCO, debe=importe, haber=Decimal(0),
            ),
            JournalEntryLine(
                empresa_id=empresa_id, journal_entry_id=asiento.id,
                cuenta=cuenta_anticipo, debe=Decimal(0), haber=importe,
            ),
        ]
    else:
        lineas = [
            JournalEntryLine(
                empresa_id=empresa_id, journal_entry_id=asiento.id,
                cuenta=cuenta_anticipo, debe=importe, haber=Decimal(0),
            ),
            JournalEntryLine(
                empresa_id=empresa_id, journal_entry_id=asiento.id,
                cuenta=CUENTA_BANCO, debe=Decimal(0), haber=importe,
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


async def registrar_anticipo(
    db: AsyncSession,
    *,
    empresa_id: int,
    tercero_id: uuid.UUID,
    tipo: TipoAnticipo,
    fecha: date,
    importe: str,
    concepto: str,
    cuenta_contable: str | None = None,
    notas: str | None = None,
    actor: str | None = None,
) -> Anticipo:
    importe_d = _cuantizar(importe)
    if importe_d <= 0:
        raise AnticipoError("importe_invalido", 422, "El importe debe ser > 0")
    if tipo not in (TipoAnticipo.CLIENTE, TipoAnticipo.PROVEEDOR):
        raise AnticipoError("tipo_invalido", 422, "El tipo de anticipo no es válido")
    await ejercicio_abierto(db, empresa_id, fecha, AnticipoError)

    tercero = await db.scalar(
        select(Tercero).where(
            Tercero.empresa_id == empresa_id, Tercero.id == tercero_id
        )
    )
    if tercero is None:
        raise AnticipoError("tercero_no_encontrado", 404, "Tercero inexistente para la empresa activa")

    cuenta = _cuenta_contable(tipo, cuenta_contable)
    asiento, lineas = _asiento_anticipo(
        empresa_id=empresa_id,
        ejercicio=fecha.year,
        fecha=fecha,
        importe=importe_d,
        tipo=tipo,
        cuenta_anticipo=cuenta,
        concepto=f"Anticipo {'cliente' if tipo == TipoAnticipo.CLIENTE else 'proveedor'}: {concepto}",
    )
    await _persistir_asiento(db, asiento, lineas)

    anticipo = Anticipo(
        empresa_id=empresa_id,
        tercero_id=tercero_id,
        tipo=tipo,
        cuenta_contable=cuenta,
        fecha=fecha,
        importe=importe_d,
        concepto=concepto,
        estado=EstadoAnticipo.pendiente,
        saldo_pendiente=importe_d,
        asiento_id=asiento.id,
        notas=notas,
        created_by=actor,
    )
    db.add(anticipo)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        operacion="REGISTRAR_ANTICIPO",
        entidad="anticipo",
        entidad_id=anticipo.id,
        payload={
            "tercero_id": str(tercero_id),
            "tipo": tipo.value,
            "cuenta_contable": cuenta,
            "importe": f"{importe_d:0.4f}",
            "asiento_id": str(asiento.id),
        },
    )
    await db.flush()
    return anticipo


@dataclass
class AnticipoCorto:
    id: uuid.UUID
    tercero_id: uuid.UUID
    tercero_nombre: str
    tipo: str
    fecha: date
    importe: Decimal
    saldo_pendiente: Decimal
    estado: str
    asiento_id: uuid.UUID | None


async def listar_anticipos(
    db: AsyncSession,
    *,
    empresa_id: int,
    tipo: TipoAnticipo | None = None,
    estado: str | None = None,
    tercero_id: uuid.UUID | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    pagina: int = 1,
    tamano: int = 20,
) -> tuple[list[AnticipoCorto], int]:
    filtros = [Anticipo.empresa_id == empresa_id]
    if tipo is not None:
        filtros.append(Anticipo.tipo == tipo)
    if estado is not None:
        filtros.append(Anticipo.estado == estado)
    if tercero_id is not None:
        filtros.append(Anticipo.tercero_id == tercero_id)
    if fecha_desde is not None:
        filtros.append(Anticipo.fecha >= fecha_desde)
    if fecha_hasta is not None:
        filtros.append(Anticipo.fecha <= fecha_hasta)

    total = await db.scalar(
        select(func.count()).select_from(Anticipo).where(*filtros)
    )
    filas = (
        await db.execute(
            select(Anticipo, Tercero.nombre)
            .join(Tercero, Tercero.empresa_id == Anticipo.empresa_id, isouter=True)
            .where(*filtros)
            .order_by(Anticipo.fecha.desc(), Anticipo.created_at.desc())
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    items = [
        AnticipoCorto(
            id=a.id,
            tercero_id=a.tercero_id,
            tercero_nombre=nombre or "",
            tipo=a.tipo.value,
            fecha=a.fecha,
            importe=a.importe,
            saldo_pendiente=a.saldo_pendiente,
            estado=a.estado.value,
            asiento_id=a.asiento_id,
        )
        for a, nombre in filas
        if isinstance(a, Anticipo)
    ]
    return items, int(total or 0)


async def detalle_anticipo(
    db: AsyncSession, *, empresa_id: int, anticipo_id: uuid.UUID
) -> dict:
    anticipo = await db.scalar(
        select(Anticipo).where(
            Anticipo.empresa_id == empresa_id, Anticipo.id == anticipo_id
        )
    )
    if anticipo is None:
        raise AnticipoError("anticipo_no_encontrado", 404, "Anticipo inexistente")
    tercero = await db.get(Tercero, anticipo.tercero_id)
    liquidaciones = (
        await db.scalars(
            select(LiquidacionAnticipo)
            .where(LiquidacionAnticipo.empresa_id == empresa_id)
            .order_by(LiquidacionAnticipo.fecha_aplicacion)
        )
    ).all()
    return {
        "id": anticipo.id,
        "tercero_id": anticipo.tercero_id,
        "tercero_nombre": tercero.nombre if tercero else "",
        "tipo": anticipo.tipo.value,
        "cuenta_contable": anticipo.cuenta_contable,
        "fecha": anticipo.fecha.isoformat(),
        "importe": f"{anticipo.importe:0.4f}",
        "saldo_pendiente": f"{anticipo.saldo_pendiente:0.4f}",
        "estado": anticipo.estado.value,
        "asiento_id": anticipo.asiento_id,
        "notas": anticipo.notas,
        "liquidaciones": [
            {
                "id": l.id,
                "factura_id": l.factura_id,
                "fecha_aplicacion": l.fecha_aplicacion.isoformat(),
                "importe_aplicado": f"{l.importe_aplicado:0.4f}",
                "asiento_id": l.asiento_id,
            }
            for l in liquidaciones
            if l.anticipo_id == anticipo.id
        ],
    }