"""Router de documentos adjuntos al asiento (SPEC-030).

Prefijo plano ``/api/v1/documentos`` con el segmento estatico ``/asiento/`` para
las rutas que cuelgan de un asiento (research D7): anidarlas bajo
``/api/v1/asientos/{id}/documentos`` colisionaria con la ruta comodin
``GET /api/v1/asientos/{entry_id}`` de SPEC-002/SPEC-006.

Paquete y no modulo suelto: cada historia de usuario aporta un fichero propio
(``adjuntos.py``, ``consulta.py``, ``bajas.py``) y asi pueden avanzar en
paralelo sin editar el mismo fichero.

`empresa_id` **nunca** se acepta en el cuerpo, la query ni la ruta: se deriva
siempre de `get_empresa_id` (constitucion III).
"""

from __future__ import annotations

from fastapi import APIRouter

from api.documentos.adjuntos import router as adjuntos_router
from api.documentos.bajas import router as bajas_router
from api.documentos.consulta import router as consulta_router

router = APIRouter(tags=["documentos"])
# Orden importante: las rutas estaticas (`/asiento/{id}`) se declaran antes que
# las de recurso (`/{documento_id}`) para que el comodin no las capture.
# El prefijo `/api/v1/documentos` lo lleva cada sub-router, igual que en
# `api/costcenters/` (SPEC-017): un `include_router` con prefijo y camino vacios
# es un error de FastAPI, y la ruta del listado global es exactamente `""`.
router.include_router(adjuntos_router)
router.include_router(consulta_router)
router.include_router(bajas_router)

__all__ = ["router"]
