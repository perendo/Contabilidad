"""Modelo multi-divisa (SPEC-016 T010).

Verifica a nivel de modelos: una sola moneda funcional por empresa (índice
parcial), UNIQUE (empresa, divisa, fecha) de tipos, FK compuestas con la
empresa, CHECK sellado <-> usos y UNIQUE de valoración.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import UniqueConstraint, select, text
from sqlalchemy.exc import IntegrityError

from models.monedas.diferencia_cambio import DiferenciaCambio
from models.monedas.moneda import Moneda
from models.monedas.tipo_cambio import TipoCambio

# ---------------------------------------------------------------------------
# Moneda funcional única (índice parcial por empresa)
# ---------------------------------------------------------------------------


def test_solo_una_funcional_por_empresa(forex_client):
    fx = forex_client

    async def _segunda_funcional(session):
        session.add(
            Moneda(empresa_id=10, codigo_iso="GBP", es_funcional=True, activa=True)
        )
        await session.flush()

    with pytest.raises(IntegrityError):
        fx.run(fx.mutar(_segunda_funcional))


def test_funcional_y_divisa_comparten_tabla_pero_se_distinguen(forex_client):
    fx = forex_client

    async def _consultar(session):
        filas = (
            await session.execute(
                text(
                    "SELECT codigo_iso, es_funcional FROM moneda "
                    "WHERE empresa_id = 10 ORDER BY es_funcional DESC"
                )
            )
        ).all()
        return filas

    filas = fx.run(fx.consultar(_consultar))
    assert filas[0] == ("EUR", 1)  # la funcional es siempre la primera
    codigos_divisa = [codigo for codigo, funcional in filas if funcional == 0]
    assert codigos_divisa == ["USD"]  # la divisa de trabajo vive en la misma tabla


# ---------------------------------------------------------------------------
# UNIQUE (empresa, divisa, fecha) — duplicado rechazado
# ---------------------------------------------------------------------------


def test_tipo_duplicado_rechazado_en_db(forex_client):
    fx = forex_client
    respuesta = fx.registrar_tipo(
        empresa_id=10, fecha="2026-10-01", ratio="1.08500000"
    )
    assert respuesta.status_code == 201

    async def _duplicado(session):
        session.add(
            TipoCambio(
                empresa_id=10,
                divisa_id=fx.divisas(10)["usd"],
                fecha=date(2026, 10, 1),
                ratio=Decimal("1.09000000"),
                usos_posteados=0,
                sellado=False,
            )
        )
        await session.flush()

    with pytest.raises(IntegrityError):
        fx.run(fx.mutar(_duplicado))


def test_unique_divisa_fecha_declarado_en_modelo():
    nombres = {
        tc.name
        for tc in TipoCambio.__table_args__
        if isinstance(tc, UniqueConstraint)
    }
    assert "uq_tipo_cambio_divisa_fecha" in nombres
    assert "uq_tipo_cambio_empresa_id" in nombres


# ---------------------------------------------------------------------------
# FK compuesta (empresa_id, divisa_id): no permite usar la divisa de otra empresa
# ---------------------------------------------------------------------------


def test_fk_compuesta_divisa_de_otra_empresa_rechazada(forex_client):
    fx = forex_client

    async def _fk_rota(session):
        session.add(
            TipoCambio(
                empresa_id=10,
                divisa_id=fx.divisas(20)["usd"],  # divisa de B con empresa de A
                fecha=date(2026, 10, 1),
                ratio=Decimal("1.08500000"),
                usos_posteados=0,
                sellado=False,
            )
        )
        await session.flush()

    with pytest.raises(IntegrityError):
        fx.run(fx.mutar(_fk_rota))


# ---------------------------------------------------------------------------
# CHECK sellado <-> usos_posteados (consistencia de la inmutabilidad)
# ---------------------------------------------------------------------------


def test_sellado_sin_usos_rechazado(forex_client):
    fx = forex_client

    async def _inconsistente(session):
        session.add(
            TipoCambio(
                empresa_id=10,
                divisa_id=fx.divisas(10)["usd"],
                fecha=date(2026, 10, 1),
                ratio=Decimal("1.08500000"),
                usos_posteados=0,
                sellado=True,
            )
        )
        await session.flush()

    with pytest.raises(IntegrityError):
        fx.run(fx.mutar(_inconsistente))


def test_usos_sin_sellado_rechazado(forex_client):
    fx = forex_client

    async def _inconsistente(session):
        session.add(
            TipoCambio(
                empresa_id=10,
                divisa_id=fx.divisas(10)["usd"],
                fecha=date(2026, 10, 1),
                ratio=Decimal("1.08500000"),
                usos_posteados=1,
                sellado=False,
            )
        )
        await session.flush()

    with pytest.raises(IntegrityError):
        fx.run(fx.mutar(_inconsistente))


# ---------------------------------------------------------------------------
# UNIQUE valoración (empresa, ejercicio, fecha_valoracion)
# ---------------------------------------------------------------------------


def test_unique_valoracion_declarado_en_modelo():
    nombres = {
        tc.name
        for tc in DiferenciaCambio.__table_args__
        if isinstance(tc, UniqueConstraint)
    }
    assert "uq_diferencia_cierre_unica" in nombres
    assert "uq_diferencia_empresa_id" in nombres


def test_una_sola_funcional_en_tabla_por_unicidad_de_indice(forex_client):
    fx = forex_client
    funciones = [i.name for i in Moneda.__table__.indexes]
    assert "ix_moneda_funcional_unica" in funciones
    assert any(
        getattr(i, "unique", False) and "funcional" in i.name
        for i in Moneda.__table__.indexes
    )
    # La empresa activa solo tiene una fila funcional
    filas = fx.run(
        fx.consultar(
            lambda s: s.execute(
                select(Moneda).where(
                    Moneda.empresa_id == 10, Moneda.es_funcional.is_(True)
                )
            )
        )
    ).all()
    assert len(filas) == 1
