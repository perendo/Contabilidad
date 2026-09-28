"""Efectos HTTP (SPEC-021 T021, T022, T023 + tenancy).

Escenarios de quickstart por HTTP: alta de efecto, cobro con asiento
balanceado y impago con REVERSAL, gastos y reapertura del vencimiento;
aislamiento multi-tenant en cada endpoint.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4


def _body(efectos_client, *, empresa_id: int = 10, numero: str = "CH-001",
          tipo: str = "CHEQUE", importe: str = "1200.0000") -> dict:
    return {
        "tercero_id": str(efectos_client.terceros[empresa_id]),
        "tipo_efecto": tipo,
        "numero_documento": numero,
        "fecha_emision": "2026-05-01",
        "fecha_vencimiento": "2026-07-01",
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
        return [
            {"cuenta": l.cuenta, "debe": l.debe or Decimal(0), "haber": l.haber or Decimal(0)}
            for l in filas
        ]

    return efectos_client.run(efectos_client.consultar(_op))


def test_crear_y_listar_efecto(efectos_client):
    r = efectos_client.post("/api/v1/efectos", empresa_id=10, json=_body(efectos_client))
    assert r.status_code == 201
    data = r.json()
    assert data["estado"] == "emitido"
    efecto_id = data["id"]

    lista = efectos_client.get(10, "/api/v1/efectos")
    assert lista.status_code == 200
    body = lista.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == efecto_id
    assert body["items"][0]["importe"] == "1200.0000"
    assert body["items"][0]["estado"] == "emitido"
    assert body["por_estado"][0]["estado"] == "emitido"

    detalle = efectos_client.get(10, f"/api/v1/efectos/{efecto_id}")
    assert detalle.status_code == 200
    assert detalle.json()["numero_documento"] == "CH-001"


def test_cobro_efecto_balance_y_estado(efectos_client):
    r = efectos_client.post("/api/v1/efectos", empresa_id=10, json=_body(efectos_client))
    efecto_id = r.json()["id"]
    r = efectos_client.post(f"/api/v1/efectos/{efecto_id}/cobrar", empresa_id=10,
                            json={"fecha_cobro": "2026-07-02"})
    assert r.status_code == 200
    data = r.json()
    assert data["estado"] == "cobrado"
    assert data["asiento_cobro_id"]

    asiento_id = data["asiento_cobro_id"]
    lineas = _lineas(efectos_client, asiento_id)
    debe = sum(l["debe"] for l in lineas)
    haber = sum(l["haber"] for l in lineas)
    assert debe == haber == Decimal("1200.0000")
    assert {l["cuenta"] for l in lineas} == {"572", "431"}

    detalle = efectos_client.get(10, f"/api/v1/efectos/{efecto_id}").json()
    assert detalle["asientos"]["asiento_cobro_id"]["tipo"] == "COBRO"


def test_cobro_doble_rechazado_409(efectos_client):
    efecto_id = efectos_client.post(
        "/api/v1/efectos", empresa_id=10, json=_body(efectos_client)
    ).json()["id"]
    efectos_client.post(f"/api/v1/efectos/{efecto_id}/cobrar", empresa_id=10,
                        json={"fecha_cobro": "2026-07-02"})
    r = efectos_client.post(f"/api/v1/efectos/{efecto_id}/cobrar", empresa_id=10,
                            json={"fecha_cobro": "2026-07-03"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "efecto_estado_no_valido"


def test_impago_letra_reversal_y_reapertura_vencimiento(efectos_client):
    vencimiento_id = efectos_client.vencimientos[10][0]
    r = efectos_client.post(f"/api/v1/vencimientos/{vencimiento_id}/cobrar", empresa_id=10,
                            json={"fecha": "2026-06-30", "importe": "1500.0000"})
    assert r.status_code == 200

    r = efectos_client.post("/api/v1/efectos", empresa_id=10,
                            json=_body(efectos_client, numero="LE-001", tipo="LETRA",
                                       importe="1200.0000"))
    assert r.status_code == 201
    efecto_id = r.json()["id"]

    r = efectos_client.post(f"/api/v1/efectos/{efecto_id}/impago", empresa_id=10,
                            json={"fecha_impago": "2026-07-05", "motivo": "Impagado",
                                  "gastos_devolucion": "35.0000"})
    assert r.status_code == 200
    data = r.json()
    assert data["estado"] == "impagado"
    assert data["asiento_impago_id"]

    lineas = _lineas(efectos_client, data["asiento_impago_id"])
    debe = sum(l["debe"] for l in lineas)
    haber = sum(l["haber"] for l in lineas)
    assert debe == haber == Decimal("1235.0000")
    por_cuenta = {l["cuenta"]: (l["debe"], l["haber"]) for l in lineas}
    assert por_cuenta["431"] == (Decimal("1200.0000"), Decimal(0))
    assert por_cuenta["626"] == (Decimal("35.0000"), Decimal(0))
    assert por_cuenta["572"] == (Decimal(0), Decimal("1235.0000"))

    detalle = efectos_client.get(10, f"/api/v1/efectos/{efecto_id}").json()
    assert detalle["asientos"]["asiento_impago_id"]["tipo"] == "REVERSAL"

    async def _estado_vencimiento():
        from sqlalchemy import select

        from models.ar.vencimiento import Vencimiento

        async def _op(session):
            v = await session.scalar(
                select(Vencimiento).where(Vencimiento.id == vencimiento_id)
            )
            return v.estado.value, v.acumulado

        return await efectos_client.consultar(_op)

    estado, acumulado = efectos_client.run(_estado_vencimiento())
    assert estado == "pendiente"
    assert acumulado == Decimal("0.0000")


def test_documento_duplicado_409(efectos_client):
    efectos_client.post("/api/v1/efectos", empresa_id=10,
                        json=_body(efectos_client, numero="CH-DUP"))
    r = efectos_client.post("/api/v1/efectos", empresa_id=10,
                            json=_body(efectos_client, numero="CH-DUP"))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "documento_duplicado"


def test_impago_sobre_efecto_cobrado_409(efectos_client):
    efecto_id = efectos_client.post(
        "/api/v1/efectos", empresa_id=10, json=_body(efectos_client, numero="CH-CB")
    ).json()["id"]
    efectos_client.post(f"/api/v1/efectos/{efecto_id}/cobrar", empresa_id=10,
                        json={"fecha_cobro": "2026-07-02"})
    r = efectos_client.post(f"/api/v1/efectos/{efecto_id}/impago", empresa_id=10,
                            json={"fecha_impago": "2026-07-05"})
    assert r.status_code == 409


def test_efecto_inexistente_404(efectos_client):
    r = efectos_client.post(f"/api/v1/efectos/{uuid4()}/cobrar", empresa_id=10,
                            json={"fecha_cobro": "2026-07-02"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "efecto_no_encontrado"


def test_aislamiento_por_empresa(efectos_client):
    efectos_client.post("/api/v1/efectos", empresa_id=10, json=_body(efectos_client, numero="CH-A1"))
    efectos_client.post("/api/v1/efectos", empresa_id=20,
                        json=_body(efectos_client, empresa_id=20, numero="CH-B1"))
    lista_a = efectos_client.get(10, "/api/v1/efectos").json()
    lista_b = efectos_client.get(20, "/api/v1/efectos").json()
    assert lista_a["total"] == 1
    assert lista_b["total"] == 1


def test_aislamiento_efecto_otra_empresa_404(efectos_client):
    efecto_a = efectos_client.post(
        "/api/v1/efectos", empresa_id=10, json=_body(efectos_client)
    ).json()["id"]
    r = efectos_client.get(20, f"/api/v1/efectos/{efecto_a}")
    assert r.status_code == 404
    r = efectos_client.post(f"/api/v1/efectos/{efecto_a}/cobrar", empresa_id=20,
                            json={"fecha_cobro": "2026-07-02"})
    assert r.status_code == 404
    r = efectos_client.post(f"/api/v1/efectos/{efecto_a}/impago", empresa_id=20,
                            json={"fecha_impago": "2026-07-05"})
    assert r.status_code == 404