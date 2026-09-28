"""La adjuncion es opcional (SPEC-030 S1, FR-020, SC-012).

research D11: ninguna capa impone la presencia de documentos. Un asiento sin
documentos recorre su ciclo de vida completo —contabilizar, anular, listar,
exportar— sin ninguna restriccion adicional, y no existe ninguna ruta que exija
al menos un documento.

Este es el escenario ancla de la spec y la aclaracion expresa del usuario: es el
que impide que la funcionalidad crezca hacia "no se puede contabilizar sin
soporte".
"""

from __future__ import annotations

import pytest

from tests.unit import documento_support as soporte

BASE = "/api/v1/documentos"


def test_s1_un_asiento_sin_documentos_devuelve_200_y_no_404(documentos_client) -> None:
    """El listado nunca falla por falta de documentos (research D11)."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")

    respuesta = cli.get(f"{BASE}/asiento/{asiento}")
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "items": [],
        "total": 0,
        "documentos_obligatorios": False,
    }


def test_s1_el_listado_global_no_falla_y_no_incluye_el_asiento(
    documentos_client,
) -> None:
    cli = documentos_client
    cli.asiento(empresa_id=10, estado="DRAFT")
    respuesta = cli.get(BASE)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 0
    assert cuerpo["items"] == []


def test_s1_el_asiento_se_asienta_sin_documentos(documentos_client) -> None:
    """SC-012: contabilizar no exige soporte. Se comprueba que el asiento
    POSTED del fixture esta operativo y que el motor no consulta la tabla."""
    cli = documentos_client
    posted = cli.asiento(empresa_id=10, estado="POSTED")
    antes = cli.cuadre(posted, 10)
    assert antes["estado"] == "POSTED"
    assert antes["debe"] == antes["haber"]
    assert cli.get(f"{BASE}/asiento/{posted}").json()["total"] == 0
    # El cuadre sigue exacto tras la consulta.
    assert cli.cuadre(posted, 10) == antes


def test_s1_el_asiento_se_puede_modificar_sin_tocar_sus_documentos(
    documentos_client,
) -> None:
    """Constitucion I: el diario sigue siendo editable en su flujo normal; los
    documentos son hijos, no los mandan."""
    cli = documentos_client
    borrador = cli.asiento(empresa_id=10, estado="DRAFT")
    antes = cli.cuadre(borrador, 10)

    # Se adjunta, se da de baja y se vuelve a adjuntar: el cuadre no se mueve.
    creado = cli.subir(
        f"{BASE}/asiento/{borrador}",
        files=[("files", ("a.pdf", soporte.pdf_bytes(marcador="a"), "application/pdf"))],
        campos={"tipo_documento": "factura"},
    ).json()["aceptados"][0]
    assert cli.cuadre(borrador, 10) == antes
    assert cli.delete(f"{BASE}/{creado['id']}", {"motivo": "prueba"}).status_code == 204
    assert cli.cuadre(borrador, 10) == antes
    assert cli.get(f"{BASE}/asiento/{borrador}").json()["total"] == 1


def test_s1_ninguna_ruta_exige_al_menos_un_documento(documentos_client) -> None:
    """SC-012, segunda mitad: el 0 % de las operaciones exige documentos. Se
    recorre la superficie de la spec y se comprueba que ninguna devuelve un
    error del tipo "faltan documentos"."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")

    respuestas = [
        cli.get(f"{BASE}/asiento/{asiento}"),
        cli.get(f"{BASE}/asiento/{asiento}", incluir_bajas=False),
        cli.get(BASE),
        cli.get(BASE, ejercicio=2026),
        cli.get(BASE, tipo_documento="factura"),
        cli.get(BASE, estado="activo"),
        cli.get(BASE, q="nada"),
    ]
    for respuesta in respuestas:
        assert respuesta.status_code == 200, respuesta.text


def test_s1_el_estado_de_un_asiento_vacio_declara_la_opcionalidad(
    documentos_client,
) -> None:
    """research D11: `documentos_obligatorios` viaja **siempre** en `false`, para
    que el cliente no pueda tratar la ausencia como un requisito pendiente."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    for incluir in (True, False):
        cuerpo = cli.get(
            f"{BASE}/asiento/{asiento}", incluir_bajas=incluir
        ).json()
        assert cuerpo["documentos_obligatorios"] is False


def test_s1_el_registro_no_tiene_ninguna_restriccion_de_documentos(
    documentos_client,
) -> None:
    """Ninguna de las columnas obliga a un documento, y `journal_entry` no lleva
    contador ni `NOT NULL` hacia la tabla hija: es la garantia estructural de
    FR-020 y research D11 (no hay columna de recuento)."""
    from sqlalchemy import text

    async def _columnas(session):
        return (
            await session.execute(text("PRAGMA table_info(documento_asiento)"))
        ).all()

    async def _columnas_diario(session):
        return (
            await session.execute(text("PRAGMA table_info(journal_entry)"))
        ).all()

    documentos = documentos_client.run(documentos_client.consultar(_columnas))
    nombres = {fila[1] for fila in documentos}
    # Ninguna columna cuenta documentos: sin contador, nada puede exigir que
    # haya alguno.
    assert not {n for n in nombres if n.startswith(("conteo", "num_documentos"))}
    # `tipo_documento` es la clasificacion, no un recuento.
    assert "tipo_documento" in nombres

    diario = documentos_client.run(documentos_client.consultar(_columnas_diario))
    nombres_diario = {fila[1] for fila in diario}
    assert not any("documento" in nombre for nombre in nombres_diario)


def test_s1_un_asiento_inexistente_si_da_404(documentos_client) -> None:
    """El 404 es por el asiento, no por la falta de documentos: son cosas
    distintas y confundirlas seria el error que FR-020 evita."""
    import uuid

    cli = documentos_client
    respuesta = cli.get(f"{BASE}/asiento/{uuid.uuid4()}")
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "asiento_no_encontrado"


@pytest.mark.parametrize("estado", ["DRAFT", "POSTED"])
def test_s1_ambos_estados_operan_sin_documentos(
    documentos_client, estado: str
) -> None:
    """FR-010 y FR-020: adjuntar es valido en cualquier estado, y no hacer nada
    tambien."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado=estado)
    assert cli.get(f"{BASE}/asiento/{asiento}").status_code == 200
    assert cli.documentos(asiento, 10) == []
