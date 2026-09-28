"""Arqueos de caja (SPEC-019 US3 / FR-009).

El arqueo contrasta el saldo contable de la 570 (suma de líneas POSTED hasta la
fecha) con el efectivo físico anotado. `cuadra` (diferencia == 0) se aprueba
automáticamente sin asiento; `con_diferencia` queda `pendiente` hasta que el
responsable la aprueba (exige asiento de ajuste que cuadre 570 con el efectivo)
o la archiva (diferencia pendiente visible, sin asiento).
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
from models.ngo.arqueo import (
    Arqueo,
    ArqueoDecision,
    ArqueoEstado,
)
from models.ngo.caja import Caja, CajaEstado
from services.audit.writer import audit_escribir
from services.ngo.caja import saldo_570
from services.ngo.errores import NgoError

PAGINA_MIN, PAGINA_MAX = 1, 100


def _cuatro(value: Decimal) -> str:
    return f"{value:0.4f}"


def _arqueo_dto(a: Arqueo) -> dict:
    return {
        "id": str(a.id),
        "caja_id": str(a.caja_id),
        "fecha": a.fecha.isoformat(),
        "saldo_libros": _cuatro(a.saldo_libros),
        "efectivo_contado": _cuatro(a.efectivo_contado),
        "diferencia": _cuatro(a.diferencia),
        "estado": a.estado.value,
        "decision": a.decision.value if a.decision else None,
        "asiento_ajuste_id": str(a.asiento_ajuste_id) if a.asiento_ajuste_id else None,
        "archivado": a.archivado,
        "detalle_diferencia": a.detalle_diferencia,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


async def _caja_activa(db: AsyncSession, empresa_id: int, caja_id: uuid.UUID) -> Caja:
    caja = await db.scalar(
        select(Caja).where(
            Caja.empresa_id == empresa_id,
            Caja.id == caja_id,
        )
    )
    if caja is None:
        raise NgoError("caja_no_encontrada", "La caja no existe en la empresa activa")
    if caja.estado == CajaEstado.inactiva:
        raise NgoError("caja_inactiva", "La caja está inactiva")
    return caja


async def realizar_arqueo(
    db: AsyncSession,
    *,
    empresa_id: int,
    caja_id: uuid.UUID,
    fecha: date,
    efectivo_contado: Decimal,
    detalle: str | None = None,
    actor: str | None = None,
) -> dict:
    caja = await _caja_activa(db, empresa_id, caja_id)
    if efectivo_contado < 0:
        raise NgoError("efectivo_invalido", "El efectivo contado no puede ser negativo")

    saldo = await saldo_570(db, empresa_id=empresa_id, account_id=caja.cuenta_570_id, hasta=fecha)
    diferencia = efectivo_contado - saldo
    estado = ArqueoEstado.cuadra if diferencia == 0 else ArqueoEstado.con_diferencia
    decision = ArqueoDecision.aprobada if estado == ArqueoEstado.cuadra else ArqueoDecision.pendiente

    arqueo = Arqueo(
        empresa_id=empresa_id,
        caja_id=caja.id,
        fecha=fecha,
        saldo_libros=saldo,
        efectivo_contado=efectivo_contado,
        diferencia=diferencia,
        estado=estado,
        decision=decision,
        asiento_ajuste_id=None,
        archivado=False,
        detalle_diferencia=detalle.strip() if detalle else None,
    )
    if arqueo.id is None:
        arqueo.id = uuid.uuid4()
    db.add(arqueo)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="REALIZAR_ARQUEO",
        entity="arqueo",
        entity_id=str(arqueo.id),
        payload={
            "caja_id": str(caja.id),
            "saldo_libros": str(saldo),
            "efectivo_contado": str(efectivo_contado),
            "diferencia": str(diferencia),
        },
    )
    await db.flush()
    return _arqueo_dto(arqueo)


async def _ajuste_570(
    db: AsyncSession,
    *,
    empresa_id: int,
    asiento_id: uuid.UUID,
    cuenta_570_id: int,
) -> Decimal:
    """Delta (debe - haber) que el asiento aplica sobre la 570 de la caja."""
    return Decimal(
        await db.scalar(
            select(func.coalesce(func.sum(JournalEntryLine.debe - JournalEntryLine.haber), 0)).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == asiento_id,
                JournalEntryLine.account_id == cuenta_570_id,
            )
        )
        or 0
    )


async def aprobar_arqueo(
    db: AsyncSession,
    *,
    empresa_id: int,
    arqueo_id: uuid.UUID,
    asiento_ajuste_id: uuid.UUID | None = None,
    actor: str | None = None,
) -> dict:
    arqueo = await db.scalar(
        select(Arqueo).where(
            Arqueo.empresa_id == empresa_id,
            Arqueo.id == arqueo_id,
        )
    )
    if arqueo is None:
        raise NgoError("arqueo_no_encontrado", "El arqueo no existe en la empresa activa")
    if arqueo.decision is not None and arqueo.decision != ArqueoDecision.pendiente:
        raise NgoError("arqueo_ya_decidido", "El arqueo ya está aprobado o archivado")

    if arqueo.estado == ArqueoEstado.cuadra:
        arqueo.decision = ArqueoDecision.aprobada
        arqueo.asiento_ajuste_id = None
        arqueo.archivado = False
        await db.flush()
        await audit_escribir(
            db,
            empresa_id=empresa_id,
            actor=actor or "system",
            action="APROBAR_ARQUEO",
            entity="arqueo",
            entity_id=str(arqueo.id),
            payload={"caja_id": str(arqueo.caja_id), "asiento_ajuste_id": None},
        )
        await db.flush()
        return _arqueo_dto(arqueo)

    if asiento_ajuste_id is None:
        raise NgoError("falta_asiento_ajuste", "Aprobar un arqueo con diferencia exige asiento de ajuste")

    caja = await _caja_activa(db, empresa_id, arqueo.caja_id)
    asiento = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.id == asiento_ajuste_id,
        )
    )
    if asiento is None:
        raise NgoError("asiento_no_encontrado", "El asiento de ajuste no existe en la empresa activa")
    if asiento.estado != JournalEntryEstado.POSTED:
        raise NgoError("ajuste_no_asentado", "El asiento de ajuste debe estar POSTED")

    delta = await _ajuste_570(db, empresa_id=empresa_id, asiento_id=asiento.id, cuenta_570_id=caja.cuenta_570_id)
    if arqueo.saldo_libros + delta != arqueo.efectivo_contado:
        raise NgoError(
            "ajuste_no_cuadra",
            "Tras aplicar el ajuste, la 570 no cuadra con el efectivo contado",
        )

    arqueo.decision = ArqueoDecision.aprobada
    arqueo.asiento_ajuste_id = asiento.id
    arqueo.archivado = False
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="APROBAR_ARQUEO",
        entity="arqueo",
        entity_id=str(arqueo.id),
        payload={
            "caja_id": str(arqueo.caja_id),
            "asiento_ajuste_id": str(asiento.id),
            "diferencia_ajustada": str(delta),
        },
    )
    await db.flush()
    return _arqueo_dto(arqueo)


async def archivar_arqueo(
    db: AsyncSession,
    *,
    empresa_id: int,
    arqueo_id: uuid.UUID,
    actor: str | None = None,
) -> dict:
    arqueo = await db.scalar(
        select(Arqueo).where(
            Arqueo.empresa_id == empresa_id,
            Arqueo.id == arqueo_id,
        )
    )
    if arqueo is None:
        raise NgoError("arqueo_no_encontrado", "El arqueo no existe en la empresa activa")
    if arqueo.decision is not None and arqueo.decision != ArqueoDecision.pendiente:
        raise NgoError("arqueo_ya_decidido", "El arqueo ya está aprobado o archivado")

    arqueo.decision = ArqueoDecision.archivada
    arqueo.asiento_ajuste_id = None
    arqueo.archivado = True
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="ARCHIVAR_ARQUEO",
        entity="arqueo",
        entity_id=str(arqueo.id),
        payload={"caja_id": str(arqueo.caja_id)},
    )
    await db.flush()
    return _arqueo_dto(arqueo)


async def listar_arqueos(
    db: AsyncSession,
    *,
    empresa_id: int,
    caja_id: uuid.UUID | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise NgoError("page_size_invalido", "page_size debe estar entre 1 y 100")
    filtros = [Arqueo.empresa_id == empresa_id]
    if caja_id is not None:
        filtros.append(Arqueo.caja_id == caja_id)
    if estado is not None:
        valores = [e.value for e in ArqueoEstado]
        if estado.lower() not in valores:
            raise NgoError("estado_invalido", f"Estado de arqueo desconocido: {estado}")
        filtros.append(Arqueo.estado == estado.lower())
    base = select(Arqueo).where(*filtros)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    arqueos = (
        await db.scalars(
            base.order_by(Arqueo.fecha.desc(), Arqueo.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [_arqueo_dto(a) for a in arqueos],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }