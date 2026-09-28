from sqlalchemy import select

from models.acct.journal import JournalEntry
from tests.unit.is_support import contabilizar, crear_calculo


def test_contabilizacion_is_no_visible_para_otra_empresa(is_client):
    api = is_client
    calculo = crear_calculo(api)
    asiento_id = contabilizar(api, calculo["id"])["asiento_id"]
    path = f"/api/v1/fiscal/is/calculos/{calculo['id']}"

    assert api.get(20, path).status_code == 404
    segundo_intento = api.post(
        f"{path}/contabilizar",
        empresa_id=20,
        json={"fecha_asiento": "2025-12-31"},
    )
    assert segundo_intento.status_code == 404
    assert segundo_intento.json()["detail"]["code"] == "calculo_no_encontrado"

    async def _query(session):
        return list(
            (
                await session.scalars(
                    select(JournalEntry).where(
                        JournalEntry.empresa_id == 20,
                        JournalEntry.concepto == "Impuesto sobre sociedades 2025",
                    )
                )
            ).all()
        )

    assert api.run(api.consultar(_query)) == []
    assert api.get(20, "/api/v1/fiscal/is/calculos", ejercicio=2025).json()["total"] == 0
    assert api.get(
        10, f"/api/v1/fiscal/is/calculos/{calculo['id']}"
    ).json()["asiento_id"] == asiento_id
