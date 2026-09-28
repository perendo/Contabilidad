"""Registro e introspección de rutas protegidas por `require_permission`
(SPEC-015). Sólo identidad/tenencia/salud quedan fuera de la matriz (los
endpoints de `mis-permisos` se conceden a sí mismos); cualquier otra ruta de
datos sin guard debe ser detectada por `inventario_permisos`.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.routing import APIRoute

EXCLUSIONES_NO_BYPASS: tuple[tuple[str, str], ...] = (
    ("GET", "/health"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/switch-company"),
    ("GET", "/api/v1/companies"),
    ("POST", "/api/v1/companies"),
    ("GET", "/api/v1/permisos/mis-permisos"),
)


def guard_de_ruta(route: APIRoute) -> tuple[str, str] | None:
    """Return ``(modulo, operacion)`` if the route carries a
    ``require_permission`` dependency, else ``None``."""
    for dep in route.dependencies:
        marca = getattr(getattr(dep, "dependency", None), "_rbac_permiso", None)
        if marca is not None:
            return (marca[0], marca[1])
    return None


def _iter_api_routes(routes: list) -> Iterator[APIRoute]:
    """Recorre rutas planas y routers incluidos (``_IncludedRouter``).

    Las versiones recientes de FastAPI envuelven `include_router` en un objeto
    perezoso; se desciende por `original_router.routes` para llegar a los
    `APIRoute` reales.
    """
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_api_routes(list(original.routes))
            continue
        if isinstance(route, APIRoute):
            yield route


def inventario_permisos(app: FastAPI) -> list[dict]:
    """Listado de rutas con su guard de permiso (nulo si no tiene)."""
    inventario: list[dict] = []
    for route in _iter_api_routes(list(app.routes)):
        metodos = sorted(m for m in route.methods or [] if m not in ("HEAD", "OPTIONS"))
        if not metodos:
            continue
        for metodo in metodos:
            inventario.append(
                {
                    "metodo": metodo,
                    "path": route.path,
                    "permiso": guard_de_ruta(route),
                }
            )
    return inventario


def rutas_sin_permiso(app: FastAPI) -> list[str]:
    """Rutas de datos que deberían estar protegidas y no lo están."""
    excluidas = set(EXCLUSIONES_NO_BYPASS)
    sin_guard: list[str] = []
    for item in inventario_permisos(app):
        clave = (item["metodo"], item["path"])
        if clave in excluidas:
            continue
        if item["permiso"] is None:
            sin_guard.append(f"{item['metodo']} {item['path']}")
    return sin_guard