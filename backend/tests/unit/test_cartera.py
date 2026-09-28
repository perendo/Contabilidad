"""Consulta y agrupación de la cartera de efectos (SPEC-021 T031, T032).

Filtros por estado/tipo/tercero/rango de vencimiento, paginación y
agrupación por estado y tipo de efecto con importes agregados; siempre
acotado a la empresa activa (constitución III).
"""

from __future__ import annotations

import uuid
from datetime import date

from models.ar.tercero import Tercero
from models.treasury.efecto import EstadoEfecto, TipoEfecto
from services.treasury import cartera
from services.treasury.efecto import (
    cobrar_efecto,
    impagar_efecto,
    registrar_efecto,
)

TERCERO_A = uuid.uuid4()
TERCERO_B = uuid.uuid4()
TERCERO_C = uuid.uuid4()


async def _crear(db, *, empresa_id: int = 1, tercero=TERCERO_A, numero: str,
                 tipo: TipoEfecto = TipoEfecto.CHEQUE,
                 vencimiento: date = date(2026, 7, 1),
                 importe: str = "1000.0000"):
    return await registrar_efecto(
        db,
        empresa_id=empresa_id,
        tercero_id=tercero,
        tipo_efecto=tipo,
        numero_documento=numero,
        fecha_emision=date(2026, 5, 1),
        fecha_vencimiento=vencimiento,
        importe=importe,
    )


async def _sembrar(db):
    """Tres efectos: uno emitido (cheque, TERCERO_A, 1000), uno cobrado
    (pagaré, TERCERO_B, 500) y uno impagado (letra, TERCERO_A, 750, gastos 25)."""
    db.add(
        Tercero(
            empresa_id=1,
            id=TERCERO_A,
            nombre="Cliente A",
            nif="B10000000",
            es_cliente=True,
            es_proveedor=False,
        )
    )
    db.add(
        Tercero(
            empresa_id=1,
            id=TERCERO_B,
            nombre="Cliente B",
            nif="B10000001",
            es_cliente=True,
            es_proveedor=False,
        )
    )
    e1 = await _crear(db, numero="CH-1", tercero=TERCERO_A, importe="1000.0000")
    e2 = await _crear(
        db, numero="PG-1", tercero=TERCERO_B, tipo=TipoEfecto.PAGARE,
        vencimiento=date(2026, 8, 1), importe="500.0000",
    )
    e3 = await _crear(
        db, numero="LE-1", tercero=TERCERO_A, tipo=TipoEfecto.LETRA,
        vencimiento=date(2026, 9, 1), importe="750.0000",
    )
    await db.flush()
    await cobrar_efecto(db, empresa_id=1, efecto_id=e2.id, fecha_cobro=date(2026, 8, 1))
    await impagar_efecto(
        db, empresa_id=1, efecto_id=e3.id, fecha_impago=date(2026, 9, 5),
        gastos_devolucion="25.0000",
    )
    await db.flush()
    return e1, e2, e3


async def test_cartera_todas_y_total(db_session):
    await _sembrar(db_session)
    items, total = await cartera.consultar_cartera(db_session, empresa_id=1)
    assert total == 3
    assert len(items) == 3
    assert {i["numero_documento"] for i in items} == {"CH-1", "PG-1", "LE-1"}
    por_doc = next(i for i in items if i["numero_documento"] == "CH-1")
    assert por_doc["importe"] == "1000.0000"
    assert por_doc["estado"] == "emitido"


async def test_cartera_filtro_estado(db_session):
    await _sembrar(db_session)
    items, total = await cartera.consultar_cartera(
        db_session, empresa_id=1, estado=EstadoEfecto.cobrado
    )
    assert total == 1
    assert items[0]["numero_documento"] == "PG-1"
    items, total = await cartera.consultar_cartera(
        db_session, empresa_id=1, estado=EstadoEfecto.impagado
    )
    assert total == 1
    assert items[0]["numero_documento"] == "LE-1"


async def test_cartera_filtro_tipo(db_session):
    await _sembrar(db_session)
    items, total = await cartera.consultar_cartera(
        db_session, empresa_id=1, tipo_efecto=TipoEfecto.LETRA
    )
    assert total == 1
    assert items[0]["numero_documento"] == "LE-1"


