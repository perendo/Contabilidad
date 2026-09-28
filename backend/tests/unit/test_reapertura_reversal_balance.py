"""Asiento de rectificacion de la reapertura (SPEC-028 T040, US3/FR-004).

El asiento rectificativo lo publica el motor de asientos de SPEC-002 durante el
periodo reabierto; este test verifica que `rectificar_reapertura` lo enlaza, que
el periodo vuelve a quedar bloqueado con `n_reaperturas + 1` y que **el asiento
original nunca se modifica** (constitucion II).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntryEstado, JournalEntryTipo
from models.closing.periodo_cerrado import EstadoPeriodo
from models.closing.solicitud_reapertura import EstadoSolicitud, TipoPeriodoReapertura
from services.closing.errores import ClosingError
from services.closing.reapertura import (
    marcar_reabierta,
    rectificar_reapertura,
    solicitar_reapertura,
)
from tests.unit import closing_support as soporte

EMPRESA = soporte.A
OTRA = soporte.B
EJERCICIO = 2026


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await soporte.empresa(session, OTRA)
        await session.commit()


async def _periodo_reabierto(session, empresa_id: int = EMPRESA, mes: int = 3):
    """Cierra el mes, solicita la reapertura y la aprueba: deja el periodo abierto."""
    await soporte.publicar_asiento(
        session,
        empresa_id=empresa_id,
        fecha=date(EJERCICIO, mes, 15),
        lineas=[
            {"cuenta": "7000", "haber": "1000.0000"},
            {"cuenta": "4300", "debe": "1000.0000"},
        ],
    )
    await soporte.cerrar_meses(
        session, empresa_id=empresa_id, ejercicio=EJERCICIO, meses=[mes]
    )
    fila = await solicitar_reapertura(
        session,
        empresa_id=empresa_id,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=mes,
        motivo="Error de imputacion",
        actor="solicitante",
    )
    await marcar_reabierta(
        session, empresa_id=empresa_id, solicitud_id=fila.id, actor="responsable"
    )
    return fila


async def test_el_asiento_rectificativo_se_publica_durante_la_reapertura(db_session) -> None:
    """Research D7: en `reabierto_ajuste` el motor vuelve a admitir el periodo."""
    await _periodo_reabierto(db_session)
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 20),
        lineas=[
            {"cuenta": "7000", "haber": "250.0000"},
            {"cuenta": "4300", "debe": "250.0000"},
        ],
        concepto="Rectificacion de la venta",
        tipo="ADJUSTMENT",
    )
    debe, haber = await soporte.saldos_asiento(
        db_session, empresa_id=EMPRESA, asiento_id=asiento
    )
    assert debe == haber == Decimal("250.0000")


async def test_rectificar_enlaza_el_asiento_y_vuelve_a_cerrar(db_session) -> None:
    solicitud = await _periodo_reabierto(db_session)
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 22),
        lineas=[
            {"cuenta": "7000", "haber": "250.0000"},
            {"cuenta": "4300", "debe": "250.0000"},
        ],
        concepto="Rectificacion",
        tipo="ADJUSTMENT",
    )
    fila = await rectificar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        solicitud_id=solicitud.id,
        asiento_id=asiento,
        actor="responsable",
    )
    assert fila.estado is EstadoSolicitud.cerrada
    assert fila.asiento_rectificacion_id == asiento
    assert fila.fecha_cierre_efectivo is not None

    periodo = await soporte.periodo(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, numero=3)
    assert periodo is not None
    assert periodo.estado is EstadoPeriodo.cerrado_ajustado
    assert periodo.n_reaperturas == 1


async def test_el_periodo_vuelve_a_bloquearse_despues_del_ajuste(db_session) -> None:
    solicitud = await _periodo_reabierto(db_session)
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 22),
        lineas=[
            {"cuenta": "7000", "haber": "10.0000"},
            {"cuenta": "4300", "debe": "10.0000"},
        ],
        tipo="ADJUSTMENT",
    )
    await rectificar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        solicitud_id=solicitud.id,
        asiento_id=asiento,
        actor="responsable",
    )
    from services.journal.entry_service import AsientoError

    with pytest.raises(AsientoError) as exc:
        await soporte.publicar_asiento(
            db_session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 3, 28),
            lineas=[
                {"cuenta": "7000", "haber": "5.0000"},
                {"cuenta": "4300", "debe": "5.0000"},
            ],
        )
    assert exc.value.code == "periodo_cerrado"


async def test_el_asiento_original_no_se_modifica(db_session) -> None:
    """Constitucion II: la correccion es un asiento nuevo, nunca un UPDATE."""
    from models.acct.journal import JournalEntry, JournalEntryLine

    original = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 15),
        lineas=[
            {"cuenta": "7000", "haber": "1000.0000"},
            {"cuenta": "4300", "debe": "1000.0000"},
        ],
        concepto="Venta original",
    )
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    solicitud = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Error",
        actor="test",
    )
    await marcar_reabierta(
        db_session, empresa_id=EMPRESA, solicitud_id=solicitud.id, actor="responsable"
    )
    rectificativo_id = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 25),
        lineas=[
            {"cuenta": "7000", "haber": "1000.0000"},
            {"cuenta": "4300", "debe": "1000.0000"},
        ],
        concepto="Anulacion de la venta",
        tipo="REVERSAL",
        # research D7: el enlace con el original se fija al crear el asiento;
        # un POSTED es inmutable, asi que no puede asignarse despues.
        original_id=original,
    )

    antes_debe, antes_haber = await soporte.saldos_asiento(
        db_session, empresa_id=EMPRESA, asiento_id=original
    )
    firma = (
        await db_session.execute(
            select(JournalEntry.concepto, JournalEntry.estado, JournalEntry.tipo)
            .where(JournalEntry.id == original)
        )
    ).one()
    await rectificar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        solicitud_id=solicitud.id,
        asiento_id=rectificativo_id,
        actor="responsable",
    )
    despues_debe, despues_haber = await soporte.saldos_asiento(
        db_session, empresa_id=EMPRESA, asiento_id=original
    )
    firma_despues = (
        await db_session.execute(
            select(JournalEntry.concepto, JournalEntry.estado, JournalEntry.tipo)
            .where(JournalEntry.id == original)
        )
    ).one()
    assert (antes_debe, antes_haber) == (despues_debe, despues_haber)
    assert firma == firma_despues
    assert firma.estado is JournalEntryEstado.POSTED
    # El original sigue siendo inmutable tambien para la base de datos.
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text("UPDATE journal_entry SET concepto = 'tocada' WHERE id = :id"),
            {"id": original.hex},
        )
    assert "inmutable" in str(exc.value).lower()
    await db_session.rollback()
    assert JournalEntryLine is not None



async def test_el_asiento_rectificativo_tiene_la_fecha_dentro_del_periodo(db_session) -> None:
    solicitud = await _periodo_reabierto(db_session)
    fuera = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 5, 10),
        lineas=[
            {"cuenta": "7000", "haber": "10.0000"},
            {"cuenta": "4300", "debe": "10.0000"},
        ],
        tipo="ADJUSTMENT",
    )
    with pytest.raises(ClosingError) as exc:
        await rectificar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            solicitud_id=solicitud.id,
            asiento_id=fuera,
            actor="responsable",
        )
    assert exc.value.code == "fecha_fuera_de_rango"
    assert exc.value.status_code == 409


async def test_el_asiento_rectificativo_debe_ser_adjustment_o_reversal(db_session) -> None:
    solicitud = await _periodo_reabierto(db_session)
    general = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 18),
        lineas=[
            {"cuenta": "7000", "haber": "10.0000"},
            {"cuenta": "4300", "debe": "10.0000"},
        ],
        tipo="GENERAL",
    )
    with pytest.raises(ClosingError) as exc:
        await rectificar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            solicitud_id=solicitud.id,
            asiento_id=general,
            actor="responsable",
        )
    assert exc.value.code == "asiento_tipo_invalido"


async def test_el_asiento_rectificativo_debe_estar_asentado(db_session) -> None:
    """Un borrador no cierra la reapertura: el asiento tiene que ser POSTED."""
    from services.journal.entry_service import crear_borrador

    solicitud = await _periodo_reabierto(db_session)
    mapa = await soporte.cuentas(db_session, EMPRESA)
    borrador = await crear_borrador(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 19),
        concepto="Borrador de rectificacion",
        lineas=[
            {"account_id": mapa["7000"], "debit": "0", "credit": "10.0000"},
            {"account_id": mapa["4300"], "debit": "10.0000", "credit": "0"},
        ],
        actor="test",
        tipo=JournalEntryTipo.ADJUSTMENT,
    )
    with pytest.raises(ClosingError) as exc:
        await rectificar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            solicitud_id=solicitud.id,
            asiento_id=borrador.id,
            actor="responsable",
        )
    assert exc.value.code == "asiento_no_asentado"


async def test_un_asiento_sin_lineas_no_cierra_la_reapertura(db_session) -> None:
    """Defense-in-depth: el servicio re-verifica el cuadre antes de enlazar.

    El motor de SPEC-002 y el trigger de balance impiden crear un asiento POSTED
    desbalanceado, asi que el caso se reproduce insertando una cabecera sin
    lineas directamente a nivel ORM: el servicio debe rechazarla con
    `asiento_desbalanceado` en vez de dar por buena la rectificacion.
    """
    import uuid

    from models.acct.journal import JournalEntry

    solicitud = await _periodo_reabierto(db_session)
    vacio = JournalEntry(
        id=uuid.uuid4(),
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        fecha=date(EJERCICIO, 3, 21),
        tipo=JournalEntryTipo.ADJUSTMENT,
        concepto="Cabecera sin lineas",
        estado=JournalEntryEstado.POSTED,
        numero_asiento=999,
        created_by="test",
    )
    db_session.add(vacio)
    await db_session.flush()
    with pytest.raises(ClosingError) as exc:
        await rectificar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            solicitud_id=solicitud.id,
            asiento_id=vacio.id,
            actor="responsable",
        )
    assert exc.value.code == "asiento_desbalanceado"
    assert exc.value.status_code == 409


async def test_no_se_puede_rectificar_dos_veces(db_session) -> None:
    solicitud = await _periodo_reabierto(db_session)
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 23),
        lineas=[
            {"cuenta": "7000", "haber": "15.0000"},
            {"cuenta": "4300", "debe": "15.0000"},
        ],
        tipo="ADJUSTMENT",
    )
    await rectificar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        solicitud_id=solicitud.id,
        asiento_id=asiento,
        actor="responsable",
    )
    with pytest.raises(ClosingError) as exc:
        await rectificar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            solicitud_id=solicitud.id,
            asiento_id=asiento,
            actor="responsable",
        )
    assert exc.value.code == "solicitud_no_reabierta"
    assert exc.value.status_code == 409


async def test_no_se_rectifica_sin_haver_aprobado(db_session) -> None:
    """Quickstart Scenario 4: la rectificacion exige la aprobacion previa."""
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    solicitud = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Error",
        actor="test",
    )
    with pytest.raises(ClosingError) as exc:
        await rectificar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            solicitud_id=solicitud.id,
            asiento_id=solicitud.id,
            actor="responsable",
        )
    assert exc.value.code == "solicitud_no_reabierta"


async def test_el_asiento_de_otra_empresa_no_sirve(db_session) -> None:
    """Constitucion III: un asiento de B no cierra la solicitud de A."""
    from models.acct.journal import JournalEntry

    solicitud = await _periodo_reabierto(db_session)
    await soporte.publicar_asiento(
        db_session,
        empresa_id=OTRA,
        fecha=date(EJERCICIO, 3, 21),
        lineas=[
            {"cuenta": "7000", "haber": "7.0000"},
            {"cuenta": "4300", "debe": "7.0000"},
        ],
        tipo="ADJUSTMENT",
    )
    await soporte.cerrar_meses(
        db_session, empresa_id=OTRA, ejercicio=EJERCICIO, meses=[3]
    )
    ajeno = await db_session.scalar(
        select(JournalEntry.id).where(JournalEntry.empresa_id == OTRA)
    )
    with pytest.raises(ClosingError) as exc:
        await rectificar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            solicitud_id=solicitud.id,
            asiento_id=ajeno,
            actor="responsable",
        )
    assert exc.value.status_code == 404


async def test_n_reaperturas_acumula_en_sucesivas(db_session) -> None:
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 15),
        lineas=[
            {"cuenta": "7000", "haber": "1000.0000"},
            {"cuenta": "4300", "debe": "1000.0000"},
        ],
    )
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    for ronda in range(2):
        solicitud = await solicitar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo_periodo="MES",
            periodo=3,
            motivo=f"Ronda {ronda + 1}",
            actor="test",
        )
        await marcar_reabierta(
            db_session, empresa_id=EMPRESA, solicitud_id=solicitud.id, actor="responsable"
        )
        asiento = await soporte.publicar_asiento(
            db_session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 3, 20 + ronda),
            lineas=[
                {"cuenta": "7000", "haber": f"{ronda + 1}.0000"},
                {"cuenta": "4300", "debe": f"{ronda + 1}.0000"},
            ],
            tipo="ADJUSTMENT",
        )
        await rectificar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            solicitud_id=solicitud.id,
            asiento_id=asiento,
            actor="responsable",
        )
        periodo = await soporte.periodo(
            db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, numero=3
        )
        assert periodo is not None
        assert periodo.n_reaperturas == ronda + 1
        assert periodo.estado is EstadoPeriodo.cerrado_ajustado


async def test_la_reapertura_anual_no_se_cierra_con_un_asiento(db_session) -> None:
    await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO, cerrado=True)
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo=TipoPeriodoReapertura.ANUAL,
        motivo="Error en el cierre anual",
        actor="test",
    )
    await marcar_reabierta(
        db_session, empresa_id=EMPRESA, solicitud_id=fila.id, actor="responsable"
    )
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO + 1, 1, 1),
        lineas=[
            {"cuenta": "7000", "haber": "1.0000"},
            {"cuenta": "4300", "debe": "1.0000"},
        ],
        tipo="ADJUSTMENT",
    )
    with pytest.raises(ClosingError) as exc:
        await rectificar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            solicitud_id=fila.id,
            asiento_id=asiento,
            actor="responsable",
        )
    assert exc.value.code == "reapertura_anual_no_rectificable"
