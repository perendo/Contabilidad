"""Motor de asientos multilínea (SPEC-006 US1/US2 T009).

`crear_asiento_multilinea` registra de una sola vez un asiento con N partidas
al Debe y M al Haber (o el caso clásico 1:1): valida con
`validar_asiento_multilinea` y persiste cabecera + líneas de forma indivisible
reutilizando el motor de SPEC-002 (`crear_borrador` + `asentar`), que asigna la
numeración correlativa por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE`.
Todo dentro del boundary ACID del llamante (`get_db`): si algo falla se
rechaza sin escribir nada (constitución I y IV).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
)
from models.costcenters.imputacion import ImputacionCentro
from services.journal.entry_service import AsientoError, asentar, crear_borrador
from services.journal.validador_multilinea import (
    LIMITE_LINEAS_DEFAULT,
    MultilineaError,
    validar_asiento_multilinea,
)

PAGINA_MIN, PAGINA_MAX = 1, 100


def _cuatro(value: Decimal) -> str:
    return f"{value:0.4f}"


def _totales(lineas: list[JournalEntryLine]) -> tuple[Decimal, Decimal]:
    debe = sum((l.debe for l in lineas), Decimal(0))
    haber = sum((l.haber for l in lineas), Decimal(0))
    return debe, haber


async def crear_asiento_multilinea(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha: date,
    concepto: str,
    lineas: list[dict],
    actor: str | None = None,
    limite: int = LIMITE_LINEAS_DEFAULT,
) -> JournalEntry:
    """Registra y asienta (POSTED) un asiento multilínea en una sola operación."""
    lineas_norm, _ = await validar_asiento_multilinea(
        db, empresa_id=empresa_id, lineas=lineas, limite=limite
    )
    borrador = await crear_borrador(
        db,
        empresa_id=empresa_id,
        fecha=fecha,
        concepto=concepto,
        lineas=lineas_norm,
        actor=actor,
    )
    entrada = await asentar(db, empresa_id=empresa_id, entry_id=borrador.id, actor=actor)
    if any(ln.get("centro_coste_id") is not None for ln in lineas_norm):
        lineas_db = (
            await db.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.empresa_id == empresa_id,
                    JournalEntryLine.journal_entry_id == entrada.id,
                )
            )
        ).all()
        por_numero = {l.line_no: l for l in lineas_db}
        for idx, ln in enumerate(lineas_norm, start=1):
            centro_id = ln.get("centro_coste_id")
            if centro_id is None:
                continue
            linea_db = por_numero.get(idx)
            if linea_db is None:
                continue
            db.add(
                ImputacionCentro(
                    empresa_id=empresa_id,
                    asiento_id=entrada.id,
                    linea_id=linea_db.id,
                    centro_coste_id=centro_id,
                    periodo=fecha.month,
                )
            )
        await db.flush()
    return entrada


async def obtener_asiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    entry_id: uuid.UUID,
) -> dict | None:
    """Detalle de un asiento con todas sus líneas (contrato SPEC-006)."""
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
    lista = list(lineas)
    total_debe, total_haber = _totales(lista)

    return {
        "id": str(entrada.id),
        "numero_asiento": entrada.numero_asiento,
        "fecha": entrada.fecha.isoformat(),
        "concepto": entrada.concepto,
        "estado": entrada.estado.value,
        "tipo": entrada.tipo.value,
        "asiento_original_id": str(entrada.original_id) if entrada.original_id else None,
        "total_debe": _cuatro(total_debe),
        "total_haber": _cuatro(total_haber),
        "n_lineas": len(lista),
        "lineas": [
            {
                "id": str(linea.id),
                "cuenta": linea.cuenta,
                "debe": _cuatro(linea.debe),
                "haber": _cuatro(linea.haber),
                "detalle": linea.descripcion,
                "centro_coste_id": str(linea.centro_coste_id) if linea.centro_coste_id else None,
            }
            for linea in lista
        ],
    }


async def listar_asientos(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Listado paginado de asientos multilínea con resumen de líneas."""
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise AsientoError("page_size_invalido", "page_size debe estar entre 1 y 100")

    filtros = [JournalEntry.empresa_id == empresa_id]
    if fecha_desde is not None:
        filtros.append(JournalEntry.fecha >= fecha_desde)
    if fecha_hasta is not None:
        filtros.append(JournalEntry.fecha <= fecha_hasta)
    if estado is not None:
        estados = [e.value for e in JournalEntryEstado]
        if estado.upper() not in estados:
            raise AsientoError("estado_invalido", f"Estado desconocido: {estado}")
        filtros.append(JournalEntry.estado == estado.upper())

    base = select(JournalEntry).where(*filtros)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))

    entradas = (
        await db.scalars(
            base.order_by(JournalEntry.fecha, JournalEntry.numero_asiento)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items: list[dict] = []
    for entrada in entradas:
        lineas = (
            await db.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.empresa_id == empresa_id,
                    JournalEntryLine.journal_entry_id == entrada.id,
                )
            )
        ).all()
        lista = list(lineas)
        total_debe, total_haber = _totales(lista)
        items.append(
            {
                "id": str(entrada.id),
                "numero_asiento": entrada.numero_asiento,
                "fecha": entrada.fecha.isoformat(),
                "concepto": entrada.concepto,
                "estado": entrada.estado.value,
                "total_debe": _cuatro(total_debe),
                "total_haber": _cuatro(total_haber),
                "n_lineas": len(lista),
            }
        )

    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}

__all__ = [
    "MultilineaError",
    "crear_asiento_multilinea",
    "listar_asientos",
    "obtener_asiento",
]