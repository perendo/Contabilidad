"""Contrato HTTP de los cierres (SPEC-028 T025, T037, T051).

Verifica los codigos de estado y la forma del cuerpo que fija
`contracts/api-contracts.md` para el cierre intermedio, el cierre anual y las
reaperturas, incluidos los rechazos por permisos y los cuerpos `{code, detail}`.
"""

from __future__ import annotations

import uuid

import pytest

A = 10
B = 20
EJERCICIO = 2026
MESES = list(range(1, 13))


def _detalle(respuesta) -> dict:
    cuerpo = respuesta.json()
    assert isinstance(cuerpo["detail"], dict), cuerpo
    assert "code" in cuerpo["detail"]
    assert "detail" in cuerpo["detail"]
    return cuerpo["detail"]


# --- T025 · contrato del cierre intermedio --------------------------------


def test_cierre_intermedio_201_devuelve_periodo_y_balanza(closing_client) -> None:
    respuesta = closing_client.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    for clave in (
        "periodo_id",
        "ejercicio",
        "tipo",
        "periodo",
        "estado",
        "balanza",
        "resultado_provisional",
    ):
        assert clave in cuerpo, clave
    balanza = cuerpo["balanza"]
    for clave in ("id", "total_debe", "total_haber", "cuadra", "n_lineas", "sha256"):
        assert clave in balanza, clave
    assert balanza["cuadra"] is True
    assert balanza["total_debe"] == balanza["total_haber"]


def test_cierre_intermedio_409_si_el_periodo_ya_esta_cerrado(closing_client) -> None:
    cuerpo = {"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3}
    assert (
        closing_client.post("/api/v1/cierres/intermedios", json=cuerpo, empresa_id=A).status_code
        == 201
    )
    repetido = closing_client.post("/api/v1/cierres/intermedios", json=cuerpo, empresa_id=A)
    assert repetido.status_code == 409
    assert _detalle(repetido)["code"] == "periodo_ya_cerrado"


def test_cierre_intermedio_422_si_el_periodo_no_cuadra_con_el_tipo(closing_client) -> None:
    mes_invalido = closing_client.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 13},
        empresa_id=A,
    )
    assert mes_invalido.status_code == 422
    trimestre_invalido = closing_client.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "TRIMESTRE", "periodo": 5},
        empresa_id=A,
    )
    assert trimestre_invalido.status_code == 422


def test_cierre_intermedio_422_si_el_cuerpo_no_cumple_el_contrato(closing_client) -> None:
    for cuerpo in (
        {"ejercicio": 1999, "tipo": "MES", "periodo": 3},
        {"ejercicio": EJERCICIO, "tipo": "MES"},
        {"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 0},
        {"ejercicio": "dosmil", "tipo": "MES", "periodo": 3},
    ):
        respuesta = closing_client.post(
            "/api/v1/cierres/intermedios", json=cuerpo, empresa_id=A
        )
        assert respuesta.status_code == 422, cuerpo


def test_cierre_intermedio_422_si_el_tipo_no_existe(closing_client) -> None:
    respuesta = closing_client.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "SEMANAL", "periodo": 1},
        empresa_id=A,
    )
    assert respuesta.status_code == 422
    assert _detalle(respuesta)["code"] == "tipo_periodo_invalido"


def test_listado_de_intermedios_200_con_items_y_total(closing_client) -> None:
    respuesta = closing_client.get("/api/v1/cierres/intermedios", empresa_id=A)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert "items" in cuerpo and "total" in cuerpo


