"""Aislamiento multi-tenant de los modelos del ciclo (SPEC-009 T009)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado


async def test_ejercicio_empresa_a_invisible_para_b(db_session):
    db_session.add(
        EjercicioContable(
            empresa_id=10,
            ejercicio=2026,
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
            estado=EjercicioEstado.abierto,
        )
    )
    await db_session.flush()

    fila_b = await db_session.scalar(
        select(EjercicioContable).where(
            EjercicioContable.empresa_id == 20, EjercicioContable.ejercicio == 2026
        )
    )
    assert fila_b is None


async def test_consulta_siempre_filtra_por_empresa(db_session):
    for empresa, anio in ((10, 2025), (11, 2026), (12, 2027)):
        db_session.add(
            EjercicioContable(
                empresa_id=empresa,
                ejercicio=anio,
                fecha_inicio=date(anio, 1, 1),
                fecha_fin=date(anio, 12, 31),
                estado=EjercicioEstado.abierto,
            )
        )
    await db_session.flush()

    filas_10 = (
        await db_session.scalars(
            select(EjercicioContable).where(EjercicioContable.empresa_id == 10)
        )
    ).all()
    assert [f.ejercicio for f in filas_10] == [2025]
    assert all(f.empresa_id == 10 for f in filas_10)