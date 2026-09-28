"""T014: Centros tipo subvención y `subvencion_id` libre (SPEC-017).

SPEC-019 no está implementado: `subvencion_id` es un UUID sin FK y sin
validación cross-empresa; se persiste tal cual (desviación documentada en el
"Estado real" de tasks.md: la validación queda diferida a SPEC-019).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from models.costcenters.centro_coste import CentroCoste, CentroTipo
from services.costcenters.centros import crear_centro, obtener_centro
from tests.conftest import sembrar_empresa_pgc


async def test_crear_centro_subvencion_con_subvencion_id(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    subvencion = uuid.uuid4()
    creado = await crear_centro(
        db_session, empresa_id=10, codigo="SUB1", nombre="Subvención SEUR",
        tipo="subvencion", subvencion_id=subvencion,
    )
    assert creado["tipo"] == "subvencion"
    assert creado["subvencion_id"] == str(subvencion)

    centro = await db_session.scalar(
        select(CentroCoste).where(CentroCoste.empresa_id == 10, CentroCoste.id == uuid.UUID(creado["id"]))
    )
    assert centro is not None
    assert centro.tipo == CentroTipo.subvencion
    assert centro.subvencion_id == subvencion


async def test_subvencion_id_libre_persistido_y_leido(db_session):
    """Sin validación cross-empresa en esta fase (SPEC-019): se guarda el UUID."""
    await sembrar_empresa_pgc(db_session, 10)
    subvencion = uuid.uuid4()
    creado = await crear_centro(
        db_session, empresa_id=10, codigo="S2", nombre="S2",
        tipo="subvencion", subvencion_id=subvencion,
    )
    detalle = await obtener_centro(db_session, empresa_id=10, centro_id=uuid.UUID(creado["id"]))
    assert detalle is not None
    assert detalle["subvencion_id"] == str(subvencion)
    assert detalle["tipo"] == "subvencion"


async def test_subvencion_hijo_de_proyecto_ok(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    proy = await crear_centro(db_session, empresa_id=10, codigo="P1", nombre="P1", tipo="proyecto")
    sub = await crear_centro(
        db_session, empresa_id=10, codigo="S3", nombre="S3",
        tipo="subvencion", parent_id=uuid.UUID(proy["id"]), subvencion_id=uuid.uuid4(),
    )
    assert sub["parent_id"] == str(proy["id"])


async def test_subvencion_imputable_igual_que_los_demas(db_session):
    """Un centro subvención es un centro de coste normal (imputa apuntes)."""
    await sembrar_empresa_pgc(db_session, 10)
    sub = await crear_centro(
        db_session, empresa_id=10, codigo="S4", nombre="S4",
        tipo="subvencion", subvencion_id=uuid.uuid4(),
    )
    assert sub["es_hoja"] is True