def test_balanza_200_devuelve_lineas_con_los_campos_del_contrato(closing_client) -> None:
    creado = closing_client.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    ).json()
    respuesta = closing_client.get(
        f"/api/v1/cierres/intermedios/{creado['periodo_id']}/balanza", empresa_id=A
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    for clave in ("id", "ejercicio", "fecha_generacion", "total_debe", "total_haber", "lineas", "sha256"):
        assert clave in cuerpo, clave
    for linea in cuerpo["lineas"]:
        for clave in ("cuenta_id", "codigo", "nombre", "nivel", "debe", "haber", "saldo"):
            assert clave in linea, clave


def test_balanza_404_para_un_periodo_ajeno(closing_client) -> None:
    respuesta = closing_client.get(
        f"/api/v1/cierres/intermedios/{uuid.uuid4()}/balanza", empresa_id=A
    )
    assert respuesta.status_code == 404
    assert _detalle(respuesta)["code"] == "periodo_no_encontrado"


def test_balanza_422_para_un_identificador_no_uuid(closing_client) -> None:
    respuesta = closing_client.get(
        "/api/v1/cierres/intermedios/no-es-uuid/balanza", empresa_id=A
    )
    assert respuesta.status_code == 422


# --- T037 · contrato del cierre anual -------------------------------------


def _preparar(cierres, meses=MESES) -> None:
    """Libro con grupos 1-3 equilibrados, requisito de la apertura de SPEC-009."""
    cierres.asiento(
        A,
        "2026-01-15",
        [
            {"cuenta": "1110", "haber": "17000.0000"},
            {"cuenta": "2100", "debe": "17000.0000"},
        ],
    )
    cierres.asiento(
        A,
        "2026-02-01",
        [
            {"cuenta": "2100", "debe": "3000.0000"},
            {"cuenta": "4100", "haber": "3000.0000"},
        ],
    )
    cierres.asiento(
        A,
        "2026-03-31",
        [
            {"cuenta": "7000", "haber": "10000.0000"},
            {"cuenta": "4300", "debe": "10000.0000"},
        ],
    )
    cierres.asiento(
        A,
        "2026-06-30",
        [
            {"cuenta": "6000", "debe": "7000.0000"},
            {"cuenta": "4300", "haber": "7000.0000"},
        ],
    )
    cierres.cerrar_periodos(A, EJERCICIO, meses)


def test_cierre_anual_201_devuelve_los_identificadores_del_contrato(closing_client) -> None:
    _preparar(closing_client)
    respuesta = closing_client.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    for clave in (
        "cierre_id",
        "ejercicio",
        "estado",
        "resultado_ejercicio",
        "asiento_regularizacion_id",
        "asiento_cierre_id",
        "asiento_apertura_id",
    ):
        assert clave in cuerpo, clave
    assert cuerpo["estado"] == "completado"
    assert cuerpo["asiento_apertura_id"]


def test_cierre_anual_409_si_el_ejercicio_ya_esta_cerrado(closing_client) -> None:
    _preparar(closing_client)
    assert (
        closing_client.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A).status_code
        == 201
    )
    repetido = closing_client.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert repetido.status_code == 409
    assert _detalle(repetido)["code"] == "ejercicio_cerrado"


def test_cierre_anual_409_si_faltan_periodos(closing_client) -> None:
    # Diciembre queda abierto: el resto del ejercicio si se cierra.
    _preparar(closing_client, meses=[mes for mes in MESES if mes != 12])
    respuesta = closing_client.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert respuesta.status_code == 409
    assert _detalle(respuesta)["code"] == "periodos_intermedios_pendientes"
    assert "12" in _detalle(respuesta)["detail"]


def test_cierre_anual_422_si_el_ejercicio_no_cumple_el_rango(closing_client) -> None:
    for cuerpo in ({"ejercicio": 1999}, {"ejercicio": 2101}, {"ejercicio": "x"}, {}):
        respuesta = closing_client.post("/api/v1/cierres/anual", json=cuerpo, empresa_id=A)
        assert respuesta.status_code == 422, cuerpo


def test_detalle_del_cierre_anual_200_y_404(closing_client) -> None:
    assert closing_client.get(f"/api/v1/cierres/anual/{EJERCICIO}", empresa_id=A).status_code == 404
    _preparar(closing_client)
    assert (
        closing_client.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A).status_code
        == 201
    )
    respuesta = closing_client.get(f"/api/v1/cierres/anual/{EJERCICIO}", empresa_id=A)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    for clave in (
        "cierre_id",
        "ejercicio",
        "estado",
        "resultado_ejercicio",
        "asiento_regularizacion_id",
        "asiento_cierre_id",
        "asiento_apertura_id",
        "cerrado_at",
    ):
        assert clave in cuerpo, clave


# --- T051 · contrato de las reaperturas -----------------------------------


def _cerrar_mes(cierres, mes: int = 3, empresa: int = A) -> None:
    assert (
        cierres.post(
            "/api/v1/cierres/intermedios",
            json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": mes},
            empresa_id=empresa,
        ).status_code
        == 201
    )


