"""Escenarios de quickstart de SPEC-021 (T041).

Reproduce los 6 escenarios de `specs/021-medios-pago-efectos/quickstart.md`
sobre un cliente HTTP real: balances de asientos, REVERSAL con gastos y
reapertura de vencimiento, cobro con comisión, filtros de cartera, rechazo
por ejercicio cerrado y aislamiento por empresa.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID


def _efecto(efectos_client, *, empresa_id: int = 10, numero: str, tipo: str = "CHEQUE",
            importe: str, vencimiento: str = "2026-10-15"):
    return {
        "tercero_id": str(efectos_client.terceros[empresa_id]),
        "tipo_efecto": tipo,
        "numero_documento": numero,
        "fecha_emision": "2026-09-15",
        "fecha_vencimiento": vencimiento,
        "importe": importe,
        "moneda": "EUR",
    }


def _lineas(efectos_client, entry_id):
    from sqlalchemy import select

    from models.acct.journal import JournalEntryLine

    async def _op(session):
        filas = (
            await session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == UUID(entry_id)
                )
            )
        ).all()
        return {
            l.cuenta: (l.debe or Decimal(0), l.haber or Decimal(0)) for l in filas
        }

    return efectos_client.run(efectos_client.consultar(_op))


def test_escenario_1_registrar_y_cobrar_cheque(efectos_client):
    r = efectos_client.post("/api/v1/efectos", empresa_id=10,
                            json=_efecto(efectos_client, numero="CHQ-001", importe="2500.0000"))
    assert r.status_code == 201
    efecto_id = r.json()["id"]
    assert r.json()["estado"] == "emitido"

    r = efectos_client.post(f"/api/v1/efectos/{efecto_id}/cobrar", empresa_id=10,
                            json={"fecha_cobro": "2026-10-15"})
    assert r.status_code == 200
    assert r.json()["estado"] == "cobrado"
    assert r.json()["asiento_cobro_id"]

    cuentas = _lineas(efectos_client, r.json()["asiento_cobro_id"])
    assert cuentas["572"] == (Decimal("2500.0000"), Decimal(0))
    assert cuentas["431"] == (Decimal(0), Decimal("2500.0000"))


def test_escenario_2_impago_letra_con_gastos(efectos_client):
    vencimiento_id = efectos_client.vencimientos[10][0]
    r = efectos_client.post(f"/api/v1/vencimientos/{vencimiento_id}/cobrar", empresa_id=10,
                            json={"fecha": "2026-06-30", "importe": "1500.0000"})
    assert r.status_code == 200

    r = efectos_client.post("/api/v1/efectos", empresa_id=10,
                            json=_efecto(efectos_client, numero="LET-001", tipo="LETRA",
                                         importe="1200.0000", vencimiento="2026-10-01"))
    assert r.status_code == 201
    efecto_id = r.json()["id"]

    r = efectos_client.post(f"/api/v1/efectos/{efecto_id}/impago", empresa_id=10,
                            json={"fecha_impago": "2026-10-02", "motivo": "Fondos insuficientes",
                                  "gastos_devolucion": "35.0000"})
    assert r.status_code == 200
    assert r.json()["estado"] == "impagado"
    asiento_id = r.json()["asiento_impago_id"]

    cuentas = _lineas(efectos_client, asiento_id)
    assert cuentas["431"] == (Decimal("1200.0000"), Decimal(0))
    assert cuentas["626"] == (Decimal("35.0000"), Decimal(0))
    assert cuentas["572"] == (Decimal(0), Decimal("1235.0000"))
    assert (cuentas["431"][0] + cuentas["626"][0]) == cuentas["572"][1]

    async def _vencimiento():
        from sqlalchemy import select

        from models.ar.vencimiento import Vencimiento

        async def _op(session):
            v = await session.scalar(
                select(Vencimiento).where(Vencimiento.id == vencimiento_id)
            )
            return v.estado.value, v.acumulado

        return await efectos_client.consultar(_op)

    estado, acumulado = efectos_client.run(_vencimiento())
    assert estado == "pendiente"
    assert acumulado == Decimal("0.0000")

    detalle = efectos_client.get(10, f"/api/v1/efectos/{efecto_id}").json()
    assert detalle["asientos"]["asiento_impago_id"]["tipo"] == "REVERSAL"


def test_escenario_3_cobro_tpv_con_comision(efectos_client):
    vencimiento_id = efectos_client.vencimientos[10][0]
    r = efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                            json={
                                "vencimiento_id": str(vencimiento_id),
                                "medio_cobro": "TARJETA",
                                "fecha_cobro": "2026-10-05",
                                "importe_comision": "25.0000",
                            })
    assert r.status_code == 201
    data = r.json()
    assert data["importe_total"] == "1500.0000"
    assert data["importe_neto"] == "1475.0000"
    cuentas = _lineas(efectos_client, data["asiento_cobro_id"])
    assert cuentas["572"] == (Decimal("1475.0000"), Decimal(0))
    assert cuentas["626"] == (Decimal("25.0000"), Decimal(0))
    assert cuentas["430"] == (Decimal(0), Decimal("1500.0000"))


def test_escenario_4_filtros_cartera(efectos_client):
    efectos_client.post("/api/v1/efectos", empresa_id=10,
                        json=_efecto(efectos_client, numero="P1", importe="800.0000"))
    efectos_client.post("/api/v1/efectos", empresa_id=10,
                        json=_efecto(efectos_client, numero="L2", tipo="LETRA",
                                     importe="1200.0000", vencimiento="2026-12-15"))
    efectos_client.post("/api/v1/efectos", empresa_id=10,
                        json=_efecto(efectos_client, numero="PG3", tipo="PAGARE",
                                     importe="900.0000"))
    emitidos = efectos_client.get(10, "/api/v1/efectos", estado="emitido").json()
    assert emitidos["total"] == 3
    letras = efectos_client.get(10, "/api/v1/efectos",
                                tipo_efecto="LETRA", fecha_desde="2026-10-01",
                                fecha_hasta="2026-12-31").json()
    assert letras["total"] == 1
    assert letras["items"][0]["numero_documento"] == "L2"


def test_escenario_5_rechazo_por_ejercicio_cerrado(efectos_client):
    r = efectos_client.post("/api/v1/efectos", empresa_id=10,
                            json=_efecto(efectos_client, numero="CC-1", importe="500.0000"))
    efecto_id = r.json()["id"]
    r = efectos_client.post(f"/api/v1/efectos/{efecto_id}/cobrar", empresa_id=10,
                            json={"fecha_cobro": "2025-12-31"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"


def test_escenario_6_aislamiento_multi_empresa(efectos_client):
    r = efectos_client.post("/api/v1/efectos", empresa_id=10,
                            json=_efecto(efectos_client, numero="PAG-001",
                                         tipo="PAGARE", importe="800.0000",
                                         vencimiento="2026-11-15"))
    assert r.status_code == 201
    efecto_id = r.json()["id"]
    detalle_b = efectos_client.get(20, f"/api/v1/efectos/{efecto_id}")
    assert detalle_b.status_code == 404