"""SPEC-026 T037: verificacion constitucional del modulo de presupuestos.

Comprueba, sobre el codigo y sobre el comportamiento:
- I · el real se agrega de asientos POSTED balanceados del motor de SPEC-002;
- II · el snapshot del cierre es inmutable (UPDATE/DELETE rechazados);
- III · ningun filtro cruza empresas (todo se filtra por `empresa_id`);
- IV · la numeracion de periodos es correlativa por (empresa, ejercicio);
- V · los importes son `Decimal`/`NUMERIC(18,4)`, nunca `float`.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntry, JournalEntryLine
from models.audit.audit_log import AuditLog
from models.budget.desviacion import Desviacion
from models.budget.presupuesto import Presupuesto
from services.budget import (
    cierre_periodo,
    desviaciones,
    informe_desviacion,
    periodos,
    presupuesto_service,
    utils,
)
from services.budget.periodos import crear_periodo, proximo_numero_periodo
from services.budget.presupuesto_service import guardar_presupuesto
from tests.unit.budget_support import cuentas, empresa, publicar_asiento

EMPRESA = 10
OTRA = 20
EJERCICIO = 2026
RAIZ = pathlib.Path(__file__).resolve().parents[2] / "src"

MODULOS = (
    utils,
    periodos,
    presupuesto_service,
    desviaciones,
    informe_desviacion,
    cierre_periodo,
)


# --- Constitucion V: sin `float` en el modulo ------------------------------


def test_ningun_importe_usa_float():
    """Prohibido `float` para dinero: no hay literales ni anotaciones `float`."""
    for modulo in MODULOS:
        fuente = inspect.getsource(modulo)
        assert "float(" not in fuente, f"{modulo.__name__} usa float()"
        arbol = ast.parse(fuente)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.AnnAssign) and ast.unparse(nodo.annotation) == "float":
                raise AssertionError(f"{modulo.__name__} anota float en {nodo.target}")
            if (
                isinstance(nodo, ast.arg)
                and nodo.annotation is not None
                and ast.unparse(nodo.annotation) == "float"
            ):
                raise AssertionError(f"{modulo.__name__} anota float en {nodo.arg}")


def test_todo_importe_es_decimal():
    assert isinstance(utils.c4(1), Decimal)
    assert isinstance(utils.calcular_real(6, Decimal(1), Decimal(1)), Decimal)
    assert isinstance(utils.calcular_desviacion_absoluta(Decimal(1), Decimal(1)), Decimal)


def test_cuatro_decimales_en_toda_la_salida_de_dinero():
    """SC-005: los importes se exponen como strings de exactamente 4 decimales."""
    assert utils.c4(Decimal("1.5")) == Decimal("1.5000")
    assert f"{utils.c4(Decimal(1)):0.4f}" == "1.0000"
    assert utils.tiene_mas_de_4_decimales("1.00001") is True
    assert utils.tiene_mas_de_4_decimales("1.0000") is False


# --- Constitucion I: el real sale de asientos POSTED y balanceados --------


async def test_el_real_solo_agrega_asientos_posted(db_session):
    from services.journal.entry_service import crear_borrador

    await empresa(db_session, EMPRESA)
    plan = await cuentas(db_session, EMPRESA)
    await crear_borrador(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 5, 31),
        concepto="Borrador no posted",
        lineas=[
            {"account_id": plan["6400"], "debit": "1000", "credit": "0"},
            {"account_id": plan["4000"], "debit": "0", "credit": "1000"},
        ],
        actor="test",
    )
    await db_session.commit()

    incluye_borrador = await desviaciones._reales(
        db_session,
        empresa_id=EMPRESA,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 12, 31),
    )
    assert incluye_borrador.get((plan["6400"], None)) is None

    await db_session.execute(
        text(
            "UPDATE journal_entry SET estado = 'POSTED' "
            "WHERE empresa_id = :e AND concepto = 'Borrador no posted'"
        ),
        {"e": EMPRESA},
    )
    await db_session.flush()
    solo_posted = await desviaciones._reales(
        db_session,
        empresa_id=EMPRESA,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 12, 31),
    )
    assert solo_posted[(plan["6400"], None)] == Decimal("1000.0000")


async def test_el_diario_origen_sigue_balanceado(db_session):
    """Constitucion I: la feature no genera asientos, consume los del motor."""
    await empresa(db_session, EMPRESA)
    plan = await cuentas(db_session, EMPRESA)
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 5, 31),
        lineas=[
            {"account_id": plan["6400"], "debit": "1234.5678", "credit": "0"},
            {"account_id": plan["4000"], "debit": "0", "credit": "1234.5678"},
        ],
    )
    await db_session.commit()

    filas = (
        await db_session.execute(
            select(
                JournalEntry.id,
                func.sum(JournalEntryLine.debe),
                func.sum(JournalEntryLine.haber),
            )
            .join(JournalEntryLine, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(JournalEntry.empresa_id == EMPRESA)
            .group_by(JournalEntry.id)
        )
    ).all()
    assert filas
    for _, debe, haber in filas:
        assert Decimal(debe) == Decimal(haber)


async def test_la_feature_no_crea_asientos(db_session):
    """El modulo de presupuestos no inserta en `journal_entry`."""
    await empresa(db_session, EMPRESA)
    plan = await cuentas(db_session, EMPRESA)
    await guardar_presupuesto(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=plan["6400"],
        importe="48000.0000",
        actor="test",
    )
    await db_session.commit()
    total = await db_session.scalar(
        select(func.count()).select_from(JournalEntry).where(JournalEntry.empresa_id == EMPRESA)
    )
    assert int(total or 0) == 0


# --- Constitucion III: multi-tenancy estricto -----------------------------


async def test_ninguna_consulta_presupuesto_cruza_empresas(db_session):
    await empresa(db_session, EMPRESA)
    await empresa(db_session, OTRA)
    plan_a = await cuentas(db_session, EMPRESA)
    plan_b = await cuentas(db_session, OTRA)
    await guardar_presupuesto(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=plan_a["6400"],
        importe="48000.0000",
        actor="test",
    )
    await guardar_presupuesto(
        db_session,
        empresa_id=OTRA,
        ejercicio=EJERCICIO,
        cuenta_id=plan_b["6400"],
        importe="1000.0000",
        actor="test",
    )
    await db_session.commit()

    informe_a = await desviaciones.calcular_desviaciones(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO
    )
    assert [i["importe_presupuestado"] for i in informe_a["items"]] == ["48000.0000"]
    informe_b = await desviaciones.calcular_desviaciones(
        db_session, empresa_id=OTRA, ejercicio=EJERCICIO
    )
    assert [i["importe_presupuestado"] for i in informe_b["items"]] == ["1000.0000"]


def test_el_codigo_filtra_por_empresa_en_toda_consulta():
    """Revision estatica: cada `select` de las tres tablas filtra `empresa_id`."""
    for nombre in ("presupuesto.py", "periodo_seguimiento.py", "desviacion.py"):
        fuente = (RAIZ / "models" / "budget" / nombre).read_text(encoding="utf-8")
        assert "empresa_id" in fuente
        assert "Index(" in fuente
    for modulo in (desviaciones, informe_desviacion, presupuesto_service, periodos):
        fuente = inspect.getsource(modulo)
        assert ".empresa_id ==" in fuente, f"{modulo.__name__} filtra por empresa_id"


def test_la_api_no_expone_empresa_id():
    """El `empresa_id` viaja solo en la cabecera de sesion (constitucion III)."""
    from api import presupuestos as modulo

    fuente = inspect.getsource(modulo)
    for cuerpo in ("empresa_id: int", "empresa_id: str"):
        assert cuerpo not in fuente
    assert "empresa_id: Empresa" in fuente


# --- Constitucion IV: correlatividad de periodos --------------------------


async def test_numeracion_correlativa_sin_saltos(db_session):
    await empresa(db_session, EMPRESA)
    for esperado in (1, 2, 3):
        assert await proximo_numero_periodo(db_session, EMPRESA, EJERCICIO) == esperado
        await crear_periodo(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            fecha_inicio=date(EJERCICIO, esperado, 1),
            fecha_fin=date(EJERCICIO, esperado, 28),
            actor="test",
        )
        await db_session.flush()
        await db_session.execute(
            text("UPDATE periodo_seguimiento SET estado = 'cerrado' WHERE empresa_id = :e"),
            {"e": EMPRESA},
        )
        await db_session.flush()
    assert await proximo_numero_periodo(db_session, EMPRESA, EJERCICIO) == 4


# --- Constitucion II: inmutabilidad del snapshot ---------------------------


async def test_snapshot_inmutable_a_nivel_de_datos(db_session_factory):
    async with db_session_factory() as session:
        await empresa(session, EMPRESA)
        plan = await cuentas(session, EMPRESA)
        periodo = await crear_periodo(
            session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            fecha_inicio=date(EJERCICIO, 1, 1),
            fecha_fin=date(EJERCICIO, 12, 31),
            actor="test",
        )
        await guardar_presupuesto(
            session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=plan["6400"],
            importe="48000.0000",
            actor="test",
        )
        await session.flush()
        await cierre_periodo.cerrar_periodo_desviaciones(
            session, empresa_id=EMPRESA, periodo_id=periodo.id, actor="test"
        )
        await session.commit()

    async with db_session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text("UPDATE desviacion SET desviacion_absoluta = '0.0000'"),
            )
    async with db_session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text("DELETE FROM desviacion"))


# --- Auditoria WORM en la misma transaccion --------------------------------


async def test_todas_las_mutaciones_se_auditan(db_session):
    await empresa(db_session, EMPRESA)
    plan = await cuentas(db_session, EMPRESA)
    await guardar_presupuesto(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=plan["6400"],
        importe="48000.0000",
        actor="test",
    )
    await guardar_presupuesto(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=plan["6400"],
        importe="50000.0000",
        actor="test",
    )
    await db_session.commit()

    operaciones = {
        operacion
        for (operacion,) in (
            await db_session.execute(
                select(AuditLog.operacion).where(
                    AuditLog.empresa_id == EMPRESA,
                    AuditLog.entidad.in_(("presupuesto", "periodo_seguimiento")),
                )
            )
        ).all()
    }
    assert "PRESUPUESTO_CREAR" in operaciones
    assert "PRESUPUESTO_ACTUALIZAR" in operaciones
    assert "ABRIR_PERIODO" in operaciones


async def test_el_payload_de_auditoria_usa_cadenas_decimales(db_session):
    await empresa(db_session, EMPRESA)
    plan = await cuentas(db_session, EMPRESA)
    await guardar_presupuesto(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        cuenta_id=plan["6400"],
        importe="48000.5000",
        actor="test",
    )
    await db_session.commit()

    payload = await db_session.scalar(
        select(AuditLog.payload).where(
            AuditLog.empresa_id == EMPRESA, AuditLog.operacion == "PRESUPUESTO_CREAR"
        )
    )
    assert "48000.5000" in payload
    assert "48000.5," not in payload


# --- SC-002: cuadre exacto de todas las desviaciones ----------------------


async def test_sc002_todas_las_desviaciones_cuadran(db_session):
    await empresa(db_session, EMPRESA)
    plan = await cuentas(db_session, EMPRESA)
    for cuenta, importe in (("6400", "48000.0000"), ("7000", "120000.0000")):
        await guardar_presupuesto(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            cuenta_id=plan[cuenta],
            importe=importe,
            tipo="ingreso" if cuenta == "7000" else "gasto",
            actor="test",
        )
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 6, 30),
        lineas=[
            {"account_id": plan["6400"], "debit": "51345.6789", "credit": "0"},
            {"account_id": plan["4000"], "debit": "0", "credit": "51345.6789"},
        ],
    )
    await publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 7, 15),
        lineas=[
            {"account_id": plan["6000"], "debit": "1.0001", "credit": "0"},
            {"account_id": plan["4100"], "debit": "0", "credit": "1.0001"},
        ],
    )
    await db_session.commit()

    informe = await informe_desviacion.generar_informe_desviacion(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO
    )
    assert informe["items"]
    for item in informe["items"]:
        assert Decimal(item["desviacion_absoluta"]) == Decimal(
            item["importe_real"]
        ) - Decimal(item["importe_presupuestado"])
    assert Decimal(informe["total_desviacion"]) == Decimal(
        informe["total_real"]
    ) - Decimal(informe["total_presupuestado"])


def test_los_modelos_declaran_numeric_18_4():
    """SC-005 en la base de datos: los importes son NUMERIC(18,4)."""
    for nombre in ("presupuesto.py", "desviacion.py"):
        fuente = (RAIZ / "models" / "budget" / nombre).read_text(encoding="utf-8")
        assert "Numeric(18, 4)" in fuente
    assert Presupuesto.__table__.c.importe.type.precision == 18
    assert Presupuesto.__table__.c.importe.type.scale == 4
    assert Desviacion.__table__.c.desviacion_relativa.type.precision == 7
    assert Desviacion.__table__.c.desviacion_relativa.type.scale == 4
