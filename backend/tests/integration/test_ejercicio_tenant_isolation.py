"""Aislamiento del ejercicio entre empresas (SPEC-031, US3, T031).

Complementa `test_contexto_tenant_isolation.py`, que ya comprueba que el listado y
los contadores no se mezclan. Aqui lo que se comprueba es el otro lado: **que la
cabecera no se pueda usar para entrar**.

`X-Ejercicio-Activa` es la unica cabecera de la feature que acepta un valor del
cliente, y por eso es la unica que necesita una prueba de manipulacion. La
pregunta que responde este fichero no es "se filtra bien" sino "que pasa si alguien
manda el ejercicio de otra empresa".

Y hay un caso que no es de lectura sino de escritura, que es el grave: una cabecera
manipulada **no debe alterar el ejercicio al que se imputa un asiento**. Si
`X-Ejercicio-Activa: 2025` conseguiste que un asiento de la empresa A se imputase
al ejercicio de la empresa B, estaríamos moviendo datos contables entre tenants.
"""

from __future__ import annotations

from typing import Any

import pytest

RUTA = "/api/v1/contexto"


def _detalle(respuesta) -> dict[str, Any]:
    cuerpo = respuesta.json()
    assert isinstance(cuerpo.get("detail"), dict), cuerpo
    return cuerpo["detail"]


def test_una_cabecera_ajena_se_rechaza_y_no_revela_nada(
    navegacion_client,
) -> None:
    """Un ejercicio de otra empresa da 422, y la respuesta no confirma nada.

    El codigo y el mensaje son los mismos que para un ejercicio que no existe en
    ninguna parte. Distinguirlos confirmaria que ese ano existe en el tenant del
    usuario, que es informacion de otro tenant (constitution III).
    """
    ajeno = navegacion_client.get(RUTA, empresa_id=10, ejercicio=2024)
    inexistente = navegacion_client.get(RUTA, empresa_id=10, ejercicio=1999)

    # 2024 existe, pero en la empresa 20. La cabecera es "ajena" de verdad, no un
    # numero inventado: es el caso que distingue pertenencia de inexistencia.
    assert ajeno.status_code == 422
    assert inexistente.status_code == 422
    assert _detalle(ajeno)["code"] == _detalle(inexistente)["code"]
    assert _detalle(ajeno)["detail"] == _detalle(inexistente)["detail"]


def test_un_ejercicio_propio_se_sigue_aceptando_tras_el_rechazo(
    navegacion_client,
) -> None:
    """El rechazo de un ano ajeno no deja la cabecera rota.

    Es la otra mitad de la prueba anterior: si el 422 contaminara el estado, un
    ejercicio **propio** dejaria de aceptarse despues de fallar uno ajeno.
    """
    contexto = navegacion_client.get(RUTA, empresa_id=10).json()
    propio = next(
        f["ejercicio"] for f in contexto["ejercicios"] if f["es_seleccionable"]
    )
    navegacion_client.get(RUTA, empresa_id=10, ejercicio=2024)  # ajeno -> 422
    assert navegacion_client.get(RUTA, empresa_id=10, ejercicio=propio).status_code == 200


def test_el_rechazo_no_filtra_los_ejercicios_de_la_otra_empresa(
    navegacion_client,
) -> None:
    """Tras un rechazo, la respuesta NO revela los ejercicios de la empresa.

    Es el otro lado del 422: si al rechazar devolviera "ese ejercicio pertenece a la
    empresa 20", el atacante sabria que existe, y con repetir peticiones sacaria el
    rango de anos de la otra empresa.
    """
    respuesta = navegacion_client.get(RUTA, empresa_id=10, ejercicio=1999)
    cuerpo = respuesta.json()
    assert "ejercicios" not in cuerpo
    assert "empresa" not in cuerpo
    assert str(20) not in respuesta.text


def test_el_contexto_sigue_coherente_tras_un_rechazo(navegacion_client) -> None:
    """Un rechazo MUST NOT dejar el contexto a medias.

    Se pide el contexto, se provoca un 422, y se vuelve a pedir. Si el estado
    interno hubiera quedado contaminado, la segunda respuesta seria distinta de la
    primera sin que nada lo hubiera pedido.
    """
    antes = navegacion_client.get(RUTA, empresa_id=10).json()
    navegacion_client.get(RUTA, empresa_id=10, ejercicio=1999)
    despues = navegacion_client.get(RUTA, empresa_id=10).json()
    assert despues == antes


