"""SPEC-026 US2 · T027: aislamiento del diario y del presupuesto en el seguimiento.

La empresa B ve el seguimiento vacio aunque la A tenga presupuesto y asientos
reales, y el filtro por cuenta de la A desde la B no devuelve filas. El
seguimiento se construye con `empresa_id` en ambos lados del JOIN al diario
(constitucion III + constitucion I).
"""

from __future__ import annotations

from datetime import date

EJERCICIO = 2026


def _preparar(ns, empresa_id: int) -> None:
    ns.post(
        "/api/v1/presupuestos",
        empresa_id=empresa_id,
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(empresa_id, "6400"),
            "importe": "48000.0000",
        },
    )
    ns.asiento(
        empresa_id,
        date(EJERCICIO, 6, 30),
        [
            {
                "account_id": ns.cuenta(empresa_id, "6400"),
                "debit": "45000",
                "credit": "0",
            },
            {
                "account_id": ns.cuenta(empresa_id, "4000"),
                "debit": "0",
                "credit": "45000",
            },
        ],
    )


def test_seguimiento_de_B_no_ve_nada_de_A(presupuestos_client):
    ns = presupuestos_client
    _preparar(ns, 10)

    de_a = ns.get("/api/v1/presupuestos/seguimiento", ejercicio=EJERCICIO).json()
    assert de_a["total"] >= 1

    de_b = ns.get(
        "/api/v1/presupuestos/seguimiento", empresa_id=20, ejercicio=EJERCICIO
    ).json()
    assert de_b["total"] == 0
    assert de_b["items"] == []


def test_filtrar_por_cuenta_de_A_desde_B_no_devuelve_filas(presupuestos_client):
    ns = presupuestos_client
    _preparar(ns, 10)
    cuenta_de_a = ns.cuenta(10, "6400")

    desde_b = ns.get(
        "/api/v1/presupuestos/seguimiento",
        empresa_id=20,
        ejercicio=EJERCICIO,
        cuenta_id=cuenta_de_a,
    ).json()
    assert desde_b["total"] == 0


def test_las_cuentas_del_plan_son_distintas_por_empresa(presupuestos_client):
    """Los ids de `account_plan` son globales: 6400 en A no es 6400 en B."""
    ns = presupuestos_client
    assert ns.cuenta(10, "6400") != ns.cuenta(20, "6400")


def test_cada_empresa_conserva_su_propia_desviacion(presupuestos_client):
    ns = presupuestos_client
    _preparar(ns, 10)
    ns.post(
        "/api/v1/presupuestos",
        empresa_id=20,
        json={
            "ejercicio": EJERCICIO,
            "cuenta_id": ns.cuenta(20, "6400"),
            "importe": "30000.0000",
        },
    )
    ns.asiento(
        20,
        date(EJERCICIO, 6, 30),
        [
            {"account_id": ns.cuenta(20, "6400"), "debit": "33000", "credit": "0"},
            {"account_id": ns.cuenta(20, "4000"), "debit": "0", "credit": "33000"},
        ],
    )

    de_a = ns.get(
        "/api/v1/presupuestos/seguimiento",
        ejercicio=EJERCICIO,
        cuenta_id=ns.cuenta(10, "6400"),
    ).json()
    de_b = ns.get(
        "/api/v1/presupuestos/seguimiento",
        empresa_id=20,
        ejercicio=EJERCICIO,
        cuenta_id=ns.cuenta(20, "6400"),
    ).json()
    assert de_a["items"][0]["desviacion_absoluta"] == "-3000.0000"
    assert de_b["items"][0]["desviacion_absoluta"] == "3000.0000"
    assert de_a["items"][0]["importe_presupuestado"] == "48000.0000"
    assert de_b["items"][0]["importe_presupuestado"] == "30000.0000"


def test_informe_de_B_no_hereda_totales_de_A(presupuestos_client):
    ns = presupuestos_client
    _preparar(ns, 10)

    de_a = ns.get(
        "/api/v1/presupuestos/informes/desviacion", ejercicio=EJERCICIO
    ).json()
    de_b = ns.get(
        "/api/v1/presupuestos/informes/desviacion", empresa_id=20, ejercicio=EJERCICIO
    ).json()
    assert de_a["total_presupuestado"] != "0.0000"
    assert de_b["total_presupuestado"] == "0.0000"
    assert de_b["total_real"] == "0.0000"
    assert de_b["items"] == []
    assert de_b["total"] == 0


def test_periodo_de_B_es_distinto_del_de_A(presupuestos_client):
    ns = presupuestos_client
    _preparar(ns, 10)

    periodo_a = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", ejercicio=EJERCICIO
    ).json()
    periodo_b = ns.get(
        "/api/v1/presupuestos/seguimiento/periodo", empresa_id=20, ejercicio=EJERCICIO
    ).json()
    assert periodo_a["periodo_id"] != periodo_b["periodo_id"] or (
        periodo_a["periodo_id"] is None and periodo_b["periodo_id"] is None
    )
    assert periodo_b["estado"] == "sin_periodo"
