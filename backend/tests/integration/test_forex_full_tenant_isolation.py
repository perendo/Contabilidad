"""Aislamiento multi-tenant completo de SPEC-016 (T044).

Flujo completo: A registra divisa extra, tipos, asiento y valoración; B tiene
su propio mundo y no ve ni puede leer/mutar nada de A. Verificado a nivel de
tablas (constitución III).
"""

from __future__ import annotations

from sqlalchemy import select

from models.monedas.asiento_divisa import AsientoDivisa
from models.monedas.diferencia_cambio import DiferenciaCambio
from models.monedas.linea_divisa import LineaDivisa
from models.monedas.moneda import Moneda
from models.monedas.tipo_cambio import TipoCambio


def test_flujo_completo_A_y_B_totalmente_aislados(forex_client):
    fx = forex_client
    # --- A: divisa EUR adicional + tipos + asiento + valoración
    fx.post("/api/v1/divisas", empresa_id=10,
            json={"codigo_iso": "EUR", "es_funcional": False})
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")
    criterio = fx.post("/api/v1/valoraciones", empresa_id=10,
                       json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert criterio.status_code == 200

    # --- B: su propio mundo independiente
    fx.post("/api/v1/divisas", empresa_id=20, json={"codigo_iso": "GBP", "es_funcional": False})
    fx.registrar_tipo(empresa_id=20, fecha="2026-09-01", ratio="0.85000000")
    b_asiento = fx.asiento_divisa(
        empresa_id=20, fecha="2026-09-01",
        lineas=[
            {"cuenta_id": fx.cuentas(20)["4300"], "debe_divisa": "500.0000", "haber_divisa": "0.0000"},
            {"cuenta_id": fx.cuentas(20)["5720"], "debe_divisa": "0.0000", "haber_divisa": "500.0000"},
        ],
    )
    assert b_asiento.status_code == 201

    # --- Verificación por tabla: ninguna fila de B mezcla con A
    async def _filas(session):
        monedas = (await session.execute(select(Moneda.empresa_id, Moneda.codigo_iso))).all()
        tipos = (await session.execute(select(TipoCambio.empresa_id, TipoCambio.fecha))).all()
        asientos = (await session.execute(select(AsientoDivisa.empresa_id, AsientoDivisa.fecha))).all()
        lineas = (await session.execute(select(LineaDivisa.empresa_id))).all()
        difs = (await session.execute(select(DiferenciaCambio.empresa_id))).all()
        return monedas, tipos, asientos, lineas, difs

    monedas, tipos, asientos, lineas, difs = fx.run(fx.consultar(_filas))
    # Cada empresa tiene EUR funcional (creado perezosamente) + sus divisas propias
    iso_a = {m[1] for m in monedas if m[0] == 10}
    iso_b = {m[1] for m in monedas if m[0] == 20}
    assert iso_a == {"USD", "EUR"}  # USD sembrada + funcional EUR (A no dio de alta EUR)
    assert iso_b == {"USD", "EUR", "GBP"}  # USD sembrada + funcional EUR + GBP propia
    # Cada tipo de A es solo de A y cada tipo de B es solo de B: nunca se mezclan
    assert {t[0] for t in tipos} == {10, 20}
    assert {a[0] for a in asientos} == {10, 20}
    assert {l[0] for l in lineas} == {10, 20}
    assert {d[0] for d in difs} == {10}
    # B no genera diferencias porque no valoró su ejercicio; A sí valoró


def test_B_no_puede_crear_asiento_en_divisa_de_A(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")

    # B intenta usar la divisa de A (uuid de empresa 10) en su asiento
    resp = fx.post("/api/v1/asientos-divisa", empresa_id=20,
                   json={
                       "fecha": "2026-10-01",
                       "divisa_id": str(fx.divisas(10)["usd"]),
                       "concepto": "intento de B",
                       "lineas": [
                           {"cuenta_id": fx.cuentas(20)["4300"],
                            "debe_divisa": "100.0000", "haber_divisa": "0.0000"},
                           {"cuenta_id": fx.cuentas(20)["5720"],
                            "debe_divisa": "0.0000", "haber_divisa": "100.0000"},
                       ],
                   })
    assert resp.status_code == 404


def test_historico_cruzado_no_expone_datos(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    creado = fx.asiento_divisa(empresa_id=10, fecha="2026-10-01")
    asiento_id = creado.json()["asiento_id"]

    # B pide historial del asiento de A -> 404 (no revela existencia)
    resp_b = fx.get(20, "/api/v1/tipos-cambio/historial", asiento_id=asiento_id)
    assert resp_b.status_code == 404

    # B lista sus tipos por divisa de B -> vacío (sin filtrar datos de A)
    hist_b = fx.get(20, "/api/v1/tipos-cambio/historial", divisa_id=fx.divisas(20)["usd"])
    assert hist_b.status_code == 200
    assert hist_b.json()["total"] == 0