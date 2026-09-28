from tests.unit.is_support import agregar_ajuste, crear_calculo


def test_calculo_is_aislado_por_empresa(is_client):
    api = is_client
    calculo = crear_calculo(api)
    ajuste = agregar_ajuste(
        api,
        calculo["id"],
        tipo="DEDUCCION",
        importe="100.0000",
    )
    path = f"/api/v1/fiscal/is/calculos/{calculo['id']}"

    detalle = api.get(20, path)
    assert detalle.status_code == 404
    assert detalle.json()["detail"]["code"] == "calculo_no_encontrado"

    listado = api.get(20, "/api/v1/fiscal/is/calculos", ejercicio=2025)
    assert listado.status_code == 200
    assert listado.json()["total"] == 0

    nuevo_ajuste = api.post(
        f"{path}/ajustes",
        empresa_id=20,
        json={
            "tipo": "AJUSTE_POSITIVO",
            "descripcion": "No visible",
            "importe": "10.0000",
        },
    )
    assert nuevo_ajuste.status_code == 404

    recalculo = api.post(
        f"{path}/recalcular",
        empresa_id=20,
        json={"ajustes": [], "deducciones": []},
    )
    assert recalculo.status_code == 404

    borrado = api.delete(
        f"{path}/ajustes/{ajuste['id']}", empresa_id=20
    )
    assert borrado.status_code == 404

    visible = api.get(10, f"{path}/ajustes")
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()] == [ajuste["id"]]
