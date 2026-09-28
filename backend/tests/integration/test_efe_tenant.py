"""Aislamiento multi-tenant del informe EFE (T030, constitucion III).

Empresa A formula su EFE; empresa B no ve ese informe y, sobre todo, no puede
usar los movimientos de A para formular el suyo (los ids de cuenta son globales
por empresa, de modo que un override cruzado se rechaza).
"""

from __future__ import annotations

EJERCICIO = 2026
A = 10
B = 20


def _asientos_de(cf, empresa_id: int) -> None:
    cf.plantar(empresa_id=empresa_id, code="1000", parent="100", name="Capital social")
    cf.asiento(
        empresa_id=empresa_id,
        fecha="2026-01-02",
        lineas=[
            {"cuenta": "5720", "debe": "5000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "5000.0000"},
        ],
        concepto="Apertura",
        tipo="OPENING",
    )
    cf.asiento(
        empresa_id=empresa_id,
        fecha="2026-04-01",
        lineas=[
            {"cuenta": "5720", "debe": "2000.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "2000.0000"},
        ],
        concepto="Cobro de venta",
    )


def test_efe_de_A_no_aparece_en_B(cashflow_client):
    cf = cashflow_client
    _asientos_de(cf, A)
    formulado = cf.post("/api/v1/tesoreria/efe/formular", {"ejercicio": EJERCICIO}, empresa_id=A)
    assert formulado.status_code == 200
    informe_id = formulado.json()["informe_id"]

    de_a = cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO, empresa_id=A).json()
    de_b = cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO, empresa_id=B).json()
    assert de_a["formulado"] is True
    assert de_a["informe_id"] == informe_id
    assert de_a["saldo_final"] == "7000.0000"
    assert de_b["formulado"] is False
    assert de_b["informe_id"] is None
    assert de_b["saldo_final"] == "0.0000"
    assert de_b["bloques"]["operativa"]["items"] == []


def test_formular_en_B_no_consume_el_snapshot_de_A(cashflow_client):
    cf = cashflow_client
    _asientos_de(cf, A)
    cf.post("/api/v1/tesoreria/efe/formular", {"ejercicio": EJERCICIO}, empresa_id=A)

    # B puede formular su propio EFE vacio: la unicidad es por (empresa, ejercicio).
    respuesta = cf.post("/api/v1/tesoreria/efe/formular", {"ejercicio": EJERCICIO}, empresa_id=B)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["saldo_final"] == "0.0000"
    assert cuerpo["informe_id"] != cf.get(
        "/api/v1/tesoreria/efe", ejercicio=EJERCICIO, empresa_id=A
    ).json()["informe_id"]

    # Y ambos snapshots siguen vivos e independientes.
    assert cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO, empresa_id=A).json()[
        "saldo_final"
    ] == "7000.0000"
    assert cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO, empresa_id=B).json()[
        "saldo_final"
    ] == "0.0000"


def test_override_con_cuenta_de_otra_empresa_se_rechaza(cashflow_client):
    cf = cashflow_client
    _asientos_de(cf, A)
    _asientos_de(cf, B)
    cuentas_a = cf.cuentas(A)

    # A no puede reclasificar la cuenta de B (no es suya ni tiene movimientos).
    respuesta = cf.post(
        "/api/v1/tesoreria/efe/formular",
        {"ejercicio": EJERCICIO, "clasificaciones": [{"cuenta_id": cuentas_a["7000"], "bloque": "inversion"}]},
        empresa_id=B,
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "cuenta_no_clasificable"

    # Y el override legitimo de A si se guarda.
    ok = cf.post(
        "/api/v1/tesoreria/efe/formular",
        {"ejercicio": EJERCICIO, "clasificaciones": [{"cuenta_id": cuentas_a["7000"], "bloque": "inversion"}]},
        empresa_id=A,
    )
    assert ok.status_code == 200
    assert ok.json()["totales"]["inversion"] == "2000.0000"


def test_saldo_de_tesoreria_no_se_filtra_entre_empresas(cashflow_client):
    cf = cashflow_client
    _asientos_de(cf, A)
    informe_b = cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO, empresa_id=B).json()
    assert informe_b["saldo_inicial"] == "0.0000"
    assert informe_b["saldo_final"] == "0.0000"


def test_conciliacion_de_A_no_alimenta_el_efe_de_B(cashflow_client):
    cf = cashflow_client
    _asientos_de(cf, A)
    cf.conciliacion(
        empresa_id=A, saldo_banco="100.0000", saldo_libros="7000.0000"
    )
    de_b = cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO, empresa_id=B).json()
    assert de_b["saldo_conciliacion"] is None
    assert de_b["sin_conciliar"] is False


def test_read_only_puede_leer_el_efe_pero_no_formularlo(cashflow_client):
    cf = cashflow_client
    _asientos_de(cf, A)
    assert cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO, token_key="readonly").status_code == 200
    respuesta = cf.post(
        "/api/v1/tesoreria/efe/formular", {"ejercicio": EJERCICIO}, token_key="readonly"
    )
    assert respuesta.status_code == 403
