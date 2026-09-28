"""Seguimiento presupuesto vs real (SPEC-026 US2, FR-002/SC-002).

El real se agrega del diario de SPEC-002 en modo **lectura** (`SUM(Debe)` para
el grupo 6, `SUM(Haber)` para el grupo 7, research.md D2/D3), el presupuesto se
combina con el y se calculan desviacion absoluta y relativa. Las combinaciones
que tienen real distinto de cero pero ningun presupuesto se incluyen con
`sin_presupuesto = true` y desviacion igual al real (D4).
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.budget.periodo_seguimiento import PeriodoSeguimiento
from models.budget.presupuesto import Presupuesto
from models.costcenters.centro_coste import CentroCoste
from services.budget.errores import error
from services.budget.periodos import obtener_periodo
from services.budget.utils import (
    c4,
    calcular_desviacion_absoluta,
    calcular_desviacion_relativa,
    calcular_real,
    cuenta_grupo,
)

__all__ = [
    "GRUPOS_PRESUPUESTABLES",
    "FilaDesviacion",
    "calcular_desviaciones",
    "desviaciones_de_periodo",
    "obtener_periodo_actual",
    "rango_mes",
]

ClaveCombinacion = tuple[int, uuid.UUID | None]

#: Solo los grupos 6 (gasto) y 7 (ingreso) son presupuestables; las cuentas de
#: balance se excluyen del seguimiento para que los totales sean comparables.
GRUPOS_PRESUPUESTABLES: tuple[int, ...] = (6, 7)


@dataclass
class FilaDesviacion:
    """Una combinacion cuenta-centro con su cotejo presupuesto/real."""

    cuenta_id: int
    codigo_cuenta: str = ""
    nombre_cuenta: str = ""
    centro_coste_id: uuid.UUID | None = None
    nombre_centro: str | None = None
    importe_presupuestado: Decimal = field(default_factory=lambda: Decimal("0.0000"))
    importe_real: Decimal = field(default_factory=lambda: Decimal("0.0000"))
    desviacion_absoluta: Decimal = field(default_factory=lambda: Decimal("0.0000"))
    desviacion_relativa: Decimal | None = None
    sin_presupuesto: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "cuenta_id": self.cuenta_id,
            "codigo_cuenta": self.codigo_cuenta,
            "nombre_cuenta": self.nombre_cuenta,
            "centro_coste_id": str(self.centro_coste_id)
            if self.centro_coste_id
            else None,
            "nombre_centro": self.nombre_centro,
            "importe_presupuestado": f"{c4(self.importe_presupuestado):0.4f}",
            "importe_real": f"{c4(self.importe_real):0.4f}",
            "desviacion_absoluta": f"{c4(self.desviacion_absoluta):0.4f}",
            "desviacion_relativa": None
            if self.desviacion_relativa is None
            else f"{c4(self.desviacion_relativa):0.4f}",
            "sin_presupuesto": self.sin_presupuesto,
        }


def rango_mes(ejercicio: int, mes: int) -> tuple[date, date]:
    """Rango [inicio, fin] ambos incluidos del mes 1-12 dentro del ejercicio."""
    if not 1 <= mes <= 12:
        raise error("mes_invalido", f"Mes {mes} fuera de rango (1-12)", 422)
    ultimo = calendar.monthrange(ejercicio, mes)[1]
    return date(ejercicio, mes, 1), date(ejercicio, mes, ultimo)


async def obtener_periodo_actual(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> dict[str, Any]:
    """Estado del periodo de seguimiento del ejercicio (T023, 200 con nulls)."""
    periodo = await db.scalar(
        select(PeriodoSeguimiento)
        .where(
            PeriodoSeguimiento.empresa_id == empresa_id,
            PeriodoSeguimiento.ejercicio == ejercicio,
        )
        .order_by(PeriodoSeguimiento.numero_periodo.desc())
        .limit(1)
    )
    if periodo is None:
        return {
            "periodo_id": None,
            "ejercicio": ejercicio,
            "numero_periodo": None,
            "estado": "sin_periodo",
            "fecha_inicio": None,
            "fecha_fin": None,
            "fecha_cierre": None,
            "cerrado_por": None,
            "desviaciones_registradas": 0,
        }
    return {
        "periodo_id": str(periodo.id),
        "ejercicio": ejercicio,
        "numero_periodo": int(periodo.numero_periodo),
        "estado": periodo.estado.value,
        "fecha_inicio": periodo.fecha_inicio.isoformat(),
        "fecha_fin": periodo.fecha_fin.isoformat(),
        "fecha_cierre": periodo.fecha_cierre.isoformat() if periodo.fecha_cierre else None,
        "cerrado_por": periodo.cerrado_por,
        "desviaciones_registradas": int(periodo.desviaciones_registradas),
    }


async def _reales(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha_desde: date,
    fecha_hasta: date,
    cuenta_id: int | None = None,
    centro_coste_id: uuid.UUID | None = None,
    grupos: tuple[int, ...] = GRUPOS_PRESUPUESTABLES,
) -> dict[ClaveCombinacion, Decimal]:
    """Real del diario por combinacion (cuenta, centro) en el rango de fechas.

    Solo asientos `POSTED` de la empresa activa (constitucion I: el diario ya
    valida `SUM(Debe) == SUM(Haber)`; aqui solo se agrega en lectura) y solo
    cuentas de gasto (6) e ingreso (7), que son las presupuestables: incluir
    las contrapartes de balance haria que los totales del informe se anulasen.
    """
    filtros: list[Any] = [
        JournalEntryLine.empresa_id == empresa_id,
        JournalEntry.empresa_id == empresa_id,
        JournalEntry.estado == JournalEntryEstado.POSTED,
        JournalEntry.fecha >= fecha_desde,
        JournalEntry.fecha <= fecha_hasta,
        JournalEntryLine.account_id.is_not(None),
    ]
    if cuenta_id is not None:
        filtros.append(JournalEntryLine.account_id == cuenta_id)
    if centro_coste_id is not None:
        filtros.append(JournalEntryLine.centro_coste_id == centro_coste_id)
    filas = (
        await db.execute(
            select(
                JournalEntryLine.account_id,
                JournalEntryLine.centro_coste_id,
                func.sum(JournalEntryLine.debe),
                func.sum(JournalEntryLine.haber),
            )
            .join(
                JournalEntry,
                (JournalEntry.id == JournalEntryLine.journal_entry_id)
                & (JournalEntry.empresa_id == JournalEntryLine.empresa_id),
            )
            .where(*filtros)
            .group_by(JournalEntryLine.account_id, JournalEntryLine.centro_coste_id)
        )
    ).all()
    grupos_por_cuenta = await _grupos(db, empresa_id, {int(f[0]) for f in filas})
    reales: dict[ClaveCombinacion, Decimal] = {}
    for cuenta, centro, debe, haber in filas:
        grupo = grupos_por_cuenta.get(int(cuenta), cuenta_grupo(str(cuenta)))
        if grupo not in grupos:
            continue
        real = calcular_real(grupo, debe, haber)
        if real == 0:
            continue
        reales[(int(cuenta), uuid.UUID(str(centro)) if centro else None)] = real
    return reales


async def _grupos(
    db: AsyncSession, empresa_id: int, cuenta_ids: set[int]
) -> dict[int, int]:
    """Grupo PGC (primer digito del codigo) por id de cuenta de la empresa."""
    if not cuenta_ids:
        return {}
    filas = (
        await db.execute(
            select(AccountPlan.id, AccountPlan.code).where(
                AccountPlan.tenant_id == empresa_id,
                AccountPlan.id.in_(cuenta_ids),
            )
        )
    ).all()
    return {int(cuenta): cuenta_grupo(codigo) for cuenta, codigo in filas}


async def _nombres(
    db: AsyncSession, empresa_id: int, cuenta_ids: set[int], centro_ids: set[str]
) -> tuple[dict[int, tuple[str, str]], dict[str, str]]:
    cuentas: dict[int, tuple[str, str]] = {}
    if cuenta_ids:
        for cuenta_id, codigo, nombre in (
            await db.execute(
                select(AccountPlan.id, AccountPlan.code, AccountPlan.name).where(
                    AccountPlan.tenant_id == empresa_id,
                    AccountPlan.id.in_(cuenta_ids),
                )
            )
        ).all():
            cuentas[int(cuenta_id)] = (codigo, nombre)
    centros: dict[str, str] = {}
    if centro_ids:
        for centro_id, codigo, nombre in (
            await db.execute(
                select(CentroCoste.id, CentroCoste.codigo, CentroCoste.nombre).where(
                    CentroCoste.empresa_id == empresa_id,
                    CentroCoste.id.in_([uuid.UUID(c) for c in centro_ids]),
                )
            )
        ).all():
            centros[str(centro_id)] = f"{codigo} · {nombre}"
    return cuentas, centros


async def calcular_desviaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    cuenta_id: int | None = None,
    centro_coste_id: str | None = None,
    mes: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Desviacion por cuenta/centro para el ejercicio (T022).

    Cuando se pasa `mes`, el real se limita al mes pero el presupuesto sigue
    siendo el anual (research.md D1: el presupuesto no se desglosa; el informe
    desglosa el real acumulado). SC-002: el 100 % de las desviaciones cuadran
    con `real - presupuesto`.
    """
    if mes is not None:
        fecha_desde, fecha_hasta = rango_mes(ejercicio, mes)
    inicio = fecha_desde or date(ejercicio, 1, 1)
    fin = fecha_hasta or date(ejercicio, 12, 31)
    centro = uuid.UUID(centro_coste_id) if centro_coste_id else None

    filtros_presupuesto: list[Any] = [
        Presupuesto.empresa_id == empresa_id, Presupuesto.ejercicio == ejercicio
    ]
    if cuenta_id is not None:
        filtros_presupuesto.append(Presupuesto.cuenta_id == cuenta_id)
    if centro is not None:
        filtros_presupuesto.append(Presupuesto.centro_coste_id == centro)
    elif centro_coste_id is not None:  # pragma: no cover - defensivo
        raise error("centro_invalido", "centro_coste_id invalido", 422)

    presupuestos: dict[ClaveCombinacion, Decimal] = {}
    for cuenta, centro_id, importe in (
        await db.execute(
            select(Presupuesto.cuenta_id, Presupuesto.centro_coste_id, Presupuesto.importe)
            .where(*filtros_presupuesto)
        )
    ).all():
        clave = (int(cuenta), uuid.UUID(str(centro_id)) if centro_id else None)
        presupuestos[clave] = presupuestos.get(clave, Decimal(0)) + Decimal(importe or 0)

    reales = await _reales(
        db,
        empresa_id=empresa_id,
        fecha_desde=inicio,
        fecha_hasta=fin,
        cuenta_id=cuenta_id,
        centro_coste_id=centro,
    )

    filas: list[FilaDesviacion] = []
    for clave in sorted(
        set(presupuestos) | set(reales), key=lambda k: (k[0], str(k[1] or ""))
    ):
        cuenta, centro_id = clave
        presupuestado = presupuestos.get(clave, Decimal(0))
        real = reales.get(clave, Decimal(0))
        sin_presupuesto = clave not in presupuestos
        filas.append(
            FilaDesviacion(
                cuenta_id=cuenta,
                codigo_cuenta="",
                centro_coste_id=centro_id,
                importe_presupuestado=c4(presupuestado),
                importe_real=c4(real),
                desviacion_absoluta=calcular_desviacion_absoluta(real, presupuestado),
                desviacion_relativa=calcular_desviacion_relativa(real, presupuestado),
                sin_presupuesto=sin_presupuesto,
            )
        )
    cuentas, centros = await _nombres(
        db,
        empresa_id,
        {f.cuenta_id for f in filas},
        {str(f.centro_coste_id) for f in filas if f.centro_coste_id is not None},
    )
    for fila in filas:
        codigo, nombre = cuentas.get(fila.cuenta_id, ("", ""))
        fila.codigo_cuenta = codigo
        fila.nombre_cuenta = nombre
        if fila.centro_coste_id is not None:
            fila.nombre_centro = centros.get(str(fila.centro_coste_id))

    filas.sort(key=lambda f: (f.codigo_cuenta, f.nombre_centro or ""))
    total = len(filas)
    inicio_pagina = (max(page, 1) - 1) * max(page_size, 1)
    return {
        "ejercicio": ejercicio,
        "desde": inicio.isoformat(),
        "hasta": fin.isoformat(),
        "items": [f.as_dict() for f in filas[inicio_pagina : inicio_pagina + max(page_size, 1)]],
        "total": total,
    }


