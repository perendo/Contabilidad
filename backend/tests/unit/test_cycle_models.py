"""Modelos fundacionales del ciclo contable (SPEC-009 T008)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado


@pytest.fixture
async def ejercicio_2026(db_session):
    ej = EjercicioContable(
        empresa_id=10,
        ejercicio=2026,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        estado=EjercicioEstado.abierto,
    )
    db_session.add(ej)
    await db_session.flush()
    return ej


async def test_unicidad_empresa_ejercicio(db_session, ejercicio_2026):
    duplicado = EjercicioContable(
        empresa_id=10,
        ejercicio=2026,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        estado=EjercicioEstado.abierto,
    )
    db_session.add(duplicado)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_mismo_anio_otra_empresa_permitido(db_session, ejercicio_2026):
    otro = EjercicioContable(
        empresa_id=20,
        ejercicio=2026,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        estado=EjercicioEstado.abierto,
    )
    db_session.add(otro)
    await db_session.flush()
    fila = await db_session.scalar(
        select(EjercicioContable).where(
            EjercicioContable.empresa_id == 20, EjercicioContable.ejercicio == 2026
        )
    )
    assert fila is not None
    assert fila.id != ejercicio_2026.id


async def test_fecha_inicio_menor_que_fin(db_session):
    invalido = EjercicioContable(
        empresa_id=10,
        ejercicio=2027,
        fecha_inicio=date(2027, 12, 31),
        fecha_fin=date(2027, 1, 1),
        estado=EjercicioEstado.abierto,
    )
    db_session.add(invalido)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_estados_validos(db_session):
    ej = EjercicioContable(
        empresa_id=10,
        ejercicio=2028,
        fecha_inicio=date(2028, 1, 1),
        fecha_fin=date(2028, 12, 31),
        estado=EjercicioEstado.cerrado,
    )
    db_session.add(ej)
    await db_session.flush()
    fila = await db_session.scalar(
        select(EjercicioContable).where(EjercicioContable.ejercicio == 2028)
    )
    assert fila.estado == EjercicioEstado.cerrado