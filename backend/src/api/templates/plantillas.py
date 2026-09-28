"""REST API for accounting templates."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_permission
from api.templates.deps import get_empresa_activa
from database import get_db
from models.iam.user import User
from models.templates.plantilla import EstadoPlantilla
from services.templates import generacion, plantillas
from services.templates.errores import TemplateError

router = APIRouter(prefix="/api/v1/plantillas", tags=["plantillas"])
Db = Annotated[AsyncSession, Depends(get_db)]
Empresa = Annotated[int, Depends(get_empresa_activa)]
UserDep = Annotated[User, Depends(get_current_user)]


class VariableInput(BaseModel):
    id: uuid.UUID | None = None
    nombre: str = Field(min_length=1, max_length=60)
    es_requerida: bool = True


class LineaInput(BaseModel):
    id: uuid.UUID | None = None
    orden: int = Field(ge=1)
    cuenta_id: int = Field(gt=0)
    posicion: str
    importe_fijo: str | None = None
    variable_id: uuid.UUID | None = None


class PlantillaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str | None = None
    categoria: str | None = Field(None, max_length=50)
    variables: list[VariableInput] = Field(default_factory=list)
    lineas: list[LineaInput] = Field(min_length=2)


class PlantillaPatch(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=120)
    descripcion: str | None = None
    categoria: str | None = Field(None, max_length=50)
    variables: list[VariableInput] | None = None
    lineas: list[LineaInput] | None = None


class GenerarInput(BaseModel):
    fecha_asiento: date
    variables: dict[str, str] = Field(default_factory=dict)
    concepto: str | None = None


def _error(exc: TemplateError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "detail": exc.message})


def _payload(items: Sequence[BaseModel] | None) -> list[dict[str, Any]] | None:
    return [item.model_dump(exclude_none=True) for item in items] if items is not None else None


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("treasury", "crear"))])
async def crear(body: PlantillaCreate, db: Db, empresa_id: Empresa, user: UserDep) -> dict:
    try:
        plantilla = await plantillas.crear_plantilla(db, empresa_id=empresa_id, nombre=body.nombre, descripcion=body.descripcion, categoria=body.categoria, variables=_payload(body.variables) or [], lineas=_payload(body.lineas) or [], actor=user.email)
        return await plantillas.detalle_plantilla(db, empresa_id=empresa_id, plantilla_id=plantilla.id)
    except TemplateError as exc:
        raise _error(exc) from exc


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar(db: Db, empresa_id: Empresa, estado: str | None = None, categoria: str | None = None, q: str | None = None, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20) -> dict:
    return await plantillas.listar_plantillas(db, empresa_id=empresa_id, estado=estado, categoria=categoria, q=q, page=page, page_size=page_size)


@router.get("/{plantilla_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle(plantilla_id: uuid.UUID, db: Db, empresa_id: Empresa) -> dict:
    try:
        return await plantillas.detalle_plantilla(db, empresa_id=empresa_id, plantilla_id=plantilla_id)
    except TemplateError as exc:
        raise _error(exc) from exc


@router.patch("/{plantilla_id}", dependencies=[Depends(require_permission("treasury", "editar"))])
async def editar(plantilla_id: uuid.UUID, body: PlantillaPatch, db: Db, empresa_id: Empresa, user: UserDep) -> dict:
    try:
        await plantillas.actualizar_plantilla(db, empresa_id=empresa_id, plantilla_id=plantilla_id, nombre=body.nombre, descripcion=body.descripcion, categoria=body.categoria, variables=_payload(body.variables), lineas=_payload(body.lineas), actor=user.email)
        return await plantillas.detalle_plantilla(db, empresa_id=empresa_id, plantilla_id=plantilla_id)
    except TemplateError as exc:
        raise _error(exc) from exc


async def _estado(plantilla_id: uuid.UUID, estado: EstadoPlantilla, db: Db, empresa_id: Empresa, user: UserDep) -> dict:
    try:
        plantilla = await plantillas.cambiar_estado(db, empresa_id=empresa_id, plantilla_id=plantilla_id, estado=estado, actor=user.email)
        return {"id": str(plantilla.id), "estado": plantilla.estado.value}
    except TemplateError as exc:
        raise _error(exc) from exc


@router.post("/{plantilla_id}/activar", dependencies=[Depends(require_permission("treasury", "editar"))])
async def activar(plantilla_id: uuid.UUID, db: Db, empresa_id: Empresa, user: UserDep) -> dict:
    return await _estado(plantilla_id, EstadoPlantilla.activa, db, empresa_id, user)


@router.post("/{plantilla_id}/inactivar", dependencies=[Depends(require_permission("treasury", "baja"))])
async def inactivar(plantilla_id: uuid.UUID, db: Db, empresa_id: Empresa, user: UserDep) -> dict:
    return await _estado(plantilla_id, EstadoPlantilla.inactiva, db, empresa_id, user)


@router.post("/{plantilla_id}/generar", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("treasury", "crear"))])
async def generar(plantilla_id: uuid.UUID, body: GenerarInput, db: Db, empresa_id: Empresa, user: UserDep) -> dict:
    try:
        return await generacion.generar_asiento(db, empresa_id=empresa_id, plantilla_id=plantilla_id, fecha=body.fecha_asiento, variables=body.variables, concepto=body.concepto, actor=user.email, usuario_id=user.id)
    except TemplateError as exc:
        raise _error(exc) from exc


@router.get("/{plantilla_id}/generados", dependencies=[Depends(require_permission("treasury", "ver"))])
async def generados(plantilla_id: uuid.UUID, db: Db, empresa_id: Empresa) -> dict:
    try:
        await plantillas.detalle_plantilla(db, empresa_id=empresa_id, plantilla_id=plantilla_id)
        return await generacion.listar_generados(db, empresa_id=empresa_id, plantilla_id=plantilla_id)
    except TemplateError as exc:
        raise _error(exc) from exc

