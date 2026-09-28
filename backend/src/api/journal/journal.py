"""Journal API router (SPEC-002): crear/asentar/consultar/anular asientos.

Prefix ``/api/v1/journal`` con dependency de sesión autenticada
``get_empresa_id()`` (SPEC-003) — la empresa nunca se acepta del cliente.
Names del modelo (`numero_asiento`, `debe/haber`, `original_id`) se mapean al
contrato (`numero`, `debit/credit`, `reversal_of_id`) en esta capa.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.iam.user import User
from services.journal.entry_service import (
    AsientoError,
    asentar,
    crear_borrador,
)
from services.journal.journal_query import consultar_diario, obtener_detalle
from services.journal.reversal import anular

router = APIRouter(prefix="/api/v1/journal", tags=["journal"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class LineaCreate(BaseModel):
    account_id: int = Field(..., gt=0)
    debit: str = "0"
    credit: str = "0"
    detail: str | None = Field(None, max_length=255)


class AsientoCreate(BaseModel):
    fecha: date
    concepto: str = Field(..., min_length=1, max_length=255)
    lineas: list[LineaCreate] = Field(..., min_length=1)


class ReversalBody(BaseModel):
    fecha: date | None = None
    concepto: str | None = Field(None, max_length=255)


def _http_error(exc: AsientoError) -> HTTPException:
    if exc.code in ("asiento_no_encontrado",):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "detail": str(exc)},
        )
    if exc.code in ("estado_invalido",):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "detail": str(exc)},
        )
    if exc.code in ("ejercicio_cerrado", "ejercicio_invalido"):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "detail": str(exc)},
        )
    if exc.code == "cuenta_otra_empresa":
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "detail": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": exc.code, "detail": str(exc)},
    )


def _lineas_request(body: AsientoCreate) -> list[dict]:
    return [
        {
            "account_id": linea.account_id,
            "debit": linea.debit,
            "credit": linea.credit,
            "detail": linea.detail,
        }
        for linea in body.lineas
    ]


@router.post(
    "/entries",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("acct", "crear"))],
)
async def crear_asiento(
    body: AsientoCreate,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    try:
        entrada = await crear_borrador(
            session,
            empresa_id=empresa_id,
            fecha=body.fecha,
            concepto=body.concepto,
            lineas=_lineas_request(body),
            actor=user.full_name,
        )
    except AsientoError as exc:
        raise _http_error(exc) from exc
    return {
        "id": str(entrada.id),
        "estado": entrada.estado.value,
        "fecha": entrada.fecha.isoformat(),
        "concepto": entrada.concepto,
        "lineas": [
            {"account_id": l["account_id"], "debit": l["debit"], "credit": l["credit"]}
            for l in _lineas_request(body)
        ],
        "suma_debe": _suma(body.lineas, lambda l: l.debit),
        "suma_haber": _suma(body.lineas, lambda l: l.credit),
    }


def _suma(lineas: list[LineaCreate], campo) -> str:
    total = Decimal(0)
    for linea in lineas:
        total += Decimal(str(campo(linea) or 0))
    return f"{total:0.4f}"


@router.post(
    "/entries/{entry_id}/post",
    dependencies=[Depends(require_permission("acct", "editar"))],
)
async def asentar_asiento(
    entry_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    try:
        entrada = await asentar(
            session,
            empresa_id=empresa_id,
            entry_id=entry_id,
            actor=user.full_name,
        )
    except AsientoError as exc:
        raise _http_error(exc) from exc
    return {
        "id": str(entrada.id),
        "estado": entrada.estado.value,
        "numero": entrada.numero_asiento,
        "ejercicio": entrada.ejercicio,
    }


@router.get("/entries", dependencies=[Depends(require_permission("acct", "ver"))])
async def listar_diario(
    empresa_id: EmpresaDep,
    session: SessionDep,
    date_from: Annotated[date | None, Query(description="Inicio del rango (obligatorio)")] = None,
    date_to: Annotated[date | None, Query(description="Fin del rango (obligatorio)")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        return await consultar_diario(
            session,
            empresa_id=empresa_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except AsientoError as exc:
        raise _http_error(exc) from exc


@router.get("/entries/{entry_id}", dependencies=[Depends(require_permission("acct", "ver"))])
async def detalle_asiento(
    entry_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict:
    detalle = await obtener_detalle(session, empresa_id=empresa_id, entry_id=entry_id)
    if detalle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "asiento_no_encontrado", "detail": "Asiento inexistente"},
        )
    return detalle


@router.post(
    "/entries/{entry_id}/reverse",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("acct", "editar"))],
)
async def anular_asiento(
    entry_id: uuid.UUID,
    body: ReversalBody,
    empresa_id: EmpresaDep,
    session: SessionDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    try:
        return await anular(
            session,
            empresa_id=empresa_id,
            entry_id=entry_id,
            actor=user.full_name,
            fecha=body.fecha,
            concepto=body.concepto,
        )
    except AsientoError as exc:
        raise _http_error(exc) from exc