async def test_cartera_filtro_tercero(db_session):
    await _sembrar(db_session)
    items, total = await cartera.consultar_cartera(
        db_session, empresa_id=1, tercero_id=TERCERO_B
    )
    assert total == 1
    assert items[0]["numero_documento"] == "PG-1"


async def test_cartera_filtro_rango_fechas(db_session):
    await _sembrar(db_session)
    items, total = await cartera.consultar_cartera(
        db_session,
        empresa_id=1,
        fecha_desde=date(2026, 8, 1),
        fecha_hasta=date(2026, 8, 31),
    )
    assert total == 1
    assert items[0]["numero_documento"] == "PG-1"


async def test_cartera_paginacion(db_session):
    await _sembrar(db_session)
    items, total = await cartera.consultar_cartera(db_session, empresa_id=1, limit=2, offset=1)
    assert total == 3
    assert len(items) == 2
    assert items[0]["numero_documento"] != "CH-1"


async def _tercero_empresa2(db) -> None:
    db.add(
        Tercero(
            empresa_id=2,
            id=TERCERO_C,
            nombre="Cliente C",
            nif="B10000002",
            es_cliente=True,
            es_proveedor=False,
        )
    )
    await db.flush()


async def test_cartera_aislada_por_empresa(db_session):
    await _sembrar(db_session)
    await _tercero_empresa2(db_session)
    await _crear(db_session, empresa_id=2, tercero=TERCERO_C, numero="CH-99")
    await db_session.flush()
    _items, total = await cartera.consultar_cartera(db_session, empresa_id=1)
    assert total == 3
    items2, total2 = await cartera.consultar_cartera(db_session, empresa_id=2)
    assert total2 == 1
    assert items2[0]["numero_documento"] == "CH-99"


async def test_agrupar_por_estado_y_tipo(db_session):
    await _sembrar(db_session)
    agrupado = await cartera.agrupar_cartera(db_session, empresa_id=1)
    por_estado = {x["estado"]: x for x in agrupado["por_estado"]}
    assert por_estado["emitido"]["total"] == 1
    assert por_estado["emitido"]["importe"] == "1000.0000"
    assert por_estado["cobrado"]["total"] == 1
    assert por_estado["cobrado"]["importe"] == "500.0000"
    assert por_estado["impagado"]["total"] == 1
    assert por_estado["impagado"]["importe"] == "750.0000"
    por_tipo = {x["tipo_efecto"]: x for x in agrupado["por_tipo"]}
    assert por_tipo["LETRA"]["total"] == 1
    assert por_tipo["CHEQUE"]["importe"] == "1000.0000"


async def test_agrupar_aislada_por_empresa(db_session):
    await _sembrar(db_session)
    await _tercero_empresa2(db_session)
    await _crear(db_session, empresa_id=2, tercero=TERCERO_C, numero="CH-99", importe="9999.0000")
    await db_session.flush()
    agrupado_a = await cartera.agrupar_cartera(db_session, empresa_id=1)
    agrupado_b = await cartera.agrupar_cartera(db_session, empresa_id=2)
    total_a = sum(x["total"] for x in agrupado_a["por_estado"])
    total_b = sum(x["total"] for x in agrupado_b["por_estado"])
    assert total_a == 3
    assert total_b == 1
    assert agrupado_b["por_estado"][0]["importe"] == "9999.0000"


async def test_detalle_efecto_con_asientos(db_session):
    _e1, e2, e3 = await _sembrar(db_session)
    detalle = await cartera.detalle_efecto(db_session, empresa_id=1, efecto_id=e3.id)
    assert detalle is not None
    assert detalle["estado"] == "impagado"
    assert str(e3.asiento_impago_id) == detalle["asiento_impago_id"]
    assert detalle["asientos"]["asiento_impago_id"]["tipo"] == "REVERSAL"
    detalle_cobrado = await cartera.detalle_efecto(db_session, empresa_id=1, efecto_id=e2.id)
    assert detalle_cobrado["asientos"]["asiento_cobro_id"]["tipo"] == "COBRO"


async def test_detalle_efecto_inexistente(db_session):
    await _sembrar(db_session)
    detalle = await cartera.detalle_efecto(db_session, empresa_id=1, efecto_id=uuid.uuid4())
    assert detalle is None


async def test_detalle_efecto_otra_empresa(db_session):
    e1, _e2, _e3 = await _sembrar(db_session)
    detalle = await cartera.detalle_efecto(db_session, empresa_id=2, efecto_id=e1.id)
    assert detalle is None