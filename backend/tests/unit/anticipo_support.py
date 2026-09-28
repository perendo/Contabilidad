"""Helpers compartidos por los tests de anticipos y cesiones (SPEC-022).

Proporciona la siembra base de empresa + terceros (cliente/proveedor) + serie
+ factura de venta/compra + ejercicio abierto 2026 (y 2025 cerrado opcional) +
vencimientos pendientes, y helpers de verificación de balance del diario.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntryLine
from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.iam.company import Company
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.serie_factura import SerieFactura, SerieFacturaEstado

CLIENTE = uuid.uuid4()
PROVEEDOR = uuid.uuid4()


async def sembrar_base(
    db: AsyncSession,
    empresa_id: int,
    *,
    cliente_id: uuid.UUID = CLIENTE,
    proveedor_id: uuid.UUID = PROVEEDOR,
    n_vencimientos: int = 0,
    cerrar_2025: bool = True,
) -> dict:
    db.add(
        Company(company_id=empresa_id, nif=f"T{empresa_id:08d}", razon_social=f"E{empresa_id}")
    )
    await db.flush()
    cliente = Tercero(
        empresa_id=empresa_id, id=cliente_id, nombre="Cliente", nif=f"B{empresa_id}000001",
        es_cliente=True, es_proveedor=False,
    )
    proveedor = Tercero(
        empresa_id=empresa_id, id=proveedor_id, nombre="Proveedor", nif=f"B{empresa_id}000002",
        es_cliente=False, es_proveedor=True,
    )
    db.add_all([cliente, proveedor])
    await db.flush()
    serie = SerieFactura(
        empresa_id=empresa_id, codigo="SERIE", nombre="Serie", prefijo="F",
        siguiente_numero=1, estado=SerieFacturaEstado.activa,
    )
    db.add(serie)
    await db.flush()
    venta = Factura(
        empresa_id=empresa_id, serie_id=serie.id, numero=1, ejercicio=2026,
        fecha=date(2026, 2, 1), tipo=FacturaTipo.VENTA, tercero_id=cliente_id,
        importe_total=Decimal("2000.0000"), estado=FacturaEstado.emitida,
    )
    compra = Factura(
        empresa_id=empresa_id, serie_id=serie.id, numero=2, ejercicio=2026,
        fecha=date(2026, 2, 2), tipo=FacturaTipo.COMPRA, tercero_id=proveedor_id,
        importe_total=Decimal("2500.0000"), estado=FacturaEstado.emitida,
    )
    db.add_all([venta, compra])
    db.add(
        FiscalYear(
            empresa_id=empresa_id, year=2026,
            date_start=date(2026, 1, 1), date_end=date(2026, 12, 31), is_closed=False,
        )
    )
    if cerrar_2025:
        db.add(
            FiscalYear(
                empresa_id=empresa_id, year=2025,
                date_start=date(2025, 1, 1), date_end=date(2025, 12, 31), is_closed=True,
            )
        )
    await db.flush()
    vencimientos = []
    for i in range(n_vencimientos):
        v = Vencimiento(
            empresa_id=empresa_id, tercero_id=cliente_id, recibo_num=f"V{empresa_id}-{i}",
            iban="ES9121000418450200051332", ejercicio=2026,
            tipo=TipoVencimiento.cobro, fecha_vencimiento=date(2026, 9, 30),
            importe=Decimal("1500.0000"), acumulado=Decimal("0.0000"),
            estado=EstadoVencimiento.pendiente,
        )
        db.add(v)
        await db.flush()
        vencimientos.append(v.id)
    return {
        "cliente_id": cliente_id,
        "proveedor_id": proveedor_id,
        "serie_id": serie.id,
        "factura_venta_id": venta.id,
        "factura_compra_id": compra.id,
        "vencimientos": vencimientos,
    }


async def sumas(db: AsyncSession, entry_id: uuid.UUID) -> tuple[Decimal, Decimal]:
    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
        )
    ).all()
    return (
        sum(l.debe or Decimal(0) for l in lineas),
        sum(l.haber or Decimal(0) for l in lineas),
    )


async def cuentas(db: AsyncSession, entry_id: uuid.UUID) -> dict[str, tuple[Decimal, Decimal]]:
    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
        )
    ).all()
    return {l.cuenta: (l.debe or Decimal(0), l.haber or Decimal(0)) for l in lineas}