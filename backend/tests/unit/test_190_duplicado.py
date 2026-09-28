from __future__ import annotations

from decimal import Decimal

import pytest

from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from services.fiscal.modelo_190_gen import Modelo190Error, generar_modelo_190


async def _crear_liquidacion(session, api, empresa_id: int = 10):
    tercero_id = api.terceros[empresa_id]["con_nif"]
    liquidacion = LiquidacionRetenciones(
        empresa_id=empresa_id,
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
            empresa_id=empresa_id,
            liquidacion_retenciones_id=liquidacion.id,
            tercero_id=tercero_id,
            nif="12345678Z",
            nombre="Perceptor con NIF",
            tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
            base_imponible=Decimal("1000.0000"),
            tipo_porcentaje=Decimal("15.00"),
            retencion_practicada=Decimal("150.0000"),
            facturas=[],
        )
    )
    await session.flush()
    return await generar_modelo_190(
        session, empresa_id=empresa_id, ejercicio=2025
    )


def test_modelo_190_duplicado_es_409(retenciones_client):
    api = retenciones_client
    api.run(api.mutar(lambda session: _crear_liquidacion(session, api)))

    with pytest.raises(Modelo190Error) as error:
        api.run(
            api.consultar(
                lambda session: generar_modelo_190(
                    session, empresa_id=10, ejercicio=2025
                )
            )
        )

    assert error.value.status_code == 409
    assert error.value.code == "modelo_ya_generado"


def test_modelo_190_sin_retenciones_es_422(retenciones_client):
    api = retenciones_client

    with pytest.raises(Modelo190Error) as error:
        api.run(
            api.consultar(
                lambda session: generar_modelo_190(
                    session, empresa_id=10, ejercicio=2025
                )
            )
        )

    assert error.value.status_code == 422
    assert error.value.code == "sin_retenciones"