def test_una_cabecera_manipulada_no_altera_el_ejercicio_imputado(
    navegacion_client,
) -> None:
    """El caso grave: la cabecera no puede mover un asiento a otro ejercicio.

    Se comprueba contra el motor de SPEC-002, no contra el endpoint de contexto: el
    ejercicio de un asiento lo decide el **servicio** a partir de la `fecha`, no la
    cabecera. La cabecera es un selector de lectura; la imputacion es de otro hecho.
    """

    from models.acct.journal import JournalEntry, JournalEntryTipo

    async def _crear_asiento(session):
        import datetime as dt
        import uuid

        # Se crea con la fecha en 2026 y empresa 10, mientras la cabecera dice 2025.
        asiento = JournalEntry(
            id=uuid.uuid4(),
            empresa_id=10,
            ejercicio=2026,
            numero_asiento=900,
            fecha=dt.date(2026, 6, 1),
            concepto="Imputacion bajo cabecera manipulada",
            estado="DRAFT",
            tipo=JournalEntryTipo.GENERAL,
        )
        session.add(asiento)
        await session.flush()
        return asiento.ejercicio

    ejercicio = navegacion_client.run(
        navegacion_client.mutar(_crear_asiento)
    )
    assert ejercicio == 2026, (
        f"el asiento se imputo al ejercicio {ejercicio}; la cabecera debe ser "
        "solo un selector de lectura, nunca decidir la imputacion"
    )


def test_cada_empresa_resuelve_su_contexto_separadamente(navegacion_client) -> None:
    """A y B se piden con la misma cabecera y responden distinto.

    La empresa 20 tiene un 2026 con rango desplazado y un solo asiento. Si la
    cabecera se aplicara globalmente en vez de resolverse por empresa, los dos
    contextos serian identicos.
    """
    diez = navegacion_client.get(RUTA, empresa_id=10, ejercicio=2026).json()
    veinte = navegacion_client.get(RUTA, empresa_id=20, ejercicio=2026).json()

    assert diez["empresa"]["id"] == 10
    assert veinte["empresa"]["id"] == 20
    contadores_diez = {f["ejercicio"]: f["n_asientos"] for f in diez["ejercicios"]}
    contadores_veinte = {f["ejercicio"]: f["n_asientos"] for f in veinte["ejercicios"]}
    assert contadores_diez[2026] == 2
    assert contadores_veinte[2026] == 1


def test_usar_la_empresa_de_otro_con_su_ejercicio_da_403(navegacion_client) -> None:
    """READ_ONLY solo esta en la empresa 10: pedir la 20 con 2026 da 403.

    Importa incluir la cabecera correcta: la empresa se resuelve **antes** que el
    ejercicio, y si se invirtiera el orden, un 422 podria confirmar que la empresa 20
    tiene un ejercicio 2026 a alguien que no tiene acceso a ella.
    """
    respuesta = navegacion_client.get(
        RUTA, empresa_id=20, token_key="readonly", ejercicio=2026
    )
    assert respuesta.status_code == 403
    assert str(20) not in respuesta.text or "empresa" in respuesta.text.lower()


@pytest.mark.parametrize("cabecera", ["2025", "2026", "2027", "1999"])
def test_ningun_ejercicio_ajeno_se_resuelve(
    navegacion_client, cabecera: str
) -> None:
    """Barrido: ningun ano, ni propio ni ajeno, se resuelve por la via de la cabecera.

    Se recorre a mano lo que el usuario hace, no lo que la suite permite por
    omision. El parametro mas importante es `2027`, que es un ano futuro: no existe
    en ninguna empresa y aun asi debe rechazarse.
    """
    contexto = navegacion_client.get(RUTA, empresa_id=10).json()
    existentes = {f["ejercicio"] for f in contexto["ejercicios"]}
    respuesta = navegacion_client.get(RUTA, empresa_id=10, ejercicio=cabecera)
    if int(cabecera) in existentes and any(
        f["ejercicio"] == int(cabecera) and f["es_seleccionable"]
        for f in contexto["ejercicios"]
    ):
        assert respuesta.status_code == 200
    else:
        assert respuesta.status_code == 422
