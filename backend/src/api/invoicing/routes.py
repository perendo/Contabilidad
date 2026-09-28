"""Routers de facturación operativa (SPEC-007).

Agrega los endpoints de series y facturas bajo ``/api/v1/facturacion`` con la
empresa activa resuelta únicamente desde la sesión (`get_empresa_id`).
"""

from api.invoicing.facturas import router as facturas_router
from api.invoicing.series import router as series_router

__all__ = ["facturas_router", "series_router"]