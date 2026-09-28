"""API de asientos multilínea (SPEC-006).

Router versionado ``/api/v1/asientos`` con la empresa activa derivada de la
sesión (`get_empresa_id`, NUNCA del cliente — constitución VII). Expone:
POST ``/asientos`` (creación 1:1 y N:M en un solo paso POSTED), POST
``/asientos/{id}/anular`` (rectificativo invertido), GET ``/asientos``
(listado paginado) y GET ``/asientos/{id}`` (detalle con líneas).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from services.journal.anulador import anular_asiento
from services.journal.entry_service import AsientoError
from services.journal.motor import (
    crear_asiento_multilinea,
    listar_asientos,
    obtener_asiento,
)
from services.journal.validador_multilinea import MultilineaError

router = APIRouter(prefix="/api/v1/asientos", tags=["asientos"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class LineaMultilinea(BaseModel):
    cuenta: str = Field(..., min_length=1, max_length=8)
    debe: str = "0"
    haber: str = "0"
    detalle: str | None = Field(None, max_length=255)
    centro_coste_id: uuid.UUID | None = None


class AsientoMultilineaCreate(BaseModel):
    fecha: date
    concepto: str = Field(..., min_length=1, max_length=255)
    lineas: list[LineaMultilinea] = Field(..., min_length=1)


def _http_error(exc: AsientoError | MultilineaError) -> HTTPException:
    code = exc.code
    if code in ("asiento_no_encontrado", "centro_no_encontrado"):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": code, "detail": str(exc)},
        )
    if code in ("estado_invalido", "linea_posteada"):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": code, "detail": str(exc)},
        )
    if code in ("ejercicio_cerrado", "ejercicio_invalido"):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "detail": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": code, "detail": str(exc)},
    )


def _lineas_request(body: AsientoMultilineaCreate) -> list[dict]:
    return [
        {
            "cuenta": linea.cuenta,
            "debe": linea.debe,
            "haber": linea.haber,
            "detalle": linea.detalle,
            "centro_coste_id": str(linea.centro_coste_id) if linea.centro_coste_id else None,
        }
        for linea in body.lineas
    ]


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("acct", "crear"))])
async def crear_asiento(
    body: AsientoMultilineaCreate,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        entrada = await crear_asiento_multilinea(
            session,
            empresa_id=empresa_id,
            fecha=body.fecha,
            concepto=body.concepto,
            lineas=_lineas_request(body),
        )
    except (AsientoError, MultilineaError) as exc:
        raise _http_error(exc) from exc
    detalle = await obtener_asiento(
        session, empresa_id=empresa_id, entry_id=entrada.id
    )
    assert detalle is not None
    return {
        "id": detalle["id"],
        "numero_asiento": detalle["numero_asiento"],
        "fecha": detalle["fecha"],
        "concepto": detalle["concepto"],
        "total_debe": detalle["total_debe"],
        "total_haber": detalle["total_haber"],
        "n_lineas": detalle["n_lineas"],
        "estado": detalle["estado"],
    }


@router.post(
    "/{entry_id}/anular",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("acct", "editar"))],
)
async def anular_asiento_ep(
    entry_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    try:
        return await anular_asiento(
            session, empresa_id=empresa_id, entry_id=entry_id
        )
    except (AsientoError, MultilineaError) as exc:
        raise _http_error(exc) from exc


@router.get("", dependencies=[Depends(require_permission("acct", "ver"))])
async def listar_asientos_ep(
    empresa_id: EmpresaDep,
    session: SessionDep,
    fecha_desde: Annotated[date | None, Query()] = None,
    fecha_hasta: Annotated[date | None, Query()] = None,
    estado: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        return await listar_asientos(
            session,
            empresa_id=empresa_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            page=page,
            page_size=page_size,
        )
    except AsientoError as exc:
        raise _http_error(exc) from exc


@router.get("/{entry_id}", dependencies=[Depends(require_permission("acct", "ver"))])
async def detalle_asiento_ep(
    entry_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    detalle = await obtener_asiento(session, empresa_id=empresa_id, entry_id=entry_id)
    if detalle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "asiento_no_encontrado", "detail": "Asiento inexistente"},
        )
    return detalle