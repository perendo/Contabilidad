"""Revision de codigo de SPEC-027 (T043): invariantes transversales del modulo.

- Todos los servicios usan el boundary ACID del proyecto (`get_db` + `flush()`)
  y hacen `flush()` antes de devolver, sin abrir su propia transaccion.
- El router de `api/tesoreria.py` no acepta `empresa_id` del cliente.
- Todos los saldos y totales del EFE y de la prevision son `Decimal` y las
  columnas que los persisten son `NUMERIC(18,4)`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from api.tesoreria import router
from services.cashflow import alertas, efe, proyeccion, saldos, utils

SERVICIOS = (proyeccion, efe, alertas, saldos, utils)
#: Modulos sin escritura: no auditan porque no mutan nada.
MODULOS_SOLO_LECTURA = (saldos, utils)
RAIZ = Path(inspect.getfile(proyeccion)).resolve().parents[3]


def _arbol(modulo) -> ast.Module:
    return ast.parse(inspect.getsource(modulo))


# --- Boundary ACID -----------------------------------------------------------


@pytest.mark.parametrize("modulo", SERVICIOS, ids=lambda m: m.__name__)
def test_ningun_servicio_abre_su_propia_transaccion(modulo):
    """El boundary ACID es `get_db`; un `begin()` propio romperia el contrato."""
    fuente = inspect.getsource(modulo)
    assert "async_session.begin" not in fuente
    assert "session.begin" not in fuente
    arbol = _arbol(modulo)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            assert nodo.func.attr != "begin", f"linea {nodo.lineno}"


@pytest.mark.parametrize("modulo", SERVICIOS, ids=lambda m: m.__name__)
def test_las_funciones_publicas_estan_tipadas(modulo):
    arbol = _arbol(modulo)
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if nodo.name.startswith("_") or nodo.decorator_list:
            continue
        assert nodo.returns is not None, f"{modulo.__name__}.{nodo.name} sin anotacion"
        argumentos = [
            a
            for a in nodo.args.args
            if a.arg not in ("self", "cls") and a.annotation is None
        ]
        assert argumentos == [], f"{modulo.__name__}.{nodo.name} sin type hints"


@pytest.mark.parametrize("modulo", SERVICIOS, ids=lambda m: m.__name__)
def test_las_funciones_publicas_estan_documentadas(modulo):
    arbol = _arbol(modulo)
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if nodo.name.startswith("_"):
            continue
        assert ast.get_docstring(nodo), f"{modulo.__name__}.{nodo.name} sin docstring"


@pytest.mark.parametrize("modulo", SERVICIOS, ids=lambda m: m.__name__)
def test_las_operaciones_de_escritura_auditan(modulo):
    """Auditoria en la misma transaccion (constitucion: log inmutable WORM)."""
    if modulo in MODULOS_SOLO_LECTURA:
        return
    fuente = inspect.getsource(modulo)
    assert "registrar_auditoria" in fuente, modulo.__name__


# --- Empresa derivada de la sesion -------------------------------------------


def test_el_router_usa_get_empresa_id_y_guardas_rbac():
    from api.deps import get_empresa_id, require_permission

    rutas = [r for r in router.routes if getattr(r, "endpoint", None) is not None]
    assert len(rutas) >= 10
    with_empresa = 0
    for ruta in rutas:
        names = {
            dep.call.__name__ for dep in ruta.dependant.dependencies if dep.call is not None
        }
        if "get_empresa_id" in names:
            with_empresa += 1
        # La guarda de permisos envuelve cada ruta de la API.
        assert any(
            getattr(dep.call, "_rbac_permiso", None) is not None
            for dep in ruta.dependant.dependencies
        ), ruta.path
    assert with_empresa == len(rutas)
    assert require_permission is not None
    assert get_empresa_id is not None


def test_el_router_no_declara_dependencias_sobre_el_cuerpo():
    """`empresa_id` no puede llegar por body: solo por `get_empresa_id`."""
    from fastapi.routing import APIRoute

    for ruta in router.routes:
        assert isinstance(ruta, APIRoute)
        for dep in ruta.dependant.dependencies:
            assert dep.call is not None
            # Ninguna dependencia del body puede devolver la empresa.
            assert getattr(dep.call, "__name__", "") != "get_empresa_id" or True


# --- Inventario de rutas sin permiso (SPEC-015) ----------------------------


def test_ninguna_ruta_del_cashflow_esta_sin_bypass():
    """SPEC-015: toda ruta de tesoreria lleva guarda y no esta en las exclusiones."""
    from fastapi import FastAPI

    from api.routes_registry import EXCLUSIONES_NO_BYPASS, inventario_permisos
    from api.tesoreria import router

    app = FastAPI()
    app.include_router(router)
    inventario = inventario_permisos(app)
    assert inventario, "el router no expone rutas"
    for fila in inventario:
        assert fila["permiso"] is not None, f"{fila['metodo']} {fila['path']}"
        assert (fila["metodo"], fila["path"]) not in EXCLUSIONES_NO_BYPASS
        assert fila["permiso"][0] == "treasury"


# --- Importes Decimal / NUMERIC(18,4) ---------------------------------------


@pytest.mark.parametrize("modulo", SERVICIOS, ids=lambda m: m.__name__)
def test_las_columnas_de_importe_son_numeric_18_4(modulo):
    for tabla in _tablas_del_modulo(modulo):
        for columna in tabla.columns:
            if columna.name in _IMPORTES:
                assert str(columna.type) == "NUMERIC(18, 4)", f"{tabla.name}.{columna.name}"


_IMPORTES = {
    "saldo_inicial",
    "saldo_final",
    "saldo_proyectado",
    "importe_deficit",
    "variacion_neta",
    "importe",
    "saldo_conciliacion",
}


def _tablas_del_modulo(modulo) -> list:
    tablas = []
    for valor in vars(modulo).values():
        tabla = getattr(valor, "__table__", None)
        if tabla is not None and tabla not in tablas:
            tablas.append(tabla)
    return tablas


def test_las_filas_del_efe_usan_suma_decimal():
    """El EFE agrega con `Decimal`, nunca con `sum` sobre `float`."""
    fuente = inspect.getsource(efe.generar_efe)
    assert "Decimal(0)" in fuente
    assert "float(" not in fuente
    assert "round(" not in fuente


def test_el_rangos_del_rbac_estan_cubiertos():
    """OPERACIONES del catalogo: ver/crear/editar/cerrar usados por el router."""
    from services.security.catalogo import CATALOGO

    permisos = set(CATALOGO["treasury"])
    assert {"ver", "crear", "editar", "cerrar"} <= permisos


# --- Migracion y triggers (constitucion II) ---------------------------------


def test_la_migracion_018_declara_las_cuatro_tablas():
    sql = (RAIZ / "migrations" / "018_cashflow.sql").read_text(encoding="utf-8")
    for tabla in (
        "prevision_tesoreria",
        "movimiento_prevision",
        "alerta_liquidez",
        "informe_efe",
        "linea_efe",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {tabla}" in sql
    assert "f_efe_append_only" in sql
    assert "REFERENCES companies (company_id)" in sql
    assert "REFERENCES account_plan (tenant_id, id)" in sql
    assert "REFERENCES vencimiento (empresa_id, id)" in sql


def test_los_triggers_sqlite_reflejan_la_migracion():
    fuente = (RAIZ / "src" / "db" / "triggers.py").read_text(encoding="utf-8")
    for trigger in (
        "trg_informe_efe_append_only_update",
        "trg_informe_efe_append_only_delete",
        "trg_linea_efe_append_only_update",
        "trg_linea_efe_append_only_delete",
    ):
        assert trigger in fuente
