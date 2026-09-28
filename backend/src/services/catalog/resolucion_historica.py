"""Resolucion historica del catalogo (SPEC-025 US1, FR-003/SC-001).

Dada una fecha, devuelve la version del catalogo vigente en ese dia. Si
ninguna version cubre la fecha se usa la mas antigua en ``fecha_inicio`` y se
audita ``RESOLUCION_FALLBACK`` para que el fallo sea trazable.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.catalog.catalogo_version import CatalogoVersion, EstadoVersion
from services.audit.writer import audit_escribir
from services.catalog.errores import CatalogoError

__all__ = ["resolver_version", "version_para_fecha"]


def _payload(version: CatalogoVersion, resolucion: str) -> dict[str, Any]:
    return {
        "version_id": str(version.id),
        "numero_version": version.numero_version,
        "codigo": version.codigo,
        "fecha_inicio": version.fecha_inicio.isoformat(),
        "fecha_fin": version.fecha_fin.isoformat() if version.fecha_fin else None,
        "resolucion": resolucion,
    }


async def version_para_fecha(
    db: AsyncSession, *, empresa_id: int, fecha: date
) -> tuple[CatalogoVersion, bool]:
    """(version vigente en ``fecha``, ¿es fallback?) de la empresa activa.

    Solo las versiones ``vigente`` resuelven; sin candidatas -> 404.
    """
    candidatas = (
        await db.scalars(
            select(CatalogoVersion)
            .where(
                CatalogoVersion.empresa_id == empresa_id,
                CatalogoVersion.estado == EstadoVersion.vigente,
            )
            .order_by(CatalogoVersion.fecha_inicio)
        )
    ).all()
    if not candidatas:
        raise CatalogoError(
            "version_no_encontrada",
            f"No hay version vigente del catalogo para la fecha {fecha.isoformat()}",
            404,
        )
    for version in candidatas:
        if version.fecha_inicio <= fecha and (
            version.fecha_fin is None or fecha <= version.fecha_fin
        ):
            return version, False
    return candidatas[0], True


async def resolver_version(
    db: AsyncSession, *, empresa_id: int, fecha: date
) -> dict[str, Any]:
    """Version ``vigente`` en ``fecha`` (nunca cross-tenant; fallback auditado)."""
    version, fallback = await version_para_fecha(db, empresa_id=empresa_id, fecha=fecha)
    if fallback:
        await audit_escribir(
            db,
            empresa_id=empresa_id,
            actor="sistema",
            action="RESOLUCION_FALLBACK",
            entity="catalogo_version",
            entity_id=str(version.id),
            payload={
                "fecha": fecha.isoformat(),
                "version_id": str(version.id),
                "codigo": version.codigo,
            },
        )
    return _payload(version, "fallback" if fallback else "vigente")
