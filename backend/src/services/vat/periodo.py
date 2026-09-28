"""Periodos fiscales (SPEC-012 T001/T005).

Define el rango de fechas de cada trimestre/mes y persiste ``PeriodoFiscal``
para trazar el estado (pendiente → exportado). Los limites se validan en
backend (409 ``periodo_fuera_de_rango``).
"""

from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal.periodo_fiscal import (
    EstadoPeriodo,
    PeriodoFiscal,
    TipoPeriodo,
)
from services.vat.errores import error

TRIMESTRES = 4
MESES = 12


def rango_periodo(
    ejercicio: int, tipo_periodo: TipoPeriodo | str, numero: int
) -> tuple[date, date]:
    tipo = TipoPeriodo(tipo_periodo)
    if tipo == TipoPeriodo.TRIMESTRE:
        if not (1 <= numero <= TRIMESTRES):
            raise error("periodo_fuera_de_rango", "El trimestre debe estar entre 1 y 4")
        mes_ini = (numero - 1) * 3 + 1
        mes_fin = mes_ini + 2
    else:
        if not (1 <= numero <= MESES):
            raise error("periodo_fuera_de_rango", "El mes debe estar entre 1 y 12")
        mes_ini = mes_fin = numero
    inicio = date(ejercicio, mes_ini, 1)
    ultimo = calendar.monthrange(ejercicio, mes_fin)[1]
    fin = date(ejercicio, mes_fin, ultimo)
    return inicio, fin


def etiqueta_periodo(tipo_periodo: TipoPeriodo | str, numero: int) -> str:
    tipo = TipoPeriodo(tipo_periodo)
    rango = TRIMESTRES if tipo == TipoPeriodo.TRIMESTRE else MESES
    if not (1 <= numero <= rango):
        raise error("periodo_fuera_de_rango", "Numero de periodo fuera de rango")
    return f"{numero:02d}"


async def obtener_o_crear_periodo(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipo_periodo: TipoPeriodo | str,
    numero: int,
) -> PeriodoFiscal:
    tipo = TipoPeriodo(tipo_periodo)
    periodo = await db.scalar(
        select(PeriodoFiscal).where(
            PeriodoFiscal.empresa_id == empresa_id,
            PeriodoFiscal.ejercicio == ejercicio,
            PeriodoFiscal.tipo_periodo == tipo,
            PeriodoFiscal.numero_periodo == numero,
        )
    )
    if periodo is not None:
        return periodo
    inicio, fin = rango_periodo(ejercicio, tipo, numero)
    periodo = PeriodoFiscal(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        tipo_periodo=tipo,
        numero_periodo=numero,
        fecha_inicio=inicio,
        fecha_fin=fin,
        estado=EstadoPeriodo.pendiente,
    )
    db.add(periodo)
    await db.flush()
    return periodo


async def marcar_estado(
    db: AsyncSession, *, periodo: PeriodoFiscal, estado: EstadoPeriodo
) -> PeriodoFiscal:
    periodo.estado = estado
    await db.flush()
    return periodo