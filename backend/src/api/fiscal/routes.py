"""Routers del modulo fiscal de IVA y modelos (SPEC-012)."""

from fastapi import APIRouter

from api.fiscal.calculos_is import configuracion_router as configuracion_is_router
from api.fiscal.calculos_is import router as calculos_is_router
from api.fiscal.exportaciones import router as exportaciones_router
from api.fiscal.libros_iva import router as libros_iva_router
from api.fiscal.modelo_200 import router as modelo_200_router
from api.fiscal.modelos import router as modelos_router
from api.fiscal.regimenes import router as regimenes_router
from api.fiscal.retenciones import router as retenciones_router
from api.fiscal.sii import router as sii_router

router = APIRouter()
router.include_router(libros_iva_router)
router.include_router(modelos_router)
router.include_router(exportaciones_router)
router.include_router(regimenes_router)
router.include_router(sii_router)
router.include_router(calculos_is_router)
router.include_router(modelo_200_router)
router.include_router(configuracion_is_router)
router.include_router(retenciones_router)

__all__ = ["router"]