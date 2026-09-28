"""Tests SPEC-008 Polish (T048): escenarios de quickstart.md."""

from __future__ import annotations


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def _alta(client, token, empresa, **over):
    cuerpo = {
        "nif": "A12345674",
        "razon_social": "ACME Servicios S.L.",
        "es_cliente": True,
        "es_proveedor": True,
        "iban": "ES9121000418450200051332",
        **over,
    }
    return client.post("/api/v1/terceros", json=cuerpo, headers=_hh(token, empresa))


def test_s1_alta_con_subcuentas(terceros_client) -> None:
    client, token, _ = terceros_client
    resp = _alta(client, token, 10)
    assert resp.status_code == 201
    detalle = client.get(f"/api/v1/terceros/{resp.json()['id']}", headers=_hh(token, 10))
    assert {s["tipo"] for s in detalle.json()["saldo"]["subcuentas"]} == {"CLIENTE", "PROVEEDOR"}


def test_s2_duplicado_y_nif_invalido(terceros_client) -> None:
    client, token, _ = terceros_client
    assert _alta(client, token, 10).status_code == 201
    assert _alta(client, token, 10).status_code == 409
    assert _alta(client, token, 20).status_code == 201
    invalido = _alta(client, token, 10, nif="ABC123")
    assert invalido.status_code == 422


def test_s3_iban_invalido_y_optativo(terceros_client) -> None:
    client, token, _ = terceros_client
    malo = _alta(client, token, 10, iban="ES0000000000000000000000")
    assert malo.status_code == 422
    sin = _alta(client, token, 10, nif="12345678Z", iban=None)
    assert sin.status_code == 201
    assert sin.json()["iban"] is None


def test_s5_retirada_y_proteccion(terceros_client) -> None:
    client, token, factory = terceros_client
    creado = _alta(client, token, 10).json()
    # Sin movimientos → borrado físico 204
    assert client.delete(f"/api/v1/terceros/{creado['id']}", headers=_hh(token, 10)).status_code == 204
    # Con vencimiento → DELETE 409, POST retirar inactiva
    otro = _alta(client, token, 10, nif="12345678Z").json()
    import asyncio
    from datetime import date
    from decimal import Decimal

    from models.ar.vencimiento import EstadoVencimiento, Vencimiento

    async def _venc() -> None:
        async with factory() as s:
            s.add(
                Vencimiento(
                    empresa_id=10, tercero_id=__import__("uuid").UUID(otro["id"]),
                    factura_id=None, recibo_num="R", iban="ES9121000418450200051332",
                    ejercicio=2026, fecha_vencimiento=date(2026, 6, 1),
                    importe=Decimal("10.0000"), estado=EstadoVencimiento.pendiente,
                )
            )
            await s.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_venc())
    finally:
        loop.close()
    assert client.delete(f"/api/v1/terceros/{otro['id']}", headers=_hh(token, 10)).status_code == 409
    retirado = client.post(f"/api/v1/terceros/{otro['id']}/retirar", headers=_hh(token, 10))
    assert retirado.status_code == 200
    assert retirado.json()["activo"] is False


def test_s6_condiciones_pronto_pago(terceros_client) -> None:
    client, token, _ = terceros_client
    tercero = _alta(client, token, 10).json()
    url = f"/api/v1/terceros/{tercero['id']}/condiciones"
    primera = client.post(
        url, json={"plazo_dias": 10, "porcentaje": "2.00", "vigente": True}, headers=_hh(token, 10)
    )
    assert primera.status_code == 201
    listado = client.get(url, headers=_hh(token, 10))
    assert listado.status_code == 200
    assert len(listado.json()) == 1
    assert listado.json()[0]["vigente"] is True


def test_s7_aislamiento_multiempresa(terceros_client) -> None:
    client, token, _ = terceros_client
    a = _alta(client, token, 10).json()
    assert client.get(f"/api/v1/terceros/{a['id']}", headers=_hh(token, 20)).status_code == 404
    assert client.delete(f"/api/v1/terceros/{a['id']}", headers=_hh(token, 20)).status_code == 404
