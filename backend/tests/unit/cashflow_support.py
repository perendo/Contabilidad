"""Helpers compartidos de SPEC-027 (prevision de tesoreria, EFE y alertas)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from services.acct.seed import seed_default_pgc
from services.cashflow.utils import c4
from services.journal.entry_service import asentar, crear_borrador

__all__ = [
    "A",
    "B",
    "cuentas",
    "empresa",
    "plantar_cuenta",
    "publicar_asiento",
    "saldos_por_cuenta",
    "tercero",
    "vencimiento",
]

A = 10
B = 20

IBAN = "ES9121000418450200051332"


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
            razon_social=f"Tesorería {empresa_id} SL",
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


async def tercero(db: AsyncSession, empresa_id: int, nif: str | None = None) -> uuid.UUID:
    """Tercero de la empresa. `Tercero.id` es PK global: no se puede compartir."""
    nif_real = nif or f"T{empresa_id:08d}"
    existente = await db.scalar(
        select(Tercero).where(
            Tercero.empresa_id == empresa_id, Tercero.nif == nif_real
        )
    )
    if existente is not None:
        return existente.id
    nuevo = Tercero(
        empresa_id=empresa_id,
        nif=nif_real,
        nombre=f"Cliente {nif_real}",
        activo=True,
        es_cliente=True,
        es_proveedor=False,
    )
    db.add(nuevo)
    await db.flush()
    return nuevo.id


async def vencimiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha_vencimiento: date,
    importe: str = "1000.0000",
    tipo: str = "cobro",
    estado: str = "pendiente",
    acumulado: str = "0.0000",
    tercero_id: uuid.UUID | None = None,
    recibo_num: str = "R-0001",
) -> Vencimiento:
    """Vencimiento pendiente de la empresa (fuente de la proyeccion)."""
    fila = Vencimiento(
        empresa_id=empresa_id,
        tercero_id=tercero_id or await tercero(db, empresa_id),
        recibo_num=recibo_num,
        iban=IBAN,
        ejercicio=fecha_vencimiento.year,
        tipo=TipoVencimiento(tipo),
        fecha_vencimiento=fecha_vencimiento,
        importe=c4(Decimal(importe)),
        acumulado=c4(Decimal(acumulado)),
        estado=EstadoVencimiento(estado),
    )
    db.add(fila)
    await db.flush()
    return fila


async def plantar_cuenta(
    db: AsyncSession, *, empresa_id: int, code: str, parent: str, name: str | None = None
) -> int:
    """Planta una cuenta de nivel 4 apuntable bajo un padre existente.

    El seed base de SPEC-001 no crea apuntables en los grupos 1/9/16/17 (los de
    financiacion del EFE), asi que el escenario los planta explicitamente.
    """
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


async def publicar_asiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha: date,
    lineas: list[dict[str, Any]],
    concepto: str = "Movimiento de tesorería",
    tipo: str = "GENERAL",
) -> uuid.UUID:
    """Asienta un movimiento POSTED y devuelve su id (motor de SPEC-002).

    Las lineas se expresan en forma contable (`{"cuenta": "5720", "debe": ...,
    "haber": ...}`) y se traducen al formato del motor resolviendo el
    `account_id` del plan de la empresa.
    """
    mapa = await cuentas(db, empresa_id)
    normalizadas: list[dict[str, Any]] = []
    for linea in lineas:
        codigo = str(linea["cuenta"])
        assert codigo in mapa, f"cuenta {codigo} no sembrada para {empresa_id}"
        debe = str(linea.get("debe") or "0")
        haber = str(linea.get("haber") or "0")
        normalizadas.append(
            {
                "account_id": mapa[codigo],
                "debit": debe,
                "credit": haber,
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
        tipo=tipo,
    )
    asiento = await asentar(
        db, empresa_id=empresa_id, entry_id=borrador.id, actor="test"
    )
    return asiento.id


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
        netos[codigo] = netos.get(codigo, Decimal(0)) + c4(
            Decimal(str(debe or 0)) - Decimal(str(haber or 0))
        )
    return netos
