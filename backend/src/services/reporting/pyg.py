"""Cuenta de Perdidas y Ganancias (SPEC-010 T020).

Agrega ingresos (grupo 7) y gastos (grupo 6) del ejercicio excluyendo los
asientos de regularizacion y cierre, de modo que el resultado de gestion se
reconstruye aunque el ejercicio ya este cerrado (FR-002). Lo compara con el
resultado reconocido en la cuenta 129 por el asiento de regularizacion
(SPEC-004) y advierte con `descuadre_cierre` si difiere (FR-006).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntryLine
from models.reporting.configuracion import InformeTipo
from services.reporting.agrupacion import agrupar, cargar_reglas
from services.reporting.saldos import (
    error,
    fiscal_year,
    netos_por_cuenta,
    resultado_de_gestion,
)
from services.reports.common import cuantizar, fmt

PREFIJO_RESULTADO = "129"


async def _resultado_regularizacion(
    db: AsyncSession, *, empresa_id: int, entry_id
) -> Decimal:
    filas = (
        await db.execute(
            select(JournalEntryLine.cuenta, JournalEntryLine.debe, JournalEntryLine.haber)
            .where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == entry_id,
                JournalEntryLine.cuenta.like(f"{PREFIJO_RESULTADO}%"),
            )
        )
    ).all()
    neto = sum((debe - haber for _, debe, haber in filas), Decimal(0))
    return -neto


async def generar_pyg(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    modo: str = "provisional",
) -> dict:
    if modo not in ("provisional", "oficial"):
        raise error("modo_invalido", "modo debe ser provisional u oficial")

    netos = await netos_por_cuenta(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        excluir_cierre=True,
        excluir_regularizacion=True,
    )
    gastos = sum((n for c, n in netos.items() if c[:1] == "6"), Decimal(0))
    ingresos = -sum((n for c, n in netos.items() if c[:1] == "7"), Decimal(0))
    resultado = ingresos - gastos

    reglas = await cargar_reglas(
        db, empresa_id=empresa_id, ejercicio=ejercicio, informe_tipo=InformeTipo.PYG
    )
    gestion = {c: n for c, n in netos.items() if c[:1] in ("6", "7")}
    masas, hay_otros = agrupar(gestion, reglas)
    partidas = [
        {
            "grupo": masa["codigo"],
            "nombre": masa["nombre"],
            "importe": fmt(-masa["importe"] if masa["codigo"][:1] == "7" else masa["importe"]),
        }
        for masa in sorted(masas.values(), key=lambda m: m["codigo"])
    ]

    fy = await fiscal_year(db, empresa_id, ejercicio)
    resultado_cierre: Decimal | None = None
    if fy is not None and fy.regularizacion_entry_id is not None:
        resultado_cierre = await _resultado_regularizacion(
            db, empresa_id=empresa_id, entry_id=fy.regularizacion_entry_id
        )
    coincide = (
        resultado_cierre is not None
        and cuantizar(resultado) == cuantizar(resultado_cierre)
    )
    if modo == "oficial" and not coincide:
        raise error(
            "descuadre_cierre",
            "El resultado de la PyG no coincide con la regularizacion del cierre",
        )

    return {
        "ejercicio": ejercicio,
        "modo": modo,
        "total_ingresos": fmt(ingresos),
        "total_gastos": fmt(gastos),
        "resultado_ejercicio": fmt(resultado),
        "resultado_cierre": fmt(resultado_cierre) if resultado_cierre is not None else None,
        "coincide_cierre": coincide,
        "descuadre_cierre": not coincide,
        "hay_cuentas_sin_agrupar": hay_otros,
        "partidas": partidas,
        "resultado_gestion": fmt(resultado_de_gestion(netos)),
    }