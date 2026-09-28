from __future__ import annotations


def test_no_permite_duplicar_liquidacion_del_trimestre(retenciones_client) -> None:
    api = retenciones_client
    body = {"ejercicio": 2025, "trimestre": 3}
    first = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json=body,
        headers=api.headers(),
    )
    assert first.status_code == 201, first.text
    second = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json=body,
        headers=api.headers(),
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "liquidacion_ya_existente"
