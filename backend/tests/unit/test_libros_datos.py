"""Generación de libros oficiales PDF y reutilización por huella (SPEC-019 US2).

Los libros solo se generan sobre ejercicios cerrados (SPEC-004). Un PDF idéntico
(por sha256 del contenido canónico) reutiliza el registro previo.
"""

from __future__ import annotations

import pytest

from services.ngo.errores import NgoError
from services.ngo.libros_pdf import generar_libros, listar_libros


def _abrir(ns, empresa_id=10, year=2026):
    from datetime import date

    from models.acct.fiscal_year import FiscalYear

    async def _op(session):
        session.add(
            FiscalYear(
                empresa_id=empresa_id,
                year=year,
                date_start=date(year, 1, 1),
                date_end=date(year, 12, 31),
                is_closed=False,
            )
        )
        await session.flush()

    ns.run(ns.mutar(_op))


def test_diario_generado_y_reutilizado(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    r1 = ns.run(ns.mutar(lambda s: generar_libros(s, empresa_id=10, ejercicio=2025, tipos=["diario"])))
    assert len(r1) == 1
    assert r1[0]["tipo"] == "diario"
    assert len(r1[0]["sha256"]) == 64
    assert r1[0]["reusado"] is False
    assert r1[0]["size_bytes"] > 1000

    r2 = ns.run(ns.mutar(lambda s: generar_libros(s, empresa_id=10, ejercicio=2025, tipos=["diario"])))
    assert r2[0]["reusado"] is True
    assert r2[0]["sha256"] == r1[0]["sha256"]
    assert r2[0]["size_bytes"] == r1[0]["size_bytes"]

    listado = ns.run(ns.mutar(lambda s: listar_libros(s, empresa_id=10, ejercicio=2025)))
    assert listado["total"] == 1
    assert listado["items"][0]["tipo"] == "diario"


def test_mayor_y_cuentas_anuales(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    resultado = ns.run(
        ns.mutar(lambda s: generar_libros(s, empresa_id=10, ejercicio=2025, tipos=["mayor", "cuentas_anuales"]))
    )
    assert [r["tipo"] for r in resultado] == ["mayor", "cuentas_anuales"]
    assert all(r["reusado"] is False for r in resultado)


def test_tipos_invalidos_y_vacios(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    with pytest.raises(NgoError) as exc:
        ns.run(ns.mutar(lambda s: generar_libros(s, empresa_id=10, ejercicio=2025, tipos=["diario", "pantalla"])))
    assert exc.value.code == "tipo_invalido"

    with pytest.raises(NgoError) as exc2:
        ns.run(ns.mutar(lambda s: generar_libros(s, empresa_id=10, ejercicio=2025, tipos=[])))
    assert exc2.value.code == "tipos_vacios"


def test_ejercicio_abierto_e_inexistente(ngo_client):
    ns = ngo_client
    _abrir(ns, 10, 2026)
    with pytest.raises(NgoError) as exc:
        ns.run(ns.mutar(lambda s: generar_libros(s, empresa_id=10, ejercicio=2026, tipos=["diario"])))
    assert exc.value.code == "ejercicio_abierto"

    with pytest.raises(NgoError) as exc2:
        ns.run(ns.mutar(lambda s: generar_libros(s, empresa_id=10, ejercicio=1999, tipos=["diario"])))
    assert exc2.value.code == "ejercicio_inexistente"