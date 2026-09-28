"""Entrypoint de la aplicación FastAPI (G1).

Registra los routers versionados (``/api/v1``), habilita CORS para el frontend
y expone ``/health``. Arranque (desde ``backend/``, con ``src`` en el path):

    $env:PYTHONPATH="src"; ..\\.venv\\Scripts\\python.exe -m uvicorn main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.acct.accounts import router as accounts_router
from api.auth.auth import router as auth_router
from api.catalogo import router as catalogo_router
from api.ciclo.routes import router as ciclo_router
from api.closing import router as cierres_router
from api.companies import router as companies_router
from api.costcenters.routes import router as costcenters_router
from api.cuentas_anuales.routes import router as cuentas_anuales_router
from api.documentos import router as documentos_router
from api.export import router as export_router
from api.fiscal.routes import router as fiscal_vat_router
from api.forex.routes import router as forex_router
from api.importexport import router as importexport_router
from api.inmovilizado.routes import router as inmovilizado_router
from api.invoicing.facturas import router as facturas_router
from api.invoicing.series import router as series_router
from api.journal.asientos import router as asientos_router
from api.journal.journal import router as journal_router
from api.navigation import favoritos_router, resumenes_router
from api.navigation import router as navigation_router
from api.ngo.routes import router as ngo_router
from api.presupuestos import router as presupuestos_router
from api.rbac import router as rbac_router
from api.reconciliation import router as reconciliation_router
from api.reports.fiscal import router as fiscal_router
from api.reports.informes import router as informes_router
from api.templates import router as templates_router
from api.tesoreria import router as tesoreria_router
from api.thirdparty import router as thirdparty_router
from api.treasury.routes import router as treasury_router
from config import settings
from database import engine
from services.auth.security import comprobar_configuracion

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Avisos de seguridad de la configuracion (p. ej. SECRET_KEY ausente).
    for aviso in comprobar_configuracion():
        logger.warning("arranque: %s", aviso)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(accounts_router)
app.include_router(catalogo_router)
app.include_router(journal_router)
app.include_router(importexport_router)
app.include_router(asientos_router)
# SPEC-030: el prefijo `/api/v1/documentos` no colisiona con ninguna ruta
# existente (research D21), asi que el orden es irrelevante para el
# funcionamiento; se registra tras `asientos_router` e `importexport_router` por
# documentacion, no por necesidad.
app.include_router(documentos_router)
app.include_router(reconciliation_router)
app.include_router(informes_router)
app.include_router(fiscal_router)
app.include_router(thirdparty_router)
app.include_router(templates_router)
app.include_router(treasury_router)
app.include_router(ciclo_router)
app.include_router(facturas_router)
app.include_router(series_router)
app.include_router(cuentas_anuales_router)
app.include_router(fiscal_vat_router)
app.include_router(inmovilizado_router)
app.include_router(rbac_router)
app.include_router(forex_router)
app.include_router(costcenters_router)
app.include_router(ngo_router)
app.include_router(presupuestos_router)
app.include_router(tesoreria_router)
app.include_router(cierres_router)
app.include_router(export_router)
# SPEC-031: `/api/v1/contexto` no colisiona con ninguna ruta existente (verificado
# por `test_app.py`), asi que el orden es irrelevante para el funcionamiento. Se
# registra el ultimo porque es la lectura que consume el shell y no depende de
# ningun otro router.
app.include_router(navigation_router)
# Los favoritos cuelgan de `/api/v1/favoritos`, no de `/api/v1/contexto`: es otro
# recurso, con su propio ciclo de vida y sus propias escrituras auditadas.
app.include_router(favoritos_router)
# Los resúmenes de superficie (US5) cuelgan de `/api/v1/resumenes`, su propio recurso
# de lectura: cuenta datos de seis áreas y es lo que impide que el panel pida seis
# veces lo mismo en cada cambio de superficie.
app.include_router(resumenes_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}
