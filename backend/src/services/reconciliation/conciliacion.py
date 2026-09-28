"""Apertura de la sesión de conciliación (SPEC-013)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.treasury.conciliacion import Conciliacion, ConciliacionEstado
from models.treasury.extracto_bancario import ExtractoBancario
from services.audit.writer import audit_escribir
from services.reconciliation.saldos import recalcular_saldos


class ConciliacionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def abrir_conciliacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    cuenta_id: int,
    fecha_inicio: date,
    fecha_fin: date,
    extracto_id: uuid.UUID | None = None,
    actor: str | None = None,
) -> Conciliacion:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.id == cuenta_id
        )
    )
    if cuenta is None or not cuenta.is_active:
        raise ConciliacionError("cuenta_no_encontrada", "Cuenta inexistente en la empresa activa")

    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == fecha_inicio.year
        )
    )
    if fy is not None and fy.is_closed:
        raise ConciliacionError("ejercicio_cerrado", f"El ejercicio {fecha_inicio.year} está cerrado")

    previa = await db.scalar(
        select(Conciliacion).where(
            Conciliacion.empresa_id == empresa_id,
            Conciliacion.cuenta_id == cuenta_id,
            Conciliacion.estado == ConciliacionEstado.abierta,
            Conciliacion.fecha_inicio <= fecha_fin,
            Conciliacion.fecha_fin >= fecha_inicio,
        )
    )
    if previa is not None:
        raise ConciliacionError("conciliacion_previa", "Ya existe una conciliación abierta en el rango")

    if extracto_id is not None:
        extracto = await db.scalar(
            select(ExtractoBancario).where(
                ExtractoBancario.empresa_id == empresa_id, ExtractoBancario.id == extracto_id
            )
        )
        if extracto is None:
            raise ConciliacionError("extracto_no_encontrado", "Extracto inexistente")
    else:
        extracto = await db.scalar(
            select(ExtractoBancario)
            .where(
                ExtractoBancario.empresa_id == empresa_id,
                ExtractoBancario.cuenta_id == cuenta_id,
                ExtractoBancario.fecha_inicio <= fecha_fin,
                ExtractoBancario.fecha_fin >= fecha_inicio,
            )
            .order_by(ExtractoBancario.fecha_fin.desc())
        )

    conciliacion = Conciliacion(
        empresa_id=empresa_id,
        cuenta_id=cuenta_id,
        ejercicio=fecha_inicio.year,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        extracto_id=extracto.id if extracto else None,
        saldo_banco=extracto.saldo_final if extracto else 0,
        saldo_libros=0,
        diferencia=extracto.saldo_final if extracto else 0,
    )
    db.add(conciliacion)
    await db.flush()
    await recalcular_saldos(db, empresa_id=empresa_id, conciliacion=conciliacion)
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="ABRIR_CONCILIACION",
        entity="conciliacion",
        entity_id=str(conciliacion.id),
    )
    await db.flush()
    return conciliacion
