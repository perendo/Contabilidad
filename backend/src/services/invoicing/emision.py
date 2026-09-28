"""Emisión de facturas (SPEC-007 T022/T024).

Flujo: `crear_factura_borrador` (valida líneas y tercero) -> `emitir_factura`
(asigna número correlativo, genera el asiento vinculado balanceado con el motor
SPEC-002/006 y pasa a `emitida`, todo en la misma transacción ACID con
auditoría). Rechaza ejercicios cerrados (400) y series inactivas (409).

`listar_facturas`/`obtener_factura_detalle` exponen listado paginado con
filtros y detalle con líneas + asiento para el API.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry
from models.ar.tercero import Tercero
from models.fiscal.retencion import TipoRetencion
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from models.invoice.serie_factura import SerieFactura
from services.audit.writer import audit_escribir
from services.invoicing.asiento_factura import crear_asiento_factura
from services.invoicing.calculo_impuestos import calcular_linea, calcular_totales
from services.invoicing.errores import error
from services.invoicing.numeracion import (
    next_numero_factura,
    numero_formateado,
    obtener_serie,
)
from services.invoicing.recargo_equivalencia import tipo_recargo_valido
from services.journal.entry_service import _validar_ejercicio
from services.journal.motor import obtener_asiento

TIPOS_IRPF_VALIDOS = (0, 1, 7, 15, 19)
PAGINA_MIN, PAGINA_MAX = 1, 100


def _tipo_retencion(valor: object) -> TipoRetencion:
    if valor in (None, ""):
        return TipoRetencion.IRPF_OTROS
    try:
        return TipoRetencion(valor)
    except (TypeError, ValueError) as exc:
        raise error("tipo_retencion_invalido", "La categoría de retención no es válida") from exc


def _validar_tipos(linea: dict) -> None:
    tipo_recargo = Decimal(str(linea.get("tipo_recargo") or "0"))
    if not tipo_recargo_valido(tipo_recargo):
        raise error("tipo_recargo_invalido", f"Tipo de recargo {tipo_recargo} no vigente")
    tipo_irpf = Decimal(str(linea.get("tipo_irpf") or "0"))
    if tipo_irpf not in (Decimal(t) for t in TIPOS_IRPF_VALIDOS):
        raise error("tipo_irpf_invalido", f"Tipo de IRPF {tipo_irpf} no vigente")


async def _compilar_lineas(
    db: AsyncSession, *, empresa_id: int, factura_id: uuid.UUID
) -> tuple[list[dict], dict]:
    filas = (
        await db.scalars(
            select(FacturaLinea)
            .where(
                FacturaLinea.empresa_id == empresa_id,
                FacturaLinea.factura_id == factura_id,
            )
            .order_by(FacturaLinea.line_no)
        )
    ).all()
    lineas_calc: list[dict] = []
    for fila in filas:
        res = calcular_linea(
            {
                "cantidad": fila.cantidad,
                "precio_unitario": fila.precio_unitario,
                "porcentaje_descuento": fila.porcentaje_descuento,
                "tipo_iva": fila.tipo_iva,
                "tipo_recargo": fila.tipo_recargo,
                "tipo_irpf": fila.tipo_irpf,
                "base_irpf": fila.base_irpf,
            }
        )
        lineas_calc.append(
            {
                "base": res["base"],
                "cuota_iva": res["cuota_iva"],
                "cuota_recargo": res["cuota_recargo"],
                "cuota_irpf": res["cuota_irpf"],
            }
        )
    totales = calcular_totales(lineas_calc)
    return lineas_calc, totales


async def crear_factura_borrador(
    db: AsyncSession,
    *,
    empresa_id: int,
    serie_id: uuid.UUID,
    ejercicio: int,
    fecha: date,
    tipo: str,
    tercero_id: uuid.UUID,
    concepto_global: str | None,
    lineas: list[dict],
    regimen_caja: bool = False,
    actor: str | None = None,
) -> Factura:
    try:
        tipo_norm = FacturaTipo(tipo)
    except ValueError:
        raise error("tipo_invalido", "El tipo debe ser VENTA o COMPRA")
    if tipo_norm == FacturaTipo.RECTIFICATIVA:
        raise error("tipo_invalido", "Las rectificativas se crean vía /rectificar")

    serie = await obtener_serie(db, empresa_id=empresa_id, serie_id=serie_id)
    if serie is None:
        raise error("serie_no_encontrada", "Serie inexistente en la empresa activa")
    tercero = await db.scalar(
        select(Tercero).where(
            Tercero.empresa_id == empresa_id, Tercero.id == tercero_id
        )
    )
    if tercero is None:
        raise error("tercero_no_encontrado", "Tercero inexistente en la empresa activa")

    lineas_calc: list[dict] = []
    for i, linea in enumerate(lineas, start=1):
        _validar_tipos(linea)
        lineas_calc.append(calcular_linea(linea))
    totales = calcular_totales(lineas_calc)

    factura = Factura(
        empresa_id=empresa_id,
        serie_id=serie_id,
        numero=None,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=tipo_norm,
        tercero_id=tercero_id,
        concepto_global=(concepto_global or "")[:255] or None,
        importe_base=Decimal(totales["base"]),
        importe_iva=Decimal(totales["iva"]),
        importe_recargo=Decimal(totales["recargo"]),
        importe_irpf=Decimal(totales["irpf"]),
        importe_total=Decimal(totales["total"]),
        regimen_caja=regimen_caja,
        iva_devengado=not regimen_caja,
        estado=FacturaEstado.borrador,
        created_by=actor,
    )
    db.add(factura)
    await db.flush()

    for i, (linea, calc) in enumerate(zip(lineas, lineas_calc), start=1):
        db.add(
            FacturaLinea(
                empresa_id=empresa_id,
                factura_id=factura.id,
                line_no=i,
                descripcion=str(linea.get("descripcion") or "")[:255],
                cantidad=Decimal(linea["cantidad"]),
                precio_unitario=Decimal(linea["precio_unitario"]),
                porcentaje_descuento=Decimal(str(linea.get("porcentaje_descuento") or "0")),
                base=Decimal(calc["base"]),
                tipo_iva=Decimal(str(linea.get("tipo_iva") or "0")),
                cuota_iva=Decimal(calc["cuota_iva"]),
                tipo_recargo=Decimal(str(linea.get("tipo_recargo") or "0")),
                cuota_recargo=Decimal(calc["cuota_recargo"]),
                tipo_irpf=Decimal(str(linea.get("tipo_irpf") or "0")),
                base_irpf=Decimal(str(linea.get("base_irpf") or "0")),
                cuota_irpf=Decimal(calc["cuota_irpf"]),
                tipo_retencion=_tipo_retencion(linea.get("tipo_retencion")),
                direccion_inmueble=(
                    str(linea.get("direccion_inmueble") or "")[:200] or None
                ),
            )
        )
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREAR_FACTURA_BORRADOR",
        entity="factura",
        entity_id=str(factura.id),
        payload={"serie": serie.codigo, "ejercicio": ejercicio, "tipo": tipo_norm.value},
    )
    await db.flush()
    return factura


async def emitir_factura(
    db: AsyncSession,
    *,
    empresa_id: int,
    factura_id: uuid.UUID,
    actor: str | None = None,
) -> tuple[Factura, JournalEntry]:
    factura = await db.scalar(
        select(Factura).where(
            Factura.empresa_id == empresa_id, Factura.id == factura_id
        )
    )
    if factura is None:
        raise error("factura_no_encontrada", "Factura inexistente en la empresa activa")
    if factura.estado != FacturaEstado.borrador:
        raise error("estado_invalido", "La factura ya está emitida o anulada")
    if factura.numero is not None:
        raise error("estado_invalido", "La factura ya tiene número asignado")

    await _validar_ejercicio(db, empresa_id, factura.fecha)  # 400 si cerrado

    _, totales = await _compilar_lineas(db, empresa_id=empresa_id, factura_id=factura.id)

    numero = await next_numero_factura(
        db, empresa_id=empresa_id, serie_id=factura.serie_id, ejercicio=factura.ejercicio
    )
    factura.numero = numero
    factura.importe_base = Decimal(totales["base"])
    factura.importe_iva = Decimal(totales["iva"])
    factura.importe_recargo = Decimal(totales["recargo"])
    factura.importe_irpf = Decimal(totales["irpf"])
    factura.importe_total = Decimal(totales["total"])
    factura.iva_devengado = not factura.regimen_caja
    await db.flush()

    asiento = await crear_asiento_factura(
        db, empresa_id=empresa_id, factura=factura, actor=actor
    )
    factura.estado = FacturaEstado.emitida
    factura.asiento_id = asiento.id
    await db.flush()

    serie = await obtener_serie(db, empresa_id=empresa_id, serie_id=factura.serie_id)
    assert serie is not None
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="EMITIR_FACTURA",
        entity="factura",
        entity_id=str(factura.id),
        payload={
            "numero": numero_formateado(serie, numero),
            "asiento_id": str(asiento.id),
            "total": f"{factura.importe_total:0.4f}",
        },
    )
    await db.flush()
    return factura, asiento


async def listar_facturas(
    db: AsyncSession,
    *,
    empresa_id: int,
    serie_id: uuid.UUID | None = None,
    estado: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    ejercicio: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise error("page_size_invalido", "page_size debe estar entre 1 y 100")

    filtros = [Factura.empresa_id == empresa_id]
    if serie_id is not None:
        filtros.append(Factura.serie_id == serie_id)
    if estado is not None:
        estados = [e.value for e in FacturaEstado]
        if estado.lower() not in estados:
            raise error("estado_invalido", f"Estado desconocido: {estado}")
        filtros.append(Factura.estado == estado.lower())
    if fecha_desde is not None:
        filtros.append(Factura.fecha >= fecha_desde)
    if fecha_hasta is not None:
        filtros.append(Factura.fecha <= fecha_hasta)
    if ejercicio is not None:
        filtros.append(Factura.ejercicio == ejercicio)

    base = select(Factura).where(*filtros)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))

    facturas = (
        await db.scalars(
            base.order_by(Factura.fecha, Factura.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
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
    items = []
    for f in facturas:
        serie = series.get(f.serie_id)
        items.append(
            {
                "id": str(f.id),
                "numero": numero_formateado(serie, f.numero) if serie else None,
                "numero_int": f.numero,
                "fecha": f.fecha.isoformat(),
                "tipo": f.tipo.value,
                "tercero_id": str(f.tercero_id),
                "importe_total": f"{f.importe_total:0.4f}",
                "estado": f.estado.value,
                "serie_id": str(f.serie_id),
                "asiento_id": str(f.asiento_id) if f.asiento_id else None,
                "regimen_caja": f.regimen_caja,
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


async def obtener_factura_detalle(
    db: AsyncSession,
    *,
    empresa_id: int,
    factura_id: uuid.UUID,
) -> dict | None:
    factura = await db.scalar(
        select(Factura).where(
            Factura.empresa_id == empresa_id, Factura.id == factura_id
        )
    )
    if factura is None:
        return None
    serie = await obtener_serie(db, empresa_id=empresa_id, serie_id=factura.serie_id)
    assert serie is not None

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

    asiento = None
    if factura.asiento_id is not None:
        asiento = await obtener_asiento(
            db, empresa_id=empresa_id, entry_id=factura.asiento_id
        )

    return {
        "id": str(factura.id),
        "empresa_id": factura.empresa_id,
        "serie_id": str(factura.serie_id),
        "numero": numero_formateado(serie, factura.numero),
        "numero_int": factura.numero,
        "ejercicio": factura.ejercicio,
        "fecha": factura.fecha.isoformat(),
        "tipo": factura.tipo.value,
        "tercero_id": str(factura.tercero_id),
        "factura_original_id": str(factura.factura_original_id)
        if factura.factura_original_id
        else None,
        "concepto_global": factura.concepto_global,
        "importe_base": f"{factura.importe_base:0.4f}",
        "importe_iva": f"{factura.importe_iva:0.4f}",
        "importe_recargo": f"{factura.importe_recargo:0.4f}",
        "importe_irpf": f"{factura.importe_irpf:0.4f}",
        "importe_total": f"{factura.importe_total:0.4f}",
        "regimen_caja": factura.regimen_caja,
        "iva_devengado": factura.iva_devengado,
        "estado": factura.estado.value,
        "asiento_id": str(factura.asiento_id) if factura.asiento_id else None,
        "asiento": asiento,
        "lineas": [
            {
                "id": str(l.id),
                "line_no": l.line_no,
                "descripcion": l.descripcion,
                "cantidad": f"{l.cantidad:0.4f}",
                "precio_unitario": f"{l.precio_unitario:0.4f}",
                "porcentaje_descuento": f"{l.porcentaje_descuento:0.2f}",
                "base": f"{l.base:0.4f}",
                "tipo_iva": f"{l.tipo_iva:0.2f}",
                "cuota_iva": f"{l.cuota_iva:0.4f}",
                "tipo_recargo": f"{l.tipo_recargo:0.2f}",
                "cuota_recargo": f"{l.cuota_recargo:0.4f}",
                "tipo_irpf": f"{l.tipo_irpf:0.2f}",
                "base_irpf": f"{l.base_irpf:0.4f}",
                "cuota_irpf": f"{l.cuota_irpf:0.4f}",
                "tipo_retencion": (
                    l.tipo_retencion.value if l.tipo_retencion is not None else None
                ),
                "direccion_inmueble": l.direccion_inmueble,
            }
            for l in lineas
        ],
    }


async def eliminar_factura_borrador(
    db: AsyncSession, *, empresa_id: int, factura_id: uuid.UUID, actor: str | None = None
) -> None:
    factura = await db.scalar(
        select(Factura).where(
            Factura.empresa_id == empresa_id, Factura.id == factura_id
        )
    )
    if factura is None:
        raise error("factura_no_encontrada", "Factura inexistente en la empresa activa")
    if factura.estado != FacturaEstado.borrador:
        raise error("estado_invalido", "Solo se pueden eliminar facturas en borrador")
    await db.execute(
        delete(FacturaLinea).where(
            FacturaLinea.empresa_id == empresa_id,
            FacturaLinea.factura_id == factura_id,
        )
    )
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="ELIMINAR_FACTURA_BORRADOR",
        entity="factura",
        entity_id=str(factura_id),
        payload={},
    )
    await db.flush()
    await db.delete(factura)
    await db.flush()


async def anular_factura(
    db: AsyncSession, *, empresa_id: int, factura_id: uuid.UUID, actor: str | None = None
) -> Factura:
    factura = await db.scalar(
        select(Factura).where(
            Factura.empresa_id == empresa_id, Factura.id == factura_id
        )
    )
    if factura is None:
        raise error("factura_no_encontrada", "Factura inexistente en la empresa activa")
    if factura.estado != FacturaEstado.emitida:
        raise error("estado_invalido", "Solo se puede anular una factura emitida")
    rectificativa = await db.scalar(
        select(Factura.id).where(
            Factura.empresa_id == empresa_id,
            Factura.factura_original_id == factura.id,
            Factura.tipo == FacturaTipo.RECTIFICATIVA,
        )
    )
    if rectificativa is None:
        raise error(
            "sin_rectificativa",
            "La factura necesita una rectificativa total que la anule",
        )
    factura.estado = FacturaEstado.anulada
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="ANULAR_FACTURA",
        entity="factura",
        entity_id=str(factura.id),
        payload={"asiento_id": str(factura.asiento_id) if factura.asiento_id else None},
    )
    await db.flush()
    return factura