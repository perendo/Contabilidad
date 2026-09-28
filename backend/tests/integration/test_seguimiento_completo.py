"""SPEC-026 US2 · T026: seguimiento completo presupuesto vs real.

Reproduce el quickstart (Escenario 2): presupuesto de 48000 en la 6400, gasto
real de 45000 y una cuenta sin presupuesto con real 2000. Verifica que
`real - presupuesto == desviacion_absoluta` con 4 decimales exactos, y que los
endpoints de seguimiento y de estado del periodo responden segun el contrato.
"""

from __future__ import annotations

from datetime import date

EJERCICIO = 2026


def _presupuesto(ns, codigo="6400", importe="48000.0000", empresa_id=10):
    return ns.post(
        "/api/v1/presupuestos",
        empresa_id=empresa_id,
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(empresa_id, codigo),
            "importe": importe,
        },
    )


def _gasto(ns, empresa_id, de, haber, importe, fecha=date(EJERCICIO, 6, 30)):
    """Asienta `de` al Debe y `haber` al Haber por el importe indicado."""
    return ns.asiento(
        empresa_id,
        fecha,
        [
            {"account_id": ns.cuenta(empresa_id, de), "debit": str(importe), "credit": "0"},
            {
                "account_id": ns.cuenta(empresa_id, haber),
                "debit": "0",
                "credit": str(importe),
            },
        ],
    )


def test_quickstart_escenario_2(presupuestos_client):
    ns = presupuestos_client
    assert _presupuesto(ns, "6400", "48000.0000").status_code == 200
    _gasto(ns, 10, "6400", "4000", 45000)
    _gasto(ns, 10, "6000", "4100", 2000)

    respuesta = ns.get(
        "/api/v1/presupuestos/seguimiento", ejercicio=EJERCICIO, cuenta_id=ns.cuenta(10, "6400")
    )
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["total"] == 1
    item = datos["items"][0]
    assert item["importe_presupuestado"] == "48000.0000"
    assert item["importe_real"] == "45000.0000"
    assert item["desviacion_absoluta"] == "-3000.0000"
    assert item["desviacion_relativa"] == "-0.0625"
    assert item["sin_presupuesto"] is False


def test_cuenta_sin_presupuesto_en_el_seguimiento(presupuestos_client):
    ns = presupuestos_client
    _gasto(ns, 10, "6000", "4100", 2000)

    respuesta = ns.get(
        "/api/v1/presupuestos/seguimiento", ejercicio=EJERCICIO, cuenta_id=ns.cuenta(10, "6000")
    )
    item = respuesta.json()["items"][0]
    assert item["sin_presupuesto"] is True
    assert item["importe_presupuestado"] == "0.0000"
    assert item["importe_real"] == "2000.0000"
    assert item["desviacion_absoluta"] == "2000.0000"
    assert item["desviacion_relativa"] is None


def test_todas_las_desviaciones_cuadran(presupuestos_client):
    """SC-002 sobre el endpoint HTTP."""
    from decimal import Decimal

    ns = presupuestos_client
    _presupuesto(ns, "6400", "48000.0000")
    _presupuesto(ns, "7000", "120000.0000")
    _gasto(ns, 10, "6400", "4000", 45000)
    _gasto(ns, 10, "6000", "4100", 2000)
    ns.asiento(
        10,
        date(EJERCICIO, 4, 30),
        [
            {"account_id": ns.cuenta(10, "4300"), "debit": "130000", "credit": "0"},
            {"account_id": ns.cuenta(10, "7000"), "debit": "0", "credit": "130000"},
        ],
    )

    datos = ns.get("/api/v1/presupuestos/seguimiento", ejercicio=EJERCICIO).json()
    assert datos["total"] >= 3
    for item in datos["items"]:
        esperado = Decimal(item["importe_real"]) - Decimal(item["importe_presupuestado"])
        assert Decimal(item["desviacion_absoluta"]) == esperado
        absoluto = item["desviacion_absoluta"]
        assert len(absoluto.split(".")[1]) == 4


def test_seguimiento_filtrado_por_mes(presupuestos_client):
    ns = presupuestos_client
    _presupuesto(ns, "6400", "48000.0000")
    ns.asiento(
        10,
        date(EJERCICIO, 2, 10),
        [
            {"account_id": ns.cuenta(10, "6400"), "debit": "1000", "credit": "0"},
            {"account_id": ns.cuenta(10, "4000"), "debit": "0", "credit": "1000"},
        ],
    )
    ns.asiento(
        10,
        date(EJERCICIO, 11, 10),
        [
            {"account_id": ns.cuenta(10, "6400"), "debit": "7000", "credit": "0"},
            {"account_id": ns.cuenta(10, "4000"), "debit": "0", "credit": "7000"},
        ],
    )

    febrero = ns.get(
        "/api/v1/presupuestos/seguimiento",
        ejercicio=EJERCICIO,
        mes=2,
        cuenta_id=ns.cuenta(10, "6400"),
    ).json()
    assert febrero["desde"] == "2026-02-01"
    assert febrero["hasta"] == "2026-02-28"
    assert febrero["items"][0]["importe_real"] == "1000.0000"

    anual = ns.get(
        "/api/v1/presupuestos/seguimiento",
        ejercicio=EJERCICIO,
        cuenta_id=ns.cuenta(10, "6400"),
    ).json()
    assert anual["items"][0]["importe_real"] == "8000.0000"


