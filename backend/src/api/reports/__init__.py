"""Reports and fiscal-year API package (SPEC-004)."""

from api.reports.fiscal import router as fiscal_router
from api.reports.informes import router as informes_router

__all__ = ["fiscal_router", "informes_router"]
