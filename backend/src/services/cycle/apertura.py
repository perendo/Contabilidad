"""Servicio de apertura del ejercicio (SPEC-009 US1/US2).

Toma los saldos de las cuentas patrimoniales (grupo 1-3 del PGC) del cierre
anterior, genera un asiento OPENING balanceado en el ejercicio siguiente y
reinicia la numeración desde 1 (FR-001/FR-003/FR-005). La corrección de una
apertura errónea es por anulación (OPENING_REVERSAL enlazado) y regeneración,
sin alterar asientos ya asentados (FR-006, constitución II).

Todo ocurre con `flush()` dentro del boundary ACID del llamante.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado
from services.audit.writer import audit_escribir
from services.cycle.validacion_previa import (
    CicloError,
    ContextoApertura,
    RangoEjercicio,
    apertura_vigente,
    validar_precondiciones_apertura,
)
from services.journal.sequence import next_numero

GRUPOS_PATRIMONIALES = ("1", "2", "3")


class CuentasPatrimonialesVaciasError(CicloError):
    status_code = 422
    code = "cuentas_patrimoniales_vacias"


class AsientoDesbalanceadoError(CicloError):
    status_code = 422
    code = "asiento_desbalanceado"


class CuentaNoExisteError(CicloError):
    status_code = 422
    code = "cuenta_no_existe"


async def _netos_por_cuenta(
    db: AsyncSession,
    empresa_id: int,
    rango: RangoEjercicio,
    excluir_entrada_id: uuid.UUID | None,
) -> list[tuple[str, str, Decimal]]:
    """Líneas (cuenta, lado D/H, importe) de las cuentas patrimoniales del cierre
    previo (grupos 1-3), excluyendo el asiento de cierre para conservar los
    saldos a aperturar (FR-003)."""
    query = select(JournalEntryLine.cuenta, JournalEntryLine.debe, JournalEntryLine.haber)
    if excluir_entrada_id is not None:
        query = query.where(JournalEntryLine.journal_entry_id != excluir_entrada_id)
    filas = (
        await db.execute(
            query.join(
                JournalEntry,
                (JournalEntryLine.journal_entry_id == JournalEntry.id)
                & (JournalEntryLine.empresa_id == JournalEntry.empresa_id),
            ).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.estado == JournalEntryEstado.POSTED,
                JournalEntry.fecha >= rango.date_start,
                JournalEntry.fecha <= rango.date_end,
            )
        )
    ).all()
    netos: dict[str, Decimal] = {}
    for cuenta, debe, haber in filas:
        netos[cuenta] = netos.get(cuenta, Decimal(0)) + debe - haber
    return [
        (cuenta, "D", neto) if neto > 0 else (cuenta, "H", -neto)
        for cuenta, neto in netos.items()
        if (neto != 0 and cuenta[:1] in GRUPOS_PATRIMONIALES)
    ]


async def _ids_por_codigo(db: AsyncSession, empresa_id: int) -> dict[str, int]:
    return {
        code: ident
        for code, ident in (
            await db.execute(
                select(AccountPlan.code, AccountPlan.id).where(
                    AccountPlan.tenant_id == empresa_id,
                    AccountPlan.is_active.is_(True),
                )
            )
        ).all()
    }


async def _publicar_apertura(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha: date,
    contexto: ContextoApertura,
    saldos: list[tuple[str, str, Decimal]],
    actor: str | None,
    cierre_entry_id: uuid.UUID | None = None,
) -> JournalEntry:
    ids = await _ids_por_codigo(db, empresa_id)
    if any(codigo not in ids for codigo, _, _ in saldos):
        raise CuentaNoExisteError(
            "Alguna cuenta patrimonial con saldo no existe en el plan contable"
        )

    debe_total = sum(importe for _, lado, importe in saldos if lado == "D")
    haber_total = sum(importe for _, lado, importe in saldos if lado == "H")
    if debe_total <= 0 or haber_total <= 0 or debe_total != haber_total:
        raise AsientoDesbalanceadoError(
            f"Asiento de apertura desbalanceado: Debe {debe_total} != Haber {haber_total}"
        )

    numero = await next_numero(db, empresa_id, contexto.destino.year)
    entrada = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=contexto.destino.year,
        fecha=fecha,
        tipo=JournalEntryTipo.OPENING,
        concepto=f"Apertura del ejercicio {contexto.destino.year}",
        estado=JournalEntryEstado.POSTED,
        numero_asiento=numero,
        referencia_cierre_id=cierre_entry_id,
        created_by=actor,
    )
    entrada.id = uuid.uuid4()
    db.add(entrada)
    await db.flush()

    for numero_linea, (codigo, lado, importe) in enumerate(sorted(saldos), start=1):
        db.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=entrada.id,
                account_id=ids[codigo],
                line_no=numero_linea,
                cuenta=codigo,
                debe=importe if lado == "D" else Decimal(0),
                haber=importe if lado == "H" else Decimal(0),
                descripcion="Asiento de apertura",
            )
        )
    await db.flush()

    destino = await db.scalar(
        select(EjercicioContable).where(
            EjercicioContable.empresa_id == empresa_id,
            EjercicioContable.ejercicio == contexto.destino.year,
        )
    )
    if destino is not None:
        destino.estado = EjercicioEstado.con_apertura
        destino.apertura_entry_id = entrada.id
        await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="APERTURA",
        entity="journal_entry",
        entity_id=str(entrada.id),
        payload={
            "ejercicio": contexto.destino.year,
            "numero": numero,
            "lineas": len(saldos),
            "importe_debe": f"{debe_total:0.4f}",
        },
    )
    await db.flush()
    return entrada


async def calcular_saldos_patrimoniales(
    db: AsyncSession,
    empresa_id: int,
    contexto: ContextoApertura,
    cierre_entry_id: uuid.UUID | None = None,
) -> list[tuple[str, str, Decimal]]:
    """Saldos a aperturar: cuentas 1-3 del cierre previo (FR-003)."""
    return await _netos_por_cuenta(
        db, empresa_id, contexto.previo, excluir_entrada_id=cierre_entry_id
    )


async def generar_asiento_apertura(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio_destino: int,
    actor: str | None = None,
) -> dict[str, Any]:
    contexto = await validar_precondiciones_apertura(
        db, empresa_id, ejercicio_destino
    )
    cierre_entry_id = await _cierre_del_previo(db, empresa_id, contexto.previo.year)
    saldos = await calcular_saldos_patrimoniales(
        db, empresa_id, contexto, cierre_entry_id=cierre_entry_id
    )
    if not saldos:
        raise CuentasPatrimonialesVaciasError(
            f"No hay cuentas patrimoniales con saldo para abrir {ejercicio_destino}"
        )
    fecha = contexto.destino.date_start
    cierre = cierre_entry_id
    entrada = await _publicar_apertura(
        db,
        empresa_id=empresa_id,
        fecha=fecha,
        contexto=contexto,
        saldos=saldos,
        actor=actor,
        cierre_entry_id=cierre,
    )
    return {
        "ejercicio": ejercicio_destino,
        "asiento_id": str(entrada.id),
        "numero_asiento": entrada.numero_asiento,
        "total_lineas": len(saldos),
        "importe_total_debe": f"{sum(i for _, lado, i in saldos if lado == 'D'):0.4f}",
        "estado": "con_apertura",
    }


async def _cierre_del_previo(
    db: AsyncSession, empresa_id: int, year: int
) -> uuid.UUID | None:
    from models.acct.fiscal_year import FiscalYear

    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == year
        )
    )
    if fy is not None and fy.cierre_entry_id is not None:
        return fy.cierre_entry_id
    return None


async def anular_apertura(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    actor: str | None = None,
) -> dict[str, Any]:
    """Revierte una apertura con un asiento OPENING_REVERSAL enlazado (FR-006)."""
    apertura = await apertura_vigente(db, empresa_id, ejercicio)

    lineas = (
        await db.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == apertura.id,
            )
        )
    ).all()
    reversal = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=apertura.fecha,
        tipo=JournalEntryTipo.OPENING_REVERSAL,
        concepto=f"Anulación apertura del ejercicio {ejercicio}",
        estado=JournalEntryEstado.POSTED,
        numero_asiento=await next_numero(db, empresa_id, ejercicio),
        original_id=apertura.id,
        created_by=actor,
    )
    reversal.id = uuid.uuid4()
    db.add(reversal)
    await db.flush()

    for numero_linea, linea in enumerate(lineas, start=1):
        db.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=reversal.id,
                account_id=linea.account_id,
                line_no=numero_linea,
                cuenta=linea.cuenta,
                debe=linea.haber,
                haber=linea.debe,
                descripcion="Anulación de apertura",
            )
        )
    await db.flush()

    destino = await db.scalar(
        select(EjercicioContable).where(
            EjercicioContable.empresa_id == empresa_id,
            EjercicioContable.ejercicio == ejercicio,
        )
    )
    if destino is not None:
        destino.estado = EjercicioEstado.abierto
        destino.apertura_reversal_entry_id = reversal.id
        await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="ANULAR_APERTURA",
        entity="journal_entry",
        entity_id=str(reversal.id),
        payload={
            "ejercicio": ejercicio,
            "original_id": str(apertura.id),
            "numero": reversal.numero_asiento,
        },
    )
    await db.flush()
    return {
        "ejercicio": ejercicio,
        "asiento_anulacion_id": str(reversal.id),
        "asiento_apertura_id": str(apertura.id),
        "estado": "apertura_anulada",
    }


async def regenerar_apertura(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    actor: str | None = None,
) -> dict[str, Any]:
    """Regenera la apertura tras anularla (nueva apertura con saldos recalculados)."""
    resultado = await generar_asiento_apertura(
        db, empresa_id=empresa_id, ejercicio_destino=ejercicio, actor=actor
    )
    resultado["regenerada"] = True
    return resultado