"""API package for accounting templates."""

from fastapi import APIRouter

from api.templates.plantillas import router as plantillas_router

router = APIRouter(tags=["templates"])
router.include_router(plantillas_router)

__all__ = ["router"]
