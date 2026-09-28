"""T122: Test integración import-export multilínea (SPEC-006 US4).

Exportar un asiento 3:2 y volver a importarlo: la copia conserva 5 líneas y
Debe == Haber.
"""

from __future__ import annotations

LINEAS_3_2 = [
    {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000", "detalle": "Compra"},
    {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000", "detalle": "Alquiler"},
    {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000", "detalle": "Sueldo"},
    {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000", "detalle": "Prov A"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000", "detalle": "Prov B"},
]

BODY = {"fecha": "2026-01-15", "concepto": "Gastos varios", "lineas": LINEAS_3_2}


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_exportar_e_importar_3_2(asientos_client):
    client, token, _ = asientos_client
    creado = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert creado.status_code == 201, creado.text

    exp = client.get(
        "/api/v1/asientos/exportar",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31", "formato": "CSV"},
        headers=_hh(token, 10),
    )
    assert exp.status_code == 200
    lineas_csv = exp.content.decode("utf-8-sig").strip().splitlines()
    assert len(lineas_csv) == 6  # cabecera + 5 partidas

    reinp = client.post(
        "/api/v1/asientos/importar/confirmar",
        files={"archivo": ("diario.csv", exp.content, "text/csv")},
        headers=_hh(token, 10),
    )
    assert reinp.status_code == 201, reinp.text
    assert reinp.json()["asientos_importados"] == 1

    listado = client.get("/api/v1/asientos", headers=_hh(token, 10))
    assert listado.json()["total"] == 2
    importado = next(
        i for i in listado.json()["items"] if i["numero_asiento"] == 2
    )
    assert importado["n_lineas"] == 5
    assert importado["total_debe"] == importado["total_haber"] == "500.0000"