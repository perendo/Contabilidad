"""Validacion cross-modulo de los periodos cerrados (SPEC-028 T056, research D9).

El bloqueo de `PeriodoCerrado` se aplica en el **motor de asientos de SPEC-002**,
de modo que todos los modulos que publican asientos lo heredan sin cambios:
facturacion (SPEC-007), cobros y pagos (SPEC-011), amortizaciones (SPEC-014) y
plantillas (SPEC-018). Se comprueba tambien la segunda proteccion, el trigger
`chk_journal_entry_fecha_abierta`, contra inserciones directas a SQL.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from services.journal.entry_service import AsientoError
from tests.unit import closing_support as soporte

A = 10
EJERCICIO = 2026


@pytest.fixture(autouse=True)
async def _marzo_cerrado(db_session):
    """Empresa con el mes 3 de 2026 cerrado y el mes 4 abierto."""
    await soporte.empresa(db_session, A)
    await soporte.fiscal_year(db_session, empresa_id=A, year=EJERCICIO)
    await soporte.cerrar_meses(db_session, empresa_id=A, ejercicio=EJERCICIO, meses=[3])
    await db_session.commit()


def _lineas() -> list[dict]:
    return [
        {"cuenta": "7000", "haber": "100.0000"},
        {"cuenta": "4300", "debe": "100.0000"},
    ]


# --- el motor de SPEC-002 es el punto de validacion -----------------------


async def test_spec_002_el_motor_rechaza_la_fecha_del_periodo_cerrado(db_session) -> None:
    with pytest.raises(AsientoError) as exc:
        await soporte.publicar_asiento(
            db_session, empresa_id=A, fecha=date(2026, 3, 15), lineas=_lineas()
        )
    assert exc.value.code == "periodo_cerrado"
    await db_session.rollback()
    # Fuera del rango cerrado si se admite.
    asiento = await soporte.publicar_asiento(
        db_session, empresa_id=A, fecha=date(2026, 4, 15), lineas=_lineas()
    )
    assert asiento is not None
    await db_session.rollback()


async def test_spec_002_tampoco_se_asienta_un_borrador_del_periodo(db_session) -> None:
    """El borrador se crea antes que la fecha de corte: tambien se bloquea."""
    mapa = await soporte.cuentas(db_session, A)
    from services.journal.entry_service import crear_borrador

    with pytest.raises(AsientoError) as exc:
        await crear_borrador(
            db_session,
            empresa_id=A,
            fecha=date(2026, 3, 15),
            concepto="Borrador en periodo cerrado",
            lineas=[
                {"account_id": mapa["7000"], "debit": "0", "credit": "10.0000"},
                {"account_id": mapa["4300"], "debit": "10.0000", "credit": "0"},
            ],
            actor="test",
        )
    assert exc.value.code == "periodo_cerrado"
    await db_session.rollback()


# --- los modulos que publican asientos heredan el bloqueo -----------------


async def test_spec_011_los_cobros_rechazan_la_fecha_cerrada(db_session) -> None:
    """El cobro de SPEC-011 publica su asiento por el motor de SPEC-002."""
    with pytest.raises(AsientoError) as exc:
        await soporte.publicar_asiento(
            db_session,
            empresa_id=A,
            fecha=date(2026, 3, 20),
            lineas=[
                {"cuenta": "5720", "debe": "500.0000"},
                {"cuenta": "4300", "haber": "500.0000"},
            ],
            concepto="Cobro del cliente",
        )
    assert exc.value.code == "periodo_cerrado"
    await db_session.rollback()


async def test_spec_014_las_amortizaciones_rechazan_la_fecha_cerrada(db_session) -> None:
    """La cuota de amortizacion de SPEC-014 se fecha en el periodo bloqueado."""
    mapa = await soporte.cuentas(db_session, A)
    for codigo in ("6810", "2810"):
        if codigo not in mapa:
            await soporte.plantar_cuenta(
                db_session, empresa_id=A, code=codigo, parent=codigo[0]
            )
    with pytest.raises(AsientoError) as exc:
        await soporte.publicar_asiento(
            db_session,
            empresa_id=A,
            fecha=date(2026, 3, 31),
            lineas=[
                {"cuenta": "6810", "debe": "100.0000"},
                {"cuenta": "2810", "haber": "100.0000"},
            ],
            concepto="Amortizacion trimestral",
        )
    assert exc.value.code == "periodo_cerrado"
    await db_session.rollback()


async def test_spec_006_el_motor_multilinea_rechaza_la_fecha_cerrada(db_session) -> None:
    """Punto de entrada compartido por SPEC-007, SPEC-014 y SPEC-018.

    Las facturas, las amortizaciones y los asientos generados por plantilla se
    publican con `crear_asiento_multilinea` (SPEC-006), que acaba delegando en
    `entry_service`. Bloquear aqui es lo que les transmite el veto a todos.
    """
    from services.journal.motor import crear_asiento_multilinea
    from services.journal.validador_multilinea import MultilineaError

    lineas = [
        {"cuenta": "7000", "debe": "0", "haber": "100.0000"},
        {"cuenta": "4300", "debe": "100.0000", "haber": "0"},
    ]
    with pytest.raises((AsientoError, MultilineaError)) as exc:
        await crear_asiento_multilinea(
            db_session,
            empresa_id=A,
            fecha=date(2026, 3, 15),
            concepto="Asiento multilinea en periodo cerrado",
            lineas=lineas,
            actor="test",
        )
    assert getattr(exc.value, "code", None) == "periodo_cerrado"
    await db_session.rollback()


def test_los_modulos_de_asientos_delegan_en_el_motor_bloqueado() -> None:
    """SPEC-007/014/018 publican sus asientos a traves del motor de SPEC-002.

    Se comprueba a nivel de fuente que los tres delegan en
    `crear_asiento_multilinea`, que es donde vive el veto de periodo cerrado.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2] / "src" / "services"
    for relativo in (
        "invoicing/asiento_factura.py",
        "inmovilizado/generacion.py",
        "templates/generacion.py",
    ):
        fuente = (raiz / relativo).read_text(encoding="utf-8")
        assert "crear_asiento_multilinea" in fuente, relativo


