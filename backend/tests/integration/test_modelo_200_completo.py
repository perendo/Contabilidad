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


def test_flujo_http_modelo_200_completo(is_client):
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
        tipo="BONIFICACION",
        importe="3000.0000",
    )
    contabilizar(api, calculo["id"])
    generado = api.post(
        "/api/v1/fiscal/is/modelo-200",
        empresa_id=10,
        json={"calculo_is_id": calculo["id"]},
    )
    assert generado.status_code == 201, generado.text
    modelo = generado.json()

    duplicado = api.post(
        "/api/v1/fiscal/is/modelo-200",
        empresa_id=10,
        json={"calculo_is_id": calculo["id"]},
    )
    assert duplicado.status_code == 409
    assert duplicado.json()["detail"]["code"] == "modelo_ya_generado"

    listado = api.get(10, "/api/v1/fiscal/is/modelo-200", ejercicio=2025)
    assert listado.status_code == 200
    assert listado.json()["total"] == 1
    assert listado.json()["items"][0]["id"] == modelo["id"]

    descarga = api.get(
        10, f"/api/v1/fiscal/is/modelo-200/{modelo['id']}"
    )
    assert descarga.status_code == 200
    assert descarga.headers["content-type"].startswith("text/csv")
    assert descarga.headers["content-disposition"] == (
        f'attachment; filename="modelo-200-{modelo["id"]}.csv"'
    )
    assert descarga.text.startswith("bloque;campo;valor\n")

    async def _query(session):
        return await session.scalar(
            select(Modelo200).where(
                Modelo200.empresa_id == 10,
                Modelo200.id == uuid.UUID(modelo["id"]),
            )
        )

    persisted = api.run(api.consultar(_query))
    assert persisted is not None
    assert len(persisted.contenido) == 5
    assert persisted.contenido["base_imponible_y_cuota"]["bonificaciones"] == "3000.0000"
    canonico = json_canonico(persisted.contenido)
    assert json.loads(canonico) == persisted.contenido
    assert hashlib.sha256(canonico.encode("utf-8")).hexdigest() == persisted.hash_contenido
