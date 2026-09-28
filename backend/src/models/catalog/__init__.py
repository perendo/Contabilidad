"""Versioned chart-of-accounts models (SPEC-025).

Importing this package registers ``catalogo_version``, ``catalogo_cuenta``,
``mapeo_cuenta`` and ``reclasificacion_saldo`` on ``Base.metadata`` so the
composite multi-tenant FKs resolve during ``create_all`` and migrations.
"""

from models.catalog.catalogo_cuenta import CatalogoCuenta, EstadoCuentaVersion
from models.catalog.catalogo_version import CatalogoVersion, EstadoVersion
from models.catalog.mapeo_cuenta import MapeoCuenta, OrigenMapeo, TipoMovimiento
from models.catalog.reclasificacion_saldo import (
    EstadoReclasificacion,
    ReclasificacionSaldo,
)

__all__ = [
    "CatalogoCuenta",
    "CatalogoVersion",
    "EstadoCuentaVersion",
    "EstadoReclasificacion",
    "EstadoVersion",
    "MapeoCuenta",
    "OrigenMapeo",
    "ReclasificacionSaldo",
    "TipoMovimiento",
]
