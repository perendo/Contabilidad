"""Pure evaluation helpers used by `api.deps.require_permission` and the
matrix endpoints. Never writes to the DB."

The evaluation is deny-by-default: an operation with no catalog row or no
matrix row is denied. Callers decide whether to audit the outcome.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.rbac.evento_auditoria_acceso import MotivoAcceso
from models.rbac.matriz_permiso import MatrizPermiso
from models.rbac.permiso_operacion import OperacionPermiso, PermisoOperacion
from models.rbac.rol import Rol
from services.security.catalogo import CATALOGO


async def permiso_operacion(
    db: AsyncSession, modulo: str, operacion: str
) -> PermisoOperacion | None:
    if modulo not in CATALOGO or operacion not in CATALOGO[modulo]:
        return None
    return await db.scalar(
        select(PermisoOperacion).where(
            PermisoOperacion.modulo == modulo,
            PermisoOperacion.operacion == OperacionPermiso(operacion),
        )
    )


async def rol_de_empresa(
    db: AsyncSession, empresa_id: int, nombre: str
) -> Rol | None:
    return await db.scalar(
        select(Rol).where(
            Rol.empresa_id == empresa_id, Rol.nombre == nombre
        )
    )


async def concesion_activa(
    db: AsyncSession,
    *,
    empresa_id: int,
    rol_id: object,
    permiso_id: object,
) -> MatrizPermiso | None:
    return await db.scalar(
        select(MatrizPermiso).where(
            MatrizPermiso.empresa_id == empresa_id,
            MatrizPermiso.rol_id == rol_id,
            MatrizPermiso.permiso_id == permiso_id,
        )
    )


async def evaluar(
    db: AsyncSession,
    *,
    empresa_id: int,
    rol_id: object,
    modulo: str,
    operacion: str,
) -> tuple[bool, MotivoAcceso]:
    permiso = await permiso_operacion(db, modulo, operacion)
    if permiso is None:
        return False, MotivoAcceso.operacion_inexistente
    concesion = await concesion_activa(
        db, empresa_id=empresa_id, rol_id=rol_id, permiso_id=permiso.id
    )
    if concesion is None:
        return False, MotivoAcceso.sin_permiso
    return True, MotivoAcceso.concedido