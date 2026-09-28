"""Cierre y archivo del período conciliado (SPEC-013 US3, research D6)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.treasury.conciliacion import Conciliacion, ConciliacionEstado
from models.treasury.periodo_conciliado import PeriodoConciliado
from services.audit.writer import audit_escribir
from services.reconciliation.saldos import CERO, listar_pendientes, recalcular_saldos


class CierreError(Exception):
    def __init__(self, code: str, message: str, **extra: object) -> None:
        super().__init__(message)
        self.code = code
        self.extra = extra


async def cerrar_periodo(
    db: AsyncSession,
    *,
    empresa_id: int,
    conciliacion: Conciliacion,
    actor: str | None = None,
    usuario_id: int | None = None,
) -> PeriodoConciliado:
    if conciliacion.estado == ConciliacionEstado.cerrada:
        raise CierreError("periodo_cerrado", "La conciliación ya está cerrada")
    await recalcular_saldos(db, empresa_id=empresa_id, conciliacion=conciliacion)
    if conciliacion.diferencia != CERO:
        pendientes = await listar_pendientes(db, empresa_id, conciliacion)
        raise CierreError(
            "diferencia_no_cero",
            f"La diferencia {conciliacion.diferencia} no es cero",
            diferencia=f"{conciliacion.diferencia:0.4f}",
            pendientes=pendientes,
        )

    ultimo = await db.scalar(
        select(func.max(PeriodoConciliado.numero_periodo)).where(
            PeriodoConciliado.empresa_id == empresa_id,
            PeriodoConciliado.ejercicio == conciliacion.ejercicio,
        )
    )
    periodo = PeriodoConciliado(
        empresa_id=empresa_id,
        conciliacion_id=conciliacion.id,
        cuenta_id=conciliacion.cuenta_id,
        ejercicio=conciliacion.ejercicio,
        numero_periodo=(ultimo or 0) + 1,
        fecha_inicio=conciliacion.fecha_inicio,
        fecha_fin=conciliacion.fecha_fin,
        saldo_banco=conciliacion.saldo_banco,
        saldo_libros=conciliacion.saldo_libros,
        diferencia=Decimal("0.0000"),
        usuario_id=usuario_id,
    )
    db.add(periodo)
    await db.flush()
    conciliacion.estado = ConciliacionEstado.cerrada
    conciliacion.periodo_conciliado_id = periodo.id
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CERRAR_CONCILIACION",
        entity="periodo_conciliado",
        entity_id=str(periodo.id),
        payload={"numero_periodo": str(periodo.numero_periodo)},
    )
    await db.flush()
    return periodo
