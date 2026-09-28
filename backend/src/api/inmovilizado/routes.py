"""Router versionado del módulo inmovilizado (SPEC-014).

Prefijo ``/api/v1`` con la dependencia de empresa de sesión a nivel de
router (todas las rutas exigen cabecera autenticada). Los sub-routers
``/activos`` y ``/amortizaciones`` se montan aquí (patrón SPEC-007/009).
"""

from fastapi import APIRouter, Depends

from api.inmovilizado.activos import router as activos_router
from api.inmovilizado.amortizaciones import router as amortizaciones_router

from .deps import get_empresa_id

router = APIRouter(
    prefix="/api/v1",
    tags=["inmovilizado"],
    dependencies=[Depends(get_empresa_id)],
)

router.include_router(activos_router)
router.include_router(amortizaciones_router)

__all__ = ["router"]