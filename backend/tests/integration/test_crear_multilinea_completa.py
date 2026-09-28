"""T101: Test integración creación multilínea completa (SPEC-006 US1)."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryLine

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


def test_crear_3_2_via_http_201_y_persistido(asientos_client):
    client, token, factory = asientos_client
    resp = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    assert cuerpo["total_debe"] == "500.0000"
    assert cuerpo["total_haber"] == "500.0000"
    assert cuerpo["n_lineas"] == 5
    assert cuerpo["estado"] == "POSTED"
    assert cuerpo["numero_asiento"] == 1

    async def _verificar() -> dict:
        async with factory() as session:
            n_cab = await session.scalar(select(func.count()).select_from(JournalEntry))
            n_lin = await session.scalar(select(func.count()).select_from(JournalEntryLine))
            origen = await session.scalar(
                select(JournalEntryLine.empresa_id).limit(1)
            )
            return {"cab": int(n_cab), "lin": int(n_lin), "emp": int(origen)}

    loop = asyncio.new_event_loop()
    try:
        conteo = loop.run_until_complete(_verificar())
    finally:
        loop.close()
    assert conteo["cab"] == 1
    assert conteo["lin"] == 5
    assert conteo["emp"] == 10

    detalle = client.get(f"/api/v1/asientos/{cuerpo['id']}", headers=_hh(token, 10))
    assert detalle.status_code == 200
    assert detalle.json()["n_lineas"] == 5
    assert {linea["cuenta"] for linea in detalle.json()["lineas"]} == {
        "6000", "6210", "6400", "4000", "4100",
    }