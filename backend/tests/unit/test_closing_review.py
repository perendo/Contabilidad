"""Revision transversal del modulo de cierres (SPEC-028 T055).

Revisa por AST y por fuente las reglas que atraviesan US1, US2 y US3:

- el boundary ACID autoritativo es `get_db` + `flush()` (nunca `commit()`);
- ningun endpoint recibe `empresa_id` del cliente;
- todos los importes son `Decimal`/`NUMERIC(18,4)`, nunca `float`;
- existe el trigger DB `chk_journal_entry_fecha_abierta` (PostgreSQL y SQLite);
- cada endpoint lleva guarda de permiso y cada operacion existe en el catalogo;
- todo el dominio tiene docstrings y anotaciones de tipo.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2] / "src"
SERVICIOS = sorted((RAIZ / "services" / "closing").glob("*.py"))
MODELOS = sorted((RAIZ / "models" / "closing").glob("*.py"))
MODULOS_FUENTE = SERVICIOS + MODELOS + [RAIZ / "api" / "closing.py"]
FUNCIONES_ESPERADAS = (
    "cerrar_periodo_intermedio",
    "calcular_balanza_periodo",
    "calcular_regularizacion",
    "generar_cierre_anual",
    "solicitar_reapertura",
    "aprobar_reapertura",
    "rechazar_reapertura",
    "rectificar_reapertura",
    "validar_periodo_abierto",
    "validar_reapertura_autorizada",
    "next_numero_solicitud",
)


def _arbol(ruta: Path) -> ast.Module:
    return ast.parse(ruta.read_text(encoding="utf-8"))


# --- El boundary ACID es `get_db` + `flush()` -----------------------------


@pytest.mark.parametrize("ruta", SERVICIOS, ids=lambda p: p.name)
def test_ningun_servicio_hace_commit(ruta: Path) -> None:
    """El commit pertenece a `get_db`; los servicios solo hacen `flush()`."""
    arbol = _arbol(ruta)
    ofensas = [
        f"linea {nodo.lineno}: commit"
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Attribute) and nodo.attr in {"commit", "rollback"}
    ]
    assert ofensas == []


@pytest.mark.parametrize("ruta", SERVICIOS, ids=lambda p: p.name)
def test_ningun_servicio_abre_su_propia_transaccion(ruta: Path) -> None:
    """`async with async_session.begin()` duplicaria el boundary de `get_db`."""
    fuente = ruta.read_text(encoding="utf-8")
    assert "async_session.begin()" not in fuente
    assert "sessionmaker(" not in fuente


#: Modulos sin escritura propia: no auditan porque no abren una transaccion
#: (el `balance` se audita desde `periodo.py`, en la misma ACID, y `reglas_cierre`
#: y `secuencia` solo validan o reservan numeracion).
SIN_AUDITORIA_PROPIA = {
    "__init__.py",
    "errores.py",
    "reglas_cierre.py",
    "secuencia.py",
    "balanza.py",
    "utils.py",
}


@pytest.mark.parametrize("ruta", SERVICIOS, ids=lambda p: p.name)
def test_cada_servicio_audita(ruta: Path) -> None:
    """Cada mutacion escribe su registro de auditoria (constitucion II)."""
    if ruta.name in SIN_AUDITORIA_PROPIA:
        return
    fuente = ruta.read_text(encoding="utf-8")
    assert "audit_escribir" in fuente, ruta.name


@pytest.mark.parametrize("ruta", SERVICIOS, ids=lambda p: p.name)
def test_cada_servicio_tiene_docstrings(ruta: Path) -> None:
    arbol = _arbol(ruta)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if nodo.name.startswith("_"):
                continue
            assert ast.get_docstring(nodo), f"{ruta.name}:{nodo.name} sin docstring"


@pytest.mark.parametrize("ruta", SERVICIOS, ids=lambda p: p.name)
def test_las_funciones_publica_estan_anotadas(ruta: Path) -> None:
    arbol = _arbol(ruta)
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.AsyncFunctionDef) or nodo.name.startswith("_"):
            continue
        assert nodo.returns is not None, f"{ruta.name}:{nodo.name} sin retorno anotado"
        for argumento in nodo.args.args + nodo.args.kwonlyargs:
            if argumento.arg in {"self", "db", "session"}:
                continue
            assert argumento.annotation is not None, (
                f"{ruta.name}:{nodo.name}({argumento.arg}) sin anotacion"
            )


# --- La superficie de servicios esta completa ----------------------------


def test_los_servicios_previstos_existen() -> None:
    for nombre in FUNCIONES_ESPERADAS:
        encontrada = any(
            any(
                isinstance(nodo, ast.AsyncFunctionDef) and nodo.name == nombre
                for nodo in ast.walk(_arbol(ruta))
            )
            for ruta in SERVICIOS
        )
        assert encontrada, f"falta el servicio {nombre}"


def test_los_ficheros_previstos_existen() -> None:
    nombres = {ruta.name for ruta in SERVICIOS + MODELOS}
    for esperado in (
        "periodo.py",
        "balanza.py",
        "reglas_cierre.py",
        "cierre_anual.py",
        "reapertura.py",
        "errores.py",
        "secuencia.py",
        "periodo_cerrado.py",
        "balanza_periodo.py",
        "cierre_ejercicio.py",
        "solicitud_reapertura.py",
        "secuencia_reapertura.py",
    ):
        assert esperado in nombres, esperado


# --- Ningun endpoint acepta `empresa_id` del cliente ----------------------


def test_la_api_no_declara_empresa_id() -> None:
    arbol = _arbol(RAIZ / "api" / "closing.py")
    ofensas: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ClassDef) and any(
            isinstance(base, ast.Name) and base.id == "BaseModel" for base in nodo.bases
        ):
            for atributo in nodo.body:
                if (
                    isinstance(atributo, ast.AnnAssign)
                    and isinstance(atributo.target, ast.Name)
                    and atributo.target.id == "empresa_id"
                ):
                    ofensas.append(nodo.name)
    assert ofensas == []


def test_la_api_depende_de_get_empresa_id() -> None:
    """La empresa sale de la sesion (`X-Empresa-Activa` + JWT)."""
    fuente = (RAIZ / "api" / "closing.py").read_text(encoding="utf-8")
    assert "from api.deps import get_empresa_id, require_permission" in fuente
    assert "Depends(get_empresa_id)" in fuente


# --- El trigger de bloqueo existe en los dos motores ----------------------


def test_el_trigger_de_bloqueo_existe_en_postgresql() -> None:
    from db.migrate import MIGRATIONS_DIR

    contenido = (MIGRATIONS_DIR / "019_cierres.sql").read_text(encoding="utf-8")
    assert "CREATE TRIGGER chk_journal_entry_fecha_abierta" in contenido
    assert "ON journal_entry" in contenido
    assert "p.estado IN ('cerrado', 'cerrado_ajustado')" in contenido


def test_el_trigger_de_bloqueo_existe_en_sqlite() -> None:
    from db.triggers import _TRIGGERS_SQLITE

    disparadores = "\n".join(_TRIGGERS_SQLITE)
    assert "CREATE TRIGGER IF NOT EXISTS chk_journal_entry_fecha_abierta" in disparadores
    assert "periodo_cerrado" in disparadores


def test_el_disparo_del_motor_esta_en_el_registro_de_migraciones() -> None:
    from db.migrate import ORDEN_PREFERENTE

    assert "019_cierres.sql" in ORDEN_PREFERENTE
    # `020_export.sql` (SPEC-029) se aplica despues y no depende de 019.
    assert ORDEN_PREFERENTE.index("019_cierres.sql") < ORDEN_PREFERENTE.index(
        "020_export.sql"
    )


# --- RBAC -----------------------------------------------------------------


def test_ninguna_ruta_de_cierres_esta_sin_bypass() -> None:
    """SPEC-015: toda ruta lleva guarda y ninguna esta en las exclusiones."""
    from fastapi import FastAPI

    from api.closing import router
    from api.routes_registry import EXCLUSIONES_NO_BYPASS, inventario_permisos

    app = FastAPI()
    app.include_router(router)
    inventario = inventario_permisos(app)
    assert inventario, "el router no expone rutas"
    for fila in inventario:
        assert fila["permiso"] is not None, f"{fila['metodo']} {fila['path']}"
        assert (fila["metodo"], fila["path"]) not in EXCLUSIONES_NO_BYPASS
        assert fila["permiso"][0] == "cierres"


def test_las_operaciones_usadas_existen_en_el_catalogo() -> None:
    from fastapi import FastAPI

    from api.closing import router
    from api.routes_registry import inventario_permisos
    from services.security.catalogo import CATALOGO

    app = FastAPI()
    app.include_router(router)
    permisos = {fila["permiso"] for fila in inventario_permisos(app) if fila["permiso"]}
    for modulo, operacion in permisos:
        assert operacion in CATALOGO[modulo], f"{modulo}/{operacion}"
    assert {"ver", "crear", "editar", "aprobar", "cerrar"} <= set(CATALOGO["cierres"])


def test_el_modulo_cierres_esta_sembrado_en_los_tres_sitios() -> None:
    """SPEC-015: `catalogo.py`, `007_rbac.sql` y el trigger SQLite."""
    from db.triggers import _TRIGGERS_SQLITE
    from services.security.catalogo import CATALOGO

    assert "cierres" in CATALOGO
    from db.migrate import MIGRATIONS_DIR

    rbac = (MIGRATIONS_DIR / "007_rbac.sql").read_text(encoding="utf-8")
    assert "'cierres'" in rbac
    assert "SELECT 'cierres'" in "\n".join(_TRIGGERS_SQLITE)


# --- Importes -------------------------------------------------------------


@pytest.mark.parametrize("ruta", MODULOS_FUENTE, ids=lambda p: p.name)
def test_ningun_modulo_de_closing_usa_float(ruta: Path) -> None:
    arbol = _arbol(ruta)
    ofensas = [
        f"linea {nodo.lineno}: literal float"
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, float)
    ]
    assert ofensas == []


def test_las_tablas_de_importes_son_numeric_18_4() -> None:
    from sqlalchemy import Float

    from models.closing import BalanzaPeriodo, BalanzaPeriodoLinea, CierreEjercicio

    for modelo, campos in (
        (BalanzaPeriodo, ("total_debe", "total_haber", "resultado_provisional")),
        (BalanzaPeriodoLinea, ("debe", "haber", "saldo")),
        (CierreEjercicio, ("resultado_ejercicio",)),
    ):
        for campo in campos:
            columna = modelo.__table__.columns[campo]
            assert str(columna.type) == "NUMERIC(18, 4)", f"{modelo.__name__}.{campo}"
            assert not isinstance(columna.type, Float)


def test_la_api_formatea_los_importes_con_cuatro_decimales() -> None:
    import api.closing  # noqa: F401  (importa el router y valida los guards)
    from services.cashflow.utils import fmt

    for valor in ("0", "1", "1.5", "-3.25", None):
        resultado = fmt(valor)
        assert resultado.count(".") == 1
        assert len(resultado.split(".")[1]) == 4
