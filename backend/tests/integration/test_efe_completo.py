"""Informe EFE completo por API (T029, US2).

Reproduce el escenario 4 del quickstart: asientos de operativa, inversion y
financiacion (SPEC-002) -> GET /efe con los tres bloques y cuadre ->
POST /efe/formular con override -> snapshot inmutable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

EJERCICIO = 2026


def _escenario(cf) -> None:
    """Ejercicio completo: apertura + venta cobrada + inmovilizado + prestamo."""
    cf.plantar(empresa_id=10, code="1000", parent="100", name="Capital social")
    cf.plantar(empresa_id=10, code="1600", parent="160", name="Prestamos a LP")
    cf.asiento(
        empresa_id=10,
        fecha="2026-01-02",
        lineas=[
            {"cuenta": "5720", "debe": "5000.0000", "haber": "0"},
            {"cuenta": "1000", "debe": "0", "haber": "5000.0000"},
        ],
        concepto="Apertura de ejercicio",
        tipo="OPENING",
    )
    cf.asiento(
        empresa_id=10,
        fecha="2026-04-01",
        lineas=[
            {"cuenta": "5720", "debe": "2000.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "2000.0000"},
        ],
        concepto="Cobro de venta",
    )
    cf.asiento(
        empresa_id=10,
        fecha="2026-06-01",
        lineas=[
            {"cuenta": "2100", "debe": "1200.0000", "haber": "0"},
            {"cuenta": "5720", "debe": "0", "haber": "1200.0000"},
        ],
        concepto="Compra de inmovilizado",
    )
    cf.asiento(
        empresa_id=10,
        fecha="2026-07-01",
        lineas=[
            {"cuenta": "5720", "debe": "800.0000", "haber": "0"},
            {"cuenta": "1600", "debe": "0", "haber": "800.0000"},
        ],
        concepto="Devolucion de prestamo",
    )


# --- Escenario 4, paso 1: lectura del informe -------------------------------


def test_efe_tiene_los_tres_bloques_y_cuadra(cashflow_client):
    cf = cashflow_client
    _escenario(cf)

    informe = cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO).json()
    assert informe["ejercicio"] == EJERCICIO
    assert informe["cuadre"] is True
    assert informe["sin_conciliar"] is False
    assert informe["saldo_inicial"] == "5000.0000"
    assert informe["variacion_neta"] == "1600.0000"
    assert informe["saldo_final"] == "6600.0000"
    # 2000 venta - 1200 inmovilizado + 800 devolucion de prestamo.
    assert informe["bloques"]["operativa"]["total"] == "2000.0000"
    assert informe["bloques"]["inversion"]["total"] == "-1200.0000"
    assert informe["bloques"]["financiacion"]["total"] == "800.0000"
    assert [
        item["codigo_cuenta"] for item in informe["bloques"]["operativa"]["items"]
    ] == ["7000"]
    assert [
        item["codigo_cuenta"] for item in informe["bloques"]["inversion"]["items"]
    ] == ["2100"]
    assert [
        item["codigo_cuenta"] for item in informe["bloques"]["financiacion"]["items"]
    ] == ["1600"]
    # El cuadre aritmetico del contrato (FR-004).
    suma = sum(
        (Decimal(informe["bloques"][b]["total"]) for b in ("operativa", "inversion", "financiacion")),
        Decimal(0),
    )
    assert Decimal(informe["saldo_inicial"]) + suma == Decimal(informe["saldo_final"])
    assert informe["formulado"] is False


def test_efe_sin_movimientos_cuadra_en_cero(cashflow_client):
    informe = cashflow_client.get("/api/v1/tesoreria/efe", ejercicio=2027).json()
    assert informe["cuadre"] is True
    assert informe["saldo_inicial"] == "0.0000"
    assert informe["saldo_final"] == "0.0000"
    for bloque in ("operativa", "inversion", "financiacion"):
        assert informe["bloques"][bloque]["total"] == "0.0000"
        assert informe["bloques"][bloque]["items"] == []


def test_efe_ejercicio_invalido_devuelve_422(cashflow_client):
    respuesta = cashflow_client.get("/api/v1/tesoreria/efe", ejercicio=1800)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "ejercicio_invalido"


def test_efe_requiere_ejercicio(cashflow_client):
    respuesta = cashflow_client.get("/api/v1/tesoreria/efe")
    assert respuesta.status_code == 422


# --- Escenario 4, paso 2: formulacion con override --------------------------


def test_formular_con_override_de_clasificacion(cashflow_client):
    cf = cashflow_client
    _escenario(cf)
    cuentas = cf.cuentas(10)

    respuesta = cf.post(
        "/api/v1/tesoreria/efe/formular",
        {"ejercicio": EJERCICIO, "clasificaciones": [{"cuenta_id": cuentas["7000"], "bloque": "inversion"}]},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "formulado"
    assert cuerpo["cuadre"] is True
    assert cuerpo["saldo_final"] == "6600.0000"
    # El override mueve la linea de bloque sin alterar la suma.
    assert cuerpo["totales"]["operativa"] == "0.0000"
    assert cuerpo["totales"]["inversion"] == "800.0000"
    assert cuerpo["totales"]["financiacion"] == "800.0000"

    posterior = cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO).json()
    assert posterior["formulado"] is True
    assert posterior["informe_id"] == cuerpo["informe_id"]
    operativa = [i for i in posterior["bloques"]["inversion"]["items"] if i["codigo_cuenta"] == "7000"]
    assert operativa and operativa[0]["override_usuario"] is True


def test_formular_dos_veces_devuelve_409(cashflow_client):
    cf = cashflow_client
    _escenario(cf)
    assert cf.post("/api/v1/tesoreria/efe/formular", {"ejercicio": EJERCICIO}).status_code == 200
    repetida = cf.post("/api/v1/tesoreria/efe/formular", {"ejercicio": EJERCICIO})
    assert repetida.status_code == 409
    assert repetida.json()["detail"]["code"] == "efe_ya_formulado"


def test_formular_ejercicio_cerrado_devuelve_409(cashflow_client):
    """T044: el ejercicio cerrado bloquea la formulacion del EFE."""
    cf = cashflow_client
    _escenario(cf)
    cf.cerrar_ejercicio(empresa_id=10, year=EJERCICIO)
    respuesta = cf.post("/api/v1/tesoreria/efe/formular", {"ejercicio": EJERCICIO})
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "ejercicio_cerrado"


def test_formular_con_bloque_invalido_devuelve_422(cashflow_client):
    cf = cashflow_client
    _escenario(cf)
    cuentas = cf.cuentas(10)
    respuesta = cf.post(
        "/api/v1/tesoreria/efe/formular",
        {"ejercicio": EJERCICIO, "clasificaciones": [{"cuenta_id": cuentas["7000"], "bloque": "operativo"}]},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "bloque_invalido"


# --- Snapshot inmutable (constitucion II) -----------------------------------


def test_snapshot_formulado_es_inmutable_en_db(cashflow_client):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    cf = cashflow_client
    _escenario(cf)
    assert cf.post("/api/v1/tesoreria/efe/formular", {"ejercicio": EJERCICIO}).status_code == 200

    with pytest.raises(IntegrityError, match="inmutable"):
        cf.run(
            cf.mutar(
                lambda session: session.execute(
                    text("UPDATE informe_efe SET cuadre = 0 WHERE empresa_id = :e"),
                    {"e": 10},
                )
            )
        )


def test_lineas_formuladas_son_append_only(cashflow_client):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    cf = cashflow_client
    _escenario(cf)
    cf.post("/api/v1/tesoreria/efe/formular", {"ejercicio": EJERCICIO})

    with pytest.raises(IntegrityError, match="inmutable"):
        cf.run(
            cf.mutar(
                lambda session: session.execute(
                    text("DELETE FROM linea_efe WHERE empresa_id = :e"), {"e": 10}
                )
            )
        )


# --- Asientos de otro ejercicio no contaminan (constitucion I) --------------


def test_efe_solo_agrega_el_ejercicio_pedido(cashflow_client):
    cf = cashflow_client
    _escenario(cf)
    cf.asiento(
        empresa_id=10,
        fecha="2027-02-01",
        lineas=[
            {"cuenta": "5720", "debe": "9999.0000", "haber": "0"},
            {"cuenta": "7000", "debe": "0", "haber": "9999.0000"},
        ],
        concepto="Cobro del ejercicio siguiente",
    )
    informe = cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO).json()
    assert informe["saldo_final"] == "6600.0000"
    assert informe["bloques"]["operativa"]["total"] == "2000.0000"


def test_efe_ignora_asientos_borrador(cashflow_client):
    """Solo el diario oficial (POSTED) alimenta el EFE (constitucion II)."""
    cf = cashflow_client
    _escenario(cf)
    cuentas = cf.cuentas(10)
    banco = cuentas["5720"]
    ventas = cuentas["7000"]

    async def _borrador(session):
        from services.journal.entry_service import crear_borrador

        return await crear_borrador(
            session,
            empresa_id=10,
            fecha=date(EJERCICIO, 9, 1),
            concepto="Borrador sin asentar",
            lineas=[
                {"account_id": banco, "debit": "500.0000", "credit": "0"},
                {"account_id": ventas, "debit": "0", "credit": "500.0000"},
            ],
            actor="test",
        )

    cf.run(cf.mutar(_borrador))
    informe = cf.get("/api/v1/tesoreria/efe", ejercicio=EJERCICIO).json()
    assert informe["saldo_final"] == "6600.0000"
    assert informe["bloques"]["operativa"]["total"] == "2000.0000"
