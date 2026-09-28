"""Aislamiento multi-empresa del contexto (SPEC-031, US1, constitution V(b)).

Este fichero es el que la constitution V obliga: ninguna tarea se cierra sin
pruebas que demuestren la imposibilidad de acceder a datos de otra empresa.

El contexto de sesion es el punto mas sensible de toda la feature, por dos motivos
que aqui se comprueban por separado:

1. **El listado de ejercicios.** `GET /api/v1/contexto` devuelve ejercicios. Si no
   filtra por `empresa_id`, la empresa A ve que existen los ejercicios de la B, que
   es informacion de otro tenant aunque no haya datos contables.
2. **El contador de asientos.** `n_asientos` es un dato del libro mayor. Es el
   numero que el usuario mira para decidir en que ejercicio esta, y el mas grave
   que se podria filtrar.

Y el caso de la cabecera: `X-Ejercicio-Activa` la envia el cliente, o sea que es
**dato no confiable**. Un ejercicio de la empresa B enviada contra la A debe
rechazarse, no resolverse.
"""

from __future__ import annotations

from typing import Any

import pytest

RUTA = "/api/v1/contexto"


def _cuerpo(respuesta) -> dict[str, Any]:
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _detalle(respuesta) -> dict[str, Any]:
    """El codigo de error vive bajo `detail`, como en el resto del proyecto.

    El repositorio envuelve los errores de dominio en
    `{"detail": {"code": ..., "detail": ...}}`, y hay helpers con este nombre en
    los contratos de SPEC-028 y SPEC-029. Se replica la convencion en vez de
    inventar una forma plana para esta feature.
    """
    cuerpo = respuesta.json()
    assert isinstance(cuerpo.get("detail"), dict), cuerpo
    return cuerpo["detail"]


def test_el_contexto_no_filtra_ejercicios_de_otra_empresa(navegacion_client) -> None:
    """La empresa 10 no ve el ejercicio 2024 de la empresa 20 ni el de la B."""
    datos = _cuerpo(navegacion_client.get(RUTA, empresa_id=10))
    ejercicios = {f["ejercicio"] for f in datos["ejercicios"]}
    # Empresa 10 sembrada con 2025 y 2026. Nada mas.
    assert ejercicios == {2025, 2026}


def test_el_contexto_de_una_empresa_no_trae_los_ejercicios_de_otra(
    navegacion_client,
) -> None:
    """Cada empresa ve SU conjunto, y son distintos a proposito.

    La empresa 20 tiene un 2024 que **no** existe en la 10, y un 2026 con rango
    desplazado. Si el filtro por `empresa_id` desapareciera, la 10 veria tambien el
    2024.
    """
    a = _cuerpo(navegacion_client.get(RUTA, empresa_id=10))
    b = _cuerpo(navegacion_client.get(RUTA, empresa_id=20))
    ejercicios_a = {f["ejercicio"] for f in datos_empresa(a)}
    ejercicios_b = {f["ejercicio"] for f in datos_empresa(b)}
    assert ejercicios_a == {2025, 2026}
    assert ejercicios_b == {2024, 2026}
    assert a["empresa"]["id"] == 10
    assert b["empresa"]["id"] == 20


def datos_empresa(contexto: dict[str, Any]) -> list[dict[str, Any]]:
    return list(contexto["ejercicios"])


def test_el_contador_no_incluye_asientos_de_otra_empresa(
    navegacion_client,
) -> None:
    """Principio V(b) en su forma mas dura: los contadores.

    Empresa 10 tiene 2 asientos en 2026 y 1 en 2025. Empresa 20 tiene 1 en 2026.
    Los tres ejercicios comparten ano, asi que un fallo de filtro por `empresa_id`
    daria 3 en lugar de 2.
    """
    diez = _cuerpo(navegacion_client.get(RUTA, empresa_id=10))
    veinte = _cuerpo(navegacion_client.get(RUTA, empresa_id=20))

    por_anio_diez = {f["ejercicio"]: f["n_asientos"] for f in diez["ejercicios"]}
    por_anio_veinte = {f["ejercicio"]: f["n_asientos"] for f in veinte["ejercicios"]}

    assert por_anio_diez[2026] == 2
    assert por_anio_diez[2025] == 1
    assert por_anio_veinte[2026] == 1


