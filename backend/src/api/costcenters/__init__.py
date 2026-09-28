"""API del módulo costcenters (SPEC-017), versión /api/v1.

Router padre que agrega los sub-routers de centros, imputaciones e informes de
costes. La empresa activa SIEMPRE se deriva de la sesión autenticada
(`get_empresa_activa`), nunca de path/body (constitución III).
"""

from fastapi import APIRouter, Depends

from api.costcenters.centros import router as centros_router
from api.costcenters.imputaciones import router as imputaciones_router
from api.costcenters.informes import router as informes_router

from .deps import get_empresa_activa

router = APIRouter(
    tags=["costcenters"],
    dependencies=[Depends(get_empresa_activa)],
)

router.include_router(centros_router)
router.include_router(imputaciones_router)
router.include_router(informes_router)

__all__ = ["router"]