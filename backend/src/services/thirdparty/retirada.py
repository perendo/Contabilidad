"""Tercero retirement: physical delete only without movements (SPEC-008 US3)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntryLine
from models.ar.tercero import Tercero
from models.ar.tercero_subcuenta import TerceroSubcuenta
from models.ar.vencimiento import Vencimiento
from services.audit.writer import audit_escribir


class RetiradaError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def verificar_movimientos(
    db: AsyncSession, empresa_id: int, tercero_id: uuid.UUID
) -> tuple[bool, str | None]:
    """True if the tercero has vencimientos or journal lines on its subaccounts."""
    tiene_vencimientos = await db.scalar(
        select(Vencimiento.id).where(
            Vencimiento.empresa_id == empresa_id,
            Vencimiento.tercero_id == tercero_id,
        ).limit(1)
    )
    if tiene_vencimientos is not None:
        return True, "vencimientos"
    codigos = (
        await db.scalars(
            select(TerceroSubcuenta.cuenta_codigo).where(
                TerceroSubcuenta.empresa_id == empresa_id,
                TerceroSubcuenta.tercero_id == tercero_id,
            )
        )
    ).all()
    if codigos:
        n = await db.scalar(
            select(func.count(JournalEntryLine.id)).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.cuenta.in_(list(codigos)),
            )
        )
        if n:
            return True, "asientos"
    return False, None


async def _tercero(db: AsyncSession, empresa_id: int, tercero_id: uuid.UUID) -> Tercero:
    tercero = await db.scalar(
        select(Tercero).where(
            Tercero.empresa_id == empresa_id, Tercero.id == tercero_id
        )
    )
    if tercero is None:
        raise RetiradaError("tercero_no_encontrado", "Tercero inexistente en la empresa activa")
    return tercero


async def inactivar_tercero(
    db: AsyncSession, empresa_id: int, tercero_id: uuid.UUID, actor: str | None = None
) -> Tercero:
    tercero = await _tercero(db, empresa_id, tercero_id)
    tercero.activo = False
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="INACTIVATE_TERCERO",
        entity="tercero",
        entity_id=str(tercero.id),
    )
    await db.flush()
    return tercero


async def borrar_tercero(
    db: AsyncSession, empresa_id: int, tercero_id: uuid.UUID, actor: str | None = None
) -> None:
    """Physical delete; blocked with `tiene_movimientos` when history exists."""
    tercero = await _tercero(db, empresa_id, tercero_id)
    tiene, motivo = await verificar_movimientos(db, empresa_id, tercero_id)
    if tiene:
        raise RetiradaError(
            "tiene_movimientos",
            f"El tercero tiene {motivo}: solo se puede inactivar",
        )
    await db.delete(tercero)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="DELETE_TERCERO",
        entity="tercero",
        entity_id=str(tercero_id),
    )
    await db.flush()
