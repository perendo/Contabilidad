import uuid

from sqlalchemy import select

from models.acct.journal import JournalEntry
from models.fiscal.calculo_is import CalculoIS
from models.fiscal.modelo_200 import Modelo200
from tests.unit.is_support import contabilizar, crear_calculo


def test_aislamiento_completo_calculo_asiento_y_modelo(is_client):
    api = is_client
    calculo = crear_calculo(api)
    contabilizado = contabilizar(api, calculo["id"])
    modelo = api.post(
        "/api/v1/fiscal/is/modelo-200",
        empresa_id=10,
        json={"calculo_is_id": calculo["id"]},
    )
    assert modelo.status_code == 201

    path = f"/api/v1/fiscal/is/calculos/{calculo['id']}"
    assert api.get(20, path).status_code == 404
    assert api.post(
        f"{path}/contabilizar",
        empresa_id=20,
        json={"fecha_asiento": "2025-12-31"},
    ).status_code == 404
    assert api.post(
        "/api/v1/fiscal/is/modelo-200",
        empresa_id=20,
        json={"calculo_is_id": calculo["id"]},
    ).status_code == 404
    assert api.get(
        20, f"/api/v1/fiscal/is/modelo-200/{modelo.json()['id']}"
    ).status_code == 404

    async def _counts(session):
        return {
            "calculos": len(
                (
                    await session.scalars(
                        select(CalculoIS).where(CalculoIS.empresa_id == 20)
                    )
                ).all()
            ),
            "modelos": len(
                (
                    await session.scalars(
                        select(Modelo200).where(Modelo200.empresa_id == 20)
                    )
                ).all()
            ),
            "asientos": len(
                (
                    await session.scalars(
                        select(JournalEntry).where(
                            JournalEntry.empresa_id == 20,
                            JournalEntry.id == uuid.UUID(contabilizado["asiento_id"]),
                        )
                    )
                ).all()
            ),
        }

    assert api.run(api.consultar(_counts)) == {
        "calculos": 0,
        "modelos": 0,
        "asientos": 0,
    }
