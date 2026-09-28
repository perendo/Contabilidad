"""CRUD of `MatrizPermiso` (SPEC-015 US1/US2) with access-audit chaining.

`conceder` records the concession as an allow event and links the matrix row
to that event (`concesion_id`), keeping the pista de auditoría of who granted
the permission (FR-005). All writes happen inside the `get_db` boundary; no
nested transaction is opened here.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.rbac.evento_auditoria_acceso import MotivoAcceso, ResultadoAcceso
from models.rbac.matriz_permiso import MatrizPermiso
from models.rbac.permiso_operacion import PermisoOperacion
from models.rbac.rol import Rol
from services.security import auditoria_acceso
from services.security.autorizacion import permiso_operacion as permiso_por_clave
from services.security.catalogo import CATALOGO, _ops_por_rol, sembrar_catalogo


class MatrizError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def conceder(
    db: AsyncSession,
    *,
    empresa_id: int,
    usuario_id: int,
    rol_id: object,
    modulo: str,
    operacion: str,
    ip: str | None = None,
) -> dict:
    permiso = await permiso_por_clave(db, modulo, operacion)
    if permiso is None:
        raise MatrizError(
            "operacion_inexistente",
            "La operacion no existe en el catalogo de permisos",
        )
    rol = await db.get(Rol, rol_id)
    if rol is None or int(rol.empresa_id) != int(empresa_id):
        raise MatrizError("rol_inexistente", "El rol no existe en esta empresa")

    ya = await db.scalar(
        select(MatrizPermiso.id).where(
            MatrizPermiso.empresa_id == empresa_id,
            MatrizPermiso.rol_id == rol.id,
            MatrizPermiso.permiso_id == permiso.id,
        )
    )
    if ya is not None:
        raise MatrizError(
            "concesion_duplicada", "El permiso ya esta concedido"
        )

    evento = await auditoria_acceso.registrar(
        db,
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        rol_id=rol.id,
        modulo=modulo,
        operacion=operacion,
        resultado=ResultadoAcceso.allow,
        motivo=MotivoAcceso.concedido,
        ip=ip,
    )
    concesion = MatrizPermiso(
        empresa_id=empresa_id,
        rol_id=rol.id,
        permiso_id=permiso.id,
        concesion_id=evento.id,
    )
    db.add(concesion)
    await db.flush()
    return {
        "concesion_id": str(concesion.id),
        "rol_id": str(rol.id),
        "rol_nombre": rol.nombre,
        "modulo": modulo,
        "operacion": operacion,
        "evento_id": str(evento.id),
    }


async def revocar(db: AsyncSession, *, empresa_id: int, concesion_id: object) -> None:
    concesion = await db.get(MatrizPermiso, concesion_id)
    if concesion is None or int(concesion.empresa_id) != int(empresa_id):
        raise MatrizError("concesion_inexistente", "La concesion no existe")
    await db.delete(concesion)
    await db.flush()


async def reset(db: AsyncSession, *, empresa_id: int) -> int:
    """Drop all concessions of the company and re-seed the default matrix."""
    await db.execute(
        delete(MatrizPermiso).where(MatrizPermiso.empresa_id == empresa_id)
    )
    await sembrar_catalogo(db)
    roles = {
        r.nombre: r
        for r in (await db.scalars(select(Rol))).all()
        if int(r.empresa_id) == int(empresa_id)
    }
    permisos = {
        (p.modulo, p.operacion.value): p
        for p in (await db.scalars(select(PermisoOperacion))).all()
    }
    concedidas = 0
    for rol_nombre, rol in roles.items():
        for modulo in CATALOGO:
            for operacion in _ops_por_rol(modulo, rol_nombre):
                permiso = permisos.get((modulo, operacion))
                if permiso is None:
                    continue
                ya = await db.scalar(
                    select(MatrizPermiso.id).where(
                        MatrizPermiso.empresa_id == empresa_id,
                        MatrizPermiso.rol_id == rol.id,
                        MatrizPermiso.permiso_id == permiso.id,
                    )
                )
                if ya is None:
                    db.add(
                        MatrizPermiso(
                            empresa_id=empresa_id,
                            rol_id=rol.id,
                            permiso_id=permiso.id,
                        )
                    )
                    concedidas += 1
    await db.flush()
    return concedidas


async def matriz_empresa(db: AsyncSession, empresa_id: int) -> list[dict]:
    filas = (
        await db.execute(
            select(
                MatrizPermiso.id,
                MatrizPermiso.rol_id,
                Rol.nombre,
                MatrizPermiso.permiso_id,
                PermisoOperacion.modulo,
                PermisoOperacion.operacion,
            )
            .join(
                Rol,
                (Rol.empresa_id == MatrizPermiso.empresa_id)
                & (Rol.id == MatrizPermiso.rol_id),
            )
            .join(
                PermisoOperacion,
                PermisoOperacion.id == MatrizPermiso.permiso_id,
            )
            .where(MatrizPermiso.empresa_id == empresa_id)
            .order_by(Rol.nombre, PermisoOperacion.modulo)
        )
    ).all()
    return [
        {
            "concesion_id": str(f.id),
            "rol_id": str(f.rol_id),
            "rol_nombre": f.nombre,
            "permiso_id": str(f.permiso_id),
            "modulo": f.modulo,
            "operacion": f.operacion.value,
        }
        for f in filas
    ]


async def mis_permisos(db: AsyncSession, empresa_id: int, rol_id: object) -> dict:
    filas = await matriz_empresa(db, empresa_id)
    propios = [f for f in filas if str(f["rol_id"]) == str(rol_id)]
    rol = await db.get(Rol, rol_id)
    permisos = [
        {"modulo": f["modulo"], "operacion": f["operacion"]} for f in propios
    ]
    return {
        "rol_id": str(rol_id),
        "rol": rol.nombre if rol is not None and int(rol.empresa_id) == int(empresa_id) else None,
        "permisos": permisos,
    }