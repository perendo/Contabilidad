"""Cobros por medio HTTP (SPEC-021 T029, T030 + tenancy).

Registro de cobro con transferencia y comisión, listado paginado con filtros,
detalle y aislamiento multi-tenant (constitución III).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4


def _body(efectos_client, *, empresa_id: int = 10, vencimiento_id=None,
          medio: str = "TRANSFERENCIA", comision: str = "0") -> dict:
    return {
        "vencimiento_id": str(
            vencimiento_id or efectos_client.vencimientos[empresa_id][0]
        ),
        "medio_cobro": medio,
        "fecha_cobro": "2026-07-01",
        "importe_comision": comision,
        "tipo_comision": "TRANSFERENCIA" if medio == "TRANSFERENCIA" else "OTRA",
        "banco_codigo": "0001",
        "porcentaje": "1.50" if comision else None,
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


def test_cobro_transferencia_con_comision_201(efectos_client):
    r = efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                            json=_body(efectos_client, comision="15.0000"))
    assert r.status_code == 201
    data = r.json()
    assert data["medio_cobro"] == "TRANSFERENCIA"
    assert data["importe_total"] == "1500.0000"
    assert data["importe_comision"] == "15.0000"
    assert data["importe_neto"] == "1485.0000"
    assert data["comision_id"]

    lineas = _lineas(efectos_client, data["asiento_cobro_id"])
    debe = sum(l["debe"] for l in lineas)
    haber = sum(l["haber"] for l in lineas)
    assert debe == haber == Decimal("1500.0000")
    por_cuenta = {l["cuenta"]: (l["debe"], l["haber"]) for l in lineas}
    assert por_cuenta["572"] == (Decimal("1485.0000"), Decimal(0))
    assert por_cuenta["626"] == (Decimal("15.0000"), Decimal(0))
    assert por_cuenta["430"] == (Decimal(0), Decimal("1500.0000"))


def test_cobro_tpv_sin_comision(efectos_client):
    r = efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                            json=_body(efectos_client, medio="TARJETA"))
    assert r.status_code == 201
    data = r.json()
    assert data["importe_comision"] == "0.0000"
    assert data["importe_neto"] == "1500.0000"
    assert data["comision_id"] is None
    lineas = _lineas(efectos_client, data["asiento_cobro_id"])
    assert {l["cuenta"] for l in lineas} == {"572", "430"}


def test_vencimiento_nuevo_saldado_al_cobrar(efectos_client):
    vencimiento_id = efectos_client.vencimientos[10][0].hex
    efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                        json=_body(efectos_client, vencimiento_id=vencimiento_id))

    async def _leo():
        from sqlalchemy import select

        from models.ar.vencimiento import Vencimiento

        async def _op(session):
            v = await session.scalar(
                select(Vencimiento).where(Vencimiento.id == UUID(vencimiento_id))
            )
            return v.estado.value, v.acumulado

        return await efectos_client.consultar(_op)

    estado, acumulado = efectos_client.run(_leo())
    assert estado == "cobrado"
    assert acumulado == Decimal("1500.0000")


def test_cobro_vencimiento_ya_saldado_409(efectos_client):
    vencimiento_id = efectos_client.vencimientos[10][0].hex
    efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                        json=_body(efectos_client, vencimiento_id=vencimiento_id))
    r = efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                            json=_body(efectos_client, vencimiento_id=vencimiento_id))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "vencimiento_estado_no_valido"


def test_comision_mayor_que_total_422(efectos_client):
    r = efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                            json=_body(efectos_client, comision="5000.0000"))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "comision_no_valida"


def test_listado_y_detalle(efectos_client):
    creado = efectos_client.post(
        "/api/v1/cobros-medio", empresa_id=10, json=_body(efectos_client)
    ).json()
    lista = efectos_client.get(10, "/api/v1/cobros-medio")
    assert lista.status_code == 200
    body = lista.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == creado["id"]
    assert body["items"][0]["medio_cobro"] == "TRANSFERENCIA"

    detalle = efectos_client.get(10, f"/api/v1/cobros-medio/{creado['id']}")
    assert detalle.status_code == 200
    assert detalle.json()["importe_total"] == "1500.0000"
    assert len(detalle.json()["comisiones"]) == 0


def test_listado_filtro_medio(efectos_client):
    efectos_client.post("/api/v1/cobros-medio", empresa_id=10, json=_body(efectos_client))
    efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                        json=_body(efectos_client, medio="TARJETA",
                                   vencimiento_id=efectos_client.vencimientos[10][1]))
    lista = efectos_client.get(10, "/api/v1/cobros-medio", medio_cobro="TARJETA")
    assert lista.status_code == 200
    body = lista.json()
    assert body["total"] == 1
    assert body["items"][0]["medio_cobro"] == "TARJETA"


def test_aislamiento_por_empresa(efectos_client):
    efectos_client.post("/api/v1/cobros-medio", empresa_id=10, json=_body(efectos_client))
    efectos_client.post("/api/v1/cobros-medio", empresa_id=20,
                        json=_body(efectos_client, empresa_id=20))
    lista_a = efectos_client.get(10, "/api/v1/cobros-medio").json()
    lista_b = efectos_client.get(20, "/api/v1/cobros-medio").json()
    assert lista_a["total"] == 1
    assert lista_b["total"] == 1


def test_detalle_otra_empresa_404(efectos_client):
    creado = efectos_client.post(
        "/api/v1/cobros-medio", empresa_id=10, json=_body(efectos_client)
    ).json()
    r = efectos_client.get(20, f"/api/v1/cobros-medio/{creado['id']}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "cobro_medio_no_encontrado"


def test_cobro_otra_empresa_404(efectos_client):
    vencimiento_a = efectos_client.vencimientos[10][0]
    r = efectos_client.post("/api/v1/cobros-medio", empresa_id=20,
                            json=_body(efectos_client, vencimiento_id=vencimiento_a))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "vencimiento_no_encontrado"


def test_cobro_inexistente_404(efectos_client):
    r = efectos_client.post("/api/v1/cobros-medio", empresa_id=10,
                            json=_body(efectos_client, vencimiento_id=uuid4()))
    assert r.status_code == 404