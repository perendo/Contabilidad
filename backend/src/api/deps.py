"""Shared authentication/tenancy/RBAC dependencies (SPEC-003 US1 safeguards).

`get_empresa_id` reads the `X-Empresa-Activa` header and validates it against
the user's active user-companies relation on every request (403, without
revealing whether the company exists). `require_role` builds role-guarded deps.
`require_permission` (SPEC-015) is the central deny-by-default guard: it
resolves the active role and the matrix concession for `(modulo, operacion)`
and audits every denial plus granted operations that touch accounting data.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from models.rbac.evento_auditoria_acceso import MotivoAcceso, ResultadoAcceso
from services.auth.security import verify_token
from services.security import auditoria_acceso
from services.security.autorizacion import (
    concesion_activa,
    permiso_operacion,
    rol_de_empresa,
)

HEADER_EMPRESA = "X-Empresa-Activa"


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
        )
    token = auth.split(" ", 1)[1].strip()
    try:
        user_id = verify_token(token)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o inexistente",
        )
    return user


async def _relacion_activa(
    db: AsyncSession,
    user_id: int,
    empresa_id: int,
) -> UserCompany | None:
    return await db.scalar(
        select(UserCompany).where(
            UserCompany.user_id == user_id,
            UserCompany.company_id == empresa_id,
            UserCompany.is_active.is_(True),
        )
    )


async def get_empresa_id(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> int:
    raw = request.headers.get(HEADER_EMPRESA)
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Falta el contexto de empresa activa",
        )
    try:
        empresa_id = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Contexto de empresa inválido",
        )
    if empresa_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Contexto de empresa inválido",
        )
    relacion = await _relacion_activa(db, user.id, empresa_id)
    if relacion is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin acceso a la empresa del contexto",
        )
    company = await db.get(Company, empresa_id)
    if company is None or not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin acceso a la empresa del contexto",
        )
    request.state.empresa_id = empresa_id
    return empresa_id


def require_role(*roles: UserRol) -> Callable[..., Awaitable[int]]:
    """Build a dependency that enforces an allowed role for the active company."""

    async def _checked(
        request: Request,
        empresa_id: Annotated[int, Depends(get_empresa_id)],
        db: Annotated[AsyncSession, Depends(get_db)],
        user: Annotated[User, Depends(get_current_user)],
    ) -> int:
        relacion = await _relacion_activa(db, user.id, empresa_id)
        if relacion is None or relacion.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Rol insuficiente para la operación",
            )
        return empresa_id

    return _checked


require_write: Callable[..., Awaitable[int]] = require_role(UserRol.ADMIN, UserRol.ACCOUNTANT)


def require_permission(modulo: str, operacion: str) -> Callable[..., Awaitable[int]]:
    """Central deny-by-default guard of SPEC-015.

    Resolves the active company (nested `get_empresa_id`, keeps the existing
    403s), the user's role row and the matrix concession. Every denial is
    audited in the same committed ACID transaction of the abort; granted
    operations flagged `requiere_datos_contables` are audited and flushed so
    the event commits atomically with the business operation.
    """

    async def _checked(
        request: Request,
        empresa_id: Annotated[int, Depends(get_empresa_id)],
        db: Annotated[AsyncSession, Depends(get_db)],
        user: Annotated[User, Depends(get_current_user)],
    ) -> int:
        relacion = await _relacion_activa(db, user.id, empresa_id)
        if relacion is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sin acceso a la empresa del contexto",
            )
        ip = request.client.host if request.client is not None else None
        rol = await rol_de_empresa(db, empresa_id, relacion.role.name)
        if rol is None:
            await auditoria_acceso.registrar(
                db,
                empresa_id=empresa_id,
                usuario_id=user.id,
                rol_id=None,
                modulo=modulo,
                operacion=operacion,
                resultado=ResultadoAcceso.deny,
                motivo=MotivoAcceso.sin_rol,
                ip=ip,
                commit=True,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Rol no encontrado en la matriz de permisos",
            )
        permiso = await permiso_operacion(db, modulo, operacion)
        if permiso is None:
            await auditoria_acceso.registrar(
                db,
                empresa_id=empresa_id,
                usuario_id=user.id,
                rol_id=rol.id,
                modulo=modulo,
                operacion=operacion,
                resultado=ResultadoAcceso.deny,
                motivo=MotivoAcceso.operacion_inexistente,
                ip=ip,
                commit=True,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operación inexistente en el catálogo de permisos",
            )
        concesion = await concesion_activa(
            db,
            empresa_id=empresa_id,
            rol_id=rol.id,
            permiso_id=permiso.id,
        )
        if concesion is None:
            await auditoria_acceso.registrar(
                db,
                empresa_id=empresa_id,
                usuario_id=user.id,
                rol_id=rol.id,
                modulo=modulo,
                operacion=operacion,
                resultado=ResultadoAcceso.deny,
                motivo=MotivoAcceso.sin_permiso,
                ip=ip,
                commit=True,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permiso insuficiente para la operación",
            )
        if permiso.requiere_datos_contables:
            await auditoria_acceso.registrar(
                db,
                empresa_id=empresa_id,
                usuario_id=user.id,
                rol_id=rol.id,
                modulo=modulo,
                operacion=operacion,
                resultado=ResultadoAcceso.allow,
                motivo=MotivoAcceso.concedido,
                ip=ip,
            )
        request.state.empresa_id = empresa_id
        return empresa_id

    _checked._rbac_permiso = (modulo, operacion)  # type: ignore[attr-defined]
    return _checked