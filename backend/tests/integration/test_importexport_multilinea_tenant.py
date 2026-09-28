"""T123: Aislamiento multi-tenant US4 (SPEC-006).

Empresa A exporta un archivo con una cuenta exclusiva suya; empresa B no puede
importarlo (cuenta_no_encontrada).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from models.acct.account_plan import AccountPlan


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def test_b_no_puede_importar_archivo_de_a(asientos_client):
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

    BODY = {
        "fecha": "2026-01-15",
        "concepto": "Con cuenta exclusiva",
        "lineas": [
            {"cuenta": "1321", "debe": "100.0000", "haber": "0.0000", "detalle": "Subvención"},
            {"cuenta": "5720", "debe": "0.0000", "haber": "100.0000", "detalle": "Banco"},
        ],
    }
    creado = client.post("/api/v1/asientos", json=BODY, headers=_hh(token, 10))
    assert creado.status_code == 201, creado.text

    exp = client.get(
        "/api/v1/asientos/exportar",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31"},
        headers=_hh(token, 10),
    )
    assert exp.status_code == 200

    prev_b = client.post(
        "/api/v1/asientos/importar/previsualizar",
        files={"archivo": ("diario.csv", exp.content, "text/csv")},
        headers=_hh(token, 20),
    )
    assert prev_b.status_code == 200
    assert prev_b.json()["asientos_validos"] == 0
    assert any(
        e["tipo_error"] == "cuenta_no_encontrada" for e in prev_b.json()["errores"]
    )

    conf_b = client.post(
        "/api/v1/asientos/importar/confirmar",
        files={"archivo": ("diario.csv", exp.content, "text/csv")},
        headers=_hh(token, 20),
    )
    assert conf_b.status_code == 422

    listado_b = client.get("/api/v1/asientos", headers=_hh(token, 20))
    assert listado_b.json()["total"] == 0