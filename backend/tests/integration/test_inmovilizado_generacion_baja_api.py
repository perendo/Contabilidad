"""Tests de generación, reapertura y baja de amortizaciones (SPEC-014 US2/US3).

Cubre los escenarios del quickstart §3/§4/§5: balance estricto del asiento
681/281 (constitución I), anti-duplicación por período (409), reapertura con
REVERSAL sin tocar el asiento original (constitución II) y baja con prorrateo
(mensual/dias) y resultado exacto.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.inmovilizado.amortizacion_generada import AmortizacionGenerada
from models.inmovilizado.plan_amortizacion import PlanAmortizacion


def _uu(txt: str) -> uuid.UUID:
    return uuid.UUID(txt)


def _lineas_asiento(cli, asiento_id) -> list[tuple[str, Decimal, Decimal]]:
    async def _op(session):
        rows = (
            await session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == _uu(asiento_id)
                )
            )
        ).all()
        return [(r.cuenta, r.debe or Decimal(0), r.haber or Decimal(0)) for r in rows]

    return cli.run(cli.consultar(_op))


def _estado_asiento(cli, asiento_id) -> str:
    async def _op(session):
        e = await session.scalar(
            select(JournalEntry).where(JournalEntry.id == _uu(asiento_id))
        )
        return e.estado.value if e else None

    return cli.run(cli.consultar(_op))


def _fila_plan(cli, activo_id, ejercicio, periodo) -> dict | None:
    async def _op(session):
        fila = await session.scalar(
            select(PlanAmortizacion).where(
                PlanAmortizacion.activo_id == _uu(activo_id),
                PlanAmortizacion.ejercicio == ejercicio,
                PlanAmortizacion.periodo == periodo,
            )
        )
        if fila is None:
            return None
        return {"estado": fila.estado.value, "cuota": str(fila.cuota), "acumulado": str(fila.acumulado)}

    return cli.run(cli.consultar(_op))


def _generar(cli, empresa_id: int, periodo: int, ejercicio: int = 2026):
    return cli.post(
        "/api/v1/amortizaciones/generar",
        empresa_id=empresa_id,
        json={"ejercicio": ejercicio, "periodo": periodo},
    )


def test_generar_asiento_balanceado(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    assert r.status_code == 201, r.text
    activo_id = r.json()["id"]

    g = _generar(cli, 10, 10)
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["n"] == 1
    gen = body["generados"][0]
    assert gen["activo_id"] == activo_id
    assert gen["cuota"] == "250.0000"

    lineas = _lineas_asiento(cli, gen["asiento_id"])
    total_debe = sum((d for _, d, _ in lineas), Decimal(0))
    total_haber = sum((h for _, _, h in lineas), Decimal(0))
    assert total_debe == total_haber == Decimal("250.0000")
    assert ("6810", Decimal("250.0000"), Decimal(0)) in lineas
    assert ("2818", Decimal(0), Decimal("250.0000")) in lineas

    fila = _fila_plan(cli, activo_id, 2026, 10)
    assert fila["estado"] == "amortizado"


def test_generar_duplicado_409(inmovilizado_client) -> None:
    cli = inmovilizado_client
    cli.crear()
    assert _generar(cli, 10, 10).status_code == 200
    r = _generar(cli, 10, 10)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "periodo_ya_amortizado"


def test_generar_ejercicio_cerrado_409(inmovilizado_client) -> None:
    cli = inmovilizado_client
    cli.crear()
    cli.marcar_cerrado(10, 2026)
    r = _generar(cli, 10, 11)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"


def test_aislamiento_tenant_generacion(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r_a = cli.crear(numero_activo="ISO-1")
    assert r_a.status_code == 201
    assert _generar(cli, 10, 10).status_code == 200

    assert cli.get(20, "/api/v1/amortizaciones").json()["total"] == 0
    assert cli.get(10, "/api/v1/amortizaciones").json()["total"] == 1


def test_reabrir_reversal_original_intacto(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    activo_id = r.json()["id"]
    g = _generar(cli, 10, 10).json()
    gen = g["generados"][0]
    asiento_original = gen["asiento_id"]

    r2 = cli.post(
        f"/api/v1/amortizaciones/{_uu(gen['generada_id'])}/reabrir",
        empresa_id=10,
        json={"motivo": "corrección"},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["reversal_asiento_id"]
    assert body["estado"] == "pendiente"
    reversal_id = body["reversal_asiento_id"]

    assert _estado_asiento(cli, asiento_original) == JournalEntryEstado.POSTED.value

    async def _op(session):
        rev = await session.scalar(
            select(JournalEntry).where(JournalEntry.empresa_id == 10, JournalEntry.id == _uu(reversal_id))
        )
        return {
            "tipo": rev.tipo.value,
            "estado": rev.estado.value,
            "original_id": str(rev.original_id) if rev.original_id else None,
            "numero": rev.numero_asiento,
        }

    rev = cli.run(cli.consultar(_op))
    assert rev["tipo"] == JournalEntryTipo.REVERSAL.value
    assert rev["estado"] == JournalEntryEstado.POSTED.value
    assert rev["original_id"] == asiento_original

    lineas_rev = _lineas_asiento(cli, reversal_id)
    lineas_orig = _lineas_asiento(cli, asiento_original)
    for (cuenta_orig, debe_orig, haber_orig), (cuenta_rev, debe_rev, haber_rev) in zip(sorted(lineas_orig), sorted(lineas_rev)):
        assert cuenta_rev == cuenta_orig
        assert debe_rev == haber_orig
        assert haber_rev == debe_orig

    fila = _fila_plan(cli, activo_id, 2026, 10)
    assert fila["estado"] == "pendiente"


def test_reabrir_y_regenerar_con_trazabilidad(inmovilizado_client) -> None:
    cli = inmovilizado_client
    cli.crear()
    gen = _generar(cli, 10, 10).json()["generados"][0]
    previa_id = gen["generada_id"]

    r = cli.post(
        f"/api/v1/amortizaciones/{_uu(previa_id)}/reabrir",
        empresa_id=10,
        json={"motivo": "ajuste"},
    )
    assert r.status_code == 200

    g = _generar(cli, 10, 10)
    assert g.status_code == 200, g.text
    assert len(g.json()["generados"]) == 1

    async def _op(session):
        filas = (
            await session.scalars(
                select(AmortizacionGenerada)
                .where(AmortizacionGenerada.empresa_id == 10)
                .order_by(AmortizacionGenerada.created_at)
            )
        ).all()
        return [(str(f.reapertura_de) if f.reapertura_de else None, f.reabierta) for f in filas]

    trazabilidad = cli.run(cli.consultar(_op))
    assert trazabilidad[0] == (None, True)
    assert trazabilidad[1] == (previa_id, False)


def test_reabrir_ejercicio_cerrado_409(inmovilizado_client) -> None:
    cli = inmovilizado_client
    cli.crear()
    gen = _generar(cli, 10, 10).json()["generados"][0]
    cli.marcar_cerrado(10, 2026)
    r = cli.post(
        f"/api/v1/amortizaciones/{_uu(gen['generada_id'])}/reabrir",
        empresa_id=10,
        json={"motivo": "x"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"


def test_reabrir_inexistente_404(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.post(
        f"/api/v1/amortizaciones/{_uu('00000000-0000-0000-0000-000000000099')}/reabrir",
        empresa_id=10,
        json={"motivo": "x"},
    )
    assert r.status_code == 404


def test_baja_venta_mensual(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    activo_id = r.json()["id"]
    for periodo in range(1, 6):
        assert _generar(cli, 10, periodo).status_code == 200

    b = cli.post(
        f"/api/v1/activos/{_uu(activo_id)}/baja",
        empresa_id=10,
        json={"fecha_baja": "2026-06-15", "precio_venta": "8000.0000", "tipo": "venta"},
    )
    assert b.status_code == 201, b.text
    body = b.json()
    assert body["amortizacion_hasta_baja"] == "1500.0000"
    assert body["amortizacion_acumulada"] == "1250.0000"
    assert body["valor_neto_contable"] == "13500.0000"
    assert body["resultado"] == "-5500.0000"
    assert body["tipo"] == "venta"

    lineas = _lineas_asiento(cli, body["asiento_id"])
    total_debe = sum((d for _, d, _ in lineas), Decimal(0))
    total_haber = sum((h for _, _, h in lineas), Decimal(0))
    assert total_debe == total_haber == Decimal("15000.0000")
    assert ("2818", Decimal("1500.0000"), Decimal(0)) in lineas
    assert ("5720", Decimal("8000.0000"), Decimal(0)) in lineas
    assert ("6710", Decimal("5500.0000"), Decimal(0)) in lineas
    assert ("2180", Decimal(0), Decimal("15000.0000")) in lineas

    detalle = cli.get(10, f"/api/v1/activos/{_uu(activo_id)}").json()
    assert detalle["estado"] == "dado_de_baja"
    assert detalle["fecha_baja"] == "2026-06-15"


def test_baja_dias_prorrateo_directo(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    activo_id = r.json()["id"]
    for periodo in range(1, 6):
        assert _generar(cli, 10, periodo).status_code == 200

    from datetime import date as _date

    from services.inmovilizado import baja as baja_svc

    async def _op(session):
        return await baja_svc.dar_de_baja(
            session,
            empresa_id=10,
            activo_id=_uu(activo_id),
            fecha_baja=_date(2026, 6, 15),
            precio_venta="8000.0000",
            tipo="venta",
            prorrateo="dias",
        )

    body = cli.run(cli.mutar(_op))
    assert body["amortizacion_hasta_baja"] == "1375.0000"
    assert body["valor_neto_contable"] == "13625.0000"
    assert body["resultado"] == "-5625.0000"


def test_baja_doble_409(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    activo_id = r.json()["id"]
    assert cli.post(
        f"/api/v1/activos/{_uu(activo_id)}/baja",
        empresa_id=10,
        json={"fecha_baja": "2026-06-15", "precio_venta": "8000.0000", "tipo": "venta"},
    ).status_code == 201
    assert cli.post(
        f"/api/v1/activos/{_uu(activo_id)}/baja",
        empresa_id=10,
        json={"fecha_baja": "2026-06-16", "precio_venta": "9000.0000", "tipo": "venta"},
    ).status_code == 409


def test_baja_tenant_404(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    activo_id = r.json()["id"]
    b = cli.post(
        f"/api/v1/activos/{_uu(activo_id)}/baja",
        empresa_id=20,
        json={"fecha_baja": "2026-06-15", "precio_venta": "8000.0000", "tipo": "venta"},
    )
    assert b.status_code == 404


def test_baja_ejercicio_cerrado_409(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    activo_id = r.json()["id"]
    cli.marcar_cerrado(10, 2026)
    b = cli.post(
        f"/api/v1/activos/{_uu(activo_id)}/baja",
        empresa_id=10,
        json={"fecha_baja": "2026-03-01", "precio_venta": "1000.0000", "tipo": "retirada"},
    )
    assert b.status_code == 409
    assert b.json()["detail"]["code"] == "ejercicio_cerrado"


def test_baja_sale_del_plan(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    activo_id = r.json()["id"]
    assert _generar(cli, 10, 1).status_code == 200
    assert cli.post(
        f"/api/v1/activos/{_uu(activo_id)}/baja",
        empresa_id=10,
        json={"fecha_baja": "2026-06-15", "precio_venta": "8000.0000", "tipo": "venta"},
    ).status_code == 201

    g = _generar(cli, 10, 11)
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["generados"] == []
    assert any(o["activo_id"] == activo_id and o["motivo"] == "sin_cuota" for o in body["omitidos"])


def test_baja_fecha_anterior_alta_422(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    activo_id = r.json()["id"]
    b = cli.post(
        f"/api/v1/activos/{_uu(activo_id)}/baja",
        empresa_id=10,
        json={"fecha_baja": "2025-12-31", "precio_venta": "100.0000", "tipo": "retirada"},
    )
    assert b.status_code == 422
    assert b.json()["detail"]["code"] == "fecha_baja_invalida"