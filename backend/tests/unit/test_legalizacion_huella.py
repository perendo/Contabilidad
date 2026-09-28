"""Emisión y re-emisión de la legalización de libros (SPEC-019 US2 / FR-006).

La huella SHA-256 se calcula sobre el contenido canónico del diario (idéntica a
la del libro `diario`); la re-emisión solo con huella idéntica, y si difiere la
vigente pasa a `valido=false` y se responde 409.
"""

from __future__ import annotations

import pytest

from services.ngo.errores import NgoError
from services.ngo.legalizacion import emitir_legalizacion, listar_legalizaciones
from services.ngo.libros_pdf import generar_libros


def test_emision_coincide_con_libro_diario(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    leg = ns.run(ns.mutar(lambda s: emitir_legalizacion(s, empresa_id=10, ejercicio=2025)))
    assert leg["valido"] is True
    assert len(leg["huella"]) == 64
    assert leg["total_asientos"] == 2
    assert leg["rango_asientos_desde"] == 1
    assert leg["rango_asientos_hasta"] == 2

    libros = ns.run(ns.mutar(lambda s: generar_libros(s, empresa_id=10, ejercicio=2025, tipos=["diario"])))
    assert libros[0]["sha256"] == leg["huella"]


def test_resemision_con_huella_identica(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    leg1 = ns.run(ns.mutar(lambda s: emitir_legalizacion(s, empresa_id=10, ejercicio=2025)))
    leg2 = ns.run(ns.mutar(lambda s: emitir_legalizacion(s, empresa_id=10, ejercicio=2025)))
    assert leg2["huella"] == leg1["huella"]
    assert leg2["valido"] is True
    assert leg2["motivo_reemision"] == "Re-emisión con huella idéntica"


def test_huella_distinta_invalida_y_409(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    ns.legalizar_directa(10, 2025)
    with pytest.raises(NgoError) as exc:
        ns.run(ns.mutar(lambda s: emitir_legalizacion(s, empresa_id=10, ejercicio=2025)))
    assert exc.value.code == "huella_no_coincide"

    lista = ns.run(ns.mutar(lambda s: listar_legalizaciones(s, empresa_id=10)))
    assert lista["total"] == 1
    assert lista["items"][0]["valido"] is True
    assert lista["items"][0]["motivo_reemision"] is None