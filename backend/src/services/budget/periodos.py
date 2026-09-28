"""Periodos de seguimiento presupuestario (SPEC-026 T-04/D5/D8).

Numeracion correlativa por `(empresa_id, ejercicio)` asignada bajo
``SELECT ... FOR UPDATE`` (constitucion IV) y garantia de "un solo periodo
abierto por ejercicio" replicada en el servicio para devolver 409 legible
ademas del indice parcial UNIQUE de la base de datos.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.budget.periodo_seguimiento import EstadoPeriodo, PeriodoSeguimiento
from services.audit import registrar_auditoria
from services.budget.errores import error

__all__ = [
    "AÑO_MAX",
    "AÑO_MIN",
    "cerrar_periodo",
    "crear_periodo",
    "ejercicio_cerrado",
    "listar_periodos",
    "obtener_periodo",
    "periodo_actual",
    "periodo_bloqueante",
    "proximo_numero_periodo",
]

AÑO_MIN = 2000
AÑO_MAX = 2100


async def ejercicio_cerrado(db: AsyncSession, empresa_id: int, ejercicio: int) -> bool:
    """True si existe `fiscal_year` cerrado para el ejercicio (SPEC-004)."""
    if not AÑO_MIN <= ejercicio <= AÑO_MAX:
        raise error("ejercicio_invalido", f"Ejercicio {ejercicio} fuera de rango", 422)
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == ejercicio
        )
    )
    return fy is not None and fy.is_closed


async def proximo_numero_periodo(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> int:
    """Siguiente correlativo sin saltos, con bloqueo de fila (constitucion IV).

    El ``SELECT ... FOR UPDATE`` sobre el ultimo periodo del ejercicio serializa
    a los emisores concurrentes. Cuando no existe ninguno, el ``MAX()`` sobre una
    tabla vacia devuelve ``None`` y el correlativo es 1.
    """
    ultimo = await db.scalar(
        select(func.max(PeriodoSeguimiento.numero_periodo))
        .where(
            PeriodoSeguimiento.empresa_id == empresa_id,
            PeriodoSeguimiento.ejercicio == ejercicio,
        )
        .with_for_update()
    )
    return int(ultimo or 0) + 1


async def obtener_periodo(
    db: AsyncSession, empresa_id: int, periodo_id: uuid.UUID | str
) -> PeriodoSeguimiento | None:
    """Periodo por id **dentro de la empresa activa** (constitucion III)."""
    return await db.scalar(
        select(PeriodoSeguimiento).where(
            PeriodoSeguimiento.empresa_id == empresa_id,
            PeriodoSeguimiento.id == uuid.UUID(str(periodo_id)),
        )
    )


async def periodo_actual(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> PeriodoSeguimiento | None:
    """Ultimo periodo del ejercicio (mayor `numero_periodo`), o `None`."""
    return await db.scalar(
        select(PeriodoSeguimiento)
        .where(
            PeriodoSeguimiento.empresa_id == empresa_id,
            PeriodoSeguimiento.ejercicio == ejercicio,
        )
        .order_by(PeriodoSeguimiento.numero_periodo.desc())
        .limit(1)
    )


async def periodo_bloqueante(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> PeriodoSeguimiento | None:
    """Periodo que impide modificar el presupuesto (FR-004/SC-003).

    Devuelve el periodo cuando el ultimo del ejercicio esta `cerrado`; en ese
    caso cualquier alta/modificacion del presupuesto debe rechazarse con 409
    hasta que se abra un periodo nuevo.
    """
    ultimo = await periodo_actual(db, empresa_id, ejercicio)
    if ultimo is not None and ultimo.estado is EstadoPeriodo.cerrado:
        return ultimo
    return None


async def listar_periodos(
    db: AsyncSession, empresa_id: int, ejercicio: int | None = None
) -> list[PeriodoSeguimiento]:
    consulta = select(PeriodoSeguimiento).where(
        PeriodoSeguimiento.empresa_id == empresa_id
    )
    if ejercicio is not None:
        consulta = consulta.where(PeriodoSeguimiento.ejercicio == ejercicio)
    return list(
        (
            await db.scalars(
                consulta.order_by(
                    PeriodoSeguimiento.ejercicio,
                    PeriodoSeguimiento.numero_periodo,
                )
            )
        ).all()
    )


async def crear_periodo(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    fecha_inicio: date,
    fecha_fin: date,
    actor: str,
    notas: str | None = None,
) -> PeriodoSeguimiento:
    """Abre un nuevo periodo de seguimiento para el ejercicio.

    Rechaza el ejercicio cerrado (409 `ejercicio_cerrado`, T041), el rango
    invalido (422) y la coexistencia de otro periodo abierto (409
    `periodo_ya_abierto`), garantia que el indice parcial UNIQUE vuelve
    imposible a nivel de base de datos.
    """
    if not AÑO_MIN <= ejercicio <= AÑO_MAX:
        raise error("ejercicio_invalido", f"Ejercicio {ejercicio} fuera de rango", 422)
    if fecha_fin <= fecha_inicio:
        raise error(
            "rango_invalido",
            "La fecha de fin debe ser posterior a la fecha de inicio",
            422,
        )
    if await ejercicio_cerrado(db, empresa_id, ejercicio):
        raise error(
            "ejercicio_cerrado",
            f"El ejercicio {ejercicio} esta cerrado: no admite periodos nuevos",
            409,
        )
    abierto = await db.scalar(
        select(PeriodoSeguimiento).where(
            PeriodoSeguimiento.empresa_id == empresa_id,
            PeriodoSeguimiento.ejercicio == ejercicio,
            PeriodoSeguimiento.estado == EstadoPeriodo.abierto,
        )
    )
    if abierto is not None:
        raise error(
            "periodo_ya_abierto",
            f"El ejercicio {ejercicio} ya tiene el periodo {abierto.numero_periodo} abierto",
            409,
        )
    numero = await proximo_numero_periodo(db, empresa_id, ejercicio)
    periodo = PeriodoSeguimiento(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        numero_periodo=numero,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=EstadoPeriodo.abierto,
        notas=notas,
    )
    db.add(periodo)
    try:
        await db.flush()
    except IntegrityError as exc:  # pragma: no cover - carrera concurrente
        raise error(
            "periodo_ya_abierto",
            "El ejercicio ya tiene un periodo de seguimiento abierto",
            409,
        ) from exc
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion="ABRIR_PERIODO",
        entidad="periodo_seguimiento",
        entidad_id=periodo.id,
        payload={
            "ejercicio": ejercicio,
            "numero_periodo": numero,
            "fecha_inicio": fecha_inicio.isoformat(),
            "fecha_fin": fecha_fin.isoformat(),
        },
        usuario=actor,
    )
    return periodo


async def asegurar_periodo(
    db: AsyncSession, *, empresa_id: int, ejercicio: int, actor: str
) -> PeriodoSeguimiento:
    """Devuelve el periodo abierto, creando el anual si el ejercicio no tiene ninguno.

    El presupuesto es anual (research.md D1), asi que el primer periodo cubre
    el ejercicio completo. Si el ultimo periodo esta cerrado se devuelve tal
    cual: el llamante lo convierte en 409 (FR-004).
    """
    ultimo = await periodo_actual(db, empresa_id, ejercicio)
    if ultimo is not None:
        return ultimo
    return await crear_periodo(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha_inicio=date(ejercicio, 1, 1),
        fecha_fin=date(ejercicio, 12, 31),
        actor=actor,
        notas="Periodo anual por defecto",
    )


async def cerrar_periodo(
    db: AsyncSession,
    *,
    empresa_id: int,
    periodo_id: uuid.UUID | str,
    actor: str,
    desviaciones: list[dict],
) -> PeriodoSeguimiento:
    """Cierra el periodo y persiste el snapshot `Desviacion` (T032).

    Idempotencia por estado: un periodo ya cerrado devuelve 409
    `periodo_ya_cerrado` sin tocar el snapshot existente (constitucion II).
    """
    periodo = await obtener_periodo(db, empresa_id, periodo_id)
    if periodo is None:
        raise error(
            "periodo_no_encontrado",
            "Periodo de seguimiento inexistente en la empresa activa",
            404,
        )
    if periodo.estado is EstadoPeriodo.cerrado:
        raise error(
            "periodo_ya_cerrado",
            f"El periodo {periodo.numero_periodo} ya esta cerrado",
            409,
        )
    periodo.estado = EstadoPeriodo.cerrado
    periodo.fecha_cierre = datetime.now(timezone.utc)
    periodo.cerrado_por = actor
    periodo.desviaciones_registradas = len(desviaciones)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion="CIERRE_PERIODO",
        entidad="periodo_seguimiento",
        entidad_id=periodo.id,
        payload={
            "ejercicio": periodo.ejercicio,
            "numero_periodo": periodo.numero_periodo,
            "desviaciones_registradas": len(desviaciones),
        },
        usuario=actor,
    )
    return periodo