def test_mes_invalido_es_422(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.get("/api/v1/presupuestos/seguimiento", ejercicio=EJERCICIO, mes=13)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "mes_invalido"


def test_seguimiento_por_centro(presupuestos_client):
    ns = presupuestos_client
    centro = ns.centros(10)["CC-01"]
    ns.post(
        "/api/v1/presupuestos",
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(10, "6400"),
            "centro_coste_id": centro,
            "importe": "48000.0000",
        },
    )
    ns.asiento(
        10,
        date(EJERCICIO, 6, 30),
        [
            {
                "account_id": ns.cuenta(10, "6400"),
                "debit": "50000",
                "credit": "0",
                "centro_coste_id": centro,
            },
            {"account_id": ns.cuenta(10, "4000"), "debit": "0", "credit": "50000"},
        ],
    )

    datos = ns.get(
        "/api/v1/presupuestos/seguimiento",
        ejercicio=EJERCICIO,
        cuenta_id=ns.cuenta(10, "6400"),
        centro_coste_id=centro,
    ).json()
    assert datos["total"] == 1
    assert datos["items"][0]["centro_coste_id"] == centro
    assert "CC-01" in datos["items"][0]["nombre_centro"]
    assert datos["items"][0]["desviacion_absoluta"] == "2000.0000"


def test_periodo_actual_tras_crear_presupuesto(presupuestos_client):
    ns = presupuestos_client
    sin_periodo = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()
    assert sin_periodo["estado"] == "sin_periodo"
    assert sin_periodo["periodo_id"] is None

    assert _presupuesto(ns, "6400", "48000.0000").status_code == 200
    periodo = ns.get("/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO).json()
    assert periodo["estado"] == "abierto"
    assert periodo["numero_periodo"] == 1
    assert periodo["fecha_cierre"] is None
    assert periodo["cerrado_por"] is None
    assert periodo["fecha_inicio"] == "2026-01-01"
    assert periodo["fecha_fin"] == "2026-12-31"


def test_seguimiento_sin_datos_devuelve_lista_vacia(presupuestos_client):
    ns = presupuestos_client
    datos = ns.get("/api/v1/presupuestos/seguimiento", ejercicio=2027).json()
    assert datos["total"] == 0
    assert datos["items"] == []


def test_periodos_listado_y_creacion(presupuestos_client):
    ns = presupuestos_client
    assert ns.post(
        "/api/v1/presupuestos/periodos",
        json={
            "ejercicio": EJERCICIO,
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-03-31",
        },
    ).status_code == 201

    listado = ns.get("/api/v1/presupuestos/periodos", ejercicio=EJERCICIO).json()
    assert listado["total"] == 1
    assert listado["items"][0]["numero_periodo"] == 1
    assert listado["items"][0]["estado"] == "abierto"

    segundo = ns.post(
        "/api/v1/presupuestos/periodos",
        json={
            "ejercicio": EJERCICIO,
            "fecha_inicio": "2026-04-01",
            "fecha_fin": "2026-06-30",
        },
    )
    assert segundo.status_code == 409
    assert segundo.json()["detail"]["code"] == "periodo_ya_abierto"


def test_periodo_correlativo_incremental(presupuestos_client):
    ns = presupuestos_client
    primero = ns.post(
        "/api/v1/presupuestos/periodos",
        json={
            "ejercicio": EJERCICIO,
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-06-30",
        },
    )
    assert primero.status_code == 201
    assert primero.json()["numero_periodo"] == 1

    ns.post(
        "/api/v1/presupuestos/informes/cerrar",
        json={"ejercicio": EJERCICIO, "periodo_id": primero.json()["periodo_id"]},
    )
    segundo = ns.post(
        "/api/v1/presupuestos/periodos",
        json={
            "ejercicio": EJERCICIO,
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-12-31",
        },
    )
    assert segundo.status_code == 201
    assert segundo.json()["numero_periodo"] == 2


def test_rango_de_periodo_invalido_es_422(presupuestos_client):
    ns = presupuestos_client
    respuesta = ns.post(
        "/api/v1/presupuestos/periodos",
        json={
            "ejercicio": EJERCICIO,
            "fecha_inicio": "2026-12-31",
            "fecha_fin": "2026-01-01",
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "rango_invalido"