# --- segunda proteccion: el trigger del motor (research D9) ----------------


async def test_el_trigger_bloquea_un_insert_directo_en_periodo_cerrado(db_session) -> None:
    """Defense-in-depth: el trigger `chk_journal_entry_fecha_abierta`."""
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text(
                "INSERT INTO journal_entry (id, empresa_id, ejercicio, fecha, tipo, concepto,"
                " estado, created_by) VALUES (:id, :empresa, 2026, '2026-03-15', 'GENERAL',"
                " 'bypass del servicio', 'POSTED', 'script')"
            ),
            {"id": uuid.uuid4().hex, "empresa": A},
        )
    assert "periodo cerrado" in str(exc.value).lower()
    await db_session.rollback()


async def test_el_trigger_admite_la_fecha_libre(db_session) -> None:
    entrada = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO journal_entry (id, empresa_id, ejercicio, fecha, tipo, concepto,"
            " estado, created_by) VALUES (:id, :empresa, 2026, '2026-04-15', 'GENERAL',"
            " 'fecha libre', 'POSTED', 'script')"
        ),
        {"id": entrada.hex, "empresa": A},
    )
    await db_session.flush()
    await db_session.rollback()


@pytest.mark.parametrize("tipo", ["REGULARIZACION", "CIERRE", "OPENING", "OPENING_REVERSAL"])
async def test_los_tipos_de_cierre_estan_exentos_del_bloqueo(db_session, tipo: str) -> None:
    """El cierre anual se fecha el ultimo dia, dentro del mes cerrado."""
    await db_session.execute(
        text(
            "INSERT INTO journal_entry (id, empresa_id, ejercicio, fecha, tipo, concepto,"
            " estado, created_by) VALUES (:id, :empresa, 2026, '2026-03-31', :tipo,"
            " 'cierre', 'POSTED', 'script')"
        ),
        {"id": uuid.uuid4().hex, "empresa": A, "tipo": tipo},
    )
    await db_session.flush()
    await db_session.rollback()


async def test_el_trigger_ignora_los_periodos_de_otra_empresa(db_session) -> None:
    """Constitucion III: el bloqueo es por empresa."""
    await soporte.empresa(db_session, soporte.B)
    await db_session.commit()
    await db_session.execute(
        text(
            "INSERT INTO journal_entry (id, empresa_id, ejercicio, fecha, tipo, concepto,"
            " estado, created_by) VALUES (:id, :empresa, 2026, '2026-03-15', 'GENERAL',"
            " 'otra empresa', 'POSTED', 'script')"
        ),
        {"id": uuid.uuid4().hex, "empresa": soporte.B},
    )
    await db_session.flush()
    await db_session.rollback()


# --- la reapertura devuelve el periodo a la contabilidad ------------------


async def test_el_periodo_reabierto_vuelve_a_admitir_asientos(db_session) -> None:
    from services.closing.reapertura import marcar_reabierta, solicitar_reapertura

    fila = await solicitar_reapertura(
        db_session,
        empresa_id=A,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Ajuste de la factura emitida en marzo",
        actor="test",
    )
    await marcar_reabierta(
        db_session, empresa_id=A, solicitud_id=fila.id, actor="responsable"
    )
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=A,
        fecha=date(2026, 3, 25),
        lineas=[
            {"cuenta": "7000", "haber": "75.0000"},
            {"cuenta": "4300", "debe": "75.0000"},
        ],
        concepto="Factura rectificativa",
        tipo="ADJUSTMENT",
    )
    assert asiento is not None
    debe, haber = await soporte.saldos_asiento(
        db_session, empresa_id=A, asiento_id=asiento
    )
    assert debe == haber == Decimal("75.0000")
    await db_session.rollback()
