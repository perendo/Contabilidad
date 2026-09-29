from api.treasury.cuentas_bancarias import router as cuentas_bancarias_router
"""Versioned treasury API router."""

from fastapi import APIRouter, Depends

from api.treasury.anticipos import router as anticipos_router
from api.treasury.antiguedad import router as antiguedad_router
from api.treasury.cesiones import router as cesiones_router
from api.treasury.cobros_medio import router as cobros_medio_router
from api.treasury.devoluciones import router as devoluciones_router
from api.treasury.efectos import router as efectos_router
from api.treasury.recibos import router as recibos_router
from api.treasury.remesas import router as remesas_router
from api.treasury.tercero_amend import router as tercero_amend_router
from api.treasury.vencimientos import router as vencimientos_router

from .deps import get_empresa_id

router = APIRouter(
    prefix="/api/v1",
    tags=["treasury"],
    dependencies=[Depends(get_empresa_id)],
)

router.include_router(tercero_amend_router)
router.include_router(remesas_router)
router.include_router(recibos_router)
router.include_router(devoluciones_router)
router.include_router(vencimientos_router)
router.include_router(antiguedad_router)
router.include_router(efectos_router)
router.include_router(cobros_medio_router)
router.include_router(anticipos_router)
router.include_router(cesiones_router)
router.include_router(cuentas_bancarias_router)
