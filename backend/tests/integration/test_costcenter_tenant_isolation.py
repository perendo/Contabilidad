"""T011: Aislamiento multi-tenant de modelos de centros de coste.

Crear un centro en la empresa A; B no lo ve en ninguna consulta; el intento de
FK compuesta con empresa B (padre/closure de A) produce error.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.costcenters.centro_coste import CentroCoste, CentroTipo
from models.costcenters.imputacion import ImputacionCentro
from models.costcenters.jerarquia import JerarquiaCentro
from services.costcenters.centros import crear_centro
from tests.conftest import sembrar_empresa_pgc


async def _centro(db_session, empresa_id, codigo, parent_id=None, subvencion_id=None) -> CentroCoste:
    centro = CentroCoste(
        empresa_id=empresa_id, codigo=codigo, nombre=codigo,
        tipo=CentroTipo.departamento, parent_id=parent_id,
        subvencion_id=subvencion_id,
    )
    db_session.add(centro)
    await db_session.flush()
    return centro


async def test_centro_de_a_no_visible_desde_b(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    c_a = await _centro(db_session, 10, "A1")

    de_b = (
        await db_session.scalars(
            select(CentroCoste).where(CentroCoste.empresa_id == 20)
        )
    ).all()
    assert [c.id for c in de_b] == []
    assert de_b == []

    visible_a = await db_session.scalar(
        select(CentroCoste).where(CentroCoste.empresa_id == 10, CentroCoste.id == c_a.id)
    )
    assert visible_a is not None
    assert visible_a.empresa_id == 10


async def test_closure_de_a_no_filtra_para_b(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    a = await crear_centro(db_session, empresa_id=10, codigo="RA", nombre="RA", tipo="departamento")
    b = await crear_centro(db_session, empresa_id=20, codigo="RB", nombre="RB", tipo="departamento")
    await crear_centro(db_session, empresa_id=10, codigo="HA", nombre="HA", tipo="proyecto", parent_id=uuid.UUID(a["id"]))
    hb = await crear_centro(db_session, empresa_id=20, codigo="HB", nombre="HB", tipo="proyecto", parent_id=uuid.UUID(b["id"]))

    pares_b = (await db_session.scalars(select(JerarquiaCentro).where(JerarquiaCentro.empresa_id == 20))).all()
    ancestros_b = {str(p.ancestro_id) for p in pares_b}
    descendientes_b = {str(p.descendiente_id) for p in pares_b}
    ids_b = {b["id"], hb["id"]}
    assert ancestros_b <= ids_b
    assert descendientes_b == ids_b
    assert a["id"] not in ancestros_b
    assert a["id"] not in descendientes_b


async def test_fk_imputacion_cross_tenant_rechazada(db_session):
    """La traza imputacion_centro no puede cruzar de empresa (asiento de A)."""
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    centro = await _centro(db_session, 10, "CC1")

    db_session.add(
        ImputacionCentro(
            empresa_id=20,
            asiento_id=uuid.uuid4(),
            linea_id=uuid.uuid4(),
            centro_coste_id=centro.id,
            periodo=3,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()