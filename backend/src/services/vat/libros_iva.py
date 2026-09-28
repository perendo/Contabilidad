"""Libros de registro de IVA (SPEC-012 T015/T016/T017).

Derivados exclusivamente de las facturas emitidas (SPEC-007) con asiento
vinculado (SPEC-002); nunca hay entrada manual. Cada linea aporta base, cuota,
tipo y la cuota de recargo separada. Las facturas sin asiento se excluyen; el
IVA diferido por criterio de caja se marca ``incluir_303=false``.

Clasificacion intracomunitaria: el tercero (SPEC-008) se considera operador
intracomunitario si su NIF/VAT comienza por dos letras de pais distintas de
``ES`` o su IBAN no es espanol.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from models.invoice.serie_factura import SerieFactura
from services.reports.common import fmt
from services.vat.errores import error

TIPOS_LIBRO = ("emitidas", "recibidas", "intracomunitarias")


def es_intracomunitaria(tercero: Tercero) -> bool:
    nif = (tercero.nif or "").upper().replace(" ", "")
    iban = (tercero.iban or "").upper().replace(" ", "")
    if iban[:2].isalpha() and iban[:2] != "ES":
        return True
    return len(nif) >= 2 and nif[:2].isalpha() and nif[:2] != "ES"


async def _naturaleza(db: AsyncSession, factura: Factura) -> FacturaTipo:
    vista: Factura | None = factura
    for _ in range(20):
        if vista is None:
            break
        if vista.tipo != FacturaTipo.RECTIFICATIVA:
            return vista.tipo
        if vista.factura_original_id is None:
            break
        vista = await db.scalar(
            select(Factura).where(
                Factura.empresa_id == factura.empresa_id,
                Factura.id == vista.factura_original_id,
            )
        )
    return FacturaTipo.VENTA


async def _operaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    inicio: date,
    fin: date,
    tipos: tuple[FacturaTipo, ...],
    solo_intracomunitarias: bool,
    tercero_id: uuid.UUID | None = None,
    clave_operacion: str | None = None,
) -> list[dict]:
    facturas = (
        await db.scalars(
            select(Factura).where(
                Factura.empresa_id == empresa_id,
                Factura.estado == FacturaEstado.emitida,
                Factura.ejercicio == ejercicio,
                Factura.fecha >= inicio,
                Factura.fecha <= fin,
                Factura.asiento_id.is_not(None),
            )
        )
    ).all()

    series = {
        s.id: s
        for s in (
            await db.scalars(
                select(SerieFactura).where(SerieFactura.empresa_id == empresa_id)
            )
        ).all()
    }
    terceros = {
        t.id: t
        for t in (
            await db.scalars(
                select(Tercero).where(Tercero.empresa_id == empresa_id)
            )
        ).all()
    }

    operaciones: list[dict] = []
    for factura in facturas:
        if factura.tercero_id not in terceros:
            continue
        tercero = terceros[factura.tercero_id]
        intra = es_intracomunitaria(tercero)
        if intra != solo_intracomunitarias:
            continue
        if tercero_id is not None and factura.tercero_id != tercero_id:
            continue
        naturaleza = await _naturaleza(db, factura)
        if naturaleza not in tipos:
            continue
        if clave_operacion is not None:
            clave = "C" if naturaleza == FacturaTipo.VENTA else "B"
            if clave != clave_operacion:
                continue

        signo = Decimal(-1) if factura.tipo == FacturaTipo.RECTIFICATIVA else Decimal(1)
        lineas = (
            await db.scalars(
                select(FacturaLinea)
                .where(
                    FacturaLinea.empresa_id == empresa_id,
                    FacturaLinea.factura_id == factura.id,
                )
                .order_by(FacturaLinea.line_no)
            )
        ).all()
        serie = series.get(factura.serie_id)
        numero_texto = (
            f"{serie.prefijo}{factura.numero}" if serie and factura.numero else None
        )
        incluir_303 = not (factura.regimen_caja and not factura.iva_devengado)
        for linea in lineas:
            operaciones.append(
                {
                    "factura_id": str(factura.id),
                    "nif_tercero": tercero.nif,
                    "nombre_tercero": tercero.nombre,
                    "fecha_expedicion": factura.fecha.isoformat(),
                    "fecha_operacion": factura.fecha.isoformat(),
                    "num_factura": numero_texto,
                    "base": fmt(signo * linea.base),
                    "cuota": fmt(signo * linea.cuota_iva),
                    "tipo_iva": f"{linea.tipo_iva:0.2f}",
                    "recargo_cuota": fmt(signo * linea.cuota_recargo),
                    "incluir_303": incluir_303,
                    "es_intracomunitaria": intra,
                    "clave_operacion": "C" if naturaleza == FacturaTipo.VENTA else "B",
                }
            )
    return operaciones


def _totales(operaciones: list[dict]) -> dict:
    base = sum((Decimal(o["base"]) for o in operaciones), Decimal(0))
    cuota = sum((Decimal(o["cuota"]) for o in operaciones), Decimal(0))
    recargo = sum((Decimal(o["recargo_cuota"]) for o in operaciones), Decimal(0))
    return {
        "total_base": fmt(base),
        "total_cuota": fmt(cuota),
        "total_recargo": fmt(recargo),
        "n_operaciones": len(operaciones),
    }


async def construir_libro_emitidas(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    inicio: date,
    fin: date,
    tercero_id: uuid.UUID | None = None,
    clave_operacion: str | None = None,
) -> dict:
    operaciones = await _operaciones(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        inicio=inicio,
        fin=fin,
        tipos=(FacturaTipo.VENTA,),
        solo_intracomunitarias=False,
        tercero_id=tercero_id,
        clave_operacion=clave_operacion,
    )
    return {"tipo_libro": "emitidas", "operaciones": operaciones, **_totales(operaciones)}


async def construir_libro_recibidas(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    inicio: date,
    fin: date,
    tercero_id: uuid.UUID | None = None,
    clave_operacion: str | None = None,
) -> dict:
    operaciones = await _operaciones(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        inicio=inicio,
        fin=fin,
        tipos=(FacturaTipo.COMPRA,),
        solo_intracomunitarias=False,
        tercero_id=tercero_id,
        clave_operacion=clave_operacion,
    )
    return {"tipo_libro": "recibidas", "operaciones": operaciones, **_totales(operaciones)}


async def construir_libro_intracomunitarias(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    inicio: date,
    fin: date,
    tercero_id: uuid.UUID | None = None,
    clave_operacion: str | None = None,
) -> dict:
    operaciones = await _operaciones(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        inicio=inicio,
        fin=fin,
        tipos=(FacturaTipo.VENTA, FacturaTipo.COMPRA),
        solo_intracomunitarias=True,
        tercero_id=tercero_id,
        clave_operacion=clave_operacion,
    )
    return {
        "tipo_libro": "intracomunitarias",
        "operaciones": operaciones,
        **_totales(operaciones),
    }


async def construir_libro(
    db: AsyncSession,
    *,
    empresa_id: int,
    tipo_libro: str,
    ejercicio: int,
    inicio: date,
    fin: date,
    tercero_id: uuid.UUID | None = None,
    clave_operacion: str | None = None,
) -> dict:
    if tipo_libro not in TIPOS_LIBRO:
        raise error("tipo_libro_invalido", f"Tipo de libro desconocido: {tipo_libro}")
    constructor = {
        "emitidas": construir_libro_emitidas,
        "recibidas": construir_libro_recibidas,
        "intracomunitarias": construir_libro_intracomunitarias,
    }[tipo_libro]
    return await constructor(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        inicio=inicio,
        fin=fin,
        tercero_id=tercero_id,
        clave_operacion=clave_operacion,
    )