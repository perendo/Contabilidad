"""Diario consultation services (SPEC-002 US2): paginated diary and details.

Solo asientos ``POSTED``/``CANCELLED`` de la empresa activa, orden
``(fecha, numero_asiento)`` asc. El rango de fechas es obligatorio (422 si
falta o está invertido). Importes siempre como strings con 4 decimales.
"""

from __future__ import annotations

import uuid
from datetime import date, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
)
from services.journal.entry_service import error

PAGINA_MIN, PAGINA_MAX = 1, 100


def _iso(fecha: date) -> str:
    return fecha.isoformat()


def _as_decimal_str(value: Decimal) -> str:
    return f"{value:0.4f}"


def _item_payload(
    entrada: JournalEntry,
    lineas: list[JournalEntryLine],
) -> dict:
    suma_debe = sum((linea.debe for linea in lineas), Decimal(0))
    suma_haber = sum((linea.haber for linea in lineas), Decimal(0))
    return {
        "id": str(entrada.id),
        "numero": entrada.numero_asiento,
        "fecha": _iso(entrada.fecha),
        "concepto": entrada.concepto,
        "estado": entrada.estado.value,
        "tipo": entrada.tipo.value,
        "suma_debe": _as_decimal_str(suma_debe),
        "suma_haber": _as_decimal_str(suma_haber),
        "lineas": len(lineas),
    }


async def consultar_diario(
    db: AsyncSession,
    *,
    empresa_id: int,
    date_from: date | None,
    date_to: date | None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if date_from is None or date_to is None:
        raise error("rango_requerido", "El rango de fechas es obligatorio")
    if date_from > date_to:
        raise error(
            "rango_invertido", "date_from no puede ser posterior a date_to"
        )
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise error("page_size_invalido", "page_size debe estar entre 1 y 100")

    base = select(JournalEntry).where(
        JournalEntry.empresa_id == empresa_id,
        JournalEntry.estado.in_([JournalEntryEstado.POSTED, JournalEntryEstado.CANCELLED]),
        JournalEntry.fecha >= date_from,
        JournalEntry.fecha <= date_to,
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))

    entrada_ids = (
        await db.scalars(
            base.order_by(JournalEntry.fecha, JournalEntry.numero_asiento)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items: list[dict] = []
    for entrada in entrada_ids:
        lineas = (
            await db.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.empresa_id == empresa_id,
                    JournalEntryLine.journal_entry_id == entrada.id,
                )
            )
        ).all()
        items.append(_item_payload(entrada, list(lineas)))

    return {"total": int(total or 0), "page": page, "page_size": page_size, "items": items}


async def obtener_detalle(
    db: AsyncSession,
    *,
    empresa_id: int,
    entry_id: uuid.UUID,
) -> dict | None:
    entrada = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.id == entry_id,
        )
    )
    if entrada is None:
        return None

    lineas = (
        await db.scalars(
            select(JournalEntryLine)
            .where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == entrada.id,
            )
            .order_by(JournalEntryLine.line_no)
        )
    ).all()

    account_ids = {linea.account_id for linea in lineas if linea.account_id is not None}
    cuentas: dict[int, AccountPlan] = {}
    if account_ids:
        rows = (
            await db.scalars(select(AccountPlan).where(AccountPlan.id.in_(account_ids)))
        ).all()
        cuentas = {cuenta.id: cuenta for cuenta in rows}

    lineas_payload = [
        {
            "line_no": linea.line_no,
            "account_id": linea.account_id,
            "account_code": linea.cuenta,
            "account_name": (
                cuentas[linea.account_id].name if linea.account_id in cuentas else None
            ),
            "debit": _as_decimal_str(linea.debe),
            "credit": _as_decimal_str(linea.haber),
            "detail": linea.descripcion,
        }
        for linea in lineas
    ]

    created_at: str | None = None
    if entrada.created_at is not None:
        ts = entrada.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        created_at = ts.astimezone(timezone.utc).isoformat()

    return {
        "id": str(entrada.id),
        "numero": entrada.numero_asiento,
        "fecha": _iso(entrada.fecha),
        "concepto": entrada.concepto,
        "estado": entrada.estado.value,
        "tipo": entrada.tipo.value,
        "reversal_of_id": str(entrada.original_id) if entrada.original_id else None,
        "creado_por": entrada.created_by,
        "created_at": created_at,
        "lineas": lineas_payload,
    }