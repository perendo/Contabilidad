"""Tests HTTP del ciclo de vida del activo (SPEC-014 US1).

Cubre alta (201), validaciones de negocio (422), edición con replan del
plan futuro sin tocar posteados (constitución II) y aislamiento
multi-tenant (constitución III). Escenario del quickstart §1/§2/§6.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry


def _uu(txt: str) -> uuid.UUID:
    return uuid.UUID(txt)


def _id_cuenta(cli, code: str, empresa_id: int = 10) -> int:
    from models.acct.account_plan import AccountPlan

    async def _op(session):
        return await session.scalar(
            select(AccountPlan.id).where(
                AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
            )
        )

    return cli.run(cli.consultar(_op))


def _contar_asientos_amortizacion(cli, empresa_id: int = 10) -> int:
    async def _op(session):
        return len(
            (
                await session.scalars(
                    select(JournalEntry).where(
                        JournalEntry.empresa_id == empresa_id,
                        JournalEntry.concepto.startswith("Amortización"),
                    )
                )
            ).all()
        )

    return cli.run(cli.consultar(_op))


def test_alta_plan_lineal(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["estado"] == "en_uso"
    assert body["amortizado_acumulado"] == "0.0000"
    assert body["metodo"] == "lineal"
    assert len(body["plan"]) == 60
    assert body["plan"][0]["cuota"] == "250.0000"
    assert body["plan"][-1]["acumulado"] == "15000.0000"
    assert body["plan"][0]["ejercicio"] == 2026
    assert body["plan"][0]["periodo"] == 1


def test_alta_regresivo_decreciente(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear(numero_activo="VEH-001", cuenta_id=cli.cuentas()["2180"], coste_amortizable="20000.0000", vida_util=48, metodo="regresivo", porcentaje_regresivo="25.00")
    assert r.status_code == 201, r.text
    plan = r.json()["plan"]
    cuotas = [Decimal(f["cuota"]) for f in plan]
    for k in range(1, len(cuotas)):
        assert cuotas[k] <= cuotas[k - 1]
    assert plan[-1]["acumulado"] == "20000.0000"


def test_alta_cuenta_no_21x_rechazada(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear(cuenta_id=cli.cuentas()["6710"])
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "cuenta_invalida"


def test_alta_costes_invalidos(inmovilizado_client) -> None:
    cli = inmovilizado_client
    assert cli.crear(coste_amortizable="0").status_code == 422
    assert cli.crear(coste_amortizable="0.050000").status_code == 422


def test_alta_metodo_regresivo_sin_porcentaje(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear(numero_activo="X-1", metodo="regresivo")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "porcentaje_requerido"


def test_alta_fecha_ejercicio_cerrado(inmovilizado_client) -> None:
    cli = inmovilizado_client
    cli.marcar_cerrado(10, 2026)
    r = cli.crear(fecha_alta="2026-03-01")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "ejercicio_cerrado"


def test_alta_numero_duplicado(inmovilizado_client) -> None:
    cli = inmovilizado_client
    assert cli.crear(numero_activo="DUP-1").status_code == 201
    r = cli.crear(numero_activo="DUP-1")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "numero_activo_existente"


def test_cuentas_por_defecto(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear(numero_activo="DFT-1")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["cuenta_gasto_id"] == _id_cuenta(cli, "6810")
    assert body["cuenta_acumulada_id"] == _id_cuenta(cli, "2818")
    detalle = cli.get(10, f"/api/v1/activos/{body['id']}").json()
    assert len(detalle["plan"]) == 60
    assert {f["estado"] for f in detalle["plan"]} == {"pendiente"}


def test_listado_con_filtros(inmovilizado_client) -> None:
    cli = inmovilizado_client
    for n in ("L-1", "L-2"):
        assert cli.crear(numero_activo=n).status_code == 201
    assert cli.crear(numero_activo="L-3", cuenta_id=cli.cuentas()["2180"], fecha_alta="2025-05-01").status_code == 201

    lista = cli.get(10, "/api/v1/activos", estado="en_uso").json()
    assert lista["total"] == 3
    assert all(i["estado"] == "en_uso" for i in lista["items"])

    por_cuenta = cli.get(10, "/api/v1/activos", cuenta_id=cli.cuentas()["2180"]).json()
    assert por_cuenta["total"] == 3

    por_anio = cli.get(10, "/api/v1/activos", ejercicio_alta=2025).json()
    assert por_anio["total"] == 1
    assert por_anio["items"][0]["numero_activo"] == "L-3"

    pagina = cli.get(10, "/api/v1/activos", page=1, page_size=2).json()
    assert len(pagina["items"]) == 2
    assert pagina["total"] == 3


def test_aislamiento_tenant_alta_y_detalle(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r_a = cli.crear(numero_activo="TENANT-1")
    assert r_a.status_code == 201, r_a.text
    id_a = r_a.json()["id"]

    r_b = cli.crear(numero_activo="TENANT-1", empresa_id=20)
    assert r_b.status_code == 201, r_b.text
    id_b = r_b.json()["id"]
    assert id_a != id_b

    assert cli.get(10, "/api/v1/activos", estado="en_uso").json()["total"] == 1
    assert cli.get(20, "/api/v1/activos", estado="en_uso").json()["total"] == 1
    assert cli.get(20, "/api/v1/activos", estado="en_uso").json()["total"] == 1

    detalle_b = cli.get(20, f"/api/v1/activos/{_uu(id_a)}")
    assert detalle_b.status_code == 404


def test_patch_descripcion_no_toca_claves(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear(numero_activo="PAT-1")
    id_a = r.json()["id"]
    p = cli.patch(f"/api/v1/activos/{_uu(id_a)}", empresa_id=10, json={"descripcion": "Nueva"})
    assert p.status_code == 200, p.text
    body = p.json()
    assert body["descripcion"] == "Nueva"
    assert body["numero_activo"] == "PAT-1"
    assert body["vida_util"] == 60
    assert body["coste_amortizable"] == "15000.0000"


def test_patch_vida_util_replan_futuro(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear(numero_activo="PLN-1")
    id_a = r.json()["id"]
    for periodo in range(1, 6):
        g = cli.post("/api/v1/amortizaciones/generar", empresa_id=10, json={"ejercicio": 2026, "periodo": periodo})
        assert g.status_code == 200, g.text
        assert len(g.json()["generados"]) == 1

    p = cli.patch(f"/api/v1/activos/{_uu(id_a)}", empresa_id=10, json={"vida_util": 48})
    assert p.status_code == 200, p.text
    plan_futuro = p.json()["plan_futuro"]
    assert len(plan_futuro) == 43
    suma = sum((Decimal(f["cuota"]) for f in plan_futuro), Decimal(0))
    assert suma == Decimal("13750.0000")
    assert Decimal(plan_futuro[0]["cuota"]) == Decimal("319.7674")
    assert Decimal(plan_futuro[0]["acumulado"]) == Decimal("1250.0000") + Decimal("319.7674")

    assert _contar_asientos_amortizacion(cli) == 5


def test_patch_coste_no_toca_posteados(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear(numero_activo="COS-1")
    id_a = r.json()["id"]
    for periodo in range(1, 6):
        assert cli.post("/api/v1/amortizaciones/generar", empresa_id=10, json={"ejercicio": 2026, "periodo": periodo}).status_code == 200

    p = cli.patch(f"/api/v1/activos/{_uu(id_a)}", empresa_id=10, json={"coste_amortizable": "20000.0000", "vida_util": 48})
    assert p.status_code == 200, p.text
    plan_futuro = p.json()["plan_futuro"]
    suma = sum((Decimal(f["cuota"]) for f in plan_futuro), Decimal(0))
    assert suma == Decimal("18750.0000")
    assert _contar_asientos_amortizacion(cli) == 5


def test_patch_coste_inferior_al_acumulado(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear(numero_activo="BAJO-1")
    id_a = r.json()["id"]
    for periodo in range(1, 6):
        assert cli.post("/api/v1/amortizaciones/generar", empresa_id=10, json={"ejercicio": 2026, "periodo": periodo}).status_code == 200
    p = cli.patch(f"/api/v1/activos/{_uu(id_a)}", empresa_id=10, json={"coste_amortizable": "1000.0000"})
    assert p.status_code == 409
    assert p.json()["detail"]["code"] == "acumulado_supera_coste"


def test_patch_genera_error_por_precision(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    p = cli.patch(f"/api/v1/activos/{_uu(r.json()['id'])}", empresa_id=10, json={"coste_amortizable": "15000.00005"})
    assert p.status_code == 422


def test_plan_calcular_ambas_rutas(inmovilizado_client) -> None:
    cli = inmovilizado_client
    body = {
        "numero_activo": "CALC-1",
        "cuenta_id": cli.cuentas()["2180"],
        "descripcion": "Calc",
        "fecha_alta": "2026-10-01",
        "coste_amortizable": "15000.0000",
        "vida_util": 60,
        "metodo": "lineal",
    }
    r1 = cli.post("/api/v1/activos/plan/calcular", empresa_id=10, json=body)
    assert r1.status_code == 200, r1.text
    plan1 = r1.json()["plan"]
    assert len(plan1) == 60
    assert plan1[0]["cuota"] == "250.0000"
    assert r1.json()["total_amortizable"] == "15000.0000"

    alta = cli.crear(numero_activo="CALC-2")
    r2 = cli.post(
        f"/api/v1/activos/{_uu(alta.json()['id'])}/plan/calcular",
        empresa_id=10,
        json=body,
    )
    assert r2.status_code == 200, r2.text
    assert len(r2.json()["plan"]) == 60


def test_plan_calcular_activo_ajeno_404(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.post(
        f"/api/v1/activos/{_uu('00000000-0000-0000-0000-000000000001')}/plan/calcular",
        empresa_id=10,
        json={
            "numero_activo": "X",
            "cuenta_id": cli.cuentas()["2180"],
            "descripcion": "X",
            "fecha_alta": "2026-01-01",
            "coste_amortizable": "1000.0000",
            "vida_util": 12,
            "metodo": "lineal",
        },
    )
    assert r.status_code == 404


def test_detalle_activo_ajeno_404(inmovilizado_client) -> None:
    cli = inmovilizado_client
    r = cli.crear()
    id_a = r.json()["id"]
    assert cli.get(20, f"/api/v1/activos/{_uu(id_a)}").status_code == 404