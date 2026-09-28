"""Invoice persistence (SPEC-004 US4): exact amounts, atomic numbering, immutable link.

No management API in this feature (deferred assumption): entity + service
only. All amounts are :class:`~decimal.Decimal` quantized to 4 decimals.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry
from models.ar.invoice import Invoice, InvoiceTipo
from services.audit.writer import audit_escribir
from services.invoicing.sequence_factura import (
    existe_numero_factura,
    next_numero_factura,
)
from services.journal.money import tiene_mas_de_4_decimales


class FacturaError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _normalizar_importe(valor: str, campo: str) -> Decimal:
    texto = str(valor)
    if tiene_mas_de_4_decimales(texto):
        raise FacturaError("precision_invalida", f"{campo}: más de 4 decimales")
    importe = Decimal(texto).quantize(Decimal("0.0000"))
    if importe < 0:
        raise FacturaError("importe_negativo", f"{campo}: importes negativos no permitidos")
    return importe


async def crear_factura(
    db: AsyncSession,
    *,
    empresa_id: int,
    tipo: InvoiceTipo | str,
    ejercicio: int,
    nif_tercero: str,
    fecha: date,
    base: str,
    cuota_iva: str,
    actor: str | None = None,
) -> Invoice:
    """Persist an invoice with atomic numbering and exact total = base + cuota."""
    try:
        tipo_norm = InvoiceTipo(tipo) if isinstance(tipo, str) else tipo
    except ValueError:
        raise FacturaError("tipo_invalido", "tipo debe ser emitida o recibida")
    base_d = _normalizar_importe(base, "base")
    cuota_d = _normalizar_importe(cuota_iva, "cuota_iva")
    if not nif_tercero or not nif_tercero.strip():
        raise FacturaError("nif_requerido", "El NIF del tercero es obligatorio")
    numero = await next_numero_factura(db, empresa_id, ejercicio)
    if await existe_numero_factura(db, empresa_id, ejercicio, numero):
        raise FacturaError("numero_duplicado", f"Número {numero} duplicado en {ejercicio}")
    factura = Invoice(
        empresa_id=empresa_id,
        tipo=tipo_norm,
        ejercicio=ejercicio,
        numero_seq=numero,
        nif_tercero=nif_tercero.strip(),
        fecha=fecha,
        base=base_d,
        cuota_iva=cuota_d,
        total=(base_d + cuota_d).quantize(Decimal("0.0000")),
        created_by=actor,
    )
    db.add(factura)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREATE_INVOICE",
        entity="invoice",
        entity_id=factura.id,
        payload={"ejercicio": str(ejercicio), "numero": str(numero), "total": f"{factura.total:0.4f}"},
    )
    await db.flush()
    return factura


async def vincular_asiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    factura_id: int,
    asiento_id: uuid.UUID,
) -> Invoice:
    """Link an invoice to its backing entry exactly once (immutable afterwards)."""
    factura = await db.scalar(
        select(Invoice).where(Invoice.empresa_id == empresa_id, Invoice.id == factura_id)
    )
    if factura is None:
        raise FacturaError("factura_no_encontrada", "Factura inexistente en la empresa activa")
    if factura.asiento_id is not None:
        raise FacturaError("vinculo_inmutable", "La factura ya está vinculada a un asiento")
    asiento = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id, JournalEntry.id == asiento_id
        )
    )
    if asiento is None:
        raise FacturaError(
            "asiento_no_encontrado", "Asiento inexistente en la empresa activa"
        )
    factura.asiento_id = asiento.id
    await db.flush()
    return factura
