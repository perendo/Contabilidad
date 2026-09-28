"""Contrato del fichero de legalización (SPEC-019 contracts/legalizacion.md).

Formato exacto de los 10 campos (UTF-8, \n), TOTAL_ASIENTOS consistente con el
rango, HUELLA recalculable desde el canon del diario, re-emisión idéntica → 201
con huella igual y contenido alterado → 409 sin tocar la vigente.
"""

from __future__ import annotations

import hashlib
import re

from services.ngo.libros_pdf import _entradas_ejercicio, canon_diario


def _huella_recalculada(ns) -> str:
    entradas = ns.run(ns.consultar(lambda s: _entradas_ejercicio(s, 10, 2025)))
    canon = canon_diario(10, 2025, entradas)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def test_formato_campos_exactos(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    leg = ns.post(
        "/api/v1/legalizaciones", 10, {"ejercicio": 2025, "fecha_legalizacion": "2026-01-15"}
    )
    assert leg.status_code == 201, leg.text
    body = leg.json()

    fichero = ns.get(10, body["url"])
    assert fichero.status_code == 200
    texto = fichero.content.decode("utf-8")
    assert texto.endswith("\n")
    lineas = texto.split("\n")[:-1]

    # cabecera + 10 campos
    assert len(lineas) == 11
    assert lineas[0] == "LEGALIZACION V1"
    assert lineas[1] == "EMPRESA:Diez SL"
    assert lineas[2] == "NIF:A00000001"
    assert lineas[3] == "EJERCICIO:2025"
    assert lineas[4] == "RANGO_ASIENTOS_DESDE:1"
    assert lineas[5] == "RANGO_ASIENTOS_HASTA:2"
    assert lineas[6] == "TOTAL_ASIENTOS:2"
    assert re.fullmatch(r"FECHA_EMISION:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", lineas[7])
    assert lineas[8] == "FECHA_LEGALIZACION:2026-01-15"
    assert re.fullmatch(r"HUELLA:[0-9a-f]{64}", lineas[9])
    assert lineas[10] == "HUELLA_ALGORITMO:SHA-256"

    # TOTAL_ASIENTOS == rango_hasta - rango_desde + 1 y == nº asientos reales
    desde = int(lineas[4].split(":")[1])
    hasta = int(lineas[5].split(":")[1])
    total = int(lineas[6].split(":")[1])
    assert total == hasta - desde + 1 == 2
    assert body["total_asientos"] == 2

    # HUELLA recalculable 64 hex en minúscula == huella del cuerpo == huella canónica
    huella = lineas[9].split(":", 1)[1]
    assert huella == body["huella"]
    assert huella == _huella_recalculada(ns)


def test_resemision_identica_201(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    leg1 = ns.post("/api/v1/legalizaciones", 10, {"ejercicio": 2025})
    assert leg1.status_code == 201, leg1.text

    leg2 = ns.post("/api/v1/legalizaciones", 10, {"ejercicio": 2025})
    assert leg2.status_code == 201, leg2.text
    assert leg2.json()["huella"] == leg1.json()["huella"]
    assert leg2.json()["valido"] is True
    assert leg2.json()["motivo_reemision"] == "Re-emisión con huella idéntica"


def test_contenido_alterado_409(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    # la fuente (diario) se altera: la vigente queda con una huella distinta
    ns.legalizar_directa(10, 2025)  # huella "0" * 64

    r = ns.post("/api/v1/legalizaciones", 10, {"ejercicio": 2025})
    assert r.status_code == 409
    assert "huella" in r.json()["detail"].lower()

    lista = ns.get(10, "/api/v1/legalizaciones").json()
    assert lista["total"] == 1
    assert lista["items"][0]["valido"] is True
    assert lista["items"][0]["motivo_reemision"] is None