"""SPEC-015 Polish (T045): inventario completo de routers sin bypass.

Recorre todas las rutas registradas en la app (SPEC-001/002/004/005/007/008/
009/010/011/012/013/014/020) y verifica que ninguna ruta de datos queda sin
`require_permission` (SC-004). Solo se admiten las exclusiones de identidad,
tenencia y salud.
"""

from __future__ import annotations

from api.routes_registry import (
    EXCLUSIONES_NO_BYPASS,
    inventario_permisos,
    rutas_sin_permiso,
)


def test_app_completa_sin_rutas_de_datos_desprotegidas() -> None:
    from main import app

    assert rutas_sin_permiso(app) == []


def test_inventario_contiene_guards_reales() -> None:
    from main import app

    inventario = inventario_permisos(app)
    assert len(inventario) > 80
    con_guard = [i for i in inventario if i["permiso"] is not None]
    assert len(con_guard) > 60
    pares = {i["permiso"] for i in con_guard}
    assert ("treasury", "ver") in pares
    assert ("invoicing", "crear") in pares
    assert ("reporting", "ver") in pares
    assert ("acct", "cerrar") in pares


def test_exclusiones_son_las_esperadas() -> None:
    from main import app

    inventario = inventario_permisos(app)
    sin_guard = {
        (i["metodo"], i["path"]) for i in inventario if i["permiso"] is None
    }
    assert sin_guard == set(EXCLUSIONES_NO_BYPASS)
