import hashlib
import json
import uuid

from sqlalchemy import select

from models.fiscal.modelo_200 import Modelo200
from services.fiscal.modelo_200_gen import json_canonico
from tests.unit.is_support import (
    agregar_ajuste,
    contabilizar,
    crear_calculo,
)


def test_modelo_200_tiene_cinco_bloques_y_hash_consistente(is_client):
    api = is_client
    calculo = crear_calculo(api)
    agregar_ajuste(
        api,
        calculo["id"],
        tipo="AJUSTE_POSITIVO",
        importe="12000.0000",
    )
    agregar_ajuste(
        api,
        calculo["id"],
        tipo="DEDUCCION",
        importe="8000.0000",
    )
    contabilizar(api, calculo["id"])
    response = api.post(
        "/api/v1/fiscal/is/modelo-200",
        json={"calculo_is_id": calculo["id"]},
    )

    assert response.status_code == 201, response.text
    generated = response.json()
    assert len(generated["hash_contenido"]) == 64

    async def _query(session):
        return await session.scalar(
            select(Modelo200).where(
                Modelo200.empresa_id == 10,
                Modelo200.id == uuid.UUID(generated["id"]),
            )
        )

    modelo = api.run(api.consultar(_query))
    assert modelo is not None
    assert len(modelo.contenido) == 5
    assert set(modelo.contenido) == {
        "datos_declarante",
        "resultado_contable",
        "base_imponible_y_cuota",
        "pagos_a_cuenta_y_cuota_diferencial",
        "datos_liquidacion",
    }
    canonico = json_canonico(modelo.contenido)
    assert hashlib.sha256(canonico.encode("utf-8")).hexdigest() == modelo.hash_contenido
    assert json.loads(canonico) == modelo.contenido
    assert modelo.contenido["pagos_a_cuenta_y_cuota_diferencial"]["resultado"] == "cero"
