"""Flujo completo del cierre intermedio (SPEC-028 T024, US1/FR-001).

Quickstart Scenario 1: cerrar el mes 3, comprobar que la balanza cuadra, que un
asiento posterior del mismo mes se rechaza con 409 y que un asiento de abril se
acepta. El diario no se muta por el cierre (T016 verificado en la capa unitaria).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

A = 10
B = 20
EJERCICIO = 2026


def _ventas(importe: str) -> list[dict]:
    return [
        {"cuenta": "7000", "haber": importe},
        {"cuenta": "4300", "debe": importe},
    ]


def test_scenario_1_cerrar_mes_bloquea_y_cuadra(closing_client) -> None:
    cierres = closing_client
    # Movimientos en marzo y en abril.
    cierres.asiento(A, "2026-03-05", _ventas("1000.0000"))
    cierres.asiento(A, "2026-03-20", _ventas("234.5000"))
    cierres.asiento(A, "2026-04-02", _ventas("500.0000"))

    # 1) Cerrar el mes 3.
    respuesta = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "cerrado"
    assert cuerpo["tipo"] == "MES"
    assert cuerpo["periodo"] == 3
    assert cuerpo["fecha_ini"] == "2026-03-01"
    assert cuerpo["fecha_fin"] == "2026-03-31"
    assert cuerpo["balanza"]["cuadra"] is True
    assert cuerpo["balanza"]["total_debe"] == "1234.5000"
    assert cuerpo["balanza"]["total_haber"] == "1234.5000"
    assert cuerpo["balanza"]["n_lineas"] == 2
    assert cuerpo["n_reaperturas"] == 0
    # El resultado provisional solo mira los grupos 6/7 del periodo.
    assert cuerpo["resultado_provisional"] == "-1234.5000"

    # 2) Un asiento en el periodo cerrado se rechaza con 409.
    from services.journal.entry_service import AsientoError

    with pytest.raises(AsientoError) as exc:
        cierres.asiento(A, "2026-03-15", _ventas("50.0000"))
    assert exc.value.code == "periodo_cerrado"

    # 3) Un asiento fuera del rango se acepta.
    cierre = cierres.asiento(A, "2026-04-15", _ventas("50.0000"))
    assert cierre is not None

    # 4) La balanza consultada cuadra con la del cierre.
    balanza = cierres.get(
        f"/api/v1/cierres/intermedios/{cuerpo['periodo_id']}/balanza", empresa_id=A
    ).json()
    assert balanza["total_debe"] == balanza["total_haber"] == "1234.5000"
    assert balanza["n_lineas"] == 2
    assert len(balanza["lineas"]) == 2
    codigos = sorted(linea["codigo"] for linea in balanza["lineas"])
    assert codigos == ["4300", "7000"]
    for linea in balanza["lineas"]:
        assert Decimal(linea["saldo"]) == Decimal(linea["debe"]) - Decimal(linea["haber"])
    assert balanza["sha256"] == cuerpo["balanza"]["sha256"]


def test_scenario_2_trimestre_sin_movimientos_cierra_a_cero(closing_client) -> None:
    """Quickstart Scenario 2: cierre sin movimiento, sin anomalía."""
    respuesta = closing_client.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "TRIMESTRE", "periodo": 2},
        empresa_id=A,
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["balanza"]["total_debe"] == "0.0000"
    assert cuerpo["balanza"]["total_haber"] == "0.0000"
    assert cuerpo["balanza"]["n_lineas"] == 0
    assert cuerpo["balanza"]["cuadra"] is True
    assert cuerpo["fecha_ini"] == "2026-04-01"
    assert cuerpo["fecha_fin"] == "2026-06-30"
    assert cuerpo["resultado_provisional"] == "0.0000"


def test_el_calendario_devuelve_los_doce_meses(closing_client) -> None:
    cierres = closing_client
    cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    )
    respuesta = cierres.get(
        "/api/v1/cierres/intermedios", empresa_id=A, ejercicio=EJERCICIO, tipo="MES"
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 12
    estados = {item["periodo"]: item["estado"] for item in cuerpo["items"]}
    assert estados[3] == "cerrado"
    assert estados[4] == "abierto"
    assert all(item["periodo_id"] is None for item in cuerpo["items"] if item["estado"] == "abierto")


def test_cerrar_un_mes_ya_cerrado_devuelve_409(closing_client) -> None:
    cierres = closing_client
    cuerpo = {"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3}
    assert cierres.post("/api/v1/cierres/intermedios", json=cuerpo, empresa_id=A).status_code == 201
    repetido = cierres.post("/api/v1/cierres/intermedios", json=cuerpo, empresa_id=A)
    assert repetido.status_code == 409
    assert repetido.json()["detail"]["code"] == "periodo_ya_cerrado"


def test_cerrar_un_mes_bajo_un_trimestre_cerrado_devuelve_409(closing_client) -> None:
    cierres = closing_client
    assert (
        cierres.post(
            "/api/v1/cierres/intermedios",
            json={"ejercicio": EJERCICIO, "tipo": "TRIMESTRE", "periodo": 1},
            empresa_id=A,
        ).status_code
        == 201
    )
    solapado = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 2},
        empresa_id=A,
    )
    assert solapado.status_code == 409
    assert solapado.json()["detail"]["code"] == "periodo_cubierto"


def test_cerrar_un_ejercicio_cerrado_devuelve_409(closing_client) -> None:
    cierres = closing_client
    cierres.marcar_cerrado(A, 2026)
    respuesta = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "ejercicio_cerrado"


def test_el_listado_filtra_por_ejercicio_tipo_y_estado(closing_client) -> None:
    cierres = closing_client
    for periodo in (1, 2, 3):
        cierres.post(
            "/api/v1/cierres/intermedios",
            json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": periodo},
            empresa_id=A,
        )
    cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "TRIMESTRE", "periodo": 4},
        empresa_id=A,
    )
    assert cierres.get("/api/v1/cierres/intermedios", empresa_id=A, ejercicio=EJERCICIO).json()["total"] == 4
    assert cierres.get("/api/v1/cierres/intermedios", empresa_id=A, tipo="MES").json()["total"] == 3
    assert (
        cierres.get("/api/v1/cierres/intermedios", empresa_id=A, estado="cerrado").json()["total"]
        == 4
    )
    assert cierres.get("/api/v1/cierres/intermedios", empresa_id=A, ejercicio=2025).json()["total"] == 0


def test_la_balanza_de_un_periodo_inexistente_devuelve_404(closing_client) -> None:
    import uuid

    respuesta = closing_client.get(
        f"/api/v1/cierres/intermedios/{uuid.uuid4()}/balanza", empresa_id=A
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "periodo_no_encontrado"


def test_el_listado_pagina(closing_client) -> None:
    cierres = closing_client
    for periodo in range(1, 6):
        cierres.post(
            "/api/v1/cierres/intermedios",
            json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": periodo},
            empresa_id=A,
        )
    pagina = cierres.get(
        "/api/v1/cierres/intermedios", empresa_id=A, page=2, page_size=2
    ).json()
    assert pagina["total"] == 5
    assert pagina["page"] == 2
    assert len(pagina["items"]) == 2


def test_la_balanza_registra_una_linea_por_cuenta(closing_client) -> None:
    cierres = closing_client
    for dia, importe in (("2026-03-02", "100.0000"), ("2026-03-03", "250.5000")):
        cierres.asiento(A, dia, _ventas(importe))
    creado = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    ).json()
    balanza = cierres.get(
        f"/api/v1/cierres/intermedios/{creado['periodo_id']}/balanza", empresa_id=A
    ).json()
    assert balanza["n_lineas"] == 2
    por_codigo = {linea["codigo"]: linea for linea in balanza["lineas"]}
    assert por_codigo["7000"]["haber"] == "350.5000"
    assert por_codigo["7000"]["debe"] == "0.0000"
    assert por_codigo["7000"]["saldo"] == "-350.5000"
    assert por_codigo["4300"]["debe"] == "350.5000"
    assert por_codigo["4300"]["nombre"]
    assert por_codigo["4300"]["nivel"] == 4
