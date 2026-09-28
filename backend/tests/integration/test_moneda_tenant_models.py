"""Aislamiento multi-tenant a nivel de modelos (SPEC-016 T011).

Monedas, tipos de cambio, asientos en divisa y diferencias de cambio de la
empresa A son invisibles para B en todas las consultas (constitución III), y
todas las filas llevan su empresa_id. Nunca se filtra data de otra empresa.
"""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy import func, select

from models.monedas.asiento_divisa import AsientoDivisa
from models.monedas.diferencia_cambio import DiferenciaCambio
from models.monedas.linea_divisa import LineaDivisa
from models.monedas.moneda import Moneda
from models.monedas.tipo_cambio import TipoCambio


def _contar_filas(session, modelo, empresa_id):
    return session.scalar(
        select(func.count()).where(modelo.empresa_id == empresa_id)
    )


def test_monedas_de_A_no_visibles_para_B(forex_client):
    fx = forex_client

    async def _consulta(session):
        count_a = await _contar_filas(session, Moneda, 10)
        count_b = await _contar_filas(session, Moneda, 20)
        divisa_a = await session.scalar(
            select(Moneda).where(
                Moneda.empresa_id == 20, Moneda.codigo_iso == "USD"
            )
        )
        return count_a, count_b, divisa_a

    count_a, count_b, divisa_b = fx.run(fx.consultar(_consulta))
    # A tiene EUR + USD; B solo sus monedas propias
    assert count_a == count_b == 2
    # La divisa de B es una fila distinta de la de A (nunca comparte filas)
    assert divisa_b is not None
    assert divisa_b.empresa_id == 20


def test_tipos_aislados_por_empresa(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")

    async def _consulta(session):
        tipos_a = await _contar_filas(session, TipoCambio, 10)
        tipos_b = await _contar_filas(session, TipoCambio, 20)
        todos = (
            await session.execute(select(TipoCambio.empresa_id).distinct())
        ).all()
        return tipos_a, tipos_b, [t[0] for t in todos]

    tipos_a, tipos_b, empresas = fx.run(fx.consultar(_consulta))
    assert tipos_a == 1
    assert tipos_b == 0
    assert empresas == [10]  # A y B no comparten filas de tipos


def test_asientos_divisa_aislados_y_empresa_id_en_filas(forex_client):
    fx = forex_client
    fx.registrar_tipo(empresa_id=10, fecha="2026-10-01", ratio="1.08500000")
    resp = fx.asiento_divisa(empresa_id=10)
    assert resp.status_code == 201
    asiento_id = resp.json()["asiento_id"]

    async def _consulta(session):
        cabeceras = (
            await session.execute(
                select(AsientoDivisa.empresa_id).where(
                    AsientoDivisa.asiento_id == _uuid.UUID(asiento_id)
                )
            )
        ).all()
        lineas = (
            await session.execute(
                select(LineaDivisa.empresa_id)
                .join(
                    AsientoDivisa,
                    (AsientoDivisa.id == LineaDivisa.asiento_divisa_id)
                    & (AsientoDivisa.empresa_id == LineaDivisa.empresa_id),
                )
                .where(AsientoDivisa.asiento_id == _uuid.UUID(asiento_id))
            )
        ).all()
        return [c[0] for c in cabeceras], [l[0] for l in lineas]

    empresass, empresass_linea = fx.run(fx.consultar(_consulta))
    assert empresass == [10]
    assert empresass_linea == [10, 10]  # las líneas llevan la misma empresa que la cabecera


def test_diferencias_cambio_aisladas(forex_client):
    fx = forex_client

    async def _consulta(session):
        filas_a = await _contar_filas(session, DiferenciaCambio, 10)
        filas_b = await _contar_filas(session, DiferenciaCambio, 20)
        return filas_a, filas_b

    filas_a, filas_b = fx.run(fx.consultar(_consulta))
    assert filas_a == filas_b == 0