"""Tests SPEC-013 (T035/T047/T050/T051): flujo HTTP de conciliación.

El fixture `recon_client` vive en `tests/conftest.py`: lo usan tambien los tests del
XLSX de banco.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def _subir(client, token, empresa, nombre="extracto_43_19_valido.txt", cuenta="5720"):
    return client.post(
        "/api/v1/extractos",
        files={"file": (nombre, (FIXTURES / nombre).read_bytes(), "text/plain")},
        data={"layout": "norma_43_1919", "cuenta": cuenta},
        headers=_hh(token, empresa),
    )


def test_flujo_http_importar_conciliar_cerrar(recon_client) -> None:
    client, token, _ = recon_client
    resp = _subir(client, token, 10)
    assert resp.status_code == 201, resp.text
    extracto = resp.json()
    assert extracto["n_movimientos"] == 3

    # Reimportar → 409
    assert _subir(client, token, 10).status_code == 409

    # Listar
    assert client.get("/api/v1/extractos", headers=_hh(token, 10)).json()["total"] == 1

    # Abrir conciliación
    conc = client.post(
        "/api/v1/conciliaciones",
        json={"cuenta_id": extracto["cuenta_id"], "fecha_inicio": "2026-09-01",
              "fecha_fin": "2026-09-30", "extracto_id": extracto["id"]},
        headers=_hh(token, 10),
    )
    assert conc.status_code == 201, conc.text
    cid = conc.json()["id"]

    # Informe
    informe = client.get(f"/api/v1/conciliaciones/{cid}", headers=_hh(token, 10))
    assert informe.status_code == 200
    assert informe.json()["saldo_banco"] == "1105.0000"


def test_aislamiento_extracto_otra_empresa(recon_client) -> None:
    client, token, _ = recon_client
    creado = _subir(client, token, 10).json()
    assert client.get(f"/api/v1/extractos/{creado['id']}", headers=_hh(token, 20)).status_code == 404
    # La empresa A no puede importar una cuenta inexistente en su plan
    resp = _subir(client, token, 10, nombre="extracto_43_19_otra_empresa.txt", cuenta="")
    assert resp.status_code in (404, 422)
