"""Informe de desviacion acumulada (SPEC-026 US3, FR-003/T031).

Consolida las desviaciones de `desviaciones.calcular_desviaciones` con totales
globales y subtotales por centro, y las exporta a JSON paginado (D6). Cuando
el periodo ya esta cerrado, el informe puede servirse desde el snapshot
inmutable `Desviacion` en lugar de recalcular.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.budget.desviacion import Desviacion
from models.costcenters.centro_coste import CentroCoste
from services.budget.desviaciones import calcular_desviaciones
from services.budget.utils import c4

__all__ = ["filas_desde_snapshot", "generar_informe_desviacion"]


def _subtotales(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Subtotales por centro de coste con `Decimal` a 4 decimales."""
    acumulado: dict[str | None, dict[str, Any]] = {}
    for item in items:
        clave = item["centro_coste_id"]
        fila = acumulado.setdefault(
            clave,
            {
                "centro_coste_id": clave,
                "nombre_centro": item["nombre_centro"],
                "importe_presupuestado": Decimal("0.0000"),
                "importe_real": Decimal("0.0000"),
                "desviacion_absoluta": Decimal("0.0000"),
                "lineas": 0,
            },
        )
        fila["importe_presupuestado"] += Decimal(item["importe_presupuestado"])
        fila["importe_real"] += Decimal(item["importe_real"])
        fila["desviacion_absoluta"] += Decimal(item["desviacion_absoluta"])
        fila["lineas"] += 1
    return [
        {
            "centro_coste_id": fila["centro_coste_id"],
            "nombre_centro": fila["nombre_centro"] or "Sin centro",
            "importe_presupuestado": f"{c4(fila['importe_presupuestado']):0.4f}",
            "importe_real": f"{c4(fila['importe_real']):0.4f}",
            "desviacion_absoluta": f"{c4(fila['desviacion_absoluta']):0.4f}",
            "lineas": fila["lineas"],
        }
        for fila in sorted(
            acumulado.values(), key=lambda f: (f["nombre_centro"] or "", str(f["centro_coste_id"]))
        )
    ]


async def filas_desde_snapshot(
    db: AsyncSession, *, empresa_id: int, periodo_id: uuid.UUID | str
) -> list[dict[str, Any]]:
    """Snapshot `Desviacion` del periodo ya cerrado, en formato de item."""
    filas = (
        await db.scalars(
            select(Desviacion).where(
                Desviacion.empresa_id == empresa_id,
                Desviacion.periodo_id == uuid.UUID(str(periodo_id)),
            )
        )
    ).all()
    if not filas:
        return []
    from models.acct.account_plan import AccountPlan

    cuentas = {
        int(cuenta): (codigo, nombre)
        for cuenta, codigo, nombre in (
            await db.execute(
                select(AccountPlan.id, AccountPlan.code, AccountPlan.name).where(
                    AccountPlan.tenant_id == empresa_id,
                    AccountPlan.id.in_({f.cuenta_id for f in filas}),
                )
            )
        ).all()
    }
    centros = {
        str(centro_id): f"{codigo} · {nombre}"
        for centro_id, codigo, nombre in (
            await db.execute(
                select(CentroCoste.id, CentroCoste.codigo, CentroCoste.nombre).where(
                    CentroCoste.empresa_id == empresa_id,
                    CentroCoste.id.in_(
                        [f.centro_coste_id for f in filas if f.centro_coste_id is not None]
                    ),
                )
            )
        ).all()
    } if any(f.centro_coste_id is not None for f in filas) else {}
    return [
        {
            "cuenta_id": fila.cuenta_id,
            "codigo_cuenta": cuentas.get(fila.cuenta_id, ("", ""))[0],
            "nombre_cuenta": cuentas.get(fila.cuenta_id, ("", ""))[1],
            "centro_coste_id": str(fila.centro_coste_id) if fila.centro_coste_id else None,
            "nombre_centro": centros.get(str(fila.centro_coste_id))
            if fila.centro_coste_id
            else None,
            "importe_presupuestado": f"{c4(fila.importe_presupuestado):0.4f}",
            "importe_real": f"{c4(fila.importe_real):0.4f}",
            "desviacion_absoluta": f"{c4(fila.desviacion_absoluta):0.4f}",
            "desviacion_relativa": None
            if fila.desviacion_relativa is None
            else f"{c4(fila.desviacion_relativa):0.4f}",
            "sin_presupuesto": bool(fila.sin_presupuesto),
        }
        for fila in filas
    ]


async def generar_informe_desviacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    periodo_id: str | None = None,
    centro_coste_id: str | None = None,
    cuenta_id: int | None = None,
    mes: int | None = None,
    page: int = 1,
    page_size: int = 200,
) -> dict[str, Any]:
    """Informe acumulado con totales, subtotales por centro e items (T031)."""
    seguimiento = await calcular_desviaciones(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        cuenta_id=cuenta_id,
        centro_coste_id=centro_coste_id,
        mes=mes,
        page=1,
        page_size=100_000,
    )
    items: list[dict[str, Any]] = seguimiento["items"]
    origen = "calculo"
    if periodo_id:
        snapshot = await filas_desde_snapshot(
            db, empresa_id=empresa_id, periodo_id=periodo_id
        )
        if snapshot:
            items = snapshot
            origen = "snapshot"
    total_presupuestado = sum(
        (Decimal(i["importe_presupuestado"]) for i in items), Decimal(0)
    )
    total_real = sum((Decimal(i["importe_real"]) for i in items), Decimal(0))
    total_desviacion = sum(
        (Decimal(i["desviacion_absoluta"]) for i in items), Decimal(0)
    )
    inicio = (max(page, 1) - 1) * max(page_size, 1)
    return {
        "ejercicio": ejercicio,
        "origen": origen,
        "mes": mes,
        "total_presupuestado": f"{c4(total_presupuestado):0.4f}",
        "total_real": f"{c4(total_real):0.4f}",
        "total_desviacion": f"{c4(total_desviacion):0.4f}",
        "cuadra": c4(total_real - total_presupuestado) == c4(total_desviacion),
        "lineas_sin_presupuesto": sum(1 for i in items if i["sin_presupuesto"]),
        "centros": _subtotales(items),
        "items": items[inicio : inicio + max(page_size, 1)],
        "total": len(items),
    }
