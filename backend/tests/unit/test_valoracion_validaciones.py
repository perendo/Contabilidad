"""Validaciones de valoración a cierre (SPEC-016 T026).

Ejercicio cerrado -> 409; sin tipo de cierre para la fecha -> 422; valoración
duplicada (ejercicio, fecha) -> 409.
"""

from __future__ import annotations

from datetime import date

from models.acct.fiscal_year import FiscalYear


def _postear_saldo(fx, empresa_id: int = 10, fecha: str = "2026-10-01", ratio: str = "1.08500000"):
    fx.registrar_tipo(empresa_id=empresa_id, fecha=fecha, ratio=ratio)
    resp = fx.asiento_divisa(empresa_id=empresa_id, fecha=fecha)
    assert resp.status_code == 201


def _cerrar_ejercicio(fx, empresa_id: int = 10, year: int = 2026):
    async def _add(session):
        session.add(
            FiscalYear(
                empresa_id=empresa_id,
                year=year,
                date_start=date(year, 1, 1),
                date_end=date(year, 12, 31),
                is_closed=True,
            )
        )

    fx.run(fx.mutar(_add))


def test_ejercicio_cerrado_409(forex_client):
    fx = forex_client
    _postear_saldo(fx)
    _cerrar_ejercicio(fx)

    resp = fx.post("/api/v1/valoraciones", empresa_id=10,
                   json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert resp.status_code == 409
    assert "cerrado" in str(resp.json())


def test_sin_tipo_de_cierre_422(forex_client):
    fx = forex_client
    _postear_saldo(fx)  # tipo solo para 2026-10-01

    resp = fx.post("/api/v1/valoraciones", empresa_id=10,
                   json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert resp.status_code == 422


def test_valoracion_duplicada_409(forex_client):
    fx = forex_client
    _postear_saldo(fx)
    fx.registrar_tipo(empresa_id=10, fecha="2026-12-31", ratio="1.10000000")

    primera = fx.post("/api/v1/valoraciones", empresa_id=10,
                      json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert primera.status_code == 200

    segunda = fx.post("/api/v1/valoraciones", empresa_id=10,
                      json={"ejercicio": 2026, "fecha_valoracion": "2026-12-31"})
    assert segunda.status_code == 409


def test_fecha_fuera_del_ejercicio_422(forex_client):
    fx = forex_client
    resp = fx.post("/api/v1/valoraciones", empresa_id=10,
                   json={"ejercicio": 2026, "fecha_valoracion": "2027-01-31"})
    assert resp.status_code == 422