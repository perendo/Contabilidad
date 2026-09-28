"""Rectificación de facturas (abono) (SPEC-007 T034).

Genera una factura ``RECTIFICATIVA`` con ``factura_original_id`` enlazada a la
original, numeración propia correlativa de su serie y un asiento ``REVERSAL``
con las líneas del asiento original **invertidas** (Debe ⇄ Haber), sin tocar
el asiento original (constitución II). Se admite rectificar una factura ya
rectificada enlazando siempre a la factura raíz del encadenamiento.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from services.audit.writer import audit_escribir
from services.invoicing.asiento_factura import (
    crear_asiento_rectificativa,
    crear_asiento_reversal_factura,
)
from services.invoicing.calculo_impuestos import calcular_linea, calcular_totales
from services.invoicing.emision import _tipo_retencion, _validar_tipos
from services.invoicing.errores import error
from services.invoicing.numeracion import next_numero_factura, obtener_serie
from services.journal.entry_service import _validar_ejercicio


async def rectificar_factura(
    db: AsyncSession,
    *,
    empresa_id: int,
    factura_id: uuid.UUID,
    serie_id: uuid.UUID,
    motivo: str,
    actor: str | None = None,
    lineas: list[dict] | None = None,
) -> tuple[Factura, JournalEntry]:
    original = await db.scalar(
        select(Factura).where(
            Factura.empresa_id == empresa_id, Factura.id == factura_id
        )
    )
    if original is None:
        raise error("factura_no_encontrada", "Factura inexistente en la empresa activa")
    if original.estado != FacturaEstado.emitida:
        raise error(
            "estado_invalido", "Solo se puede rectificar una factura emitida"
        )
    if original.asiento_id is None:
        raise error("asiento_no_vinculado", "La factura emitida no tiene asiento")

    serie_abono = await obtener_serie(db, empresa_id=empresa_id, serie_id=serie_id)
    if serie_abono is None:
        raise error("serie_no_encontrada", "Serie inexistente en la empresa activa")

    fecha = datetime.now(timezone.utc).date()
    await _validar_ejercicio(db, empresa_id, fecha)  # 400 si cerrado
    ejercicio_abono = fecha.year

    lineas_originales = (
        await db.scalars(
            select(FacturaLinea)
            .where(
                FacturaLinea.empresa_id == empresa_id,
                FacturaLinea.factura_id == original.id,
            )
            .order_by(FacturaLinea.line_no)
        )
    ).all()

    specs: list[dict] = []
    if lineas:
        for linea in lineas:
            _validar_tipos(linea)
            specs.append(calcular_linea(linea))
    else:
        for orig_linea in lineas_originales:
            res = calcular_linea(
                {
                    "cantidad": orig_linea.cantidad,
                    "precio_unitario": orig_linea.precio_unitario,
                    "porcentaje_descuento": orig_linea.porcentaje_descuento,
                    "tipo_iva": orig_linea.tipo_iva,
                    "tipo_recargo": orig_linea.tipo_recargo,
                    "tipo_irpf": orig_linea.tipo_irpf,
                    "base_irpf": orig_linea.base_irpf,
                }
            )
            specs.append(res)
    totales = calcular_totales(specs)

    numero = await next_numero_factura(
        db, empresa_id=empresa_id, serie_id=serie_id, ejercicio=ejercicio_abono
    )
    raiz = original.factura_original_id or original.id

    abono = Factura(
        empresa_id=empresa_id,
        serie_id=serie_id,
        numero=numero,
        ejercicio=ejercicio_abono,
        fecha=fecha,
        tipo=FacturaTipo.RECTIFICATIVA,
        tercero_id=original.tercero_id,
        factura_original_id=raiz,
        concepto_global=(motivo or f"Rectificación de {original.numero or ''}")[:255],
        importe_base=Decimal(totales["base"]),
        importe_iva=Decimal(totales["iva"]),
        importe_recargo=Decimal(totales["recargo"]),
        importe_irpf=Decimal(totales["irpf"]),
        importe_total=Decimal(totales["total"]),
        regimen_caja=original.regimen_caja,
        iva_devengado=original.iva_devengado,
        estado=FacturaEstado.emitida,
        created_by=actor,
    )
    db.add(abono)
    await db.flush()

    if lineas:
        fuente: list[dict] = _lineas_raw_para(lineas)
        for indice, fila in enumerate(fuente):
            if indice >= len(lineas_originales):
                continue
            original_linea = lineas_originales[indice]
            if not fila.get("tipo_retencion_explicito", True) or fila.get("tipo_retencion") is None:
                fila["tipo_retencion"] = original_linea.tipo_retencion
            if fila.get("direccion_inmueble") is None:
                fila["direccion_inmueble"] = original_linea.direccion_inmueble
    else:
        fuente = [
            {
                "descripcion": f.descripcion,
                "cantidad": f.cantidad,
                "precio_unitario": f.precio_unitario,
                "porcentaje_descuento": f.porcentaje_descuento,
                "tipo_iva": f.tipo_iva,
                "tipo_recargo": f.tipo_recargo,
                "tipo_irpf": f.tipo_irpf,
                "base_irpf": f.base_irpf,
                "tipo_retencion": f.tipo_retencion,
                "direccion_inmueble": f.direccion_inmueble,
            }
            for f in lineas_originales
        ]
    for i, fila in enumerate(fuente, start=1):
        calc = specs[i - 1]
        db.add(
            FacturaLinea(
                empresa_id=empresa_id,
                factura_id=abono.id,
                line_no=i,
                descripcion=str(fila["descripcion"] or "")[:255],
                cantidad=Decimal(str(fila["cantidad"] or "0")),
                precio_unitario=Decimal(str(fila["precio_unitario"] or "0")),
                porcentaje_descuento=Decimal(str(fila["porcentaje_descuento"] or "0")),
                base=Decimal(calc["base"]),
                tipo_iva=Decimal(str(fila["tipo_iva"] or "0")),
                cuota_iva=Decimal(calc["cuota_iva"]),
                tipo_recargo=Decimal(str(fila["tipo_recargo"] or "0")),
                cuota_recargo=Decimal(calc["cuota_recargo"]),
                tipo_irpf=Decimal(str(fila["tipo_irpf"] or "0")),
                base_irpf=Decimal(str(fila["base_irpf"] or "0")),
                cuota_irpf=Decimal(calc["cuota_irpf"]),
                tipo_retencion=_tipo_retencion(fila.get("tipo_retencion")),
                direccion_inmueble=(
                    str(fila.get("direccion_inmueble") or "")[:200] or None
                ),
            )
        )
    await db.flush()

    concepto = f"Rectificación de factura {original.numero or original.id}"
    if lineas:
        naturaleza = (
            original.tipo
            if original.tipo != FacturaTipo.RECTIFICATIVA
            else await _naturaleza_raiz(db, empresa_id, raiz)
        )
        reversal = await crear_asiento_rectificativa(
            db,
            empresa_id=empresa_id,
            factura=abono,
            tipo_naturaleza=naturaleza,
            fecha=fecha,
            concepto=concepto,
            original_asiento_id=original.asiento_id,
            actor=actor,
        )
    else:
        reversal = await crear_asiento_reversal_factura(
            db,
            empresa_id=empresa_id,
            asiento_original_id=original.asiento_id,
            fecha=fecha,
            concepto=concepto,
            actor=actor,
        )
    abono.asiento_id = reversal.id
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="RECTIFICAR_FACTURA",
        entity="factura",
        entity_id=str(abono.id),
        payload={
            "original_id": str(original.id),
            "numero": numero,
            "asiento_reversal": str(reversal.id),
        },
    )
    await db.flush()
    return abono, reversal


async def _naturaleza_raiz(
    db: AsyncSession, empresa_id: int, raiz_id: uuid.UUID
) -> FacturaTipo:
    raiz = await db.scalar(
        select(Factura).where(
            Factura.empresa_id == empresa_id, Factura.id == raiz_id
        )
    )
    if raiz is None or raiz.tipo == FacturaTipo.RECTIFICATIVA:
        return FacturaTipo.VENTA
    return raiz.tipo


def _lineas_raw_para(lineas: list[dict]) -> list[dict]:
    return [
        {
            "descripcion": linea.get("descripcion"),
            "cantidad": linea.get("cantidad"),
            "precio_unitario": linea.get("precio_unitario"),
            "porcentaje_descuento": linea.get("porcentaje_descuento") or 0,
            "tipo_iva": linea.get("tipo_iva") or 0,
            "tipo_recargo": linea.get("tipo_recargo") or 0,
            "tipo_irpf": linea.get("tipo_irpf") or 0,
            "base_irpf": linea.get("base_irpf") or 0,
            "tipo_retencion": linea.get("tipo_retencion"),
            "tipo_retencion_explicito": linea.get(
                "tipo_retencion_explicito", "tipo_retencion" in linea
            ),
            "direccion_inmueble": linea.get("direccion_inmueble"),
        }
        for linea in lineas
    ]