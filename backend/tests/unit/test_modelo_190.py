from __future__ import annotations

import hashlib
from decimal import Decimal

from sqlalchemy import select

from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from models.fiscal.modelo_190 import Modelo190
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from services.fiscal.modelo_190_gen import generar_modelo_190, json_canonico


async def _crear_retenciones(session, api, empresa_id: int = 10):
    tercero_id = api.terceros[empresa_id]["con_nif"]
    filas = (
        (1, "1000.0000", "15.00", "150.0000"),
        (2, "2000.0000", "15.00", "300.0000"),
        (3, "3000.0000", "19.00", "570.0000"),
        (4, "4000.0000", "19.00", "760.0000"),
    )
    for trimestre, base, tasa, retencion in filas:
        liquidacion = LiquidacionRetenciones(
            empresa_id=empresa_id,
            ejercicio=2025,
            trimestre=trimestre,
            periodo=f"2025-Q{trimestre}",
            total_base_retenciones=Decimal(base),
            total_retenciones=Decimal(retencion),
            n_perceptores=1,
        )
        session.add(liquidacion)
        await session.flush()
        session.add(
            RetencionPeriodo(
                empresa_id=empresa_id,
                liquidacion_retenciones_id=liquidacion.id,
                tercero_id=tercero_id,
                nif="",
                nombre=api.terceros[empresa_id]["con_nif"].hex,
                tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
                base_imponible=Decimal(base),
                tipo_porcentaje=Decimal(tasa),
                retencion_practicada=Decimal(retencion),
                facturas=[],
            )
        )
    await session.flush()
    return await generar_modelo_190(
        session, empresa_id=empresa_id, ejercicio=2025, actor="test"
    )


def test_modelo_190_agrega_q1_q4_y_tasas(retenciones_client):
    api = retenciones_client
    modelo = api.run(api.mutar(lambda session: _crear_retenciones(session, api)))
    contenido = modelo.contenido

    assert set(contenido) == {
        "datos_declarante",
        "totales_ejercicio",
        "detalle_perceptores",
        "totales",
    }
    assert contenido["datos_declarante"]["nif"] == "A00000010"
    assert contenido["totales_ejercicio"] == {
        "total_perceptores": 1,
        "total_base_retenciones": "10000.0000",
        "total_retenciones": "1780.0000",
    }
    assert len(contenido["detalle_perceptores"]) == 2
    assert {detalle["tipo_retencion"] for detalle in contenido["detalle_perceptores"]} == {
        "15.00",
        "19.00",
    }
    assert contenido["totales"] == {"total_retenciones_anual": "1780.0000"}
    assert modelo.n_perceptores == 1
    canonico = json_canonico(contenido)
    assert hashlib.sha256(canonico.encode("utf-8")).hexdigest() == modelo.hash_contenido


def test_modelo_190_persiste_en_empresa_activa(retenciones_client):
    api = retenciones_client
    modelo = api.run(api.mutar(lambda session: _crear_retenciones(session, api)))

    async def _consultar(session):
        return await session.scalar(
            select(Modelo190).where(
                Modelo190.empresa_id == 10,
                Modelo190.id == modelo.id,
            )
        )

    persistido = api.run(api.consultar(_consultar))
    assert persistido is not None
    assert persistido.hash_contenido == modelo.hash_contenido