def test_reapertura_201_devuelve_numero_correlativo(closing_client) -> None:
    _cerrar_mes(closing_client)
    respuesta = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error de imputacion",
        },
        empresa_id=A,
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    for clave in ("solicitud_id", "numero_solicitud", "ejercicio", "estado", "fecha_solicitud"):
        assert clave in cuerpo, clave
    assert cuerpo["estado"] == "pendiente"
    assert cuerpo["numero_solicitud"] == 1


def test_reapertura_422_sin_justificacion(closing_client) -> None:
    _cerrar_mes(closing_client)
    for motivo in (None, "", "   "):
        cuerpo = {"ejercicio": EJERCICIO, "tipo_periodo": "MES", "periodo": 3}
        if motivo is not None:
            cuerpo["motivo"] = motivo
        respuesta = closing_client.post(
            "/api/v1/cierres/reaperturas", json=cuerpo, empresa_id=A
        )
        assert respuesta.status_code == 422
        assert _detalle(respuesta)["code"] == "justificacion_requerida"


def test_reapertura_422_si_el_periodo_no_aplica_al_tipo(closing_client) -> None:
    _cerrar_mes(closing_client)
    respuesta = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "TRIMESTRE",
            "periodo": 9,
            "motivo": "Fuera de rango",
        },
        empresa_id=A,
    )
    assert respuesta.status_code == 422


def test_reapertura_409_si_ya_hay_una_solicitud_activa(closing_client) -> None:
    _cerrar_mes(closing_client)
    cuerpo = {
        "ejercicio": EJERCICIO,
        "tipo_periodo": "MES",
        "periodo": 3,
        "motivo": "Error",
    }
    assert closing_client.post("/api/v1/cierres/reaperturas", json=cuerpo, empresa_id=A).status_code == 201
    segunda = closing_client.post("/api/v1/cierres/reaperturas", json=cuerpo, empresa_id=A)
    assert segunda.status_code == 409
    assert _detalle(segunda)["code"] == "solicitud_activa"


def test_reapertura_404_si_el_periodo_no_existe(closing_client) -> None:
    respuesta = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 7,
            "motivo": "Error",
        },
        empresa_id=A,
    )
    assert respuesta.status_code == 404


def test_reapertura_403_sin_permiso(closing_client) -> None:
    _cerrar_mes(closing_client)
    respuesta = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Sin permiso",
        },
        empresa_id=A,
        token_key="readonly",
    )
    assert respuesta.status_code == 403


def test_aprobar_200_registra_quien_aprueba(closing_client) -> None:
    _cerrar_mes(closing_client)
    solicitud = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error",
        },
        empresa_id=A,
    ).json()
    respuesta = closing_client.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    for clave in ("solicitud_id", "estado", "aprobada_por", "fecha_aprobacion"):
        assert clave in cuerpo, clave


def test_aprobar_409_si_ya_estaba_resuelta(closing_client) -> None:
    _cerrar_mes(closing_client)
    solicitud = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error",
        },
        empresa_id=A,
    ).json()
    assert (
        closing_client.post(
            f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
        ).status_code
        == 200
    )
    repetido = closing_client.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
    )
    assert repetido.status_code == 409
    assert _detalle(repetido)["code"] == "estado_invalido"


def test_aprobar_403_sin_permiso(closing_client) -> None:
    _cerrar_mes(closing_client)
    solicitud = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error",
        },
        empresa_id=A,
    ).json()
    respuesta = closing_client.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar",
        empresa_id=A,
        token_key="readonly",
    )
    assert respuesta.status_code == 403


def test_rechazar_200(closing_client) -> None:
    _cerrar_mes(closing_client)
    solicitud = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error",
        },
        empresa_id=A,
    ).json()
    respuesta = closing_client.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rechazar", empresa_id=A
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "rechazada"


