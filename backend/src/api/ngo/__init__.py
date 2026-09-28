"""API del módulo ngo (SPEC-019), versión /api/v1.

Router padre que agrega los sub-routers de subvenciones/gastos, libros,
legalizaciones y cajas/arqueos. La empresa activa SIEMPRE se deriva de la sesión
autenticada (`get_empresa_activa`), nunca de path/body (constitución III); cada
ruta declara su guard del catálogo SPEC-015 (módulo "ngo").
"""

from fastapi import APIRouter, Depends

from api.ngo.arqueos import router as arqueos_router
from api.ngo.cajas import router as cajas_router
from api.ngo.legalizaciones import router as legalizaciones_router
from api.ngo.libros import router as libros_router
from api.ngo.subvenciones import router as subvenciones_router

from .deps import get_empresa_activa

router = APIRouter(
    tags=["ngo"],
    dependencies=[Depends(get_empresa_activa)],
)

router.include_router(subvenciones_router)
router.include_router(libros_router)
router.include_router(legalizaciones_router)
router.include_router(cajas_router)
router.include_router(arqueos_router)

__all__ = ["router"]