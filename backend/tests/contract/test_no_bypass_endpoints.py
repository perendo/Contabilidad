"""SPEC-015 US2 (T026): contrato de no-bypass por router.

Cada endpoint de datos declara `require_permission`; el inventario no deja
rutas de negocio sin guard.
"""

from __future__ import annotations

from fastapi import FastAPI

from api.acct.accounts import router as accounts_router
from api.journal.journal import router as journal_router
from api.rbac import router as rbac_router
from api.routes_registry import inventario_permisos, rutas_sin_permiso


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(rbac_router)
    app.include_router(accounts_router)
    app.include_router(journal_router)
    return app


def test_ninguna_ruta_de_datos_sin_guard() -> None:
    # en el subconjunto (rbac/accounts/journal) `mis-permisos` es la unica
    # ruta sin guard y esta excluida por diseno
    app = _app()
    sin_guard = rutas_sin_permiso(app)
    assert sin_guard == [], sin_guard


def test_cada_metodo_de_negocio_declara_par_modulo_operacion() -> None:
    app = _app()
    guards = {
        (i["metodo"], i["path"]): i["permiso"]
        for i in inventario_permisos(app)
        if i["permiso"] is not None
    }
    assert guards[("GET", "/api/v1/accounts/tree")] == ("acct", "ver")
    assert guards[("POST", "/api/v1/accounts")] == ("acct", "crear")
    assert guards[("PATCH", "/api/v1/accounts/{account_id}")] == ("acct", "editar")
    assert guards[("POST", "/api/v1/journal/entries")] == ("acct", "crear")
    assert guards[("POST", "/api/v1/journal/entries/{entry_id}/post")] == ("acct", "editar")
    assert guards[("POST", "/api/v1/permisos/matriz")] == ("rbac", "configurar")
