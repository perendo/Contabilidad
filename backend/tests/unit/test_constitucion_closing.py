"""Constitucion aplicada a los cierres (SPEC-028 T052).

Verifica, para el modulo `closing`:

- **I (partida doble)**: el snapshot cuadra y cada asiento del paquete de
  cierre tiene Debe == Haber en `Decimal` exacto.
- **II (inmutabilidad)**: el balance de un periodo cerrado no admite UPDATE ni
  DELETE, y los asientos POSTED tampoco.
- **III (multi-tenancy)**: `empresa_id` esta en PK/indices/FKs de las cinco
  tablas y ningun endpoint acepta la empresa del cliente.
- **IV (correlatividad)**: `numero_solicitud` es unico y correlativo por
  (empresa, ejercicio).
- **Decimal / NUMERIC(18,4)**: ningun importe del dominio se trata como `float`.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from models.closing.balanza_periodo import BalanzaPeriodo, BalanzaPeriodoLinea
from models.closing.cierre_ejercicio import CierreEjercicio
from models.closing.periodo_cerrado import PeriodoCerrado
from models.closing.secuencia_reapertura import SecuenciaReapertura
from models.closing.solicitud_reapertura import SolicitudReapertura
from services.closing import balanza as modulo_balanza
from services.closing import cierre_anual as modulo_cierre_anual
from services.closing import periodo as modulo_periodo
from services.closing import reapertura as modulo_reapertura
from services.closing import reglas_cierre as modulo_reglas
from services.closing import secuencia as modulo_secuencia
from tests.unit import closing_support as soporte

EMPRESA = soporte.A
OTRA = soporte.B
EJERCICIO = 2026
RAIZ = Path(__file__).resolve().parents[2] / "src"
MODULOS = (
    modulo_reglas,
    modulo_balanza,
    modulo_periodo,
    modulo_cierre_anual,
    modulo_reapertura,
    modulo_secuencia,
)
TABLAS = (
    PeriodoCerrado,
    BalanzaPeriodo,
    BalanzaPeriodoLinea,
    CierreEjercicio,
    SolicitudReapertura,
    SecuenciaReapertura,
)


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


# --- Prohibido `float` -----------------------------------------------------


@pytest.mark.parametrize("modulo", MODULOS, ids=lambda m: m.__name__)
def test_ningun_modulo_declara_float(modulo) -> None:
    """SC-005: el dominio de cierres no tipa importes como `float`."""
    arbol = ast.parse(inspect.getsource(modulo))
    ofensas: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.AnnAssign) and ast.unparse(nodo.annotation) == "float":
            ofensas.append(f"linea {nodo.lineno}: anotacion float")
        if isinstance(nodo, ast.arg) and nodo.annotation is not None and ast.unparse(
            nodo.annotation
        ) == "float":
            ofensas.append(f"linea {nodo.lineno}: parametro float")
    assert ofensas == []


@pytest.mark.parametrize("modulo", MODULOS, ids=lambda m: m.__name__)
def test_ningun_modulo_usa_el_literal_float(modulo) -> None:
    arbol = ast.parse(inspect.getsource(modulo))
    ofensas = [
        f"linea {nodo.lineno}"
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, float)
    ]
    assert ofensas == []


def test_los_importes_de_las_tablas_son_numeric_18_4() -> None:
    """SC-005: los campos de importe son `NUMERIC(18, 4)` en el modelo."""
    importes = {
        "balanza_periodo": (BalanzaPeriodo, ("total_debe", "total_haber", "resultado_provisional")),
        "balanza_periodo_linea": (BalanzaPeriodoLinea, ("debe", "haber", "saldo")),
        "cierre_ejercicio": (CierreEjercicio, ("resultado_ejercicio",)),
    }
    for nombre, (modelo, campos) in importes.items():
        for campo in campos:
            columna = modelo.__table__.columns[campo]
            assert str(columna.type) == "NUMERIC(18, 4)", f"{nombre}.{campo}"


def test_las_tablas_de_closing_no_declaran_float() -> None:
    for modelo in TABLAS:
        for columna in modelo.__table__.columns:
            assert not isinstance(columna.type, __import__("sqlalchemy").Float), (
                f"{modelo.__tablename__}.{columna.name}"
            )


# --- Constitucion III · multi-tenancy ------------------------------------


@pytest.mark.parametrize("modelo", TABLAS, ids=lambda m: m.__tablename__)
def test_toda_tabla_lleva_empresa_id(modelo) -> None:
    assert "empresa_id" in modelo.__table__.columns


@pytest.mark.parametrize("modelo", TABLAS, ids=lambda m: m.__tablename__)
def test_toda_tabla_tiene_indice_por_empresa(modelo) -> None:
    indices = {
        tuple(columna.name for columna in indice.columns) for indice in modelo.__table__.indexes
    }
    uniques = {
        tuple(columna.name for columna in indice.columns)
        for indice in modelo.__table__.constraints
        if indice.__class__.__name__ == "UniqueConstraint"
    }
    candidatos = indices | uniques
    assert any(columnas[0] == "empresa_id" for columnas in candidatos), modelo.__tablename__


def test_las_fk_de_closing_son_compuestas_por_empresa() -> None:
    """Ninguna FK alude a `id` sin `empresa_id`: constitution III."""
    from sqlalchemy import ForeignKeyConstraint

    for modelo in TABLAS:
        for constraint in modelo.__table__.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue
            locales = list(constraint.column_keys)
            assert "empresa_id" in locales, f"{modelo.__tablename__}: {locales}"


def test_las_fk_de_reapertura_apuntan_a_tablas_multi_tenant() -> None:
    """Toda FK que referencia un `id` referencia tambien `empresa_id`/`tenant_id`."""
    for modelo in TABLAS:
        for constraint in modelo.__table__.constraints:
            if constraint.__class__.__name__ != "ForeignKeyConstraint":
                continue
            destinos = [fk.target_fullname.rsplit(".", 1)[-1] for fk in constraint.elements]
            locales = list(constraint.column_keys)
            if "id" in destinos:
                assert any(
                    destino in ("empresa_id", "tenant_id") for destino in destinos
                ), f"{modelo.__tablename__}: {locales} -> {destinos}"


def test_ningun_endpoint_acepta_empresa_id_del_cliente() -> None:
    """III: la empresa activa sale de la sesion, nunca del path ni del body."""
    from fastapi import APIRouter
    from fastapi.routing import APIRoute

    from api.closing import CerrarIntermedioBody, CierreAnualBody, ReaperturaBody

    for modelo in (CerrarIntermedioBody, CierreAnualBody, ReaperturaBody):
        assert "empresa_id" not in modelo.model_fields

    from api.closing import router

    def _rutas(rutas) -> list[APIRoute]:
        encontradas: list[APIRoute] = []
        for ruta in rutas:
            original = getattr(ruta, "original_router", None)
            if original is not None:
                encontradas.extend(_rutas(list(original.routes)))
            elif isinstance(ruta, APIRoute):
                encontradas.append(ruta)
        return encontradas

    assert isinstance(router, APIRouter)
    for ruta in _rutas(list(router.routes)):
        assert "{empresa_id}" not in ruta.path, ruta.path


async def test_el_snapshot_y_el_cierre_no_se_ven_desde_otra_empresa(db_session) -> None:
    from services.closing.errores import ClosingError
    from services.closing.periodo import obtener_balanza_periodo

    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    periodo = await soporte.periodo(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, numero=3
    )
    assert periodo is not None
    with pytest.raises(ClosingError) as exc:
        await obtener_balanza_periodo(db_session, empresa_id=OTRA, periodo_id=periodo.id)
    assert exc.value.status_code == 404


# --- Constitucion IV · correlatividad -------------------------------------


def test_numero_solicitud_es_unico_por_empresa_y_ejercicio() -> None:
    uniques = {
        tuple(columna.name for columna in indice.columns)
        for indice in SolicitudReapertura.__table__.indexes
    }
    uniques |= {
        tuple(columna.name for columna in constraint.columns)
        for constraint in SolicitudReapertura.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("empresa_id", "ejercicio", "numero_solicitud") in uniques


async def test_la_secuencia_garantiza_correlatividad_sin_saltos(db_session) -> None:
    from services.closing.secuencia import next_numero_solicitud

    assert [await next_numero_solicitud(db_session, EMPRESA, EJERCICIO) for _ in range(3)] == [
        1,
        2,
        3,
    ]


async def test_el_cierre_anual_usa_la_numeracion_del_diario(db_session) -> None:
    """Los asientos del cierre llevan numero correlativo del diario (SPEC-002)."""
    from models.acct.journal import JournalEntryTipo
    from services.closing.cierre_anual import generar_cierre_anual

    async def _preparar() -> None:
        await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO)
        await soporte.plantar_pyg(db_session, EMPRESA)
        await soporte.publicar_asiento(
            db_session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 1, 15),
            lineas=[
                {"cuenta": "1110", "haber": "17000.0000"},
                {"cuenta": "2100", "debe": "17000.0000"},
            ],
        )
        await soporte.publicar_asiento(
            db_session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 3, 31),
            lineas=[
                {"cuenta": "7000", "haber": "10000.0000"},
                {"cuenta": "4300", "debe": "10000.0000"},
            ],
        )
        await soporte.cerrar_meses(
            db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=range(1, 13)
        )

    await _preparar()
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test", abrir_siguiente=False
    )
    regularizacion = resultado["asiento_regularizacion"]
    assert regularizacion is not None
    assert regularizacion.tipo is JournalEntryTipo.REGULARIZACION
    assert regularizacion.numero_asiento == 3
    await db_session.rollback()


# --- Constitucion I · partida doble ---------------------------------------


async def test_el_snapshot_solo_se_persiste_si_cuadra(db_session) -> None:
    """`total_debe = total_haber` como CHECK en la propia tabla."""
    from sqlalchemy import CheckConstraint

    sql = " ".join(
        str(c.sqltext)
        for c in BalanzaPeriodo.__table__.constraints
        if isinstance(c, CheckConstraint)
    )
    assert "total_debe = total_haber" in sql


async def test_el_balance_sin_asientos_cuadra_a_cero(db_session) -> None:
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    periodo = await soporte.periodo(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, numero=3
    )
    assert periodo is not None and periodo.balanza_id is not None
    balanza = await db_session.get(BalanzaPeriodo, periodo.balanza_id)
    assert balanza is not None
    assert balanza.total_debe == balanza.total_haber == Decimal("0.0000")
    await db_session.rollback()


# --- Constitucion II · inmutabilidad --------------------------------------


@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE balanza_periodo SET n_lineas = 0 WHERE id = :id",
        "DELETE FROM balanza_periodo WHERE id = :id",
    ],
)
async def test_el_snapshot_rechaza_update_y_delete(db_session, sentencia: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 10),
        lineas=[
            {"cuenta": "7000", "haber": "500.0000"},
            {"cuenta": "4300", "debe": "500.0000"},
        ],
    )
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    periodo = await soporte.periodo(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, numero=3
    )
    assert periodo is not None and periodo.balanza_id is not None
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(text(sentencia), {"id": periodo.balanza_id.hex})
    assert "inmutable" in str(exc.value).lower()
    await db_session.rollback()


async def test_el_cierre_anual_no_se_borra(db_session) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from services.closing.cierre_anual import generar_cierre_anual

    await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO)
    await soporte.plantar_pyg(db_session, EMPRESA)
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 1, 15),
        lineas=[
            {"cuenta": "1110", "haber": "100.0000"},
            {"cuenta": "2100", "debe": "100.0000"},
        ],
    )
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=range(1, 13)
    )
    resultado = await generar_cierre_anual(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, actor="test", abrir_siguiente=False
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("DELETE FROM cierre_ejercicio WHERE id = :id"),
            {"id": resultado["cierre"].id.hex},
        )
    await db_session.rollback()


def test_la_migracion_declara_los_triggers_de_inmutabilidad() -> None:
    from db.migrate import MIGRATIONS_DIR

    contenido = (MIGRATIONS_DIR / "019_cierres.sql").read_text(encoding="utf-8")
    assert "trg_balanza_periodo_append_only_update" in contenido
    assert "trg_balanza_periodo_linea_append_only_delete" in contenido
    assert "trg_cierre_ejercicio_no_delete" in contenido
    assert "chk_journal_entry_fecha_abierta" in contenido


def test_los_offsets_de_decimales_se_respetan() -> None:
    """Todos los importes de la API viajan como cadenas de 4 decimales."""
    from services.cashflow.utils import fmt

    assert fmt(Decimal(0)) == "0.0000"
    assert fmt(Decimal("1234.5")) == "1234.5000"
    assert fmt(None) == "0.0000"
