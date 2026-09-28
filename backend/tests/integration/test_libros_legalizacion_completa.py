"""Libros oficiales PDF y legalización por API (SPEC-019 US2 / FR-005/FR-006).

Genera diario y mayor de un ejercicio cerrado, descarga ambos PDF, emite la
legalización y descarga el fichero de texto con la huella.
"""

from __future__ import annotations

from datetime import date as _date


def test_generar_descargar_libros_y_legalizar(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)

    r = ns.post(
        "/api/v1/libros/2025/generar", 10, {"tipos": ["diario", "mayor"]}
    )
    assert r.status_code == 201, r.text
    items = r.json()["items"]
    tipos = {item["tipo"]: item for item in items}
    assert set(tipos) == {"diario", "mayor"}
    assert all(len(item["sha256"]) == 64 for item in items)

    lista = ns.get(10, "/api/v1/libros/2025")
    assert lista.status_code == 200
    assert lista.json()["total"] == 2

    pdf_url = tipos["diario"]["url"]
    pdf = ns.get(10, pdf_url)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    leg = ns.post(
        "/api/v1/legalizaciones", 10, {"ejercicio": 2025, "fecha_legalizacion": "2026-01-15"}
    )
    assert leg.status_code == 201, leg.text
    leyenda = leg.json()
    assert len(leyenda["huella"]) == 64
    assert leyenda["fecha_legalizacion"] == "2026-01-15"
    assert leyenda["total_asientos"] == 2

    lista_leg = ns.get(10, "/api/v1/legalizaciones")
    assert lista_leg.status_code == 200
    assert lista_leg.json()["total"] == 1

    fichero = ns.get(10, f"/api/v1/legalizaciones/{leyenda['id']}/descarga")
    assert fichero.status_code == 200
    assert fichero.content.startswith(b"LEGALIZACION V1\n")
    assert b"EJERCICIO:2025" in fichero.content


def test_libro_cuenta_anuales_opcional(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    r = ns.post(
        "/api/v1/libros/2025/generar", 10, {"tipos": ["cuentas_anuales"]}
    )
    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["tipo"] == "cuentas_anuales"


def test_generar_duplicado_reusa(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    r1 = ns.post("/api/v1/libros/2025/generar", 10, {"tipos": ["diario"]})
    assert r1.status_code == 201 and r1.json()["items"][0]["reusado"] is False
    r2 = ns.post("/api/v1/libros/2025/generar", 10, {"tipos": ["diario"]})
    assert r2.status_code == 201 and r2.json()["items"][0]["reusado"] is True


def test_generar_libros_ejercicio_abierto_409(ngo_client):
    ns = ngo_client

    async def _abrir(session):
        from sqlalchemy import select as _select

        from models.acct.fiscal_year import FiscalYear

        fy = await session.scalar(
            _select(FiscalYear).where(FiscalYear.empresa_id == 10, FiscalYear.year == 2026)
        )
        if fy is None:
            session.add(
                FiscalYear(
                    empresa_id=10,
                    year=2026,
                    date_start=_date(2026, 1, 1),
                    date_end=_date(2026, 12, 31),
                    is_closed=False,
                )
            )
            await session.flush()

    ns.run(ns.mutar(_abrir))
    r = ns.post("/api/v1/libros/2026/generar", 10, {"tipos": ["diario"]})
    assert r.status_code == 409
    assert "no está cerrado" in r.json()["detail"]