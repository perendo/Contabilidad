"""Entrypoint FastAPI (G1): app, routers, CORS y health."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from main import app

RUTAS_ESPERADAS = {
    "/api/v1/auth/login",
    "/api/v1/auth/me",
    "/api/v1/companies",
    "/api/v1/accounts/tree",
    "/api/v1/remesas",
    "/api/v1/devoluciones",
}


def test_app_es_fastapi():
    assert isinstance(app, FastAPI)


def test_health():
    respuesta = TestClient(app).get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "ok"


def test_routers_registrados():
    esquema = TestClient(app).get("/openapi.json").json()
    rutas = set(esquema["paths"].keys())
    assert RUTAS_ESPERADAS <= rutas, RUTAS_ESPERADAS - rutas


def test_openapi_disponible():
    assert TestClient(app).get("/openapi.json").status_code == 200


def test_cors_habilitado():
    respuesta = TestClient(app).options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert respuesta.status_code == 200
    assert (
        respuesta.headers.get("access-control-allow-origin")
        == "http://localhost:3000"
    )


def test_no_hay_colisiones_de_ruta_en_la_app_real() -> None:
    """Regression: `/api/v1/exportaciones` es de SPEC-029 y `/api/v1/fiscal/exportaciones`
    de SPEC-012. Si vuelve a duplicarse, el router registrado primero (fiscal)
    ocultaria los endpoints de la exportacion integral del tenant."""
    from fastapi.routing import APIRoute

    from api.routes_registry import _iter_api_routes
    from main import app

    vistas: dict[tuple[tuple[str, ...], str], list[str]] = {}
    for ruta in _iter_api_routes(list(app.routes)):
        if not isinstance(ruta, APIRoute):
            continue
        metodos = tuple(
            sorted(m for m in (ruta.methods or ()) if m not in ("HEAD", "OPTIONS"))
        )
        if not metodos:
            continue
        vistas.setdefault((metodos, ruta.path), []).append(ruta.name)
    colisiones = {k: v for k, v in vistas.items() if len(v) > 1}
    assert not colisiones, colisiones


def test_las_dos_exportaciones_viven_en_rutas_distintas() -> None:
    from fastapi.routing import APIRoute

    from api.routes_registry import _iter_api_routes
    from main import app

    rutas = {
        ruta.path
        for ruta in _iter_api_routes(list(app.routes))
        if isinstance(ruta, APIRoute)
    }
    assert "/api/v1/exportaciones" in rutas
    assert "/api/v1/exportaciones/{exportacion_id}/descarga" in rutas
    assert "/api/v1/exportaciones/{exportacion_id}/verificar" in rutas
    assert "/api/v1/fiscal/exportaciones" in rutas
    assert "/api/v1/fiscal/exportaciones/{exportacion_id}/descargar" in rutas
