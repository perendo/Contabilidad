"""Helpers compartidos de SPEC-028 (cierre intermedio y reapertura controlada)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.closing.cierre_ejercicio import CierreEjercicio
from models.closing.periodo_cerrado import PeriodoCerrado, TipoPeriodo
from models.closing.solicitud_reapertura import SolicitudReapertura
from services.acct.seed import seed_default_pgc
from services.cashflow.utils import c4
from services.closing.periodo import cerrar_periodo_intermedio
from services.journal.entry_service import asentar, crear_borrador

__all__ = [
    "A",
    "B",
    "cerrar_meses",
    "cierre_anual_registrado",
    "cuentas",
    "empresa",
    "fiscal_year",
    "periodo",
    "plantar_cuenta",
    "plantar_pyg",
    "publicar_asiento",
    "saldos_asiento",
    "saldos_por_cuenta",
    "solicitud",
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
            razon_social=f"Cierres {empresa_id} SL",
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
    return {str(codigo): int(ident) for codigo, ident in filas.all()}


async def plantar_cuenta(
    db: AsyncSession, *, empresa_id: int, code: str, parent: str, name: str | None = None
) -> int:
    """Planta una cuenta de nivel 4 apuntable bajo un padre existente."""
    existente = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
        )
    )
    if existente is not None:
        return int(existente.id)
    padre = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == parent
        )
    )
    assert padre is not None, f"no existe la cuenta padre {parent} de {empresa_id}"
    nueva = AccountPlan(
        tenant_id=empresa_id,
        code=code,
        name=name or f"Cuenta {code}",
        parent_id=padre.id,
        level=4,
        is_selectable=True,
        is_active=True,
    )
    db.add(nueva)
    await db.flush()
    return int(nueva.id)


async def plantar_pyg(db: AsyncSession, empresa_id: int) -> int:
    """Planta la cuenta 129 (Pérdidas y ganancias) de nivel 3 bajo el grupo 12.

    El seed base de SPEC-001 no la crea, pero el cierre de SPEC-004/SPEC-028 la
    exige para la regularizacion (el servicio crea despues la subcuenta 1290).
    El trigger `chk_account_plan_structure` obliga a que `level == len(code)`
    y a que el padre sea de nivel 1, asi que `12` es el subgrupo correcto.
    """
    existente = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == "129"
        )
    )
    if existente is not None:
        return int(existente.id)
    padre = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == "12"
        )
    )
    assert padre is not None, f"no existe el subgrupo 12 de {empresa_id}"
    nueva = AccountPlan(
        tenant_id=empresa_id,
        code="129",
        name="Perdidas y ganancias",
        parent_id=padre.id,
        level=3,
        is_selectable=False,
        is_active=True,
    )
    db.add(nueva)
    await db.flush()
    return int(nueva.id)


async def fiscal_year(
    db: AsyncSession, *, empresa_id: int, year: int, cerrado: bool = False
) -> FiscalYear:
    """`FiscalYear` del ejercicio (el cierre anual la necesita para fechar)."""
    fila = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == year
        )
    )
    if fila is None:
        fila = FiscalYear(
            empresa_id=empresa_id,
            year=year,
            date_start=date(year, 1, 1),
            date_end=date(year, 12, 31),
            is_closed=cerrado,
        )
        db.add(fila)
        await db.flush()
    elif cerrado and not fila.is_closed:
        fila.is_closed = True
        await db.flush()
    return fila


async def publicar_asiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha: date,
    lineas: list[dict[str, Any]],
    concepto: str = "Movimiento de test",
    tipo: str = "GENERAL",
    original_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Asienta un movimiento POSTED y devuelve su id (motor de SPEC-002).

    Las lineas se expresan en forma contable (`{"cuenta": "5720", "debe": ...,
    "haber": ...}`) y se traducen al formato del motor resolviendo el
    `account_id` del plan de la empresa.
    """
    from models.acct.journal import JournalEntryTipo

    mapa = await cuentas(db, empresa_id)
    normalizadas: list[dict[str, Any]] = []
    for linea in lineas:
        codigo = str(linea["cuenta"])
        assert codigo in mapa, f"cuenta {codigo} no sembrada para {empresa_id}"
        normalizadas.append(
            {
                "account_id": mapa[codigo],
                "debit": str(linea.get("debe") or "0"),
                "credit": str(linea.get("haber") or "0"),
                "detail": linea.get("detail"),
            }
        )
    borrador = await crear_borrador(
        db,
        empresa_id=empresa_id,
        fecha=fecha,
        concepto=concepto,
        lineas=normalizadas,
        actor="test",
        tipo=JournalEntryTipo(tipo),
        original_id=original_id,
    )
    asiento = await asentar(
        db, empresa_id=empresa_id, entry_id=borrador.id, actor="test"
    )
    return asiento.id


async def cerrar_meses(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    meses: list[int],
    tipo: str = "MES",
) -> list[PeriodoCerrado]:
    """Cierra varios periodos del ejercicio y devuelve las filas."""
    filas: list[PeriodoCerrado] = []
    for mes in meses:
        resultado = await cerrar_periodo_intermedio(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            tipo=tipo,
            periodo=mes,
            actor="test",
        )
        filas.append(resultado["periodo"])
    return filas


async def periodo(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipo: str = "MES",
    numero: int = 1,
) -> PeriodoCerrado | None:
    """Periodo cerrado concreto (o `None` si sigue abierto)."""
    return await db.scalar(
        select(PeriodoCerrado).where(
            PeriodoCerrado.empresa_id == empresa_id,
            PeriodoCerrado.ejercicio == ejercicio,
            PeriodoCerrado.tipo == TipoPeriodo(tipo),
            PeriodoCerrado.periodo == numero,
        )
    )


async def cierre_anual_registrado(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> CierreEjercicio | None:
    return await db.scalar(
        select(CierreEjercicio).where(
            CierreEjercicio.empresa_id == empresa_id,
            CierreEjercicio.ejercicio == ejercicio,
        )
    )


async def solicitud(
    db: AsyncSession, *, empresa_id: int, ejercicio: int, numero: int = 1
) -> SolicitudReapertura | None:
    return await db.scalar(
        select(SolicitudReapertura).where(
            SolicitudReapertura.empresa_id == empresa_id,
            SolicitudReapertura.ejercicio == ejercicio,
            SolicitudReapertura.numero_solicitud == numero,
        )
    )


async def saldos_asiento(
    db: AsyncSession, *, empresa_id: int, asiento_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    """`(S(debe), S(haber))` de las lineas del asiento."""
    filas = (
        await db.execute(
            select(JournalEntryLine.debe, JournalEntryLine.haber).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == asiento_id,
            )
        )
    ).all()
    return (
        c4(sum((c4(fila[0]) for fila in filas), Decimal(0))),
        c4(sum((c4(fila[1]) for fila in filas), Decimal(0))),
    )


async def saldos_por_cuenta(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> dict[str, Decimal]:
    """`S(debe - haber)` por codigo de cuenta de los asientos POSTED."""
    filas = (
        await db.execute(
            select(
                JournalEntryLine.cuenta, JournalEntryLine.debe, JournalEntryLine.haber
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
    netos: dict[str, Decimal] = {}
    for codigo, debe, haber in filas:
        netos[str(codigo)] = netos.get(str(codigo), Decimal(0)) + c4(
            Decimal(str(debe or 0)) - Decimal(str(haber or 0))
        )
    return netos
