"""T125: Hardening multi-tenant completo (SPEC-006 Polish).

Escenario cross-empresa completo: crear y anular en A, consultar desde B → 404,
importar en B un archivo exportado por A con cuenta exclusiva → cuenta_no_encontrada.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from models.acct.account_plan import AccountPlan

LINEAS_3_2 = [
    {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000"},
    {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000"},
    {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000"},
    {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000"},
]

BODY = {"fecha": "2026-01-15", "concepto": "Gastos varios", "lineas": LINEAS_3_2}


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_escenario_completo_cross_empresa(asientos_client):
    client, token, factory = asientos_client

    async def _crear_cuenta_exclusiva() -> None:
        async with factory() as session:
            padre = await session.scalar(
                select(AccountPlan).where(
                    AccountPlan.tenant_id == 10, AccountPlan.code == "132"
                )
            )
            session.add(
                AccountPlan(
                    tenant_id=10, code="1321", name="Exclusiva A",
                    parent_id=padre.id if padre else None, level=4,
                    is_active=True, is_selectable=True,
                )
            )
            await session.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_crear_cuenta_exclusiva())
    finally:
        loop.close()

    # 1) A crea y anula un asiento 3:2
    creado = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert creado.status_code == 201, creado.text
    original_id = creado.json()["id"]
    anul = client.post(f"/api/v1/asientos/{original_id}/anular", headers=_hh(token, 10))
    assert anul.status_code == 201, anul.text
    rect_id = anul.json()["asiento_rectificativo"]["id"]

    # 2) B no ve ni anula ninguno de los dos
    for detalle_id in (original_id, rect_id):
        assert client.get(f"/api/v1/asientos/{detalle_id}", headers=_hh(token, 20)).status_code == 404
        assert client.post(
            f"/api/v1/asientos/{detalle_id}/anular", headers=_hh(token, 20)
        ).status_code == 404

    # 3) B no puede importar un archivo de A con cuenta exclusiva
    exclusivo = {
        "fecha": "2026-01-16",
        "concepto": "Subvención",
        "lineas": [
            {"cuenta": "1321", "debe": "100.0000", "haber": "0.0000"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "100.0000"},
        ],
    }
    creado_exclusivo = client.post("/api/v1/asientos", json=exclusivo, headers=_hh(token, 10))
    assert creado_exclusivo.status_code == 201, creado_exclusivo.text
    exp = client.get(
        "/api/v1/asientos/exportar",
        params={"fecha_desde": "2026-01-16", "fecha_hasta": "2026-01-16"},
        headers=_hh(token, 10),
    )
    assert exp.status_code == 200
    conf_b = client.post(
        "/api/v1/asientos/importar/confirmar",
        files={"archivo": ("diario.csv", exp.content, "text/csv")},
        headers=_hh(token, 20),
    )
    assert conf_b.status_code == 422
    listado_b = client.get("/api/v1/asientos", headers=_hh(token, 20))
    assert listado_b.json()["total"] == 0