async def desviaciones_de_periodo(
    db: AsyncSession, *, empresa_id: int, periodo_id: uuid.UUID | str
) -> list[FilaDesviacion]:
    """Desviaciones del rango de fechas del periodo, sin paginar (cierre T032)."""
    periodo = await obtener_periodo(db, empresa_id, periodo_id)
    if periodo is None:
        raise error(
            "periodo_no_encontrado",
            "Periodo de seguimiento inexistente en la empresa activa",
            404,
        )
    resultado = await calcular_desviaciones(
        db,
        empresa_id=empresa_id,
        ejercicio=periodo.ejercicio,
        fecha_desde=periodo.fecha_inicio,
        fecha_hasta=periodo.fecha_fin,
        page=1,
        page_size=100_000,
    )
    return [
        FilaDesviacion(
            cuenta_id=item["cuenta_id"],
            codigo_cuenta=item["codigo_cuenta"],
            nombre_cuenta=item["nombre_cuenta"],
            centro_coste_id=uuid.UUID(item["centro_coste_id"])
            if item["centro_coste_id"]
            else None,
            nombre_centro=item["nombre_centro"],
            importe_presupuestado=Decimal(item["importe_presupuestado"]),
            importe_real=Decimal(item["importe_real"]),
            desviacion_absoluta=Decimal(item["desviacion_absoluta"]),
            desviacion_relativa=None
            if item["desviacion_relativa"] is None
            else Decimal(item["desviacion_relativa"]),
            sin_presupuesto=item["sin_presupuesto"],
        )
        for item in resultado["items"]
    ]
