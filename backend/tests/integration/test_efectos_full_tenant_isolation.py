"""Aislamiento multi-tenant completo de efectos y cobros (SPEC-021 T040).

Escenario cross-empresa integral: empresa A registra y cobra un efecto en su
empresa, empresa B no lo ve en cartera, no puede cobrar/imputar, no ve el
cobro por medio ni comisiones. Ningún endpoint expone empresa del body.
"""

from __future__ import annotations

from uuid import uuid4


def _body(efectos_client, *, empresa_id: int = 10, numero: str = "CH-ISO"):
    return {
        "tercero_id": str(efectos_client.terceros[empresa_id]),
        "tipo_efecto": "CHEQUE",
        "numero_documento": numero,
        "fecha_emision": "2026-05-01",
        "fecha_vencimiento": "2026-07-01",
        "importe": "1200.0000",
    }


def test_empresa_b_no_ve_nada_de_empresa_a(efectos_client):
    r = efectos_client.post("/api/v1/efectos", empresa_id=10, json=_body(efectos_client))
    assert r.status_code == 201
    efecto_a = r.json()["id"]

    cartera_b = efectos_client.get(20, "/api/v1/efectos")
    assert cartera_b.status_code == 200
    assert cartera_b.json()["total"] == 0

    detalle_b = efectos_client.get(20, f"/api/v1/efectos/{efecto_a}")
    assert detalle_b.status_code == 404

    cobro_b = efectos_client.post(f"/api/v1/efectos/{efecto_a}/cobrar", empresa_id=20,
                                  json={"fecha_cobro": "2026-07-02"})
    assert cobro_b.status_code == 404
    assert cobro_b.json()["detail"]["code"] == "efecto_no_encontrado"

    impago_b = efectos_client.post(f"/api/v1/efectos/{efecto_a}/impago", empresa_id=20,
                                   json={"fecha_impago": "2026-07-05"})
    assert impago_b.status_code == 404


def test_empresa_a_si_puede_gestionar_su_efecto(efectos_client):
    r = efectos_client.post("/api/v1/efectos", empresa_id=10, json=_body(efectos_client))
    efecto_a = r.json()["id"]
    cobro = efectos_client.post(f"/api/v1/efectos/{efecto_a}/cobrar", empresa_id=10,
                                json={"fecha_cobro": "2026-07-02"})
    assert cobro.status_code == 200
    assert cobro.json()["estado"] == "cobrado"

    cartera_a = efectos_client.get(10, "/api/v1/efectos")
    assert cartera_a.json()["total"] == 1
    assert cartera_a.json()["items"][0]["estado"] == "cobrado"


def test_cambio_empresa_en_body_ignorado(efectos_client):
    """El cuerpo no influye en la empresa: aunque el tercero pertenece a la
    empresa A, una sesión de la empresa B debe rechazar la operación."""
    body = _body(efectos_client)
    r = efectos_client.post("/api/v1/efectos", empresa_id=20,
                            json={**body, "tercero_id": str(efectos_client.terceros[10])})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "tercero_no_encontrado"


def test_cobros_medio_cross_empresa_invisibles(efectos_client):
    vencimiento_a = efectos_client.vencimientos[10][0]
    r = efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                            json={
                                "vencimiento_id": str(vencimiento_a),
                                "medio_cobro": "TARJETA",
                                "fecha_cobro": "2026-07-01",
                                "importe_comision": "10.0000",
                            })
    assert r.status_code == 201
    cobro_id = r.json()["id"]

    lista_b = efectos_client.get(20, "/api/v1/cobros-medio")
    assert lista_b.json()["total"] == 0

    detalle_b = efectos_client.get(20, f"/api/v1/cobros-medio/{cobro_id}")
    assert detalle_b.status_code == 404

    from sqlalchemy import func, select

    async def _comisiones_empresa_b():
        from models.treasury.comision import ComisionBancaria

        async def _op(session):
            return await session.scalar(
                select(func.count()).select_from(ComisionBancaria).where(
                    ComisionBancaria.empresa_id == 20
                )
            )

        return await efectos_client.consultar(_op)

    assert efectos_client.run(_comisiones_empresa_b()) == 0


def test_vencimiento_de_otra_empresa_no_cobrable(efectos_client):
    vencimiento_a = efectos_client.vencimientos[10][0]
    r = efectos_client.post("/api/v1/cobros-medio", empresa_id=20,
                            json={
                                "vencimiento_id": str(vencimiento_a),
                                "medio_cobro": "TRANSFERENCIA",
                                "fecha_cobro": "2026-07-01",
                            })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "vencimiento_no_encontrado"


def test_detalle_efecto_inexistente_404(efectos_client):
    r = efectos_client.get(10, f"/api/v1/efectos/{uuid4()}")
    assert r.status_code == 404