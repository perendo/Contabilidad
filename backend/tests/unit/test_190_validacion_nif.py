from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from models.ar.tercero import Tercero
from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from services.fiscal.modelo_190_gen import (
    Modelo190Error,
    generar_modelo_190,
    validar_nif_perceptores,
)


async def _crear_sin_nif(session, api, empresa_id: int, nif_tercero: str | None):
    tercero_id = api.terceros[empresa_id]["sin_nif"]
    await session.execute(
        select(Tercero).where(
            Tercero.empresa_id == empresa_id,
            Tercero.id == tercero_id,
        )
    )
    tercero = await session.get(Tercero, tercero_id)
    assert tercero is not None
    tercero.nif = nif_tercero
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
            nombre=tercero.nombre,
            tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
            base_imponible=Decimal("1000.0000"),
            tipo_porcentaje=Decimal("15.00"),
            retencion_practicada=Decimal("150.0000"),
            facturas=[],
        )
    )
    await session.flush()


@pytest.mark.parametrize("nif_tercero", [None, "12345678A"])
def test_validar_nif_usa_tercero_actual_y_es_serializable(
    retenciones_client, nif_tercero
):
    api = retenciones_client
    api.run(api.mutar(lambda session: _crear_sin_nif(session, api, 10, nif_tercero)))

    resultado = api.run(
        api.consultar(
            lambda session: validar_nif_perceptores(
                session, empresa_id=10, ejercicio=2025
            )
        )
    )

    assert resultado["valido"] is False
    assert resultado["perceptores_sin_nif"] == [
        {
            "tercero_id": str(api.terceros[10]["sin_nif"]),
            "nombre": "Perceptor sin NIF 10",
        }
    ]


def test_generar_190_rechaza_nif_vacio_o_invalido(retenciones_client):
    api = retenciones_client
    api.run(api.mutar(lambda session: _crear_sin_nif(session, api, 10, None)))

    with pytest.raises(Modelo190Error) as error:
        api.run(
            api.consultar(
                lambda session: generar_modelo_190(
                    session, empresa_id=10, ejercicio=2025
                )
            )
        )

    assert error.value.status_code == 422
    assert error.value.code == "perceptores_sin_nif"
    assert error.value.perceptores_sin_nif == [
        {
            "tercero_id": str(api.terceros[10]["sin_nif"]),
            "nombre": "Perceptor sin NIF 10",
        }
    ]
