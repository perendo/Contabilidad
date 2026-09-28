"""Endpoints de facturas operativas (SPEC-007).

POST/GET ``/facturacion/facturas``, POST ``/{id}/emitir``, POST ``/{id}/anular``,
POST ``/{id}/rectificar``, GET ``/{id}`` y DELETE ``/{id}``. La empresa activa
viaja siempre en la sesión (constitución III).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from models.fiscal.retencion import TipoRetencion
from services.invoicing.emision import (
    anular_factura,
    crear_factura_borrador,
    eliminar_factura_borrador,
    emitir_factura,
    listar_facturas,
    obtener_factura_detalle,
)
from services.invoicing.errores import InvoicingError
from services.invoicing.numeracion import numero_formateado, obtener_serie
from services.invoicing.rectificacion import rectificar_factura
from services.journal.entry_service import AsientoError
from services.journal.motor import obtener_asiento
from services.journal.validador_multilinea import MultilineaError

router = APIRouter(prefix="/api/v1/facturacion/facturas", tags=["facturacion"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class LineaFactura(BaseModel):
    descripcion: str | None = Field(None, max_length=255)
    cantidad: str = "1"
    precio_unitario: str
    porcentaje_descuento: str = "0"
    tipo_iva: str = "21"
    tipo_recargo: str = "0"
    tipo_irpf: str = "0"
    base_irpf: str = "0"
    tipo_retencion: TipoRetencion | None = TipoRetencion.IRPF_OTROS
    direccion_inmueble: str | None = Field(default=None, max_length=200)


class FacturaCreate(BaseModel):
    serie_id: uuid.UUID
    ejercicio: int
    fecha: date | None = None
    tipo: str = "VENTA"
    tercero_id: uuid.UUID
    concepto_global: str | None = Field(None, max_length=255)
    regimen_caja: bool = False
    lineas: list[LineaFactura] = Field(..., min_length=1)


class RectificarCreate(BaseModel):
    serie_id: uuid.UUID
    motivo: str = Field(..., min_length=1, max_length=255)
    lineas: list[LineaFactura] | None = None


def _http_error(exc: InvoicingError | AsientoError | MultilineaError) -> HTTPException:
    code = exc.code
    detalle = {"code": code, "detail": str(exc)}
    if code in ("factura_no_encontrada", "serie_no_encontrada", "tercero_no_encontrado"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detalle)
    if code == "ejercicio_cerrado":
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detalle)
    if code in ("estado_invalido", "sin_rectificativa", "serie_inactiva"):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detalle)


def _lineas_request(body) -> list[dict]:
    return [
        {
            "descripcion": linea.descripcion,
            "cantidad": linea.cantidad,
            "precio_unitario": linea.precio_unitario,
            "porcentaje_descuento": linea.porcentaje_descuento,
            "tipo_iva": linea.tipo_iva,
            "tipo_recargo": linea.tipo_recargo,
            "tipo_irpf": linea.tipo_irpf,
            "base_irpf": linea.base_irpf,
            "tipo_retencion": linea.tipo_retencion,
            "tipo_retencion_explicito": "tipo_retencion" in linea.model_fields_set,
            "direccion_inmueble": linea.direccion_inmueble,
        }
        for linea in body.lineas
    ]


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("invoicing", "crear"))])
async def crear_factura(
    body: FacturaCreate,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        factura = await crear_factura_borrador(
            session,
            empresa_id=empresa_id,
            serie_id=body.serie_id,
            ejercicio=body.ejercicio,
            fecha=body.fecha or datetime.now(timezone.utc).date(),
            tipo=body.tipo,
            tercero_id=body.tercero_id,
            concepto_global=body.concepto_global,
            lineas=_lineas_request(body),
            regimen_caja=body.regimen_caja,
        )
    except (InvoicingError, AsientoError, MultilineaError) as exc:
        raise _http_error(exc) from exc
    detalle = await obtener_factura_detalle(
        session, empresa_id=empresa_id, factura_id=factura.id
    )
    assert detalle is not None
    return detalle


@router.post("/{factura_id}/emitir", dependencies=[Depends(require_permission("invoicing", "editar"))])
async def emitir_factura_ep(
    factura_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        factura, asiento = await emitir_factura(
            session, empresa_id=empresa_id, factura_id=factura_id
        )
    except (InvoicingError, AsientoError, MultilineaError) as exc:
        raise _http_error(exc) from exc
    asiento_detalle = await obtener_asiento(
        session, empresa_id=empresa_id, entry_id=asiento.id
    )
    serie = await obtener_serie(session, empresa_id=empresa_id, serie_id=factura.serie_id)
    assert serie is not None
    return {
        "id": str(factura.id),
        "numero": numero_formateado(serie, factura.numero),
        "numero_int": factura.numero,
        "fecha": factura.fecha.isoformat(),
        "importe_total": f"{factura.importe_total:0.4f}",
        "estado": factura.estado.value,
        "asiento_id": str(factura.asiento_id),
        "numero_asiento": (asiento_detalle or {}).get("numero_asiento"),
    }


@router.post("/{factura_id}/anular", dependencies=[Depends(require_permission("invoicing", "baja"))])
async def anular_factura_ep(
    factura_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        factura = await anular_factura(
            session, empresa_id=empresa_id, factura_id=factura_id
        )
    except (InvoicingError, AsientoError, MultilineaError) as exc:
        raise _http_error(exc) from exc
    serie = await obtener_serie(session, empresa_id=empresa_id, serie_id=factura.serie_id)
    assert serie is not None
    return {
        "id": str(factura.id),
        "numero": numero_formateado(serie, factura.numero),
        "estado": factura.estado.value,
    }


@router.post("/{factura_id}/rectificar", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("invoicing", "editar"))])
async def rectificar_factura_ep(
    factura_id: uuid.UUID,
    body: RectificarCreate,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        abono, _ = await rectificar_factura(
            session,
            empresa_id=empresa_id,
            factura_id=factura_id,
            serie_id=body.serie_id,
            motivo=body.motivo,
            lineas=_lineas_request(body) if body.lineas else None,
        )
    except (InvoicingError, AsientoError, MultilineaError) as exc:
        raise _http_error(exc) from exc
    detalle = await obtener_factura_detalle(
        session, empresa_id=empresa_id, factura_id=abono.id
    )
    assert detalle is not None
    return detalle


@router.get("", dependencies=[Depends(require_permission("invoicing", "ver"))])
async def listar_facturas_ep(
    empresa_id: EmpresaDep,
    session: SessionDep,
    serie_id: uuid.UUID | None = None,
    estado: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    ejercicio: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    try:
        return await listar_facturas(
            session,
            empresa_id=empresa_id,
            serie_id=serie_id,
            estado=estado,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            ejercicio=ejercicio,
            page=page,
            page_size=page_size,
        )
    except (InvoicingError, AsientoError, MultilineaError) as exc:
        raise _http_error(exc) from exc


@router.get("/{factura_id}", dependencies=[Depends(require_permission("invoicing", "ver"))])
async def obtener_factura_ep(
    factura_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        detalle = await obtener_factura_detalle(
            session, empresa_id=empresa_id, factura_id=factura_id
        )
    except (InvoicingError, AsientoError, MultilineaError) as exc:
        raise _http_error(exc) from exc
    if detalle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "factura_no_encontrada", "detail": "Factura inexistente"},
        )
    return detalle


@router.delete("/{factura_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("invoicing", "baja"))])
async def eliminar_factura_ep(
    factura_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> Response:
    try:
        await eliminar_factura_borrador(
            session, empresa_id=empresa_id, factura_id=factura_id
        )
    except (InvoicingError, AsientoError, MultilineaError) as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)