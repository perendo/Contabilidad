"""Flujo completo del cierre anual (SPEC-028 T028, T029, T036, US2/FR-002).

Quickstart Scenario 3: con todos los periodos intermedios cerrados, el cierre
anual genera los asientos de regularizacion, cierre y apertura, deja el ejercicio
bloqueado y es idempotente (el reintento devuelve 409 sin duplicar asientos).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

A = 10
B = 20
EJERCICIO = 2026
MESES = list(range(1, 13))


def _sembrar_libro(cierres, empresa: int = A) -> None:
    """Balance equilibrado para que la apertura de SPEC-009 cuadre."""
    cierres.asiento(
        empresa,
        "2026-01-15",
        [
            {"cuenta": "1110", "haber": "17000.0000"},
            {"cuenta": "2100", "debe": "17000.0000"},
        ],
    )
    cierres.asiento(
        empresa,
        "2026-02-01",
        [
            {"cuenta": "2100", "debe": "3000.0000"},
            {"cuenta": "4100", "haber": "3000.0000"},
        ],
    )
    cierres.asiento(
        empresa,
        "2026-03-31",
        [
            {"cuenta": "7000", "haber": "10000.0000"},
            {"cuenta": "4300", "debe": "10000.0000"},
        ],
    )
    cierres.asiento(
        empresa,
        "2026-06-30",
        [
            {"cuenta": "6000", "debe": "7000.0000"},
            {"cuenta": "4300", "haber": "7000.0000"},
        ],
    )


# --- T029 · el cierre anual exige los periodos intermedios cerrados ---------


def test_cierre_anual_con_meses_pendientes_devuelve_409(closing_client) -> None:
    cierres = closing_client
    _sembrar_libro(cierres)
    cierres.cerrar_periodos(A, EJERCICIO, range(1, 12))
    respuesta = cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert respuesta.status_code == 409
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "periodos_intermedios_pendientes"
    assert "12" in detalle["detail"]


def test_cierre_anual_acepta_cuando_todos_los_meses_estan_cerrados(closing_client) -> None:
    cierres = closing_client
    _sembrar_libro(cierres)
    cierres.cerrar_periodos(A, EJERCICIO, MESES)
    assert (
        cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A).status_code
        == 201
    )


def test_un_trimestre_cerrado_cubre_sus_meses(closing_client) -> None:
    cierres = closing_client
    _sembrar_libro(cierres)
    cierres.cerrar_periodos(A, EJERCICIO, (1, 2, 3, 4), tipo="TRIMESTRE")
    assert (
        cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A).status_code
        == 201
    )


# --- T028 · idempotencia del cierre anual ---------------------------------


def test_reintentar_el_cierre_anual_devuelve_409_sin_duplicar(closing_client) -> None:
    cierres = closing_client
    _sembrar_libro(cierres)
    cierres.cerrar_periodos(A, EJERCICIO, MESES)
    primero = cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert primero.status_code == 201
    segundo = cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert segundo.status_code == 409
    assert segundo.json()["detail"]["code"] == "ejercicio_cerrado"

    async def _contar_cierres(session):
        from sqlalchemy import func, select

        from models.acct.journal import JournalEntry, JournalEntryTipo
        from models.closing.cierre_ejercicio import CierreEjercicio

        cierres = await session.scalar(
            select(func.count())
            .select_from(CierreEjercicio)
            .where(CierreEjercicio.empresa_id == A)
        )
        asientos = await session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.empresa_id == A,
                JournalEntry.tipo.in_(
                    [JournalEntryTipo.REGULARIZACION, JournalEntryTipo.CIERRE]
                ),
            )
        )
        return cierres, asientos

    total_cierres, total_asientos = cierres.run(cierres.consultar(_contar_cierres))
    assert total_cierres == 1
    assert total_asientos == 2


# --- T036 · el cierre anual completo --------------------------------------


def test_scenario_3_cierre_anual_completo(closing_client) -> None:
    cierres = closing_client
    _sembrar_libro(cierres)
    cierres.cerrar_periodos(A, EJERCICIO, MESES)
    respuesta = cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "completado"
    assert cuerpo["ejercicio"] == EJERCICIO
    assert cuerpo["fecha_cierre"] == "2026-12-31"
    assert cuerpo["resultado_ejercicio"] == "3000.0000"
    assert cuerpo["asiento_regularizacion_id"]
    assert cuerpo["asiento_cierre_id"]
    assert cuerpo["asiento_apertura_id"]
    assert cuerpo["asiento_regularizacion_id"] != cuerpo["asiento_cierre_id"]

    detalle = cierres.get(f"/api/v1/cierres/anual/{EJERCICIO}", empresa_id=A).json()
    assert detalle["cierre_id"] == cuerpo["cierre_id"]
    assert detalle["cerrado_at"]
    assert detalle["cerrado_por"] == "api"


def test_el_cierre_anual_bloquea_el_ejercicio(closing_client) -> None:
    from sqlalchemy import select

    from models.acct.fiscal_year import FiscalYear
    from services.journal.entry_service import AsientoError

    cierres = closing_client
    _sembrar_libro(cierres)
    cierres.cerrar_periodos(A, EJERCICIO, MESES)
    assert (
        cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A).status_code
        == 201
    )

    async def _fiscal(session):
        return await session.scalar(
            select(FiscalYear).where(
                FiscalYear.empresa_id == A, FiscalYear.year == EJERCICIO
            )
        )

    fy = cierres.run(cierres.consultar(_fiscal))
    assert fy.is_closed is True
    assert fy.cierre_entry_id is not None
    assert fy.regularizacion_entry_id is not None

    # Un asiento nuevo dentro del ejercicio cerrado se rechaza. El motor
    # evalua primero el ejercicio (`ejercicio_cerrado`) y despues el periodo.
    with pytest.raises(AsientoError) as exc:
        cierres.asiento(
            A,
            "2026-12-20",
            [
                {"cuenta": "7000", "haber": "10.0000"},
                {"cuenta": "4300", "debe": "10.0000"},
            ],
        )
    assert exc.value.code in {"ejercicio_cerrado", "periodo_cerrado"}

    # El ejercicio siguiente si admite contabilidad: es lo que habilita la apertura.
    nuevo = cierres.asiento(
        A,
        "2027-01-15",
        [
            {"cuenta": "7000", "haber": "10.0000"},
            {"cuenta": "4300", "debe": "10.0000"},
        ],
    )
    assert nuevo is not None


def test_los_asientos_de_cierre_cuadran(closing_client) -> None:
    from sqlalchemy import select

    from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo

    cierres = closing_client
    _sembrar_libro(cierres)
    cierres.cerrar_periodos(A, EJERCICIO, MESES)
    cuerpo = cierres.post(
        "/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A
    ).json()

    async def _saldos(session, entrada_id):
        from sqlalchemy import func

        from models.acct.journal import JournalEntryLine

        total = await session.execute(
            select(
                func.coalesce(func.sum(JournalEntryLine.debe), 0),
                func.coalesce(func.sum(JournalEntryLine.haber), 0),
            ).where(JournalEntryLine.journal_entry_id == entrada_id)
        )
        return total.one()

    import functools
    import uuid

    for clave in ("asiento_regularizacion_id", "asiento_cierre_id", "asiento_apertura_id"):
        consultar = functools.partial(_saldos, entrada_id=uuid.UUID(cuerpo[clave]))
        debe, haber = cierres.run(cierres.consultar(consultar))
        assert Decimal(str(debe)) == Decimal(str(haber)) > 0, clave

    async def _tipos(session):
        filas = (
            await session.scalars(
                select(JournalEntry).where(
                    JournalEntry.empresa_id == A,
                    JournalEntry.ejercicio.in_([EJERCICIO, EJERCICIO + 1]),
                )
            )
        ).all()
        return {e.tipo: e.estado for e in filas}

    tipos = cierres.run(cierres.consultar(_tipos))
    assert tipos[JournalEntryTipo.REGULARIZACION] is JournalEntryEstado.POSTED
    assert tipos[JournalEntryTipo.CIERRE] is JournalEntryEstado.POSTED
    assert tipos[JournalEntryTipo.OPENING] is JournalEntryEstado.POSTED


def test_cierre_anual_sin_ejercicio_devuelve_404(closing_client) -> None:
    respuesta = closing_client.post("/api/v1/cierres/anual", json={"ejercicio": 2024}, empresa_id=A)
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "ejercicio_no_encontrado"


def test_detalle_de_cierre_inexistente_devuelve_404(closing_client) -> None:
    respuesta = closing_client.get(f"/api/v1/cierres/anual/{EJERCICIO}", empresa_id=A)
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "cierre_no_encontrado"


def test_cierre_anual_sin_movimientos_no_publica_asientos(closing_client) -> None:
    cierres = closing_client
    cierres.cerrar_periodos(A, EJERCICIO, MESES)
    cuerpo = cierres.post(
        "/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A
    ).json()
    assert cuerpo["asiento_regularizacion_id"] is None
    assert cuerpo["asiento_cierre_id"] is None
    assert cuerpo["asiento_apertura_id"] is None
    assert cuerpo["resultado_ejercicio"] == "0.0000"


def test_la_apertura_no_se_genera_si_no_hay_ejercicio_siguiente(closing_client) -> None:
    async def _borrar_2027(session):
        from sqlalchemy import delete

        from models.acct.fiscal_year import FiscalYear

        await session.execute(
            delete(FiscalYear).where(
                FiscalYear.empresa_id == A, FiscalYear.year == EJERCICIO + 1
            )
        )

    cierres = closing_client
    _sembrar_libro(cierres)
    cierres.cerrar_periodos(A, EJERCICIO, MESES)
    cierres.run(cierres.mutar(_borrar_2027))
    cuerpo = cierres.post(
        "/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A
    ).json()
    assert cuerpo["asiento_apertura_id"] is None
