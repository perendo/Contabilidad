"""Closed catalog of `PermisoOperacion` and default per-company seeding.

The catalog is static (D1 research): the API cannot create dynamic
permissions. `sembrar_seguridad` grants the initial matrix for the base roles
of SPEC-003 (ADMIN/ACCOUNTANT/READ_ONLY) right when a company is created
(trigger-equivalent; idempotent). Only `rbac` module operations are exempt
from accounting-data audit.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.rbac.matriz_permiso import MatrizPermiso
from models.rbac.permiso_operacion import OperacionPermiso, PermisoOperacion
from models.rbac.rol import Rol

OPERACIONES: tuple[str, ...] = (
    "ver",
    "crear",
    "editar",
    "aprobar",
    "importar_exportar",
    "configurar",
    "baja",
    "cerrar",
)

# Módulos de negocio cubiertos por la matriz (D1 research). `rbac` solo
# expone ver/configurar (FR-006: la configuración de la matriz se autoriza con
# la propia matriz). `bank`/`divisas` quedan en el catálogo para futuros
# módulos aunque hoy no tienen routers registrados.
_MODULOS_TODOS: tuple[str, ...] = (
    "acct",
    "ar",
    "treasury",
    "bank",
    "inmovilizado",
    "divisas",
    "reporting",
    "fiscal",
    "invoicing",
    "centros",
    "ngo",
    "presupuestos",
    "cierres",
)

# descripcion genérica ``{operacion} {modulo}`` (ASCII): debe coincidir con el
# seed SQL de `migrations/007_rbac.sql` y con el trigger SQLite de
# `db/triggers.py` (trg_companies_rbac_seed).
CATALOGO: dict[str, dict[str, str]] = {
    **{
        modulo: {op: f"{op} {modulo}" for op in OPERACIONES}
        for modulo in _MODULOS_TODOS
    },
    "rbac": {"ver": "ver rbac", "configurar": "configurar rbac"},
    # SPEC-029: la exportacion integral solo necesita generar (crear), leer y
    # ver (ver, incluida la descarga y la verificacion de integridad) y tocar
    # su configuracion SII (configurar). No expone `importar_exportar`: el
    # restore de una exportacion esta fuera de alcance (research D9).
    "export": {
        "ver": "ver export",
        "crear": "crear export",
        "configurar": "configurar export",
    },
}

ROLES_BASE: tuple[str, ...] = ("ADMIN", "ACCOUNTANT", "READ_ONLY")


def requiere_datos_contables(modulo: str, operacion: str) -> bool:
    """Only write operations over data modules touch accounting data (D7)."""
    if modulo == "rbac":
        return False
    return operacion != "ver"


def _ops_por_rol(modulo: str, rol: str) -> frozenset[str]:
    """Default grant set for one role on one module (SPEC-003 base roles).

    ADMIN: todo. ACCOUNTANT: ver/crear/editar/baja. READ_ONLY: ver. La
    configuración de la matriz (rbac) solo la otorga el seed a ADMIN — FR-006.
    """
    if rol == "ADMIN":
        return frozenset(CATALOGO[modulo].keys())
    if modulo == "rbac":
        return frozenset({"ver"})
    if rol == "ACCOUNTANT":
        return frozenset({"ver", "crear", "editar", "baja"})
    if rol == "READ_ONLY":
        return frozenset({"ver"})
    return frozenset()


async def sembrar_catalogo(db: AsyncSession) -> None:
    """Insert missing catalog rows; idempotent (UNIQUE modulo+operacion)."""
    existentes = {
        (p.modulo, p.operacion.value)
        for p in (await db.scalars(select(PermisoOperacion))).all()
    }
    for modulo, ops in CATALOGO.items():
        for operacion, descripcion in ops.items():
            if (modulo, operacion) in existentes:
                continue
            db.add(
                PermisoOperacion(
                    modulo=modulo,
                    operacion=OperacionPermiso(operacion),
                    descripcion=descripcion,
                    requiere_datos_contables=requiere_datos_contables(
                        modulo, operacion
                    ),
                )
            )
    await db.flush()


async def sembrar_seguridad(db: AsyncSession, *, empresa_id: int) -> int:
    """Seed catalog + base roles + default matrix for a company. Idempotent.

    Returns the number of concession rows present after the seed.
    """
    await sembrar_catalogo(db)
    permisos = {
        (p.modulo, p.operacion.value): p
        for p in (await db.scalars(select(PermisoOperacion))).all()
    }
    roles: dict[str, Rol] = {}
    for nombre in ROLES_BASE:
        rol = await db.scalar(
            select(Rol).where(
                Rol.empresa_id == empresa_id, Rol.nombre == nombre
            )
        )
        if rol is None:
            rol = Rol(empresa_id=empresa_id, nombre=nombre)
            db.add(rol)
            await db.flush()
        roles[nombre] = rol
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
    await db.flush()
    return (
        await db.scalar(
            select(func.count()).select_from(MatrizPermiso).where(
                MatrizPermiso.empresa_id == empresa_id
            )
        )
    ) or 0