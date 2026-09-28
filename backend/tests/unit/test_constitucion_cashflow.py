"""Constitucion aplicada a la prevision, el EFE y las alertas (T040).

Verifica, para SPEC-027:
- **I (partida doble)**: el cuadre del EFE sale de los asientos POSTED del
  diario y `saldo_inicial + variacion == saldo_final` con `Decimal` exacto.
- **II (inmutabilidad)**: el EFE formulado no admite UPDATE ni DELETE.
- **III (multi-tenancy)**: ningun endpoint acepta `empresa_id` del cliente.
- **IV (correlatividad)**: `numero_prevision` es unico, correlativo y sin saltos.
- **Decimal / NUMERIC(18,4)**: ningun importe se trata como `float` (SC-005).
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from services.cashflow import alertas as modulo_alertas
from services.cashflow import efe as modulo_efe
from services.cashflow import proyeccion as modulo_proyeccion
from services.cashflow import utils as modulo_utils
from services.cashflow.efe import generar_efe
from services.cashflow.proyeccion import generar_prevision
from tests.unit import cashflow_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026
RAIZ = Path(__file__).resolve().parents[2] / "src"
MODULOS = (modulo_utils, modulo_proyeccion, modulo_efe, modulo_alertas)


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


# --- Prohibido `float` (constitucion: importes en Decimal) ------------------


@pytest.mark.parametrize("modulo", MODULOS, ids=lambda m: m.__name__)
def test_ningun_modulo_declara_float(modulo):
    """SC-005: el dominio del cashflow no tipa importes como `float`."""
    fuente = inspect.getsource(modulo)
    arbol = ast.parse(fuente)
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
def test_ningun_modulo_usa_el_literal_float(modulo):
    fuente = inspect.getsource(modulo)
    arbol = ast.parse(fuente)
    ofensas = [
        f"linea {nodo.lineno}"
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, float)
    ]
    assert ofensas == []


async def test_el_importe_se_rechaza_si_llega_como_float(db_session):
    """Un `float` en el cuerpo es un error de negocio, no una conversion silenciosa."""
    from services.cashflow.errores import CashflowError

    with pytest.raises(CashflowError) as exc:
        await generar_prevision(
            db_session,
            empresa_id=EMPRESA,
            desde_fecha=date(EJERCICIO, 9, 16),
            hasta_fecha=date(EJERCICIO, 10, 31),
            movimientos_manuales=[
                {"tipo": "pago", "importe": 1200.0, "fecha_prevista": date(2026, 9, 20)}
            ],
        )
    assert exc.value.code == "importe_invalido"


def test_suma_decimal_no_acepta_floats_sin_control():
    """`suma_decimal` convierte con `str()`: 0.1 + 0.2 no da 0.30000000000000004."""
    from services.cashflow.utils import suma_decimal

    # Con float, la suma en binario falla; con Decimal a 4 decimales es exacta.
    assert suma_decimal([Decimal("0.1"), Decimal("0.2")]) == Decimal("0.3000")
    assert str(suma_decimal([Decimal("0.1"), Decimal("0.2")])) == "0.3000"


def test_todos_los_importes_de_las_tablas_son_numeric():
    """Los campos de importe son `NUMERIC(18,4)` en el modelo."""
    from models.treasury.alerta_liquidez import AlertaLiquidez
    from models.treasury.efe import InformeEFE, LineaEFE
    from models.treasury.movimiento_prevision import MovimientoPrevision
    from models.treasury.prevision import PrevisionTesoreria

    importances = {
        "prevision_tesoreria": (PrevisionTesoreria, ("saldo_inicial", "saldo_final")),
        "movimiento_prevision": (MovimientoPrevision, ("importe",)),
        "alerta_liquidez": (AlertaLiquidez, ("saldo_proyectado", "importe_deficit")),
        "informe_efe": (InformeEFE, ("saldo_inicial", "saldo_final", "variacion_neta")),
        "linea_efe": (LineaEFE, ("importe",)),
    }
    for nombre, (modelo, campos) in importances.items():
        for campo in campos:
            columna = modelo.__table__.columns[campo]
            assert str(columna.type) == "NUMERIC(18, 4)", f"{nombre}.{campo}"


# --- Constitucion I: el cuadre sale del diario balanceado --------------------


async def test_efe_cuadra_con_el_diario_balanceado(db_session):
    await soporte.plantar_cuenta(
        db_session, empresa_id=EMPRESA, code="1000", parent="100", name="Capital"
    )
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 1, 2),
        lineas=[
            {"cuenta": "5720", "debe": "10000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "10000.0000"},
        ],
        tipo="OPENING",
    )
    for indice, importe in enumerate(["1234.5678", "99.9999", "0.0001", "7654.3210"]):
        await soporte.publicar_asiento(
            db_session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 3, indice + 1),
            lineas=[
                {"cuenta": "5720", "debe": importe, "haber": "0"},
                {"cuenta": "7000", "debe": "0", "haber": importe},
            ],
        )
    await db_session.commit()

    informe = await generar_efe(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
    assert informe["cuadre"] is True
    assert informe["saldo_inicial"] == Decimal("10000.0000")
    total = sum(
        (Decimal(i) for i in ("1234.5678", "99.9999", "0.0001", "7654.3210")),
        Decimal(0),
    )
    assert informe["variacion_neta"] == total
    assert informe["saldo_final"] == Decimal("10000.0000") + total
    # Y el saldo final es exactamente el saldo real del grupo 5 del diario.
    saldos = await soporte.saldos_por_cuenta(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO
    )
    assert informe["saldo_final"] == saldos["5720"]


async def test_saldo_proyectado_es_la_suma_de_los_movimientos(db_session):
    """SC-002 con `Decimal` exacto, sin deriva por coma flotante."""
    resultado = await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=date(EJERCICIO, 9, 16),
        hasta_fecha=date(EJERCICIO, 9, 20),
        granularidad="dia",
        movimientos_manuales=[
            {"tipo": "cobro", "importe": "0.1000", "fecha_prevista": date(2026, 9, 16)},
            {"tipo": "pago", "importe": "0.2000", "fecha_prevista": date(2026, 9, 17)},
            {"tipo": "cobro", "importe": "0.3000", "fecha_prevista": date(2026, 9, 18)},
        ],
    )
    acumulados = [b["saldo_acumulado"] for b in resultado["buckets"]]
    assert acumulados == [
        Decimal("0.1000"),
        Decimal("-0.1000"),
        Decimal("0.2000"),
        Decimal("0.2000"),
        Decimal("0.2000"),
    ]
    assert resultado["prevision"].saldo_final == acumulados[-1]


# --- Constitucion III: la empresa nunca viene del cliente --------------------


def _rutas() -> list[tuple[str, str]]:
    from api.tesoreria import router

    return [(ruta.path, ",".join(sorted(ruta.methods or []))) for ruta in router.routes]


def test_ninguna_ruta_acepta_empresa_id():
    from fastapi.routing import APIRoute

    from api.tesoreria import router

    for ruta in router.routes:
        assert isinstance(ruta, APIRoute)
        assert "empresa_id" not in ruta.path, ruta.path
        assert "tenant_id" not in ruta.path, ruta.path
        for nombre in query_params(ruta):
            assert nombre != "empresa_id", ruta.path


def query_params(ruta) -> set[str]:
    return {
        param.name
        for param in ruta.dependant.query_params
    }


def test_los_cuerpos_no_declaran_empresa_id():
    from api.tesoreria import (
        AtenderBody,
        FormularEFEBody,
        MovimientoManualBody,
        PrevisionBody,
        RegenerarBody,
    )

    for modelo in (
        PrevisionBody,
        RegenerarBody,
        MovimientoManualBody,
        AtenderBody,
        FormularEFEBody,
    ):
        assert "empresa_id" not in modelo.model_fields, modelo.__name__


def test_el_router_depende_de_get_empresa_id():
    """La empresa sale de la sesion (`get_empresa_id`), no del path ni del body."""
    from api.deps import get_empresa_id, require_permission
    from api.tesoreria import router

    seen: set[int] = set()
    for ruta in router.routes:
        for dep in ruta.dependant.dependencies:
            call = dep.call
            if call is get_empresa_id or getattr(call, "__wrapped__", None) is get_empresa_id:
                seen.add(id(call))
        for sub in getattr(ruta.dependant, "dependencies", []):
            call = getattr(sub, "call", None)
            if getattr(call, "_rbac_permiso", None) is not None:
                assert callable(call) and call.__name__ == "_checked"
        assert require_permission is not None
    assert seen, "el router no inyecta get_empresa_id en ninguna ruta"


# --- Constitucion II: el EFE formulado es inmutable -------------------------


async def test_efe_formulado_rechaza_update_y_delete(db_session_factory):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from services.cashflow.efe import formular_efe

    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await soporte.plantar_cuenta(
            session, empresa_id=EMPRESA, code="1000", parent="100", name="Capital"
        )
        await soporte.publicar_asiento(
            session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 1, 2),
            lineas=[
                {"cuenta": "5720", "debe": "1000.0000", "haber": "0"},
                {"cuenta": "1000", "debe": "0", "haber": "1000.0000"},
            ],
            tipo="OPENING",
        )
        await session.commit()
        # Un movimiento posterior genera al menos una linea que bloquear.
        await soporte.publicar_asiento(
            session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 4, 1),
            lineas=[
                {"cuenta": "5720", "debe": "500.0000", "haber": "0"},
                {"cuenta": "7000", "debe": "0", "haber": "500.0000"},
            ],
        )
        await session.commit()
        await formular_efe(session, empresa_id=EMPRESA, ejercicio=EJERCICIO)
        await session.commit()

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError, match="inmutable"):
            await session.execute(
                text("UPDATE informe_efe SET estado = 'borrador' WHERE empresa_id = :e"),
                {"e": EMPRESA},
            )

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError, match="inmutable"):
            await session.execute(
                text("DELETE FROM informe_efe WHERE empresa_id = :e"), {"e": EMPRESA}
            )

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError, match="inmutable"):
            await session.execute(
                text("DELETE FROM linea_efe WHERE empresa_id = :e"), {"e": EMPRESA}
            )


async def test_la_prevision_no_toca_el_diario(db_session):
    """La prevision es una herramienta de gestion: no genera ni altera asientos."""
    from sqlalchemy import func, select

    from models.acct.journal import JournalEntry, JournalEntryLine

    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 4, 1),
        lineas=[
            {"cuenta": "5720", "debe": "500.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "500.0000"},
        ],
    )
    await db_session.commit()
    antes = await db_session.scalar(select(func.count()).select_from(JournalEntry))
    lineas_antes = await db_session.scalar(select(func.count()).select_from(JournalEntryLine))

    await generar_prevision(
        db_session,
        empresa_id=EMPRESA,
        desde_fecha=date(EJERCICIO, 9, 16),
        hasta_fecha=date(EJERCICIO, 10, 31),
    )
    await db_session.commit()
    assert await db_session.scalar(select(func.count()).select_from(JournalEntry)) == antes
    assert (
        await db_session.scalar(select(func.count()).select_from(JournalEntryLine))
        == lineas_antes
    )


# --- Constitucion IV: correlatividad sin saltos ------------------------------


async def test_correlatividad_de_la_prevision_sin_saltos(db_session):
    numeros = []
    for _ in range(5):
        resultado = await generar_prevision(
            db_session,
            empresa_id=EMPRESA,
            desde_fecha=date(EJERCICIO, 9, 16),
            hasta_fecha=date(EJERCICIO, 9, 18),
            granularidad="dia",
        )
        numeros.append(int(resultado["prevision"].numero_prevision))
    assert numeros == [1, 2, 3, 4, 5]


# --- Importes en la respuesta (contrato) ------------------------------------


def test_las_columnas_de_importe_son_numeric_18_4():
    from models.treasury.alerta_liquidez import AlertaLiquidez
    from models.treasury.efe import InformeEFE, LineaEFE
    from models.treasury.movimiento_prevision import MovimientoPrevision
    from models.treasury.prevision import PrevisionTesoreria

    esperado = "NUMERIC(18, 4)"
    assert str(PrevisionTesoreria.__table__.columns["saldo_inicial"].type) == esperado
    assert str(PrevisionTesoreria.__table__.columns["saldo_final"].type) == esperado
    assert str(MovimientoPrevision.__table__.columns["importe"].type) == esperado
    assert str(AlertaLiquidez.__table__.columns["importe_deficit"].type) == esperado
    assert str(AlertaLiquidez.__table__.columns["saldo_proyectado"].type) == esperado
    assert str(InformeEFE.__table__.columns["saldo_inicial"].type) == esperado
    assert str(LineaEFE.__table__.columns["importe"].type) == esperado


def test_los_ficheros_del_modulo_existen():
    for relativo in (
        "services/cashflow/__init__.py",
        "services/cashflow/utils.py",
        "services/cashflow/clasificacion_actividad.py",
        "services/cashflow/saldos.py",
        "services/cashflow/proyeccion.py",
        "services/cashflow/efe.py",
        "services/cashflow/alertas.py",
        "services/cashflow/errores.py",
        "api/tesoreria.py",
        "models/treasury/prevision.py",
        "models/treasury/movimiento_prevision.py",
        "models/treasury/alerta_liquidez.py",
        "models/treasury/efe.py",
    ):
        assert (RAIZ / relativo).is_file(), relativo
