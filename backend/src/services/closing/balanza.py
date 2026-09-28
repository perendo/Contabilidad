"""Balanza de comprobacion del periodo (SPEC-028 T018, research D1/D3).

El cierre intermedio **no crea asientos**: calcula en memoria el balance de
comprobacion de los asientos POSTED del rango del periodo y lo persiste como
snapshot inmutable (`BalanzaPeriodo` + `BalanzaPeriodoLinea`) dentro de la
misma transaccion ACID que el `PeriodoCerrado` y el audit log.

Todos los importes son `Decimal` cuantizados a 4 decimales; `total_debe ==
total_haber` se valida **antes** de persistir y tambien con el CHECK
`chk_balanza_periodo_cuadre` (constitucion I).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.closing.balanza_periodo import BalanzaPeriodo, BalanzaPeriodoLinea
from services.cashflow.utils import c4
from services.closing.errores import error

#: Grupos PGC de cuentas de gestion: 6 (gastos) y 7 (ingresos), research D4.
GRUPOS_GESTION: frozenset[str] = frozenset({"6", "7"})


class LineaBalanza(dict):
    """Fila agregada por cuenta antes de persistir el snapshot."""


async def _movimientos(
    db: AsyncSession, empresa_id: int, fecha_ini: date, fecha_fin: date
) -> list[tuple[str, int, Decimal, Decimal]]:
    """`(codigo, account_id, S(debe), S(haber))` de los asientos POSTED del rango."""
    filas = (
        await db.execute(
            select(
                JournalEntryLine.cuenta,
                JournalEntryLine.account_id,
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
                JournalEntry.fecha >= fecha_ini,
                JournalEntry.fecha <= fecha_fin,
            )
            .order_by(JournalEntryLine.cuenta)
        )
    ).all()
    agregado: dict[str, dict[str, Any]] = {}
    for codigo, account_id, debe, haber in filas:
        fila = agregado.setdefault(
            str(codigo), {"debe": Decimal(0), "haber": Decimal(0), "account_id": account_id}
        )
        fila["debe"] += Decimal(str(debe or 0))
        fila["haber"] += Decimal(str(haber or 0))
    return [
        (codigo, int(fila["account_id"] or 0), c4(fila["debe"]), c4(fila["haber"]))
        for codigo, fila in sorted(agregado.items())
    ]


async def calcular_balanza_periodo(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipo: str,
    periodo: int,
    fecha_ini: date,
    fecha_fin: date,
    periodo_id: uuid.UUID | None = None,
    actor: str | None = None,
) -> tuple[BalanzaPeriodo, list[BalanzaPeriodoLinea]]:
    """Snapshot inmutable del balance del periodo; devuelve cabecera y lineas.

    Lanza 409 `balanza_descuadrada` si `total_debe != total_haber`: un
    descuadre nunca llega a persistirse.
    """
    movimientos = await _movimientos(db, empresa_id, fecha_ini, fecha_fin)
    cuenta_ids = {account_id for _, account_id, _, _ in movimientos if account_id > 0}
    plan = await _datos_plan(db, empresa_id, cuenta_ids)

    lineas: list[BalanzaPeriodoLinea] = []
    total_debe = Decimal(0)
    total_haber = Decimal(0)
    resultado = Decimal(0)
    for codigo, account_id, debe, haber in movimientos:
        if debe == 0 and haber == 0:
            continue
        saldo = c4(debe - haber)
        total_debe += debe
        total_haber += haber
        if codigo[:1] in GRUPOS_GESTION:
            resultado = c4(resultado + saldo)
        meta = plan.get(account_id, {})
        balanza_id = uuid.uuid4()
        lineas.append(
            BalanzaPeriodoLinea(
                id=balanza_id,
                empresa_id=empresa_id,
                balanza_id=balanza_id,
                cuenta_id=account_id,
                codigo=codigo,
                nombre=str(meta.get("name") or codigo),
                nivel=int(meta.get("level") or len(codigo)),
                debe=debe,
                haber=haber,
                saldo=saldo,
            )
        )
    total_debe = c4(total_debe)
    total_haber = c4(total_haber)
    if total_debe != total_haber:
        raise error(
            "balanza_descuadrada",
            (
                f"El balance del periodo no cuadra: Debe {total_debe:0.4f} != "
                f"Haber {total_haber:0.4f}"
            ),
            409,
        )

    cabecera = BalanzaPeriodo(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        periodo_id=periodo_id,
        ejercicio=ejercicio,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        generado_por=actor,
        n_lineas=len(lineas),
        total_debe=total_debe,
        total_haber=total_haber,
        resultado_provisional=resultado,
        sha256=huella_snapshot(ejercicio, tipo, periodo, fecha_ini, fecha_fin, lineas, total_debe),
    )
    for linea in lineas:
        linea.balanza_id = cabecera.id
    return cabecera, lineas


def huella_snapshot(
    ejercicio: int,
    tipo: str,
    periodo: int,
    fecha_ini: date,
    fecha_fin: date,
    lineas: list[BalanzaPeriodoLinea],
    total_debe: Decimal,
) -> str:
    """SHA-256 canonico del contenido del snapshot (research D3).

    El canon ordena las lineas por codigo y concatena
    ``codigo|debe|haber|saldo`` con `\n`, de modo que el mismo contenido
    produce siempre la misma huella.
    """
    partes = [f"{ejercicio}|{tipo}|{periodo}|{fecha_ini.isoformat()}|{fecha_fin.isoformat()}"]
    for linea in sorted(lineas, key=lambda l: (l.codigo, l.cuenta_id)):
        partes.append(
            f"{linea.codigo}|{linea.debe:0.4f}|{linea.haber:0.4f}|{linea.saldo:0.4f}"
        )
    partes.append(f"TOTAL|{total_debe:0.4f}")
    return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()


async def _datos_plan(
    db: AsyncSession, empresa_id: int, cuenta_ids: set[int]
) -> dict[int, dict[str, Any]]:
    """Codigo/nombre/nivel del plan de la empresa para las cuentas del periodo."""
    if not cuenta_ids:
        return {}
    filas = (
        await db.execute(
            select(AccountPlan.id, AccountPlan.name, AccountPlan.level).where(
                AccountPlan.tenant_id == empresa_id,
                AccountPlan.id.in_(sorted(cuenta_ids)),
            )
        )
    ).all()
    return {int(ident): {"name": nombre, "level": nivel} for ident, nombre, nivel in filas}


async def persistir_balanza(
    db: AsyncSession,
    cabecera: BalanzaPeriodo,
    lineas: list[BalanzaPeriodoLinea],
) -> BalanzaPeriodo:
    """Inserta cabecera y lineas del snapshot; el orden importa por la FK."""
    db.add(cabecera)
    await db.flush()
    for linea in lineas:
        db.add(linea)
    await db.flush()
    return cabecera


async def leer_balanza(
    db: AsyncSession, empresa_id: int, periodo_id: uuid.UUID
) -> tuple[BalanzaPeriodo, list[BalanzaPeriodoLinea]] | None:
    """Cabecera y lineas del snapshot de un periodo; `None` si no hay cierre."""
    cabecera = await db.scalar(
        select(BalanzaPeriodo).where(
            BalanzaPeriodo.empresa_id == empresa_id,
            BalanzaPeriodo.periodo_id == periodo_id,
        )
    )
    if cabecera is None:
        return None
    lineas = (
        await db.scalars(
            select(BalanzaPeriodoLinea)
            .where(
                BalanzaPeriodoLinea.empresa_id == empresa_id,
                BalanzaPeriodoLinea.balanza_id == cabecera.id,
            )
            .order_by(BalanzaPeriodoLinea.codigo)
        )
    ).all()
    return cabecera, list(lineas)


__all__ = [
    "GRUPOS_GESTION",
    "LineaBalanza",
    "calcular_balanza_periodo",
    "huella_snapshot",
    "leer_balanza",
    "persistir_balanza",
]
