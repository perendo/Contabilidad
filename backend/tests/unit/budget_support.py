"""Helpers compartidos de SPEC-026 (presupuestos y desviaciones)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado
from models.budget.periodo_seguimiento import PeriodoSeguimiento
from models.budget.presupuesto import Presupuesto
from models.costcenters.centro_coste import CentroCoste, CentroEstado, CentroTipo
from services.acct.seed import seed_default_pgc
from services.budget.periodos import crear_periodo
from services.budget.presupuesto_service import guardar_presupuesto
from services.budget.utils import c4
from services.journal.entry_service import asentar, crear_borrador

__all__ = [
    "crear_centro",
    "crear_periodo_abierto",
    "cuentas",
    "empresa",
    "presupuesto_directo",
    "publicar_asiento",
    "saldos_por_cuenta",
    "sin_presupuesto_esperado",
]

A = 10
B = 20


async def empresa(db: AsyncSession, empresa_id: int) -> None:
    """Crea la empresa y siembra su plan de cuentas (SPEC-001)."""
    from models.iam.company import Company

    existente = await db.get(Company, empresa_id)
    if existente is not None:
        return
    db.add(
        Company(
            company_id=empresa_id,
            nif=f"T{empresa_id:08d}",
            razon_social=f"Presupuestos {empresa_id} SL",
        )
    )
    await db.flush()
    await seed_default_pgc(db, empresa_id)


async def cuentas(db: AsyncSession, empresa_id: int) -> dict[str, int]:
    """Mapa codigo -> id de todas las cuentas del plan de la empresa."""
    filas = await db.execute(
        select(AccountPlan.code, AccountPlan.id).where(
            AccountPlan.tenant_id == empresa_id
        )
    )
    return {codigo: int(ident) for codigo, ident in filas.all()}


async def crear_centro(
    db: AsyncSession, empresa_id: int, codigo: str = "CC-01", nombre: str = "Produccion"
) -> uuid.UUID:
    centro = CentroCoste(
        empresa_id=empresa_id,
        codigo=codigo,
        nombre=nombre,
        tipo=CentroTipo.departamento,
        estado=CentroEstado.activo,
    )
    db.add(centro)
    await db.flush()
    return centro.id


async def crear_periodo_abierto(
    db: AsyncSession, empresa_id: int, ejercicio: int = 2026
) -> PeriodoSeguimiento:
    return await crear_periodo(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha_inicio=date(ejercicio, 1, 1),
        fecha_fin=date(ejercicio, 12, 31),
        actor="test",
    )


async def presupuesto_directo(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    cuenta_id: int,
    importe: str,
    centro_coste_id: uuid.UUID | None = None,
    tipo: str = "gasto",
) -> Presupuesto:
    """Linea de presupuesto sin pasar por la API (util para preparar escenarios)."""
    return await guardar_presupuesto(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        cuenta_id=cuenta_id,
        centro_coste_id=centro_coste_id,
        importe=importe,
        tipo=tipo,
        actor="test",
    )


async def publicar_asiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha: date,
    lineas: list[dict[str, Any]],
    concepto: str = "Movimiento real de test",
) -> uuid.UUID:
    """Asienta un movimiento POSTED y devuelve su id (motor de SPEC-002)."""
    borrador = await crear_borrador(
        db,
        empresa_id=empresa_id,
        fecha=fecha,
        concepto=concepto,
        lineas=lineas,
        actor="test",
    )
    asiento = await asentar(
        db, empresa_id=empresa_id, entry_id=borrador.id, actor="test"
    )
    return asiento.id


async def saldos_por_cuenta(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> dict[int, dict[str, Decimal]]:
    """Suma de debe/haber POSTED por cuenta, replicando la agregacion D3."""
    from models.acct.journal import JournalEntryLine

    filas = (
        await db.execute(
            select(
                JournalEntryLine.account_id,
                JournalEntryLine.centro_coste_id,
                JournalEntryLine.debe,
                JournalEntryLine.haber,
            )
            .join(
                JournalEntry,
                (JournalEntry.id == JournalEntryLine.journal_entry_id)
                & (JournalEntry.empresa_id == JournalEntryLine.empresa_id),
            )
            .where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.estado == JournalEntryEstado.POSTED,
                JournalEntry.ejercicio == ejercicio,
            )
        )
    ).all()
    acumulado: dict[int, dict[str, Decimal]] = {}
    for cuenta, centro, debe, haber in filas:
        clave = (int(cuenta), uuid.UUID(str(centro)) if centro else None)
        fila = acumulado.setdefault(clave, {"debe": Decimal(0), "haber": Decimal(0)})
        fila["debe"] += Decimal(debe or 0)
        fila["haber"] += Decimal(haber or 0)
    return acumulado


def sin_presupuesto_esperado(real: Decimal, presupuesto: Decimal) -> Decimal:
    """`real - presupuesto` a 4 decimales (SC-002)."""
    return c4(real - presupuesto)
