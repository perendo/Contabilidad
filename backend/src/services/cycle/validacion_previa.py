"""Validaciones previas del ciclo contable (SPEC-009 US1/US3).

Precondiciones de apertura (research D4 / FR-002):
  (a) el ejercicio anterior existe y está cerrado,
  (b) el ejercicio siguiente ya está definido (rango de fechas),
  (c) no existe un asiento OPENING activo para el ejercicio siguiente,
  (d) el rango del nuevo ejercicio no se solapa con el anterior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryTipo
from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado


class CicloError(Exception):
    status_code = 400
    code = "error"


class EjercicioNoDefinidoError(CicloError):
    status_code = 422
    code = "ejercicio_no_definido"


class EjercicioCerradoError(CicloError):
    status_code = 409
    code = "ejercicio_cerrado"


class SinAperturaError(CicloError):
    status_code = 404
    code = "sin_apertura"


class AperturaActivaError(CicloError):
    status_code = 409
    code = "apertura_activa"


class EjercicioYaAbiertoError(CicloError):
    status_code = 409
    code = "ejercicio_ya_abierto"


class SolapamientoEjerciciosError(CicloError):
    status_code = 409
    code = "solapamiento_ejercicios"


@dataclass
class RangoEjercicio:
    year: int
    date_start: date
    date_end: date
    cerrado: bool
    origen: str


@dataclass
class ContextoApertura:
    previo: RangoEjercicio
    destino: RangoEjercicio


async def _tabla_rango(
    db: AsyncSession, empresa_id: int, year: int
) -> RangoEjercicio | None:
    """Resuelve el rango del ejercicio `year` desde `ejercicio_contable`
    o, en su defecto, desde `fiscal_year` (cierre SPEC-004)."""
    ej = await db.scalar(
        select(EjercicioContable).where(
            EjercicioContable.empresa_id == empresa_id, EjercicioContable.ejercicio == year
        )
    )
    if ej is not None:
        return RangoEjercicio(
            year=ej.ejercicio,
            date_start=ej.fecha_inicio,
            date_end=ej.fecha_fin,
            cerrado=ej.estado == EjercicioEstado.cerrado,
            origen="ejercicio_contable",
        )
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == year
        )
    )
    if fy is not None:
        return RangoEjercicio(
            year=fy.year,
            date_start=fy.date_start,
            date_end=fy.date_end,
            cerrado=fy.is_closed,
            origen="fiscal_year",
        )
    return None


async def _apertura_activa(
    db: AsyncSession, empresa_id: int, year: int
) -> JournalEntry | None:
    """Último asiento de apertura (OPENING) o su anulación para (empresa, ejercicio)."""
    entries = (
        await db.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.ejercicio == year,
                JournalEntry.tipo.in_(
                    [JournalEntryTipo.OPENING, JournalEntryTipo.OPENING_REVERSAL]
                ),
            )
            .order_by(JournalEntry.created_at)
        )
    ).all()
    if not entries:
        return None
    ultimo = entries[-1]
    if ultimo.tipo == JournalEntryTipo.OPENING:
        return ultimo
    return None


async def validar_precondiciones_apertura(
    db: AsyncSession, empresa_id: int, ejercicio_destino: int
) -> ContextoApertura:
    previo = await _tabla_rango(db, empresa_id, ejercicio_destino - 1)
    destino = await _tabla_rango(db, empresa_id, ejercicio_destino)
    if previo is None:
        raise EjercicioNoDefinidoError(
            f"El ejercicio {ejercicio_destino - 1} no está definido"
        )
    if destino is None:
        raise EjercicioNoDefinidoError(
            f"El ejercicio {ejercicio_destino} no está definido (rango de fechas)"
        )
    if not previo.cerrado:
        raise EjercicioCerradoError(
            f"El ejercicio {ejercicio_destino - 1} debe estar cerrado antes de abrir"
        )
    if destino.date_start <= previo.date_end:
        raise SolapamientoEjerciciosError(
            "El rango del nuevo ejercicio no puede solaparse con el anterior"
        )
    apertura = await _apertura_activa(db, empresa_id, ejercicio_destino)
    if apertura is not None:
        raise EjercicioYaAbiertoError(
            f"El ejercicio {ejercicio_destino} ya tiene apertura generada"
        )
    return ContextoApertura(previo=previo, destino=destino)


async def apertura_vigente(
    db: AsyncSession, empresa_id: int, year: int
) -> JournalEntry:
    """OPENING activo de (empresa, año); único origen de anulación."""
    apertura = await _apertura_activa(db, empresa_id, year)
    if apertura is None:
        raise SinAperturaError(f"El ejercicio {year} no tiene apertura activa")
    return apertura


async def estado_apertura(
    db: AsyncSession, empresa_id: int, year: int
) -> dict:
    """Estado observable del ciclo para `year` (quickstart Scenario 1/4)."""
    rango = await _tabla_rango(db, empresa_id, year)
    if rango is None:
        return {
            "ejercicio": year,
            "estado": "no_definido",
            "asiento_apertura_id": None,
            "asiento_anulacion_id": None,
        }
    apertura = await _apertura_activa(db, empresa_id, year)
    entry = (
        await db.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.ejercicio == year,
                JournalEntry.tipo == JournalEntryTipo.OPENING_REVERSAL,
            )
            .order_by(JournalEntry.created_at)
        )
    ).all()
    if apertura is not None:
        return {
            "ejercicio": year,
            "estado": "con_apertura",
            "asiento_apertura_id": str(apertura.id),
            "asiento_anulacion_id": (
                str(entry[-1].id) if entry and entry[-1].created_at >= apertura.created_at else None
            ),
        }
    if entry:
        return {
            "ejercicio": year,
            "estado": "apertura_anulada",
            "asiento_apertura_id": None,
            "asiento_anulacion_id": str(entry[-1].id),
        }
    if rango.cerrado:
        estado = "cerrado"
    else:
        estado = "abierto"
    return {
        "ejercicio": year,
        "estado": estado,
        "asiento_apertura_id": None,
        "asiento_anulacion_id": None,
    }