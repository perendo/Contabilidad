"""Versioned ciclo contable API router (SPEC-009)."""

from fastapi import APIRouter, Depends

from api.ciclo.apertura import router as apertura_router

from .deps import get_empresa_id

router = APIRouter(
    prefix="/api/v1",
    tags=["ciclo"],
    dependencies=[Depends(get_empresa_id)],
)

router.include_router(apertura_router)