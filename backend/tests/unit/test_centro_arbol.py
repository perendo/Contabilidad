"""T012: Test alta y árbol de centros (SPEC-017 US1).

Crear centros padre/hijo; verificar la closure (ancestro→descendiente con
profundidad) y la consulta de árbol con subtotales de agregación.
"""

from __future__ import annotations

import uuid

from services.costcenters.centros import (
    arbol_centros,
    crear_centro,
    listar_centros,
    obtener_centro,
)
from tests.conftest import sembrar_empresa_pgc


def _uid(s: str) -> uuid.UUID:
    return uuid.UUID(s)


async def _arbol(db_session, empresa_id):
    a = await crear_centro(db_session, empresa_id=empresa_id, codigo="A", nombre="Dirección", tipo="departamento")
    b = await crear_centro(db_session, empresa_id=empresa_id, codigo="B", nombre="Proyecto X", tipo="proyecto", parent_id=_uid(a["id"]))
    c = await crear_centro(db_session, empresa_id=empresa_id, codigo="C", nombre="Subvención Y", tipo="subvencion", parent_id=_uid(b["id"]))
    return a, b, c


async def test_creacion_encadena_closure(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    a, b, c = await _arbol(db_session, 10)

    arbol = await arbol_centros(db_session, empresa_id=10)
    items = arbol["items"]
    assert len(items) == 1
    raiz = items[0]
    assert raiz["id"] == a["id"]
    assert raiz["profundidad"] == 0
    hijos = raiz["hijos"]
    assert len(hijos) == 1
    assert hijos[0]["id"] == b["id"]
    assert hijos[0]["profundidad"] == 1
    nietos = hijos[0]["hijos"]
    assert len(nietos) == 1
    assert nietos[0]["id"] == c["id"]
    assert nietos[0]["profundidad"] == 2


async def test_arbol_no_duplica_directos(db_session):
    """El árbol no pierde los hijos directos (n_hijos coherente)."""
    await sembrar_empresa_pgc(db_session, 10)
    await _arbol(db_session, 10)

    arbol = await arbol_centros(db_session, empresa_id=10)
    raiz = arbol["items"][0]
    assert raiz["n_hijos"] == 1
    assert arbol["total"] == 3


async def test_listar_y_detalle_con_hijos(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    a, b, _ = await _arbol(db_session, 10)

    pagina = await listar_centros(db_session, empresa_id=10)
    assert pagina["total"] == 3
    assert {i["codigo"] for i in pagina["items"]} == {"A", "B", "C"}

    detalle = await obtener_centro(db_session, empresa_id=10, centro_id=_uid(a["id"]))
    assert detalle is not None
    assert len(detalle["hijos"]) == 1
    assert detalle["hijos"][0]["id"] == b["id"]


async def test_filtro_por_estado_en_listado(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    a, _, _ = await _arbol(db_session, 10)
    from services.costcenters.centros import inactivar_centro

    await inactivar_centro(db_session, empresa_id=10, centro_id=_uid(a["id"]))

    solo_inactivos = await listar_centros(db_session, empresa_id=10, estado="inactivo")
    assert solo_inactivos["total"] == 1
    assert solo_inactivos["items"][0]["id"] == a["id"]
    assert solo_inactivos["items"][0]["estado"] == "inactivo"

    solo_activos = await listar_centros(db_session, empresa_id=10, estado="activo")
    assert solo_activos["total"] == 2


async def test_double_inactivacion_rechazada(db_session):
    import pytest

    from services.costcenters.centros import inactivar_centro
    from services.costcenters.errores import CostcenterError

    await sembrar_empresa_pgc(db_session, 10)
    a, _, _ = await _arbol(db_session, 10)
    await inactivar_centro(db_session, empresa_id=10, centro_id=_uid(a["id"]))
    with pytest.raises(CostcenterError) as exc:
        await inactivar_centro(db_session, empresa_id=10, centro_id=_uid(a["id"]))
    assert exc.value.code == "estado_duplicado"