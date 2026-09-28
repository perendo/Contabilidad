from __future__ import annotations

from decimal import Decimal

import pytest

from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from services.fiscal.modelo_190_gen import (
    Modelo190Error,
    descargar_modelo_190,
    generar_modelo_190,
    listar_modelos_190,
    validar_nif_perceptores,
)


async def _crear_modelo_a(session, api):
    tercero_id = api.terceros[10]["con_nif"]
    liquidacion = LiquidacionRetenciones(
        empresa_id=10,
        ejercicio=2025,
        trimestre=1,
        periodo="2025-Q1",
        total_base_retenciones=Decimal("1000.0000"),
        total_retenciones=Decimal("150.0000"),
        n_perceptores=1,
    )
    session.add(liquidacion)
    await session.flush()
    session.add(
        RetencionPeriodo(
            empresa_id=10,
            liquidacion_retenciones_id=liquidacion.id,
            tercero_id=tercero_id,
            nif="",
            nombre="Perceptor A",
            tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
            base_imponible=Decimal("1000.0000"),
            tipo_porcentaje=Decimal("15.00"),
            retencion_practicada=Decimal("150.0000"),
            facturas=[],
        )
    )
    await session.flush()
    return await generar_modelo_190(session, empresa_id=10, ejercicio=2025)


def test_modelo_190_no_cruza_empresa(retenciones_client):
    api = retenciones_client
    modelo = api.run(api.mutar(lambda session: _crear_modelo_a(session, api)))

    async def _listar_b(session):
        return await listar_modelos_190(
            session, empresa_id=20, ejercicio=2025
        )

    listados, total = api.run(api.consultar(_listar_b))
    assert listados == []
    assert total == 0

    with pytest.raises(Modelo190Error) as error:
        api.run(
            api.consultar(
                lambda session: descargar_modelo_190(
                    session, empresa_id=20, modelo_190_id=modelo.id
                )
            )
        )

    assert error.value.status_code == 404
    assert error.value.code == "modelo_no_encontrado"

    validacion = api.run(
        api.consultar(
            lambda session: validar_nif_perceptores(
                session, empresa_id=20, ejercicio=2025
            )
        )
    )
    assert validacion == {"valido": True, "perceptores_sin_nif": []}
