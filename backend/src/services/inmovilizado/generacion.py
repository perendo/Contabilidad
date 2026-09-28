"""Generación y reapertura de amortizaciones (SPEC-014 US2).

``generar_amortizacion`` recorre los activos en uso con fila de plan pendiente
para el período y registra, por activo, un asiento GENERAL balanceado
(Debe 681 | Haber 281) vía el motor multilínea de SPEC-002/006 y una fila
``AmortizacionGenerada`` idempotente (índice único parcial por
activo+periodo vigente). ``reabrir_amortizacion`` crea su propio REVERSAL con
las líneas invertidas sin tocar el asiento original (constitución II; a
diferencia de ``reversal.anular`` el original permanece POSTED) y devuelve la
fila del plan a pendiente para volver a generarla.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.inmovilizado.activo import ActivoInmovilizado, EstadoActivo
from models.inmovilizado.amortizacion_generada import AmortizacionGenerada
from models.inmovilizado.plan_amortizacion import EstadoPlan, PlanAmortizacion
from services.audit.writer import audit_escribir
from services.inmovilizado.errores import error
from services.journal.motor import crear_asiento_multilinea
from services.journal.sequence import next_numero


async def _ejercicio_abierto(db: AsyncSession, empresa_id: int, anio: int) -> None:
    fy = await db.scalar(
        select(FiscalYear).where(FiscalYear.empresa_id == empresa_id, FiscalYear.year == anio)
    )
    if fy is not None and fy.is_closed:
        raise error("ejercicio_cerrado", f"El ejercicio {anio} está cerrado", 409)


def _fin_mes(ejercicio: int, periodo: int) -> date:
    return date(ejercicio, periodo, calendar.monthrange(ejercicio, periodo)[1])


async def _codigo_cuenta(db: AsyncSession, cuenta_id: int | None) -> str:
    if cuenta_id is None:
        raise error("cuenta_no_encontrada", "El activo no tiene cuenta asociada")
    cuenta = await db.scalar(select(AccountPlan).where(AccountPlan.id == cuenta_id))
    if cuenta is None:
        raise error("cuenta_no_encontrada", "No existe la cuenta asociada al activo")
    return cuenta.code


async def generar_amortizacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    periodo: int,
    actor: str | None = None,
) -> dict:
    if not 1 <= periodo <= 12:
        raise error("periodo_invalido", "periodo debe estar entre 1 y 12")
    await _ejercicio_abierto(db, empresa_id, ejercicio)

    plan_rows = (
        await db.scalars(
            select(PlanAmortizacion)
            .where(
                PlanAmortizacion.empresa_id == empresa_id,
                PlanAmortizacion.ejercicio == ejercicio,
                PlanAmortizacion.periodo == periodo,
                PlanAmortizacion.estado == EstadoPlan.pendiente,
            )
            .order_by(PlanAmortizacion.activo_id)
        )
    ).all()
    plan_rows = list(plan_rows)

    if not plan_rows:
        raise error(
            "periodo_ya_amortizado",
            f"Nada que amortizar en {ejercicio}-{periodo}: el período ya está generado",
            409,
        )

    activos = {
        a.id: a
        for a in (
            await db.scalars(
                select(ActivoInmovilizado).where(
                    ActivoInmovilizado.empresa_id == empresa_id,
                    ActivoInmovilizado.estado == EstadoActivo.en_uso,
                )
            )
        ).all()
    }

    ya_generadas: set[tuple[uuid.UUID, int]] = set()
    registros = (
        await db.scalars(
            select(AmortizacionGenerada).where(
                AmortizacionGenerada.empresa_id == empresa_id,
                AmortizacionGenerada.ejercicio == ejercicio,
                AmortizacionGenerada.periodo == periodo,
                AmortizacionGenerada.reabierta.is_(False),
            )
        )
    ).all()
    ya_generadas = {(r.activo_id, r.periodo) for r in registros}

    generadas: list[dict] = []
    omitidos: list[dict] = []
    for fila in plan_rows:
        activo = activos.get(fila.activo_id)
        if activo is None or fila.cuota <= 0:
            omitidos.append(
                {
                    "activo_id": str(fila.activo_id),
                    "motivo": "sin_cuota",
                    "detalle": "El plan no prevé cuota para este período",
                }
            )
            continue
        if (fila.activo_id, fila.periodo) in ya_generadas:
            omitidos.append(
                {
                    "activo_id": str(fila.activo_id),
                    "motivo": "periodo_ya_amortizado",
                    "detalle": f"Ya existe amortización generada para {ejercicio}-{periodo}",
                }
            )
            continue

        fecha = _fin_mes(ejercicio, periodo)
        cuenta_gasto = await _codigo_cuenta(db, activo.cuenta_gasto_id)
        cuenta_acumulada = await _codigo_cuenta(db, activo.cuenta_acumulada_id)
        concepto = (
            f"Amortización {ejercicio:04d}-{periodo:02d} · {activo.numero_activo}"
        )
        asiento = await crear_asiento_multilinea(
            db,
            empresa_id=empresa_id,
            fecha=fecha,
            concepto=concepto,
            lineas=[
                {"cuenta": cuenta_gasto, "debe": f"{fila.cuota:0.4f}", "haber": "0.0000", "detalle": concepto},
                {"cuenta": cuenta_acumulada, "haber": f"{fila.cuota:0.4f}", "debe": "0.0000", "detalle": concepto},
            ],
            actor=actor,
        )

        previa = await db.scalar(
            select(AmortizacionGenerada)
            .where(
                AmortizacionGenerada.empresa_id == empresa_id,
                AmortizacionGenerada.activo_id == activo.id,
                AmortizacionGenerada.ejercicio == ejercicio,
                AmortizacionGenerada.periodo == periodo,
                AmortizacionGenerada.reabierta.is_(True),
            )
            .order_by(AmortizacionGenerada.created_at.desc())
        )
        generada = AmortizacionGenerada(
            empresa_id=empresa_id,
            activo_id=activo.id,
            ejercicio=ejercicio,
            periodo=periodo,
            asiento_id=asiento.id,
            cuota=fila.cuota,
            reapertura_de=previa.id if previa is not None else None,
        )
        db.add(generada)
        fila.estado = EstadoPlan.amortizado
        await db.flush()

        await audit_escribir(
            db,
            empresa_id=empresa_id,
            actor=actor or "system",
            action="GENERAR_AMORTIZACION",
            entity="amortizacion_generada",
            entity_id=str(generada.id),
            payload={
                "activo_id": str(activo.id),
                "periodo": periodo,
                "ejercicio": ejercicio,
                "asiento_id": str(asiento.id),
                "cuota": f"{fila.cuota:0.4f}",
            },
        )
        await db.flush()

        generadas.append(
            {
                "activo_id": str(activo.id),
                "asiento_id": str(asiento.id),
                "generada_id": str(generada.id),
                "numero_asiento": asiento.numero_asiento,
                "cuota": f"{fila.cuota:0.4f}",
            }
        )

    return {
        "ejercicio": ejercicio,
        "periodo": periodo,
        "generadas": generadas,
        "omitidos": omitidos,
    }


async def reabrir_amortizacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    amortizacion_id: uuid.UUID,
    actor: str | None = None,
) -> dict:
    generada = await db.scalar(
        select(AmortizacionGenerada).where(
            AmortizacionGenerada.empresa_id == empresa_id,
            AmortizacionGenerada.id == amortizacion_id,
        )
    )
    if generada is None:
        raise error("amortizacion_no_encontrada", "Amortización inexistente en la empresa activa", 404)
    if generada.reabierta:
        raise error("amortizacion_ya_reabierta", "Esta amortización ya fue reabierta", 409)

    anual = generada.ejercicio
    await _ejercicio_abierto(db, empresa_id, anual)

    original = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.id == generada.asiento_id,
        )
    )
    if original is None:
        raise error("asiento_no_encontrado", "No existe el asiento de la amortización", 404)

    lineas_orig = (
        await db.scalars(
            select(JournalEntryLine)
            .where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == original.id,
            )
            .order_by(JournalEntryLine.line_no)
        )
    ).all()
    lineas_orig = list(lineas_orig)
    if not lineas_orig:
        raise error("lineas_insuficientes", "El asiento original no tiene líneas")

    fecha = _fin_mes(anual, generada.periodo)
    numero = await next_numero(db, empresa_id, anual)

    reversal = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=anual,
        fecha=fecha,
        tipo=JournalEntryTipo.REVERSAL,
        concepto=f"Reapertura de amortización {str(generada.id)[:8]} · asiento {original.numero_asiento}",
        estado=JournalEntryEstado.POSTED,
        numero_asiento=numero,
        original_id=original.id,
        created_by=actor,
    )
    if reversal.id is None:
        reversal.id = uuid.uuid4()
    db.add(reversal)
    await db.flush()

    for i, linea in enumerate(lineas_orig, start=1):
        db.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=reversal.id,
                account_id=linea.account_id,
                line_no=i,
                cuenta=linea.cuenta,
                debe=linea.haber,
                haber=linea.debe,
                descripcion=linea.descripcion,
            )
        )
    await db.flush()

    plan_row = await db.scalar(
        select(PlanAmortizacion).where(
            PlanAmortizacion.empresa_id == empresa_id,
            PlanAmortizacion.activo_id == generada.activo_id,
            PlanAmortizacion.ejercicio == generada.ejercicio,
            PlanAmortizacion.periodo == generada.periodo,
        )
    )
    if plan_row is not None:
        plan_row.estado = EstadoPlan.pendiente

    generada.reabierta = True
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="REABRIR_AMORTIZACION",
        entity="amortizacion_generada",
        entity_id=str(generada.id),
        payload={
            "asiento_id": str(original.id),
            "reversal_id": str(reversal.id),
            "numero_reversal": numero,
            "activo_id": str(generada.activo_id),
            "periodo": generada.periodo,
            "ejercicio": generada.ejercicio,
        },
    )
    await db.flush()

    return {
        "amortizacion_id": str(generada.id),
        "asiento_original_id": str(original.id),
        "asiento_reapertura_id": str(reversal.id),
        "numero_reversal": numero,
        "reabierta": True,
        "cuota": f"{generada.cuota:0.4f}",
    }


async def listar_amortizaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    activo_id: uuid.UUID | None = None,
    ejercicio: int | None = None,
    periodo: int | None = None,
    page: int = 1,
    page_size: int = 40,
) -> dict:
    filtros = [AmortizacionGenerada.empresa_id == empresa_id]
    if activo_id is not None:
        filtros.append(AmortizacionGenerada.activo_id == activo_id)
    if ejercicio is not None:
        filtros.append(AmortizacionGenerada.ejercicio == ejercicio)
    if periodo is not None:
        filtros.append(AmortizacionGenerada.periodo == periodo)

    total = await db.scalar(
        select(func.count())
        .select_from(AmortizacionGenerada)
        .where(*filtros)
    )
    registros = (
        await db.scalars(
            select(AmortizacionGenerada)
            .where(*filtros)
            .order_by(
                AmortizacionGenerada.ejercicio, AmortizacionGenerada.periodo, AmortizacionGenerada.created_at
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    registros = list(registros)

    items = [
        {
            "id": str(r.id),
            "activo_id": str(r.activo_id),
            "ejercicio": r.ejercicio,
            "periodo": r.periodo,
            "asiento_id": str(r.asiento_id) if r.asiento_id else None,
            "cuota": f"{r.cuota:0.4f}",
            "reabierta": r.reabierta,
            "reapertura_de": str(r.reapertura_de) if r.reapertura_de else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in registros
    ]
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


__all__ = ["generar_amortizacion", "listar_amortizaciones", "reabrir_amortizacion"]