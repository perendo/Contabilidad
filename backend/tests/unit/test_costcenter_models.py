"""T010: Tests de modelos fundacionales de centros de coste (SPEC-017).

Unicidad (empresa_id, codigo), FK compuesta multi-tenant (padre de otra
empresa imposible) y closure table materializada (ancestro/descendiente).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.costcenters.centro_coste import CentroCoste, CentroTipo
from models.costcenters.jerarquia import JerarquiaCentro
from services.costcenters.centros import crear_centro
from tests.conftest import sembrar_empresa_pgc


async def test_unicidad_empresa_codigo(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    db_session.add(
        CentroCoste(
            empresa_id=10, codigo="P01", nombre="Proyecto uno",
            tipo=CentroTipo.proyecto,
        )
    )
    await db_session.flush()

    db_session.add(
        CentroCoste(
            empresa_id=10, codigo="P01", nombre="Duplicado",
            tipo=CentroTipo.proyecto,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_mismo_codigo_ok_entre_empresas(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    db_session.add(CentroCoste(empresa_id=10, codigo="P01", nombre="A", tipo=CentroTipo.departamento))
    db_session.add(CentroCoste(empresa_id=20, codigo="P01", nombre="B", tipo=CentroTipo.departamento))
    await db_session.flush()


async def test_fk_parent_cross_tenant_rechazada(db_session):
    """Un centro de la empresa 20 no puede colgar de un padre de la 10."""
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    padre = CentroCoste(empresa_id=10, codigo="P10", nombre="Padre A", tipo=CentroTipo.departamento)
    db_session.add(padre)
    await db_session.flush()

    db_session.add(
        CentroCoste(
            empresa_id=20, codigo="H20", nombre="Hijo B",
            tipo=CentroTipo.departamento, parent_id=padre.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_closure_materializa_ancestro_descendiente(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    padre = await crear_centro(db_session, empresa_id=10, codigo="A", nombre="Raíz", tipo="departamento")
    hijo = await crear_centro(
        db_session, empresa_id=10, codigo="B", nombre="Hijo", tipo="proyecto",
        parent_id=uuid.UUID(padre["id"]),
    )

    filas = (await db_session.scalars(select(JerarquiaCentro))).all()
    pares = sorted(
        (str(f.ancestro_id), str(f.descendiente_id), f.profundidad) for f in filas
    )
    assert pares == sorted(
        [
            (str(padre["id"]), str(padre["id"]), 0),
            (str(padre["id"]), str(hijo["id"]), 1),
            (str(hijo["id"]), str(hijo["id"]), 0),
        ]
    )


async def test_fk_closure_cross_tenant_rechazada(db_session):
    """El par ancestro de la empresa 10 no puede materializarse en la 20."""
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    centro = CentroCoste(empresa_id=10, codigo="C1", nombre="Centro A", tipo=CentroTipo.departamento)
    db_session.add(centro)
    await db_session.flush()

    db_session.add(
        JerarquiaCentro(
            empresa_id=20, ancestro_id=centro.id,
            descendiente_id=uuid.uuid4(), profundidad=1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()