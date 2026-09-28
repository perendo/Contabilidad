"""SPEC-015 REST API: catalogo, matriz de permisos, auditoria de accesos.

La empresa activa SIEMPRE se deriva de la sesión (`Depends(get_empresa_id)`,
decorator y/o firma, cacheados por DI); nunca viaja en path/body (constitución
III). La gestión de la matriz se autoriza con la propia matriz
(`rbac`/`configurar`) — FR-006.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.iam.user import User
from models.iam.user_company import UserCompany
from models.rbac.evento_auditoria_acceso import MotivoAcceso, ResultadoAcceso
from models.rbac.permiso_operacion import PermisoOperacion
from models.rbac.rol import Rol
from services.security import auditoria_acceso
from services.security import matriz as matriz_svc
from services.security.autorizacion import rol_de_empresa

router = APIRouter(
    prefix="/api/v1/permisos",
    dependencies=[Depends(get_empresa_id)],
    tags=["permisos"],
)

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


class ConcesionCreate(BaseModel):
    rol_id: uuid.UUID
    modulo: str
    operacion: str


class ResetMatriz(BaseModel):
    confirm: bool


@router.get("/catalogo", dependencies=[Depends(require_permission("rbac", "ver"))])
async def catalogo(
    db: DbDep,
    empresa_id: EmpresaDep,
) -> dict:
    del empresa_id
    filas = (await db.scalars(select(PermisoOperacion).order_by(PermisoOperacion.modulo))).all()
    operaciones_por_modulo: dict[str, list[str]] = {}
    for p in filas:
        operaciones_por_modulo.setdefault(p.modulo, []).append(p.operacion.value)
    return {
        "modulos": [
            {"modulo": modulo, "operaciones": operaciones}
            for modulo, operaciones in operaciones_por_modulo.items()
        ],
        "total": len(operaciones_por_modulo),
    }


@router.get("/matriz", dependencies=[Depends(require_permission("rbac", "ver"))])
async def matriz(db: DbDep, empresa_id: EmpresaDep) -> dict:
    items = await matriz_svc.matriz_empresa(db, empresa_id)
    return {
        "items": [
            {
                "matriz_id": f["concesion_id"],
                "rol_id": f["rol_id"],
                "rol": f["rol_nombre"],
                "modulo": f["modulo"],
                "operacion": f["operacion"],
                "permiso_id": f["permiso_id"],
            }
            for f in items
        ],
        "roles": await _roles_nombres(db, empresa_id),
    }


@router.post(
    "/matriz",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("rbac", "configurar"))],
)
async def conceder(
    body: ConcesionCreate,
    request: Request,
    db: DbDep,
    user: UserDep,
    empresa_id: EmpresaDep,
) -> dict:
    ip = request.client.host if request.client is not None else None
    try:
        concesion = await matriz_svc.conceder(
            db,
            empresa_id=empresa_id,
            usuario_id=user.id,
            rol_id=body.rol_id,
            modulo=body.modulo,
            operacion=body.operacion,
            ip=ip,
        )
    except matriz_svc.MatrizError as exc:
        raise HTTPException(status_code=_status_para(exc.code), detail=exc.message)
    return {
        "matriz_id": concesion["concesion_id"],
        "rol_id": concesion["rol_id"],
        "modulo": concesion["modulo"],
        "operacion": concesion["operacion"],
        "concedido": True,
    }


@router.delete(
    "/matriz/{matriz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("rbac", "configurar"))],
)
async def revocar(matriz_id: uuid.UUID, db: DbDep, empresa_id: EmpresaDep) -> None:
    try:
        await matriz_svc.revocar(
            db, empresa_id=empresa_id, concesion_id=matriz_id
        )
    except matriz_svc.MatrizError as exc:
        raise HTTPException(status_code=_status_para(exc.code), detail=exc.message) from exc


@router.post(
    "/matriz/reset",
    dependencies=[Depends(require_permission("rbac", "configurar"))],
)
async def reset(
    body: ResetMatriz,
    request: Request,
    db: DbDep,
    user: UserDep,
    empresa_id: EmpresaDep,
) -> dict:
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Confirmacion requerida (confirm=true)",
        )
    ip = request.client.host if request.client is not None else None
    concedidas = await matriz_svc.reset(db, empresa_id=empresa_id)
    await auditoria_acceso.registrar(
        db,
        empresa_id=empresa_id,
        usuario_id=user.id,
        rol_id=None,
        modulo="rbac",
        operacion="configurar",
        resultado=ResultadoAcceso.allow,
        motivo=MotivoAcceso.concedido,
        ip=ip,
    )
    return {"concesiones": concedidas}


@router.get(
    "/auditoria",
    dependencies=[Depends(require_permission("rbac", "ver"))],
)
async def auditoria(
    db: DbDep,
    empresa_id: EmpresaDep,
    resultado: str | None = None,
    modulo: str | None = None,
    operacion: str | None = None,
    usuario_id: int | None = None,
    fecha_gte: datetime | None = None,
    fecha_lte: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    try:
        resultado_enum = ResultadoAcceso(resultado) if resultado else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Filtro resultado inválido",
        )
    if fecha_gte is not None and fecha_gte.tzinfo is None:
        fecha_gte = fecha_gte.replace(tzinfo=timezone.utc)
    if fecha_lte is not None and fecha_lte.tzinfo is None:
        fecha_lte = fecha_lte.replace(tzinfo=timezone.utc)
    items, total = await auditoria_acceso.listar_eventos(
        db,
        empresa_id=empresa_id,
        resultado=resultado_enum,
        modulo=modulo,
        operacion=operacion,
        usuario_id=usuario_id,
        fecha_gte=fecha_gte,
        fecha_lte=fecha_lte,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total}


@router.get("/mis-permisos")
async def mis_permisos_actual(
    db: DbDep,
    user: UserDep,
    empresa_id: EmpresaDep,
) -> dict:
    rol = await _rol_actual(db, empresa_id, user.id)
    if rol is None:
        return {"rol_id": None, "rol": None, "permisos": []}
    return await matriz_svc.mis_permisos(db, empresa_id, rol.id)


def _status_para(code: str) -> int:
    if code == "concesion_duplicada":
        return status.HTTP_409_CONFLICT
    if code in ("operacion_inexistente", "rol_inexistente"):
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    return status.HTTP_404_NOT_FOUND


async def _roles_nombres(db: AsyncSession, empresa_id: int) -> list[str]:
    filas = (
        await db.scalars(
            select(Rol.nombre)
            .where(Rol.empresa_id == empresa_id)
            .order_by(Rol.nombre)
        )
    ).all()
    return list(filas)


async def _rol_actual(
    db: AsyncSession, empresa_id: int, user_id: int
) -> Rol | None:
    rel = await db.scalar(
        select(UserCompany).where(
            UserCompany.user_id == user_id,
            UserCompany.company_id == empresa_id,
        )
    )
    if rel is None:
        return None
    return await rol_de_empresa(db, empresa_id, rel.role.name)