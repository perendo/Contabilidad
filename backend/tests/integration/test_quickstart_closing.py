"""Escenarios del quickstart de SPEC-028 (T054).

Reproduce los seis escenarios de `specs/028-cierre-intermedio/quickstart.md` a
traves de la API, que es como los ejecuta el usuario:

1. Cerrar un mes intermedio con bloqueo de contabilizacion.
2. Cerrar un trimestre con saldo a cero (sin anomalía).
3. Cierre anual completo (regularizacion + cierre + apertura).
4. Reapertura controlada con asiento de rectificacion.
5. Rechazos: sin justificacion, doble solicitud, ejercicio formulado.
6. Aislamiento multi-empresa.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.journal.entry_service import AsientoError

A = 10
B = 20
EJERCICIO = 2026
MESES = list(range(1, 13))


def _ventas(importe: str = "1000.0000") -> list[dict]:
    return [
        {"cuenta": "7000", "haber": importe},
        {"cuenta": "4300", "debe": importe},
    ]


def _libro(cierres, empresa: int) -> None:
    """Libro con grupos 1-3 equilibrados (requisito de la apertura de SPEC-009)."""
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
    cierres.asiento(empresa, "2026-03-31", _ventas("10000.0000"))
    cierres.asiento(
        empresa,
        "2026-06-30",
        [
            {"cuenta": "6000", "debe": "7000.0000"},
            {"cuenta": "4300", "haber": "7000.0000"},
        ],
    )


# --- Scenario 1 -----------------------------------------------------------


def test_scenario_1_cerrar_mes_con_bloqueo_de_contabilizacion(closing_client) -> None:
    cierres = closing_client
    cierres.asiento(A, "2026-03-10", _ventas("1000.0000"))
    cierres.asiento(A, "2026-03-20", _ventas("234.5000"))

    # 1) Cerrar el mes 3 de 2026.
    respuesta = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "cerrado"
    assert cuerpo["balanza"]["cuadra"] is True
    assert cuerpo["balanza"]["total_debe"] == cuerpo["balanza"]["total_haber"] == "1234.5000"

    # 2) Intentar asentar en el periodo cerrado -> rechazo.
    with pytest.raises(AsientoError) as exc:
        cierres.asiento(A, "2026-03-15", _ventas("10.0000"))
    assert exc.value.code == "periodo_cerrado"

    # 3) Consultar la balanza del periodo.
    balanza = cierres.get(
        f"/api/v1/cierres/intermedios/{cuerpo['periodo_id']}/balanza", empresa_id=A
    ).json()
    assert balanza["total_debe"] == balanza["total_haber"] == "1234.5000"
    assert balanza["lineas"]


# --- Scenario 2 -----------------------------------------------------------


def test_scenario_2_trimestre_con_saldo_a_cero(closing_client) -> None:
    respuesta = closing_client.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "TRIMESTRE", "periodo": 2},
        empresa_id=A,
    )
    assert respuesta.status_code == 201
    balanza = respuesta.json()["balanza"]
    assert balanza["total_debe"] == balanza["total_haber"] == "0.0000"
    assert balanza["n_lineas"] == 0
    assert balanza["cuadra"] is True


# --- Scenario 3 -----------------------------------------------------------


def test_scenario_3_cierre_anual_completo(closing_client) -> None:
    cierres = closing_client
    _libro(cierres, A)
    cierres.cerrar_periodos(A, EJERCICIO, MESES)

    respuesta = cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "completado"
    assert cuerpo["asiento_regularizacion_id"]
    assert cuerpo["asiento_cierre_id"]
    assert cuerpo["asiento_apertura_id"]

    # Los asientos generados son POSTED e inmutables y el ejercicio queda cerrado.
    async def _estado(session):
        import uuid

        from sqlalchemy import select

        from models.acct.fiscal_year import FiscalYear
        from models.acct.journal import (
            JournalEntry,
        )

        entradas = (
            await session.scalars(
                select(JournalEntry).where(
                    JournalEntry.empresa_id == A,
                    JournalEntry.id.in_(
                        [
                            uuid.UUID(cuerpo["asiento_regularizacion_id"]),
                            uuid.UUID(cuerpo["asiento_cierre_id"]),
                        ]
                    ),
                )
            )
        ).all()
        fy = await session.scalar(
            select(FiscalYear).where(
                FiscalYear.empresa_id == A, FiscalYear.year == EJERCICIO
            )
        )
        return {e.tipo: e.estado for e in entradas}, fy.is_closed

    tipos, cerrado = cierres.run(cierres.consultar(_estado))
    from models.acct.journal import JournalEntryEstado, JournalEntryTipo

    assert tipos[JournalEntryTipo.REGULARIZACION] is JournalEntryEstado.POSTED
    assert tipos[JournalEntryTipo.CIERRE] is JournalEntryEstado.POSTED
    assert cerrado is True

    # Reintento -> 409 (idempotencia).
    repetido = cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert repetido.status_code == 409


# --- Scenario 4 -----------------------------------------------------------


def test_scenario_4_reapertura_con_asiento_rectificativo(closing_client) -> None:
    cierres = closing_client
    original = cierres.asiento(A, "2026-03-10", _ventas("1000.0000"))
    periodo = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    ).json()

    # 1) Solicitar la reapertura con justificacion.
    solicitud = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error en el asiento 3",
        },
        empresa_id=A,
    )
    assert solicitud.status_code == 201
    assert solicitud.json()["numero_solicitud"] == 1

    # 2) Aprobar.
    aprobado = cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud.json()['solicitud_id']}/aprobar", empresa_id=A
    )
    assert aprobado.status_code == 200

    # 3) Crear el asiento rectificativo por el motor de SPEC-002.
    rectificativo = cierres.asiento(
        A, "2026-03-20", _ventas("1000.0000"), concepto="Rectificacion", tipo="REVERSAL"
    )

    # 4) Cerrar el ajuste -> re-cierre automatico.
    cerrado = cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud.json()['solicitud_id']}/rectificar",
        json={"asiento_id": str(rectificativo)},
        empresa_id=A,
    )
    assert cerrado.status_code == 200
    assert cerrado.json()["estado"] == "cerrada"

    detalle = cierres.get(
        f"/api/v1/cierres/reaperturas/{solicitud.json()['solicitud_id']}", empresa_id=A
    ).json()
    assert detalle["periodo_cerrado"]["estado"] == "cerrado_ajustado"
    assert detalle["periodo_cerrado"]["n_reaperturas"] == 1
    assert periodo["periodo_id"] == detalle["periodo_cerrado"]["periodo_id"]

    # El periodo vuelve a bloquearse.
    with pytest.raises(AsientoError) as exc:
        cierres.asiento(A, "2026-03-25", _ventas("1.0000"))
    assert exc.value.code == "periodo_cerrado"

    # El asiento original sigue intacto.
    async def _firma(session):
        from sqlalchemy import select

        from models.acct.journal import JournalEntry, JournalEntryLine

        entrada = await session.get(JournalEntry, original)
        filas = (
            await session.execute(
                select(JournalEntryLine.debe, JournalEntryLine.haber).where(
                    JournalEntryLine.journal_entry_id == original
                )
            )
        ).all()
        return entrada.estado.value, [
            (Decimal(str(fila[0])), Decimal(str(fila[1]))) for fila in filas
        ]

    estado, lineas = cierres.run(cierres.consultar(_firma))
    assert estado == "POSTED"
    assert lineas == [
        (Decimal("0.0000"), Decimal("1000.0000")),
        (Decimal("1000.0000"), Decimal("0.0000")),
    ]


# --- Scenario 5 -----------------------------------------------------------


def test_scenario_5_rechazos(closing_client) -> None:
    cierres = closing_client
    # Sin motivo -> 422.
    sin_motivo = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={"ejercicio": EJERCICIO, "tipo_periodo": "MES", "periodo": 2},
        empresa_id=A,
    )
    assert sin_motivo.status_code == 422
    assert sin_motivo.json()["detail"]["code"] == "justificacion_requerida"

    for mes in (2, 3):
        cierres.post(
            "/api/v1/cierres/intermedios",
            json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": mes},
            empresa_id=A,
        )
    cuerpo = {
        "ejercicio": EJERCICIO,
        "tipo_periodo": "MES",
        "periodo": 2,
        "motivo": "Error",
    }
    assert cierres.post("/api/v1/cierres/reaperturas", json=cuerpo, empresa_id=A).status_code == 201
    # Segunda solicitud activa en el mismo periodo -> 409.
    segunda = cierres.post("/api/v1/cierres/reaperturas", json=cuerpo, empresa_id=A)
    assert segunda.status_code == 409
    assert segunda.json()["detail"]["code"] == "solicitud_activa"

    # Reapertura con cuentas anuales formuladas -> 409.
    async def _formular(session):
        from models.reporting.formulacion import (
            FormulacionCuentasAnuales,
            FormulacionEstado,
        )

        session.add(
            FormulacionCuentasAnuales(
                empresa_id=A,
                ejercicio=EJERCICIO,
                numero_formulacion=1,
                fecha_formulacion=date(EJERCICIO, 12, 31),
                contenido_hash="0" * 64,
                estado=FormulacionEstado.formulada,
                snapshot={},
            )
        )

    cierres.run(cierres.mutar(_formular))
    formulado = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={**cuerpo, "periodo": 3, "motivo": "Con ejercicio formulado"},
        empresa_id=A,
    )
    assert formulado.status_code == 409
    assert formulado.json()["detail"]["code"] == "ejercicio_legalizado"


# --- Scenario 6 -----------------------------------------------------------


def test_scenario_6_aislamiento_multi_empresa(closing_client) -> None:
    cierres = closing_client
    # Empresa A cierra su mes 3.
    creado = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    )
    assert creado.status_code == 201
    periodo_a = creado.json()["periodo_id"]

    # Empresa B consulta el cierre de A -> 404.
    ajeno = cierres.get(
        f"/api/v1/cierres/intermedios/{periodo_a}/balanza", empresa_id=B
    )
    assert ajeno.status_code == 404
    assert cierres.get("/api/v1/cierres/intermedios", empresa_id=B).json()["total"] == 0

    # Y puede operar en sus propios periodos.
    propio = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=B,
    )
    assert propio.status_code == 201
    assert propio.json()["periodo_id"] != periodo_a
