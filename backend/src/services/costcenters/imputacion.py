"""Servicios de imputación de apuntes a centros de coste (SPEC-017 US2).

Una imputación es la dimensión (metadatos) de una línea del motor multilínea:
nunca altera Debe/Haber (el balance lo garantiza SPEC-002/006 al persistir) y
queda ligada al apunte en la traza append-only ``imputacion_centro``. Las
líneas de asientos ``POSTED``/``CANCELLED`` son inmutables (constitución II):
su imputación solo cambia creando un asiento de rectificación
(``rectificar_imputacion``), nunca editando el original.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.costcenters.centro_coste import CentroCoste, CentroEstado
from models.costcenters.imputacion import ImputacionCentro
from services.audit.writer import audit_escribir
from services.costcenters.errores import CostcenterError
from services.journal.motor import crear_asiento_multilinea


def _periodo(fecha: date) -> int:
    return fecha.month


async def _centro_activo(
    db: AsyncSession, empresa_id: int, centro_coste_id: uuid.UUID
) -> CentroCoste:
    centro = await db.scalar(
        select(CentroCoste).where(
            CentroCoste.empresa_id == empresa_id, CentroCoste.id == centro_coste_id
        )
    )
    if centro is None:
        raise CostcenterError("centro_no_encontrado", "El centro no existe en la empresa activa")
    if centro.estado != CentroEstado.activo:
        raise CostcenterError("centro_inactivo", "No se puede imputar a un centro inactivo")
    return centro


async def _asiento_y_linea(
    db: AsyncSession, empresa_id: int, asiento_id: uuid.UUID, linea_id: uuid.UUID
) -> tuple[JournalEntry, JournalEntryLine]:
    asiento = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id, JournalEntry.id == asiento_id
        )
    )
    if asiento is None:
        raise CostcenterError("asiento_no_encontrado", "El asiento no existe en la empresa activa")
    linea = await db.scalar(
        select(JournalEntryLine).where(
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntryLine.journal_entry_id == asiento.id,
            JournalEntryLine.id == linea_id,
        )
    )
    if linea is None:
        raise CostcenterError("linea_no_encontrada", "La línea no existe en el asiento indicado")
    return asiento, linea


def _es_inmutable(estado: JournalEntryEstado) -> bool:
    return estado in (JournalEntryEstado.POSTED, JournalEntryEstado.CANCELLED)


async def imputar_linea(
    db: AsyncSession,
    *,
    empresa_id: int,
    asiento_id: uuid.UUID,
    linea_id: uuid.UUID,
    centro_coste_id: uuid.UUID,
    actor: str | None = None,
) -> dict:
    """Imputa una línea de un asiento (borrador) a un centro de la empresa.

    Líneas posteadas -> 409 ``linea_posteada`` (exige rectificación). La
    operación reasigna con upsert de la traza en la misma transacción ACID.
    """
    centro = await _centro_activo(db, empresa_id, centro_coste_id)
    asiento, linea = await _asiento_y_linea(db, empresa_id, asiento_id, linea_id)
    if _es_inmutable(asiento.estado):
        raise CostcenterError(
            "linea_posteada",
            "La línea pertenece a un asiento POSTED/CANCELLED: reasignar vía rectificación",
        )

    linea.centro_coste_id = centro.id
    previo = await db.scalar(
        select(ImputacionCentro).where(
            ImputacionCentro.empresa_id == empresa_id,
            ImputacionCentro.asiento_id == asiento.id,
            ImputacionCentro.linea_id == linea.id,
        )
    )
    if previo is not None:
        await db.execute(
            delete(ImputacionCentro).where(ImputacionCentro.id == previo.id)
        )
    db.add(
        ImputacionCentro(
            empresa_id=empresa_id,
            asiento_id=asiento.id,
            linea_id=linea.id,
            centro_coste_id=centro.id,
            periodo=_periodo(asiento.fecha),
        )
    )
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="IMPUTAR_LINEA",
        entity="imputacion_centro",
        entity_id=str(linea.id),
        payload={
            "asiento_id": str(asiento.id),
            "centro_coste_id": str(centro.id),
            "linea": linea.cuenta,
        },
    )
    return {
        "asiento_id": str(asiento.id),
        "linea_id": str(linea.id),
        "centro_coste_id": str(centro.id),
        "codigo": centro.codigo,
        "linea_cuenta": linea.cuenta,
    }


async def quitar_imputacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    asiento_id: uuid.UUID,
    linea_id: uuid.UUID,
    actor: str | None = None,
) -> None:
    """Quita la imputación de una línea de borrador (posteadas -> 409)."""
    asiento, linea = await _asiento_y_linea(db, empresa_id, asiento_id, linea_id)
    if _es_inmutable(asiento.estado):
        raise CostcenterError(
            "linea_posteada",
            "La línea pertenece a un asiento POSTED/CANCELLED: reasignar vía rectificación",
        )
    filas = await db.scalar(
        select(func.count()).select_from(
            select(ImputacionCentro)
            .where(
                ImputacionCentro.empresa_id == empresa_id,
                ImputacionCentro.asiento_id == asiento.id,
                ImputacionCentro.linea_id == linea.id,
            )
            .subquery()
        )
    )
    if not filas:
        raise CostcenterError("imputacion_no_existente", "La línea no tiene imputación")
    await db.execute(
        delete(ImputacionCentro).where(
            ImputacionCentro.empresa_id == empresa_id,
            ImputacionCentro.asiento_id == asiento.id,
            ImputacionCentro.linea_id == linea.id,
        )
    )
    linea.centro_coste_id = None
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="QUITAR_IMPUTACION",
        entity="imputacion_centro",
        entity_id=str(linea.id),
        payload={"asiento_id": str(asiento.id), "linea_id": str(linea.id)},
    )


async def listar_imputaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    asiento_id: uuid.UUID | None = None,
    centro_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Traza de imputaciones filtrada por asiento y/o centro, con datos de línea."""
    filtros = [ImputacionCentro.empresa_id == empresa_id]
    if asiento_id is not None:
        filtros.append(ImputacionCentro.asiento_id == asiento_id)
    if centro_id is not None:
        filtros.append(ImputacionCentro.centro_coste_id == centro_id)

    base = select(ImputacionCentro).where(*filtros)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    registros = (
        await db.scalars(
            base.order_by(ImputacionCentro.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    centros = {
        c.id: c
        for c in (
            await db.scalars(select(CentroCoste).where(CentroCoste.empresa_id == empresa_id))
        ).all()
    }
    items: list[dict] = []
    for r in registros:
        centro = centros.get(r.centro_coste_id)
        linea = await db.scalar(
            select(JournalEntryLine).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.id == r.linea_id,
            )
        )
        items.append(
            {
                "id": str(r.id),
                "asiento_id": str(r.asiento_id),
                "linea_id": str(r.linea_id),
                "centro_coste_id": str(r.centro_coste_id),
                "codigo": centro.codigo if centro else None,
                "nombre": centro.nombre if centro else None,
                "linea_cuenta": linea.cuenta if linea else None,
                "periodo": r.periodo,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


async def rectificar_imputacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    asiento_id: uuid.UUID,
    linea_id: uuid.UUID,
    centro_coste_id: uuid.UUID,
    actor: str | None = None,
) -> dict:
    """Reasigna una imputación POSTED creando un asiento ADJUSTMENT (motor).

    El original queda intacto (constitución II): se invierte el apunte con su
    centro origen y se re-registra con el centro destino en un asiento nuevo.
    """
    centro = await _centro_activo(db, empresa_id, centro_coste_id)
    asiento, linea = await _asiento_y_linea(db, empresa_id, asiento_id, linea_id)
    if not _es_inmutable(asiento.estado):
        raise CostcenterError(
            "estado_invalido", "Rectificación de imputación solo aplica a líneas posteadas"
        )
    centro_original = linea.centro_coste_id
    if centro_original is None:
        raise CostcenterError("imputacion_no_existente", "La línea posteada no tenía imputación")

    if linea.debe != 0:
        revert = {"cuenta": linea.cuenta, "debe": "0", "haber": f"{linea.debe:0.4f}"}
        rebook = {"cuenta": linea.cuenta, "debe": f"{linea.debe:0.4f}", "haber": "0"}
    else:
        revert = {"cuenta": linea.cuenta, "debe": f"{linea.haber:0.4f}", "haber": "0"}
        rebook = {"cuenta": linea.cuenta, "debe": "0", "haber": f"{linea.haber:0.4f}"}
    revert["detalle"] = linea.descripcion or linea.cuenta
    rebook["detalle"] = linea.descripcion or f"Rectificación imputación {centro.codigo}"
    revert["centro_coste_id"] = str(centro_original)
    rebook["centro_coste_id"] = str(centro.id)

    nuevo = await crear_asiento_multilinea(
        db,
        empresa_id=empresa_id,
        fecha=asiento.fecha,
        concepto=f"Rectificación imputación centro {centro.codigo}",
        lineas=[revert, rebook],
        actor=actor,
    )
    return {
        "asiento_original_id": str(asiento.id),
        "asiento_rectificativo_id": str(nuevo.id),
        "numero_asiento": nuevo.numero_asiento,
        "centro_coste_id": str(centro.id),
        "linea_cuenta": linea.cuenta,
    }


__all__ = [
    "imputar_linea",
    "listar_imputaciones",
    "quitar_imputacion",
    "rectificar_imputacion",
]