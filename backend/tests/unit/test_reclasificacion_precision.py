"""Precision y cuadre de la seleccion (SPEC-025 T035).

La confirmacion exige importes de exactamente 4 decimales y que importe,
destino y mapeo coincidan con el preview (422 ``precision_invalida`` y
``cuadre_fallido``).
"""

from __future__ import annotations

import pytest

from services.catalog.errores import CatalogoError
from services.catalog.reclasificacion_saldos import (
    confirmar_reclasificacion,
    preview_reclasificacion,
)
from tests.unit.catalogo_support import preparar_trasvase


async def _preview(db, objetivo: str) -> dict:
    return await preview_reclasificacion(
        db, empresa_id=10, version_id=objetivo, ejercicio=2025
    )


async def test_importe_con_mas_de_cuatro_decimales(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    item = (await _preview(db_session, objetivo))["items"][0]
    alterado = dict(item, importe="12500.00001")

    with pytest.raises(CatalogoError) as exc:
        await confirmar_reclasificacion(
            db_session,
            empresa_id=10,
            version_id=objetivo,
            ejercicio=2025,
            items=[alterado],
            actor="test",
        )
    assert exc.value.code == "precision_invalida"
    assert exc.value.status_code == 422


async def test_importe_que_no_coincide_con_preview(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    item = (await _preview(db_session, objetivo))["items"][0]
    alterado = dict(item, importe="999.0000")

    with pytest.raises(CatalogoError) as exc:
        await confirmar_reclasificacion(
            db_session,
            empresa_id=10,
            version_id=objetivo,
            ejercicio=2025,
            items=[alterado],
            actor="test",
        )
    assert exc.value.code == "cuadre_fallido"


async def test_destino_que_no_coincide(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    item = (await _preview(db_session, objetivo))["items"][0]
    alterado = dict(item, cuenta_destino_id="00000000-0000-0000-0000-000000000001")

    with pytest.raises(CatalogoError) as exc:
        await confirmar_reclasificacion(
            db_session,
            empresa_id=10,
            version_id=objetivo,
            ejercicio=2025,
            items=[alterado],
            actor="test",
        )
    assert exc.value.code == "cuadre_fallido"


async def test_mapeo_que_no_coincide(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    item = (await _preview(db_session, objetivo))["items"][0]
    alterado = dict(item, mapeo_id="00000000-0000-0000-0000-000000000002")

    with pytest.raises(CatalogoError) as exc:
        await confirmar_reclasificacion(
            db_session,
            empresa_id=10,
            version_id=objetivo,
            ejercicio=2025,
            items=[alterado],
            actor="test",
        )
    assert exc.value.code == "cuadre_fallido"


async def test_importe_valido_de_cuatro_decimales(db_session):
    _base, objetivo, _ids = await preparar_trasvase(db_session)
    item = (await _preview(db_session, objetivo))["items"][0]
    alterado = dict(item, importe="12500.0000")

    resultado = await confirmar_reclasificacion(
        db_session,
        empresa_id=10,
        version_id=objetivo,
        ejercicio=2025,
        items=[alterado],
        actor="test",
    )
    assert resultado["reclasificaciones"] == 1
    assert resultado["total_importe"] == "12500.0000"
