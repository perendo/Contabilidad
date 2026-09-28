"""Arqueos con diferencia y asiento de ajuste por API (SPEC-019 US3 / FR-009).

Caja con 1000 contados (saldo libros 1000) → arqueo cuadra y se aprueba
automáticamente. A otro corte con solo 900 físicos la diferencia es -100: sin
asiento de ajuste queda pendiente, con un asiento que creditariza la 570 en 100
se aprueba.
"""

from __future__ import annotations


def _cuenta_codigo(ns, empresa_id, code):
    from sqlalchemy import select

    from models.acct.account_plan import AccountPlan

    async def _op(session):
        return await session.scalar(
            select(AccountPlan.id).where(
                AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
            )
        )

    return ns.run(ns.consultar(_op))


def _ajuste(ns, empresa_id, importe):
    r = ns.post(
        "/api/v1/asientos",
        empresa_id,
        {
            "fecha": "2026-08-31",
            "concepto": "Ajuste de arqueo",
            "lineas": [
                {"cuenta": "6400", "debe": importe, "haber": "0", "detalle": "a 570"},
                {"cuenta": "5700", "debe": "0", "haber": importe, "detalle": "caja"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_arqueo_cuadra_se_aprueba_solo(ngo_client):
    ns = ngo_client
    c570 = ns.subcuenta_570(10)
    capital = _cuenta_codigo(ns, 10, "1110")
    caja = ns.post(
        "/api/v1/cajas", 10, {"nombre": "Caja A", "cuenta_570_id": c570, "tipo": "caja"}
    ).json()

    ent = ns.post(
        f"/api/v1/cajas/{caja['id']}/movimientos",
        10,
        {"tipo": "entrada", "importe": "1000.0000", "fecha": "2026-08-01", "concepto": "Fondo", "contrapartida_cuenta_id": capital},
    ).json()
    assert ent["saldo"] == "1000.0000"

    arq = ns.post(
        f"/api/v1/cajas/{caja['id']}/arqueos",
        10,
        {"fecha": "2026-08-31", "efectivo_contado": "1000.0000"},
    ).json()
    assert arq["estado"] == "cuadra"
    assert arq["decision"] == "aprobada"
    assert arq["diferencia"] == "0.0000"
    assert arq["asiento_ajuste_id"] is None


def test_arqueo_con_diferencia_exige_ajuste(ngo_client):
    ns = ngo_client
    c570 = ns.subcuenta_570(10)
    capital = _cuenta_codigo(ns, 10, "1110")
    caja = ns.post(
        "/api/v1/cajas", 10, {"nombre": "Caja B", "cuenta_570_id": c570, "tipo": "caja"}
    ).json()

    ns.post(
        f"/api/v1/cajas/{caja['id']}/movimientos",
        10,
        {"tipo": "entrada", "importe": "1000.0000", "fecha": "2026-08-01", "concepto": "Fondo", "contrapartida_cuenta_id": capital},
    )

    arq = ns.post(
        f"/api/v1/cajas/{caja['id']}/arqueos",
        10,
        {"fecha": "2026-08-31", "efectivo_contado": "900.0000", "detalle": "50 en preparación"},
    )
    assert arq.status_code == 201, arq.text
    arq = arq.json()
    assert arq["estado"] == "con_diferencia"
    assert arq["decision"] == "pendiente"
    assert arq["diferencia"] == "-100.0000"

    apr = ns.post(f"/api/v1/arqueos/{arq['id']}/aprobar", 10, {})
    assert apr.status_code == 409  # falta_asiento_ajuste

    asiento = _ajuste(ns, 10, "100.0000")
    apr2 = ns.post(f"/api/v1/arqueos/{arq['id']}/aprobar", 10, {"asiento_ajuste_id": asiento})
    assert apr2.status_code == 200, apr2.text
    body = apr2.json()
    assert body["decision"] == "aprobada"
    assert body["asiento_ajuste_id"] == asiento

    repetido = ns.post(f"/api/v1/arqueos/{arq['id']}/aprobar", 10, {})
    assert repetido.status_code == 409  # arqueo_ya_decidido


def test_arqueo_ajuste_incorrecto_409(ngo_client):
    ns = ngo_client
    c570 = ns.subcuenta_570(10)
    capital = _cuenta_codigo(ns, 10, "1110")
    caja = ns.post(
        "/api/v1/cajas", 10, {"nombre": "Caja C", "cuenta_570_id": c570, "tipo": "caja"}
    ).json()

    ns.post(
        f"/api/v1/cajas/{caja['id']}/movimientos",
        10,
        {"tipo": "entrada", "importe": "1000.0000", "fecha": "2026-08-01", "concepto": "Fondo", "contrapartida_cuenta_id": capital},
    )
    arq = ns.post(
        f"/api/v1/cajas/{caja['id']}/arqueos",
        10,
        {"fecha": "2026-08-31", "efectivo_contado": "900.0000"},
    ).json()

    mal = ns.post(
        "/api/v1/asientos",
        10,
        {
            "fecha": "2026-08-31",
            "concepto": "Ajuste que no cuadra",
            "lineas": [
                {"cuenta": "6400", "debe": "200.0000", "haber": "0", "detalle": "x"},
                {"cuenta": "5700", "debe": "0", "haber": "200.0000", "detalle": "x"},
            ],
        },
    ).json()
    apr = ns.post(f"/api/v1/arqueos/{arq['id']}/aprobar", 10, {"asiento_ajuste_id": mal["id"]})
    assert apr.status_code == 409
    assert apr.json()["detail"] == "Tras aplicar el ajuste, la 570 no cuadra con el efectivo contado"


def test_archivar_arqueo(ngo_client):
    ns = ngo_client
    c570 = ns.subcuenta_570(10)
    capital = _cuenta_codigo(ns, 10, "1110")
    caja = ns.post(
        "/api/v1/cajas", 10, {"nombre": "Caja D", "cuenta_570_id": c570, "tipo": "caja"}
    ).json()

    ns.post(
        f"/api/v1/cajas/{caja['id']}/movimientos",
        10,
        {"tipo": "entrada", "importe": "1000.0000", "fecha": "2026-08-01", "concepto": "Fondo", "contrapartida_cuenta_id": capital},
    )
    arq = ns.post(
        f"/api/v1/cajas/{caja['id']}/arqueos",
        10,
        {"fecha": "2026-08-31", "efectivo_contado": "850.0000"},
    ).json()

    arch = ns.post(f"/api/v1/arqueos/{arq['id']}/archivar", 10)
    assert arch.status_code == 200
    assert arch.json()["decision"] == "archivada"
    assert arch.json()["archivado"] is True