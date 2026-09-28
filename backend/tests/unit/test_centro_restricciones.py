"""T013: Restricciones del catálogo de centros (SPEC-017 US1).

Ciclos, código duplicado, padre inexistente y bloqueo de imputaciones sobre
centros inactivos. Ninguna mutación acepta ids de empresa distinta.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from models.costcenters.centro_coste import CentroCoste, CentroEstado
from services.costcenters.centros import (
    crear_centro,
    editar_centro,
    inactivar_centro,
    obtener_centro,
)
from services.costcenters.errores import CostcenterError
from tests.conftest import sembrar_empresa_pgc


def _uid(s: str) -> uuid.UUID:
    return uuid.UUID(s)


async def _raiz(db_session, empresa_id, codigo="RAIZ"):
    return await crear_centro(db_session, empresa_id=empresa_id, codigo=codigo, nombre=codigo, tipo="departamento")


async def test_codigo_duplicado_misma_empresa(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await _raiz(db_session, 10, "RR")
    with pytest.raises(CostcenterError) as exc:
        await _raiz(db_session, 10, "RR")
    assert exc.value.code == "codigo_duplicado"


async def test_padre_no_encontrado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    with pytest.raises(CostcenterError) as exc:
        await crear_centro(
            db_session, empresa_id=10, codigo="H1", nombre="Hijo",
            tipo="proyecto", parent_id=uuid.uuid4(),
        )
    assert exc.value.code == "parent_no_encontrado"


async def test_auto_padre_ciclo(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    raiz = await _raiz(db_session, 10, "A")
    with pytest.raises(CostcenterError) as exc:
        await editar_centro(
            db_session, empresa_id=10, centro_id=_uid(raiz["id"]), parent_id=_uid(raiz["id"])
        )
    assert exc.value.code == "ciclo"


async def test_reparentar_a_descendiente_rechaza_ciclo(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    a = await _raiz(db_session, 10, "A")
    b = await crear_centro(db_session, empresa_id=10, codigo="B", nombre="B", tipo="proyecto", parent_id=_uid(a["id"]))
    c = await crear_centro(db_session, empresa_id=10, codigo="C", nombre="C", tipo="proyecto", parent_id=_uid(b["id"]))

    # Mover B como hijo de C (B es ancestro de C) -> ciclo
    with pytest.raises(CostcenterError) as exc:
        await editar_centro(db_session, empresa_id=10, centro_id=_uid(b["id"]), parent_id=_uid(c["id"]))
    assert exc.value.code == "ciclo"


async def test_tipo_invalido(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    with pytest.raises(CostcenterError) as exc:
        await crear_centro(db_session, empresa_id=10, codigo="X1", nombre="X", tipo="insolito")
    assert exc.value.code == "tipo_invalido"


async def test_obtener_centro_de_otra_empresa_es_none(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    a = await _raiz(db_session, 10, "ZZ")
    assert await obtener_centro(db_session, empresa_id=20, centro_id=_uid(a["id"])) is None


async def test_inactivar_centro_persiste_estado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    a = await _raiz(db_session, 10, "CC")
    inactivo = await inactivar_centro(db_session, empresa_id=10, centro_id=_uid(a["id"]))
    assert inactivo["estado"] == CentroEstado.inactivo.value

    centro = await db_session.scalar(
        select(CentroCoste).where(CentroCoste.empresa_id == 10, CentroCoste.id == _uid(a["id"]))
    )
    assert centro is not None
    assert centro.estado == CentroEstado.inactivo