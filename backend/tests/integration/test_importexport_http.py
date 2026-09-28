"""Tests SPEC-005 (T018/T019/T027/T028/T036/T037/T039/T040): flujo HTTP completo."""

from __future__ import annotations

import io

CABECERA = "fecha;numero_asiento;concepto;cuenta;debe;haber\n"


def _csv(*lineas: str) -> bytes:
    return (CABECERA + "\n".join(lineas)).encode("utf-8")


def _hh(token: str, empresa: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Empresa-Activa": str(empresa)}


def _subir(client, token, empresa, contenido: bytes, ruta: str):
    return client.post(
        ruta,
        files={"archivo": ("asientos.csv", contenido, "text/csv")},
        headers=_hh(token, empresa),
    )


VALIDOS = _csv(
    "2026-05-01;1;Venta;4300;100,00;0",
    "2026-05-01;1;Venta;5720;0;100,00",
)
MIXTO = _csv(
    "2026-05-01;1;Venta;4300;100,00;0",
    "2026-05-01;1;Venta;5720;0;100,00",
    "2026-05-02;2;Mal;4300;10,00;0",
    "2026-05-02;2;Mal;5720;0;5,00",
)


def test_previsualizar_dryrun_http(importexport_client) -> None:
    client, token, _ = importexport_client
    resp = _subir(client, token, 10, MIXTO, "/api/v1/asientos/importar/previsualizar")
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["total_asientos"] == 2
    assert cuerpo["asientos_validos"] == 1
    assert cuerpo["asientos_con_error"] == 1
    # No se escribió nada: exportar debe devolver solo cabecera
    exp = client.get(
        "/api/v1/asientos/exportar",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31"},
        headers=_hh(token, 10),
    )
    assert len(exp.content.decode("utf-8-sig").strip().splitlines()) == 1


def test_previsualizar_cabecera_incompleta_422(importexport_client) -> None:
    client, token, _ = importexport_client
    resp = _subir(client, token, 10, b"fecha;cuenta\n2026-05-01;4300\n",
                  "/api/v1/asientos/importar/previsualizar")
    assert resp.status_code == 422


def test_confirmar_importa_y_numera(importexport_client) -> None:
    client, token, _ = importexport_client
    resp = _subir(client, token, 10, VALIDOS, "/api/v1/asientos/importar/confirmar")
    assert resp.status_code == 201, resp.text
    assert resp.json()["asientos_importados"] == 1
    assert resp.json()["primer_numero_asiento"] == 1
    diario = client.get(
        "/api/v1/journal/entries",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        headers=_hh(token, 10),
    )
    assert diario.json()["total"] == 1


def test_confirmar_sin_validos_422(importexport_client) -> None:
    client, token, _ = importexport_client
    malo = _csv(
        "2026-05-01;1;Mal;4300;10,00;0",
        "2026-05-01;1;Mal;5720;0;5,00",
    )
    resp = _subir(client, token, 10, malo, "/api/v1/asientos/importar/confirmar")
    assert resp.status_code == 422


def test_exportar_csv_http(importexport_client) -> None:
    client, token, _ = importexport_client
    _subir(client, token, 10, VALIDOS, "/api/v1/asientos/importar/confirmar")
    resp = client.get(
        "/api/v1/asientos/exportar",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31", "formato": "CSV"},
        headers=_hh(token, 10),
    )
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert "100.0000" in resp.content.decode("utf-8-sig")


def test_exportar_xlsx_http(importexport_client) -> None:
    import openpyxl

    client, token, _ = importexport_client
    _subir(client, token, 10, VALIDOS, "/api/v1/asientos/importar/confirmar")
    resp = client.get(
        "/api/v1/asientos/exportar",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31", "formato": "XLSX"},
        headers=_hh(token, 10),
    )
    assert resp.status_code == 200
    libro = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert libro.active.title == "Diario"


def test_aislamiento_import_export_entre_empresas(importexport_client) -> None:
    import asyncio

    from models.acct.account_plan import AccountPlan

    client, token, factory = importexport_client
    # Cuenta 4309 exclusiva de la empresa A (nivel 4 bajo 430)
    async def _crear_cuenta() -> None:
        async with factory() as session:
            padre = await session.scalar(
                __import__("sqlalchemy").select(AccountPlan).where(
                    AccountPlan.tenant_id == 10, AccountPlan.code == "430"
                )
            )
            session.add(
                AccountPlan(
                    tenant_id=10, code="4309", name="Exclusiva A",
                    parent_id=padre.id if padre else None, level=4,
                    is_active=True, is_selectable=True,
                )
            )
            await session.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_crear_cuenta())
    finally:
        loop.close()

    archivo_a = _csv(
        "2026-05-01;1;V;4309;100,00;0",
        "2026-05-01;1;V;5720;0;100,00",
    )
    prev_b = _subir(client, token, 20, archivo_a, "/api/v1/asientos/importar/previsualizar")
    assert prev_b.json()["asientos_validos"] == 0
    assert any(e["tipo_error"] == "cuenta_no_encontrada" for e in prev_b.json()["errores"])

    # A importa: B exporta → vacío (aislamiento)
    _subir(client, token, 10, archivo_a, "/api/v1/asientos/importar/confirmar")
    exp_b = client.get(
        "/api/v1/asientos/exportar",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31"},
        headers=_hh(token, 20),
    )
    assert len(exp_b.content.decode("utf-8-sig").strip().splitlines()) == 1


def test_quickstart_import_export(importexport_client) -> None:
    client, token, _ = importexport_client
    prev = _subir(client, token, 10, MIXTO, "/api/v1/asientos/importar/previsualizar")
    assert prev.status_code == 200
    conf = _subir(client, token, 10, MIXTO, "/api/v1/asientos/importar/confirmar")
    assert conf.json()["asientos_importados"] == 1
    exp = client.get(
        "/api/v1/asientos/exportar",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31"},
        headers=_hh(token, 10),
    )
    assert "Venta" in exp.content.decode("utf-8-sig")
