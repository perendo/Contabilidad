"""Code review transversal del modulo de exportacion (SPEC-029 T050).

Revisa por AST lo que la constitution y el plan exigen: type hints completos,
docstrings en las funciones publicas, `flush()` dentro del boundary `get_db`
(nunca `async with async_session.begin()` en un servicio), guards RBAC en todos
los endpoints y serializacion centralizada.
"""

from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SERVICIOS = sorted((RAIZ / "src" / "services" / "export").glob("*.py"))
API = RAIZ / "src" / "api" / "export.py"
MODELOS = sorted((RAIZ / "src" / "models" / "export").glob("*.py"))
FUENTES = SERVICIOS + [API] + MODELOS


def _arbol(ruta: Path) -> ast.Module:
    return ast.parse(ruta.read_text(encoding="utf-8"))


def _decorador(nodo: ast.expr) -> str:
    """`ast.unparse` sobre un `Call` con `Call` interno (p. ej. `Depends(x)`)."""
    try:
        return ast.unparse(nodo)
    except (ValueError, AttributeError):  # pragma: no cover
        return ""


def _funciones(ruta: Path) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        nodo
        for nodo in ast.walk(_arbol(ruta))
        if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef)
    ]


def test_todas_las_funciones_tienen_type_hints() -> None:
    publicas = 0
    for ruta in FUENTES:
        for funcion in _funciones(ruta):
            if funcion.name.startswith("_") and not funcion.name.startswith("__"):
                continue
            publicas += 1
            argumentos = [
                a
                for a in funcion.args.args
                if a.arg not in ("self", "cls")
            ]
            for argumento in argumentos:
                assert argumento.annotation is not None, f"{ruta.name}:{funcion.name}({argumento.arg})"
            if funcion.returns is not None or funcion.name != "__init__":
                assert funcion.returns is not None, f"{ruta.name}:{funcion.name} sin retorno"
    assert publicas > 30, "el catalogo de funciones publicas parece incompleto"


def test_las_funciones_publicas_tienen_docstring() -> None:
    for ruta in FUENTES:
        for funcion in _funciones(ruta):
            if funcion.name.startswith("_"):
                continue
            assert ast.get_docstring(funcion), f"{ruta.name}:{funcion.name} sin docstring"


def test_los_modulos_tienen_docstring() -> None:
    for ruta in FUENTES:
        assert ast.get_docstring(_arbol(ruta)), f"{ruta.name} sin docstring de modulo"


def test_los_modelos_declaran_unica_y_empresa() -> None:
    for ruta in MODELOS:
        arbol = _arbol(ruta)
        clases = [n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef)]
        for clase in clases:
            bases = {ast.unparse(b) for b in clase.bases}
            if "Base" not in bases:
                continue
            cuerpo = ast.unparse(clase)
            assert "empresa_id" in cuerpo, f"{clase.name} sin empresa_id"
            assert "UniqueConstraint" in cuerpo or "primary_key=True" in cuerpo


def test_los_servicios_no_abren_transacciones_propias() -> None:
    """El boundary ACID del proyecto es `get_db`; un servicio no hace `begin()`."""
    for ruta in SERVICIOS:
        for nodo in ast.walk(_arbol(ruta)):
            if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
                continue
            nombre = nodo.func.attr
            receptor = ast.unparse(nodo.func.value)
            if nombre == "begin_nested":
                # Solo `persistir.exportar_tenant` usa un SAVEPOINT, y es para
                # deshacer la generacion fallida de forma atomica.
                assert ruta.name == "persistir.py", ruta.name
                assert "db" in receptor or "sesion" in receptor
            assert nombre != "begin", f"{ruta.name}: abre transaccion propia ({receptor}.begin)"


def test_uso_de_savepoint_y_flush_en_persistir() -> None:
    from services.export import persistir

    fuente = Path(persistir.__file__).read_text(encoding="utf-8")
    assert "db.begin_nested()" in fuente
    assert "await db.flush()" in fuente


def test_todos_los_endpoints_llevan_guard_rbac() -> None:
    arbol = _arbol(API)
    rutas = 0
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        decoradores = [_decorador(d) for d in nodo.decorator_list]
        if not any(d.startswith("router.") for d in decoradores):
            continue
        rutas += 1
        assert any("require_permission" in d for d in decoradores), nodo.name
    assert rutas == 8, f"se esperaban 8 endpoints y hay {rutas}"


def test_los_endpoints_usan_el_dependiente_de_empresa() -> None:
    arbol = _arbol(API)
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        decoradores = [_decorador(d) for d in nodo.decorator_list]
        if not any(d.startswith("router.") for d in decoradores):
            continue
        argumentos = {a.arg for a in nodo.args.args}
        assert "empresa_id" in argumentos, nodo.name


def test_serializacion_pasa_por_el_modulo_central() -> None:
    for ruta in SERVICIOS:
        if ruta.name in ("serializacion.py", "zip_generator.py"):
            continue
        arbol = _arbol(ruta)
        para = {
            nodo.func.id
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
        }
        assert "json" not in para, f"{ruta.name} serializa JSON por su cuenta"


def test_sha256_se_calcula_sobre_el_binario_completo() -> None:
    from services.export import zip_generator

    fuente = Path(zip_generator.__file__).read_text(encoding="utf-8")
    assert "hashlib.sha256(contenido).hexdigest()" in fuente
    assert "zipfile.ZIP_DEFLATED" in fuente
    assert "date_time=FECHA_ZIP" in fuente


def test_las_series_de_ejercicios_se_validan() -> None:
    from services.export.errores import ExportError
    from services.export.persistir import validar_rango

    validar_rango(None, None)
    validar_rango(2025, 2025)
    for argumentos, codigo in (((2026, 2025), "rango_invalido"), ((2025, None), "rango_incompleto")):
        try:
            validar_rango(*argumentos)
        except ExportError as exc:
            assert exc.code == codigo
        else:  # pragma: no cover
            raise AssertionError(f"se esperaba {codigo}")


def test_el_zip_tiene_limite_de_tamano() -> None:
    from models.export.exportacion import LIMITE_BYTES

    assert LIMITE_BYTES == 100 * 1024 * 1024


def test_la_config_sii_convive_con_la_de_spec_012() -> None:
    """`ConfigSii` (SPEC-029) y `ConfiguracionSII` (SPEC-012) son tablas distintas."""
    from base import Base

    assert "config_sii" in Base.metadata.tables
    assert "configuracion_sii" in Base.metadata.tables


def test_las_migraciones_declaran_el_modulo_de_rbac() -> None:
    rbac = (RAIZ / "migrations" / "007_rbac.sql").read_text(encoding="utf-8")
    assert "'export'" in rbac
    catalogo = (RAIZ / "src" / "services" / "security" / "catalogo.py").read_text(
        encoding="utf-8"
    )
    assert '"export"' in catalogo
    triggers = (RAIZ / "src" / "db" / "triggers.py").read_text(encoding="utf-8")
    assert "SELECT 'export' UNION ALL" in triggers
