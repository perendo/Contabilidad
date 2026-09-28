"""Registro, activacion y consulta de versiones del catalogo (SPEC-025 US1).

``registrar_version`` crea la version en borrador con su proyeccion y sus
operaciones; ``activar_version`` exige mapeos completos (FR-004) antes del
salto ``borrador -> vigente``. El listado y el detalle son consultas
tenant-scoped (constitucion III).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.catalog.catalogo_cuenta import CatalogoCuenta
from models.catalog.catalogo_version import CatalogoVersion, EstadoVersion
from models.catalog.mapeo_cuenta import MapeoCuenta
from services.audit.writer import audit_escribir
from services.catalog import _comun
from services.catalog.errores import CatalogoError
from services.catalog.importacion_catalogo import validar_mapeo_completo

__all__ = [
    "activar_version",
    "detalle_version",
    "listar_versiones",
    "registrar_version",
]


def _payload_version(version: CatalogoVersion, resolucion: str | None = None) -> dict[str, Any]:
    dato: dict[str, Any] = {
        "id": str(version.id),
        "numero_version": version.numero_version,
        "codigo": version.codigo,
        "fecha_inicio": version.fecha_inicio.isoformat(),
        "fecha_fin": version.fecha_fin.isoformat() if version.fecha_fin else None,
        "estado": version.estado.value,
        "es_migracion": version.es_migracion,
    }
    if resolucion is not None:
        dato["resolucion"] = resolucion
    return dato


async def registrar_version(
    db: AsyncSession,
    *,
    empresa_id: int,
    codigo: str,
    fecha_inicio: date,
    fecha_fin: date | None,
    operaciones: list[dict[str, Any]],
    actor: str,
) -> dict[str, Any]:
    """Alta manual de version (FR-001/FR-006) en transaccion ACID unica."""
    version = await _comun.crear_version_completa(
        db,
        empresa_id=empresa_id,
        codigo=codigo,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        operaciones=operaciones,
        mapeo_explicito=[],
        actor=actor,
    )
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor,
        action="ALTA_VERSION",
        entity="catalogo_version",
        entity_id=str(version.id),
        payload={
            "codigo": version.codigo,
            "numero_version": version.numero_version,
            "fecha_inicio": version.fecha_inicio.isoformat(),
            "fecha_fin": version.fecha_fin.isoformat() if version.fecha_fin else None,
            "operaciones": len(operaciones),
        },
    )
    return {
        "id": str(version.id),
        "numero_version": version.numero_version,
        "codigo": version.codigo,
        "estado": version.estado.value,
        "fecha_inicio": version.fecha_inicio.isoformat(),
    }


async def activar_version(
    db: AsyncSession, *, empresa_id: int, version_id: uuid.UUID | str, actor: str
) -> dict[str, Any]:
    """Pasa la version a ``vigente`` validando los mapeos (T017/FR-004)."""
    version = await _comun.obtener_version(db, empresa_id, version_id)
    if version is None:
        raise CatalogoError(
            "version_no_encontrada", "Version inexistente en la empresa activa", 404
        )
    if version.estado == EstadoVersion.anulada:
        raise CatalogoError(
            "version_anulada", "Una version anulada no puede activarse", 409
        )
    n_mapeos = int(
        await db.scalar(
            select(func.count())
            .select_from(MapeoCuenta)
            .where(
                MapeoCuenta.empresa_id == empresa_id,
                MapeoCuenta.version_destino_id == version.id,
            )
        )
        or 0
    )
    if version.estado == EstadoVersion.vigente:
        return {
            "id": str(version.id),
            "estado": version.estado.value,
            "n_mapeos": n_mapeos,
            "pendientes": [],
        }
    pendientes = await validar_mapeo_completo(db, empresa_id, version.id)
    if pendientes:
        codigos = ", ".join(p["codigo"] for p in pendientes)
        raise CatalogoError(
            "mapeo_incompleto",
            f"Cuentas suprimidas con saldo distinto de cero sin destino: {codigos}",
            422,
            extra={"pendientes": pendientes},
        )
    version.estado = EstadoVersion.vigente
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor,
        action="ACTIVAR_VERSION",
        entity="catalogo_version",
        entity_id=str(version.id),
        payload={
            "codigo": version.codigo,
            "numero_version": version.numero_version,
            "n_mapeos": n_mapeos,
        },
    )
    return {
        "id": str(version.id),
        "estado": version.estado.value,
        "n_mapeos": n_mapeos,
        "pendientes": [],
    }


async def listar_versiones(
    db: AsyncSession,
    *,
    empresa_id: int,
    estado: str | None = None,
    fecha_inicio_desde: date | None = None,
    fecha_inicio_hasta: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Listado paginado de versiones de la empresa activa."""
    filtros = [CatalogoVersion.empresa_id == empresa_id]
    if estado is not None:
        try:
            estado_enum = EstadoVersion(estado)
        except ValueError as exc:
            raise CatalogoError("estado_invalido", f"Estado desconocido: {estado}", 422) from exc
        filtros.append(CatalogoVersion.estado == estado_enum)
    if fecha_inicio_desde is not None:
        filtros.append(CatalogoVersion.fecha_inicio >= fecha_inicio_desde)
    if fecha_inicio_hasta is not None:
        filtros.append(CatalogoVersion.fecha_inicio <= fecha_inicio_hasta)
    total = int(
        await db.scalar(select(func.count()).select_from(CatalogoVersion).where(*filtros))
        or 0
    )
    filas = (
        await db.scalars(
            select(CatalogoVersion)
            .where(*filtros)
            .order_by(CatalogoVersion.numero_version.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [_payload_version(v) for v in filas],
        "total": total,
    }


async def detalle_version(
    db: AsyncSession, *, empresa_id: int, version_id: uuid.UUID | str
) -> dict[str, Any]:
    """Detalle de la version con su arbol de cuentas y sus mapeos."""
    version = await _comun.obtener_version(db, empresa_id, version_id)
    if version is None:
        raise CatalogoError(
            "version_no_encontrada", "Version inexistente en la empresa activa", 404
        )
    cuentas = (
        await db.scalars(
            select(CatalogoCuenta)
            .where(
                CatalogoCuenta.empresa_id == empresa_id,
                CatalogoCuenta.version_id == version.id,
            )
            .order_by(CatalogoCuenta.codigo_version)
        )
    ).all()
    mapeos = (
        await db.scalars(
            select(MapeoCuenta)
            .where(
                MapeoCuenta.empresa_id == empresa_id,
                MapeoCuenta.version_destino_id == version.id,
            )
            .order_by(MapeoCuenta.origen, MapeoCuenta.tipo_movimiento)
        )
    ).all()
    return {
        **_payload_version(version),
        "creado_por": version.creado_por,
        "cuentas": [
            {
                "id": str(c.id),
                "account_id": c.account_id,
                "codigo_version": c.codigo_version,
                "nombre_version": c.nombre_version,
                "estado": c.estado.value,
                "parent_version_id": str(c.parent_version_id)
                if c.parent_version_id
                else None,
            }
            for c in cuentas
        ],
        "mapeos": [
            {
                "id": str(m.id),
                "version_origen_id": str(m.version_origen_id),
                "cuenta_origen_id": str(m.cuenta_origen_id)
                if m.cuenta_origen_id
                else None,
                "cuenta_destino_id": str(m.cuenta_destino_id)
                if m.cuenta_destino_id
                else None,
                "tipo_movimiento": m.tipo_movimiento.value,
                "requiere_reclasificacion": m.requiere_reclasificacion,
                "origen": m.origen.value,
            }
            for m in mapeos
        ],
    }