def test_rectificar_200_200_y_409_segun_el_estado(closing_client) -> None:
    _cerrar_mes(closing_client)
    solicitud = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error",
        },
        empresa_id=A,
    ).json()
    ruta = f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rectificar"
    # Sin aprobar todavia el estado de la solicitud es `pendiente` -> 409.
    assert (
        closing_client.post(ruta, json={"asiento_id": str(uuid.uuid4())}, empresa_id=A).status_code
        == 409
    )
    assert (
        closing_client.post(
            f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
        ).status_code
        == 200
    )
    # Con el periodo desbloqueado se asienta el rectificativo y se cierra el ajuste.
    rectificativo = closing_client.asiento(A, "2026-03-20", _ajuste(), tipo="ADJUSTMENT")
    respuesta = closing_client.post(ruta, json={"asiento_id": str(rectificativo)}, empresa_id=A)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    for clave in (
        "solicitud_id",
        "estado",
        "asiento_rectificacion_id",
        "fecha_cierre_efectivo",
    ):
        assert clave in cuerpo, clave
    assert cuerpo["estado"] == "cerrada"
    # Segundo intento -> 409.
    repetido = closing_client.post(ruta, json={"asiento_id": str(rectificativo)}, empresa_id=A)
    assert repetido.status_code == 409


def test_rectificar_404_si_el_asiento_no_existe(closing_client) -> None:
    _cerrar_mes(closing_client)
    solicitud = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error",
        },
        empresa_id=A,
    ).json()
    closing_client.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
    )
    respuesta = closing_client.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rectificar",
        json={"asiento_id": str(uuid.uuid4())},
        empresa_id=A,
    )
    assert respuesta.status_code == 404
    assert _detalle(respuesta)["code"] == "asiento_no_encontrado"


def test_rectificar_422_si_falta_el_asiento(closing_client) -> None:
    _cerrar_mes(closing_client)
    solicitud = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error",
        },
        empresa_id=A,
    ).json()
    respuesta = closing_client.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rectificar", json={}, empresa_id=A
    )
    assert respuesta.status_code == 422


def test_listado_de_reaperturas_200_con_items_y_total(closing_client) -> None:
    _cerrar_mes(closing_client)
    closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error",
        },
        empresa_id=A,
    )
    respuesta = closing_client.get("/api/v1/cierres/reaperturas", empresa_id=A)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    for clave in (
        "solicitud_id",
        "numero_solicitud",
        "ejercicio",
        "tipo_periodo",
        "periodo",
        "estado",
        "motivo",
        "fecha_solicitud",
        "asiento_rectificacion_id",
    ):
        assert clave in cuerpo["items"][0], clave


def test_ningun_endpoint_acepta_empresa_id_en_el_cuerpo(closing_client) -> None:
    """Constitucion III: la empresa activa sale de la sesion, nunca del body."""
    _cerrar_mes(closing_client, empresa=A)
    intento = closing_client.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error",
            "empresa_id": B,
        },
        empresa_id=A,
    )
    # `empresa_id` se ignora (Pydantic v2 lo descarta): la solicitud queda en A.
    assert intento.status_code == 201
    assert closing_client.get("/api/v1/cierres/reaperturas", empresa_id=B).json()["total"] == 0
    assert closing_client.get("/api/v1/cierres/reaperturas", empresa_id=A).json()["total"] == 1


def _ajuste() -> list[dict]:
    return [
        {"cuenta": "7000", "haber": "500.0000"},
        {"cuenta": "4300", "debe": "500.0000"},
    ]


@pytest.mark.parametrize(
    "ruta",
    [
        "/api/v1/cierres/intermedios",
        "/api/v1/cierres/anual",
        "/api/v1/cierres/reaperturas",
        "/api/v1/cierres/reaperturas/x/aprobar",
        "/api/v1/cierres/reaperturas/x/rechazar",
        "/api/v1/cierres/reaperturas/x/rectificar",
    ],
)
def test_las_rutas_de_cierre_exigen_autenticacion(closing_client, ruta: str) -> None:
    """Sin token la sesion no se resuelve: 401 (o 403 si el guard va antes)."""
    respuesta = closing_client.client.post(ruta, json={})
    assert respuesta.status_code in (401, 403)


def test_las_rutas_de_lectura_exigen_empresa_activa(closing_client) -> None:
    for ruta in (
        "/api/v1/cierres/intermedios",
        "/api/v1/cierres/reaperturas",
        f"/api/v1/cierres/anual/{EJERCICIO}",
    ):
        assert closing_client.client.get(ruta).status_code in (401, 403)
