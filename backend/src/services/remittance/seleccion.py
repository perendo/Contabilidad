"""Receivable selection and correlative remesa numbering (T016, T017).

FR-002: seleccionar vencimientos pendientes de la empresa activa por rango de
fecha, cliente o banco. FR-004/FR-008: excluir cobrados/sin IBAN y rechazar
ejercicios cerrados. Constitución IV: número correlativo por (empresa, ejercicio)
asignado atómicamente dentro de la misma transacción.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.remesa import Remesa
from models.treasury.secuencia_remesa import SecuenciaRemesa

EJERCICIO_ACTUAL_ANIO = datetime.now(timezone.utc).date().year


@dataclass
class Emisor:
    """Active company data used in generated file headers (SPEC-001 scaffold)."""

    nombre: str
    nif: str
    iban: str
    bic: str | None = None


@dataclass
class VencimientoExclusion:
    vencimiento_id: uuid.UUID
    motivo: str


class EjercicioCerradoError(Exception):
    def __init__(self, empresa_id: int, ejercicio: int) -> None:
        super().__init__(
            f"el ejercicio {ejercicio} está cerrado para la empresa {empresa_id}"
        )


def ejercicio_cerrado(empresa_id: int, ejercicio: int) -> bool:
    """Un ejercicio se considera cerrado si es inferior al año en curso."""
    return ejercicio < EJERCICIO_ACTUAL_ANIO


async def siguiente_numero_remesa(
    session: AsyncSession, empresa_id: int, ejercicio: int
) -> int:
    """Next correlative remesa number, assigned atomically (constitución IV).

    The SecuenciaRemesa row is locked with SELECT ... FOR UPDATE; if none exists
    it is seeded from the max existing remesa number so numbering never collides.
    """
    secuencia = await session.scalar(
        select(SecuenciaRemesa)
        .where(
            SecuenciaRemesa.empresa_id == empresa_id,
            SecuenciaRemesa.ejercicio == ejercicio,
        )
        .with_for_update()
    )
    if secuencia is None:
        max_existente = await session.scalar(
            select(func.coalesce(func.max(Remesa.numero_remesa), 0)).where(
                Remesa.empresa_id == empresa_id,
                Remesa.ejercicio == ejercicio,
            )
        )
        secuencia = SecuenciaRemesa(
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            ultimo_numero=int(max_existente or 0),
        )
        session.add(secuencia)
    secuencia.ultimo_numero += 1
    await session.flush()
    return secuencia.ultimo_numero


async def seleccionar_vencimientos(
    session: AsyncSession,
    empresa_id: int,
    *,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    tercero_id: uuid.UUID | None = None,
    banco: str | None = None,
) -> list[Vencimiento]:
    """Eligible pending receivables for the active company (FR-002/FR-003)."""
    query = select(Vencimiento).where(
        Vencimiento.empresa_id == empresa_id,
        Vencimiento.estado == EstadoVencimiento.pendiente,
    )
    if fecha_desde is not None:
        query = query.where(Vencimiento.fecha_vencimiento >= fecha_desde)
    if fecha_hasta is not None:
        query = query.where(Vencimiento.fecha_vencimiento <= fecha_hasta)
    if tercero_id is not None:
        query = query.where(Vencimiento.tercero_id == tercero_id)
    if banco:
        query = query.where(Vencimiento.iban.startswith(banco))
    return list((await session.scalars(query)).all())


async def validar_vencimientos(
    session: AsyncSession,
    empresa_id: int,
    vencimiento_ids: Iterable[uuid.UUID],
) -> tuple[list[Vencimiento], list[VencimientoExclusion]]:
    """Validate receivables before creating a remesa (FR-003, FR-008).

    Returns (elegibles, excluidos); a closed-exercise receivable cannot be part
    of a selection and propagates as EjercicioCerradoError.
    """
    ids = list(dict.fromkeys(vencimiento_ids))
    excluidos: list[VencimientoExclusion] = []
    if not ids:
        return [], excluidos

    filas = {
        v.id: v
        for v in (
            await session.scalars(
                select(Vencimiento).where(
                    Vencimiento.empresa_id == empresa_id,
                    Vencimiento.id.in_(ids),
                )
            )
        ).all()
    }

    elegibles: list[Vencimiento] = []
    for vencimiento_id in ids:
        vencimiento = filas.get(vencimiento_id)
        if vencimiento is None:
            excluidos.append(
                VencimientoExclusion(vencimiento_id, "no_encontrado")
            )
            continue
        if ejercicio_cerrado(empresa_id, vencimiento.ejercicio):
            raise EjercicioCerradoError(empresa_id, vencimiento.ejercicio)
        if vencimiento.estado != EstadoVencimiento.pendiente:
            motivo = (
                "ya_cobrado" if vencimiento.estado == EstadoVencimiento.cobrado else "no_pendiente"
            )
            excluidos.append(VencimientoExclusion(vencimiento_id, motivo))
            continue
        if not vencimiento.iban or len(vencimiento.iban) < 15:
            excluidos.append(VencimientoExclusion(vencimiento_id, "sin_iban"))
            continue
        elegibles.append(vencimiento)

    return elegibles, excluidos