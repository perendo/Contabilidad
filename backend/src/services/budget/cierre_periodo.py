"""Cierre del periodo de seguimiento con snapshot inmutable (SPEC-026 T-04/T032).

Cierra `PeriodoSeguimiento` y persiste una fila `Desviacion` por combinacion
cuenta-centro presente en el presupuesto **o** en el diario. El snapshot no se
actualiza ni se borra nunca (constitucion II): los triggers append-only de
`017_presupuestos.sql` y `db/triggers.py` lo garantizan en la base de datos.

La atomicidad la aporta el boundary ACID del proyecto (`get_db` + `flush()`
dentro de la peticion); el servicio no abre su propia transaccion para no
anidar un `begin()` sobre la sesion.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.budget.desviacion import Desviacion
from models.budget.periodo_seguimiento import EstadoPeriodo
from services.budget.desviaciones import desviaciones_de_periodo
from services.budget.errores import error
from services.budget.periodos import cerrar_periodo, obtener_periodo

__all__ = ["cerrar_periodo_desviaciones", "listar_snapshots"]


async def cerrar_periodo_desviaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    periodo_id: uuid.UUID | str,
    actor: str = "sistema",
) -> dict[str, Any]:
    """Cierra el periodo y materializa el snapshot `Desviacion` (T032).

    Un periodo sin datos de desviacion se cierra igual con `total = 0`, tal y
    como fija el contrato. Un periodo ya cerrado devuelve 409 sin reescribir
    el snapshot existente.
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
    filas = await desviaciones_de_periodo(db, empresa_id=empresa_id, periodo_id=periodo.id)
    ya_hay_snapshot = (
        await db.scalar(
            select(Desviacion.id)
            .where(
                Desviacion.empresa_id == empresa_id,
                Desviacion.periodo_id == periodo.id,
            )
            .limit(1)
        )
        is not None
    )
    if ya_hay_snapshot:
        raise error(
            "snapshot_ya_registrado",
            "El periodo ya tiene desviaciones registradas: no se puede volver a cerrar",
            409,
        )
    for fila in filas:
        db.add(
            Desviacion(
                empresa_id=empresa_id,
                periodo_id=periodo.id,
                cuenta_id=fila.cuenta_id,
                centro_coste_id=fila.centro_coste_id,
                importe_presupuestado=fila.importe_presupuestado,
                importe_real=fila.importe_real,
                desviacion_absoluta=fila.desviacion_absoluta,
                desviacion_relativa=fila.desviacion_relativa,
                sin_presupuesto=fila.sin_presupuesto,
            )
        )
    await db.flush()
    cerrado = await cerrar_periodo(
        db,
        empresa_id=empresa_id,
        periodo_id=periodo.id,
        actor=actor,
        desviaciones=[{"cuenta_id": f.cuenta_id} for f in filas],
    )
    return {
        "periodo_id": str(cerrado.id),
        "ejercicio": cerrado.ejercicio,
        "numero_periodo": int(cerrado.numero_periodo),
        "estado": cerrado.estado.value,
        "desviaciones_registradas": len(filas),
        "fecha_cierre": cerrado.fecha_cierre.isoformat() if cerrado.fecha_cierre else None,
        "cerrado_por": cerrado.cerrado_por,
    }


async def listar_snapshots(
    db: AsyncSession, *, empresa_id: int, periodo_id: uuid.UUID | str
) -> list[Desviacion]:
    """Filas del snapshot de un periodo, ordenadas por cuenta (solo lectura)."""
    return list(
        (
            await db.scalars(
                select(Desviacion)
                .where(
                    Desviacion.empresa_id == empresa_id,
                    Desviacion.periodo_id == uuid.UUID(str(periodo_id)),
                )
                .order_by(Desviacion.cuenta_id, Desviacion.centro_coste_id)
            )
        ).all()
    )
