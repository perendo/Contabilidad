import uuid
from decimal import Decimal

import pytest

from models.fiscal.ajuste_extracontable import (
    AjusteExtracontable,
    TipoAjusteExtracontable,
)
from models.fiscal.calculo_is import CalculoIS, EstadoCalculoIS


@pytest.mark.parametrize(
    ("campo", "base", "cuota"),
    [
        ("base_imponible", Decimal("111000.0000"), Decimal("28000.0000")),
        ("cuota_integra", Decimal("112000.0000"), Decimal("27000.0000")),
    ],
)
def test_modelo_200_rechaza_inconsistencias(is_client, campo, base, cuota):
    api = is_client
    calculo_id = str(uuid.uuid4())

    async def _preparar(session):
        calculo = CalculoIS(
            id=uuid.UUID(calculo_id),
            empresa_id=10,
            ejercicio=2025,
            resultado_contable=Decimal("100000.0000"),
            ajustes_positivos=Decimal("12000.0000"),
            ajustes_negativos=Decimal("0.0000"),
            base_imponible=base,
            tipo_impositivo=Decimal("25.00"),
            cuota_integra=cuota,
            deducciones=Decimal("8000.0000"),
            cuota_liquida=Decimal("20000.0000"),
            pagos_a_cuenta=Decimal("20000.0000"),
            cuota_diferencial=Decimal("0.0000"),
            provisional=False,
            estado=EstadoCalculoIS.calculado,
        )
        session.add(calculo)
        await session.flush()
        session.add(
            AjusteExtracontable(
                id=uuid.uuid4(),
                empresa_id=10,
                calculo_is_id=calculo.id,
                tipo=TipoAjusteExtracontable.AJUSTE_POSITIVO,
                descripcion="Ajuste directo",
                importe=Decimal("12000.0000"),
            )
        )
        session.add(
            AjusteExtracontable(
                id=uuid.uuid4(),
                empresa_id=10,
                calculo_is_id=calculo.id,
                tipo=TipoAjusteExtracontable.DEDUCCION,
                descripcion="Deduccion directa",
                importe=Decimal("8000.0000"),
            )
        )
        await session.flush()
        calculo.estado = EstadoCalculoIS.contabilizado
        await session.flush()

    api.run(api.mutar(_preparar))
    response = api.post(
        "/api/v1/fiscal/is/modelo-200",
        json={"calculo_is_id": calculo_id},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "inconsistencia_modelo_200"
    assert campo in response.json()["detail"]["detail"]
