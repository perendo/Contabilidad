"""Informes de costes por centro (SPEC-017 US3).

Agrega en ``Decimal`` (prohibido float) las líneas imputadas de asientos
``POSTED`` de la empresa activa, clasifica por grupo PGC (``6xx`` coste,
``7xx`` ingreso) y calcula subtotales por ancestro mediante la closure
``jerarquia_centro`` (nunca computa en el frontend: contrato REST). Exporta
CSV (delimitador ``;``, UTF-8 con BOM) y JSON con 4 decimales.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.costcenters.centro_coste import CentroCoste
from models.costcenters.imputacion import ImputacionCentro
from models.costcenters.jerarquia import JerarquiaCentro
from services.costcenters.errores import CostcenterError

CUATRO = Decimal("0.0001")


def _cuatro(valor: Decimal) -> str:
    return f"{valor.quantize(CUATRO):0.4f}"


def _es_coste(cuenta: str) -> bool:
    return cuenta.startswith("6")


def _es_ingreso(cuenta: str) -> bool:
    return cuenta.startswith("7")


async def informe_costes(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    centro_id: uuid.UUID | None = None,
    tipo: str = "todos",
) -> dict:
    """Informe por centro y período con subtotales por jerarquía (4 decimales)."""
    if tipo not in ("coste", "ingreso", "todos"):
        raise CostcenterError("tipo_invalido", "tipo debe ser coste|ingreso|todos")
    if fecha_desde is not None and fecha_hasta is not None and fecha_desde > fecha_hasta:
        raise CostcenterError("periodo_invalido", "fecha_desde no puede ser posterior a fecha_hasta")

    centros_filas = (
        await db.scalars(
            select(CentroCoste)
            .where(CentroCoste.empresa_id == empresa_id)
            .order_by(CentroCoste.codigo)
        )
    ).all()
    centros: dict[uuid.UUID, CentroCoste] = {c.id: c for c in centros_filas}

    scope_ids: set[uuid.UUID] = set()
    if centro_id is not None:
        if centro_id not in centros:
            raise CostcenterError("centro_no_encontrado", "El centro no existe en la empresa activa")
        pares = (
            await db.scalars(
                select(JerarquiaCentro).where(
                    JerarquiaCentro.empresa_id == empresa_id,
                    JerarquiaCentro.ancestro_id == centro_id,
                )
            )
        ).all()
        scope_ids = {p.descendiente_id for p in pares}

    filtros = [
        ImputacionCentro.empresa_id == empresa_id,
        JournalEntry.empresa_id == empresa_id,
        JournalEntry.estado == JournalEntryEstado.POSTED,
        JournalEntry.ejercicio == ejercicio,
    ]
    if fecha_desde is not None:
        filtros.append(JournalEntry.fecha >= fecha_desde)
    if fecha_hasta is not None:
        filtros.append(JournalEntry.fecha <= fecha_hasta)
    if scope_ids:
        filtros.append(ImputacionCentro.centro_coste_id.in_(scope_ids))

    filas_movimiento = (
        await db.execute(
            select(JournalEntryLine.debe, JournalEntryLine.haber, JournalEntryLine.cuenta, ImputacionCentro.centro_coste_id)
            .join(ImputacionCentro, ImputacionCentro.linea_id == JournalEntryLine.id)
            .join(JournalEntry, JournalEntry.id == ImputacionCentro.asiento_id)
            .where(*filtros)
        )
    ).all()

    coste_por_centro: dict[uuid.UUID, Decimal] = {}
    ingreso_por_centro: dict[uuid.UUID, Decimal] = {}
    for debe, haber, cuenta, ccid in filas_movimiento:
        if _es_coste(cuenta):
            coste_por_centro[ccid] = coste_por_centro.get(ccid, Decimal(0)) + Decimal(str(debe or 0))
        elif _es_ingreso(cuenta):
            ingreso_por_centro[ccid] = ingreso_por_centro.get(ccid, Decimal(0)) + Decimal(str(haber or 0))

    if not scope_ids:
        scope_ids = set(coste_por_centro) | set(ingreso_por_centro)

    # Pares ancestro → descendiente estricto (closure, para agregar subtotales)
    pares_closure = (
        await db.scalars(
            select(JerarquiaCentro).where(
                JerarquiaCentro.empresa_id == empresa_id,
                JerarquiaCentro.ancestro_id != JerarquiaCentro.descendiente_id,
            )
        )
    ).all()
    descendants: dict[uuid.UUID, set[uuid.UUID]] = {}
    for p in pares_closure:
        descendants.setdefault(p.ancestro_id, set()).add(p.descendiente_id)

    filas: list[dict] = []
    total_coste = Decimal(0)
    total_ingreso = Decimal(0)
    for cid in sorted(scope_ids):
        centro = centros[cid]
        directo_coste = coste_por_centro.get(cid, Decimal(0))
        directo_ingreso = ingreso_por_centro.get(cid, Decimal(0))
        hijos_coste = sum(
            (coste_por_centro.get(d, Decimal(0)) for d in descendants.get(cid, set())), Decimal(0)
        )
        hijos_ingreso = sum(
            (ingreso_por_centro.get(d, Decimal(0)) for d in descendants.get(cid, set())), Decimal(0)
        )
        subtotal_coste = directo_coste + hijos_coste
        subtotal_ingreso = directo_ingreso + hijos_ingreso

        if tipo == "coste":
            subtotal_ingreso = Decimal(0)
            total_coste += directo_coste
        elif tipo == "ingreso":
            subtotal_coste = Decimal(0)
            total_ingreso += directo_ingreso
        else:
            total_coste += directo_coste
            total_ingreso += directo_ingreso
        filas.append(
            {
                "centro_id": str(cid),
                "codigo": centro.codigo,
                "nombre": centro.nombre,
                "parent_id": str(centro.parent_id) if centro.parent_id else None,
                "directo_debe": _cuatro(directo_coste),
                "directo_haber": _cuatro(directo_ingreso),
                "hijos_debe": _cuatro(hijos_coste),
                "hijos_haber": _cuatro(hijos_ingreso),
                "subtotal_debe": _cuatro(subtotal_coste),
                "subtotal_haber": _cuatro(subtotal_ingreso),
                "subtotal": _cuatro(subtotal_coste - subtotal_ingreso),
            }
        )

    return {
        "empresa_id": empresa_id,
        "ejercicio": ejercicio,
        "fecha_desde": fecha_desde.isoformat() if fecha_desde else None,
        "fecha_hasta": fecha_hasta.isoformat() if fecha_hasta else None,
        "tipo": tipo,
        "centro_id": str(centro_id) if centro_id else None,
        "filas": filas,
        "totales": {
            "coste": _cuatro(total_coste),
            "ingreso": _cuatro(total_ingreso),
            "neto": _cuatro(total_coste - total_ingreso),
        },
        "n_filas": len(filas),
    }


def exportar_informe(datos: dict, formato: str = "csv") -> tuple[bytes, str]:
    """Serializa el informe; devuelve (contenido, media_type)."""
    if formato == "json":
        import json

        contenido = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
        return contenido.encode("utf-8"), "application/json; charset=utf-8"

    if formato != "csv":
        raise CostcenterError("formato_invalido", "formato debe ser csv|json")

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(
        ["centro_id", "codigo", "nombre", "parent_id", "directo_debe", "directo_haber",
         "hijos_debe", "hijos_haber", "subtotal_debe", "subtotal_haber", "subtotal"]
    )
    for fila in datos["filas"]:
        writer.writerow(
            [
                fila["centro_id"], fila["codigo"], fila["nombre"], fila["parent_id"],
                fila["directo_debe"], fila["directo_haber"], fila["hijos_debe"],
                fila["hijos_haber"], fila["subtotal_debe"], fila["subtotal_haber"],
                fila["subtotal"],
            ]
        )
    escritura = buffer.getvalue()
    # BOM UTF-8 (Excel) + delimitador ';' (convención plan raíz)
    return ("\ufeff" + escritura).encode("utf-8"), "text/csv; charset=utf-8"


__all__ = ["exportar_informe", "informe_costes"]