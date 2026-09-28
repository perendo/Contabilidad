from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal.ajuste_extracontable import (
    AjusteExtracontable,
    TipoAjusteExtracontable,
)
from models.fiscal.calculo_is import CalculoIS, EstadoCalculoIS
from models.fiscal.modelo_200 import Modelo200
from tests.conftest import crear_empresas


async def _empresas(db: AsyncSession) -> None:
    await crear_empresas(
        db, 10, 20,
        nifs={10: "A00000010", 20: "B00000020"},
        razones_sociales={10: "Empresa A", 20: "Empresa B"},
    )
    await db.flush()


def _calculo(empresa_id: int, ejercicio: int) -> CalculoIS:
    return CalculoIS(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        resultado_contable=Decimal("100000.0000"),
        base_imponible=Decimal("100000.0000"),
        tipo_impositivo=Decimal("25.00"),
        cuota_integra=Decimal("25000.0000"),
        cuota_liquida=Decimal("25000.0000"),
        pagos_a_cuenta=Decimal("10000.0000"),
        cuota_diferencial=Decimal("15000.0000"),
        provisional=False,
        estado=EstadoCalculoIS.calculado,
    )


async def test_calculo_ajustes_y_modelo_aislados_por_empresa(
    db_session: AsyncSession,
) -> None:
    await _empresas(db_session)
    calculo_a = _calculo(10, 2025)
    calculo_b = _calculo(20, 2025)
    db_session.add_all([calculo_a, calculo_b])
    await db_session.flush()
    ajuste_a = AjusteExtracontable(
        empresa_id=10,
        calculo_is_id=calculo_a.id,
        tipo=TipoAjusteExtracontable.AJUSTE_POSITIVO,
        descripcion="Ajuste A",
        importe=Decimal("100.0000"),
    )
    modelo_a = Modelo200(
        empresa_id=10,
        calculo_is_id=calculo_a.id,
        contenido={"declarante": "A"},
        hash_contenido="a" * 64,
    )
    db_session.add_all([ajuste_a, modelo_a])
    await db_session.flush()

    visibles_a = (
        await db_session.scalars(
            select(CalculoIS).where(
                CalculoIS.empresa_id == 10,
                CalculoIS.id == calculo_a.id,
            )
        )
    ).all()
    visibles_b = (
        await db_session.scalars(
            select(CalculoIS).where(
                CalculoIS.empresa_id == 20,
                CalculoIS.id == calculo_a.id,
            )
        )
    ).all()
    assert [item.id for item in visibles_a] == [calculo_a.id]
    assert visibles_b == []

    for modelo, empresa_id in (
        (AjusteExtracontable, 10),
        (AjusteExtracontable, 20),
        (Modelo200, 10),
        (Modelo200, 20),
    ):
        filas = (
            await db_session.scalars(
                select(modelo).where(
                    modelo.empresa_id == empresa_id,
                    modelo.calculo_is_id == calculo_a.id,
                )
            )
        ).all()
        expected = 1 if empresa_id == 10 else 0
        assert len(filas) == expected


async def test_mismo_ejercicio_definitivo_permitido_entre_empresas(
    db_session: AsyncSession,
) -> None:
    await _empresas(db_session)
    db_session.add_all([_calculo(10, 2025), _calculo(20, 2025)])
    await db_session.flush()
    total = len(
        (
            await db_session.scalars(
                select(CalculoIS).where(CalculoIS.ejercicio == 2025)
            )
        ).all()
    )
    assert total == 2


async def test_fk_compuesta_rechaza_modelo_de_otra_empresa(
    db_session: AsyncSession,
) -> None:
    await _empresas(db_session)
    calculo_a = _calculo(10, 2025)
    db_session.add(calculo_a)
    await db_session.flush()
    db_session.add(
        Modelo200(
            empresa_id=20,
            calculo_is_id=calculo_a.id,
            contenido={"declarante": "B"},
            hash_contenido="b" * 64,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