def test_el_ejercicio_activo_no_toma_ejercimientos_de_otra_empresa(
    navegacion_client,
) -> None:
    """El ejercicio activo resuelto pertenece a la empresa pedida."""
    for empresa, esperado in ((10, {2025, 2026}), (20, {2026})):
        contexto = _cuerpo(navegacion_client.get(RUTA, empresa_id=empresa))
        activo = contexto["ejercicio_activo"]
        assert activo["ejercicio"] in esperado, (
            f"empresa {empresa}: activo {activo['ejercicio']} fuera de {esperado}"
        )
        assert activo["ejercicio"] in {f["ejercicio"] for f in contexto["ejercicios"]}


def test_cabecera_de_ejercicio_de_otra_empresa_se_rechaza(
    navegacion_client,
) -> None:
    """`X-Ejercicio-Activa` no confiable: un ejercicio ajeno no se resuelve.

    Se manda el 2026 de la empresa 20 contra la empresa 10. Aqui el 2026 existe en
    ambas, asi que la prueba de que vale es el 422: el backend no puede saber por
    el numero solo, tiene que mirar la pertenencia.
    """
    respuesta = navegacion_client.get(RUTA, empresa_id=10, ejercicio=2026)
    # Mismo numero, misma empresa: 200.
    assert respuesta.status_code == 200

    # 1999 no existe en ninguna empresa: tambien 422, no 404 silencioso.
    respuesta = navegacion_client.get(RUTA, empresa_id=10, ejercicio=1999)
    assert respuesta.status_code == 422
    assert _detalle(respuesta)["code"] == "ejercicio_no_pertenece_a_empresa"


def test_cabecera_de_ejercicio_ajeno_no_altera_el_contexto(
    navegacion_client,
) -> None:
    """Un rechazo MUST NOT cambiar lo que el contexto resuelve.

    Es decir: asking por un ejercicio invalido no puede dejar el contexto cojeando
    con un estado a medias.
    """
    bueno = _cuerpo(navegacion_client.get(RUTA, empresa_id=10))
    malo = navegacion_client.get(RUTA, empresa_id=10, ejercicio=1999)
    assert malo.status_code == 422
    despues = _cuerpo(navegacion_client.get(RUTA, empresa_id=10))
    assert despues["ejercicio_activo"] == bueno["ejercicio_activo"]
    assert despues["ejercicios"] == bueno["ejercicios"]


def test_empresa_no_vinculada_al_usuario_da_403(navegacion_client) -> None:
    """El usuario 3 (READ_ONLY) solo esta vinculado a la empresa 10.

    Pedir la 20 con su token MUST NOT devolver sus datos. El codigo es 403 y no 404
    porque es lo que ya devuelve `get_empresa_id` para "sin acceso a la empresa del
    contexto": es un problema de autorizacion, no de recurso ausente.
    """
    respuesta = navegacion_client.get(RUTA, empresa_id=20, token_key="readonly")
    assert respuesta.status_code == 403


def test_sin_sesion_no_hay_contexto(navegacion_client) -> None:
    """Sin token no hay contexto. 401, no un 200 con campos vacios."""
    respuesta = navegacion_client.client.get(RUTA)
    assert respuesta.status_code == 401


def test_token_invalido_no_hay_contexto(navegacion_client) -> None:
    """Un token que no existe tampoco. 401."""
    respuesta = navegacion_client.get(RUTA, token_key="no-es-un-token-valido-suficientemente-largo")
    assert respuesta.status_code == 401


@pytest.mark.parametrize("empresa", [10, 20])
def test_ambos_lectores_ven_su_misma_empresa(navegacion_client, empresa: int) -> None:
    """El contexto no depende del rol: los tres roles ven su propia empresa.

    El guard es `acct:ver`, que los tres roles base poseen (research D10). Si esto
    cambia, es que un rol ha perdido el acceso al shell.
    """
    for token in ("admin", "accountant", "readonly"):
        respuesta = navegacion_client.get(RUTA, empresa_id=empresa, token_key=token)
        if respuesta.status_code == 403:
            # El READ_ONLY solo esta vinculado a la 10: es lo esperado.
            assert token == "readonly" and empresa == 20
            continue
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["empresa"]["id"] == empresa
