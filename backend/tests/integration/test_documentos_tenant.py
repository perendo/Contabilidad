"""Aislamiento multi-empresa de documentos adjuntos (SPEC-030 S7, constitution III).

FR-013 y SC-003: el 0 % de los documentos de una empresa es visible,
descargable, adjuntable ni bajable desde otra, **incluso conocida la
referencia**. research D14: las cinco operaciones devuelven 404 con el mismo
texto que un recurso inexistente, de modo que un 403 no confirme la existencia
del recurso ni permita enumerar el diario del otro tenant.

Empresas A = 10 y B = 20, cada una con su asiento y sus documentos.
"""

from __future__ import annotations

import uuid

import pytest

from tests.unit import documento_support as soporte

BASE = "/api/v1/documentos"
EMPRESA_A = 10
EMPRESA_B = 20

#: Texto que devuelve un 404. research D14: no distingue "no existe" de "es de
#: otra empresa", y el del asiento es equivalente por el mismo motivo.
NO_EXISTE_DOCUMENTO = "El documento no existe o pertenece a otra empresa"
NO_EXISTE_ASIENTO = "El asiento no existe"


def _fichero(nombre: str, marcador: str) -> tuple:
    return (
        "files",
        (nombre, soporte.pdf_bytes(marcador=marcador), "application/pdf"),
    )


def _sembrar(cli, empresa: int) -> tuple[str, str]:
    """Un asiento DRAFT y un documento propio de la empresa."""
    asiento = cli.asiento(empresa_id=empresa, estado="DRAFT")
    respuesta = cli.subir(
        f"{BASE}/asiento/{asiento}",
        empresa_id=empresa,
        files=[_fichero(f"factura-{empresa}.pdf", f"doc{empresa}")],
        campos={"tipo_documento": "factura"},
    )
    assert respuesta.status_code == 201, respuesta.text
    documento = respuesta.json()["aceptados"][0]["id"]
    return asiento, documento


def test_404_listar_el_asiento_de_otra_empresa(documentos_client) -> None:
    cli = documentos_client
    asiento_b, _ = _sembrar(cli, EMPRESA_B)
    respuesta = cli.get(f"{BASE}/asiento/{asiento_b}", empresa_id=EMPRESA_A)
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["detail"] == NO_EXISTE_ASIENTO


def test_404_descargar_el_documento_de_otra_empresa(documentos_client) -> None:
    cli = documentos_client
    _, documento_b = _sembrar(cli, EMPRESA_B)
    respuesta = cli.get(f"{BASE}/{documento_b}/descarga", empresa_id=EMPRESA_A)
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["detail"] == NO_EXISTE_DOCUMENTO
    # Y no se sirve contenido ni cabecera de huella: el cuerpo es solo el
    # `detail` del error, nunca un binario.
    assert "X-Documento-SHA256" not in respuesta.headers
    assert "Content-Disposition" not in respuesta.headers
    assert respuesta.content == (
        '{"detail":{"code":"documento_no_encontrado","detail":'
        f'"{NO_EXISTE_DOCUMENTO}"}}}}'
    ).encode()


def test_el_listado_de_a_no_contiene_nada_de_b(documentos_client) -> None:
    cli = documentos_client
    _sembrar(cli, EMPRESA_B)
    _, documento_a = _sembrar(cli, EMPRESA_A)

    listado = cli.get(BASE, empresa_id=EMPRESA_A).json()
    assert listado["total"] == 1
    assert [i["id"] for i in listado["items"]] == [documento_a]
    # El filtro global, acotado a un tenant, tampoco se cruza.
    assert cli.get(BASE, empresa_id=EMPRESA_A, q="20").json()["total"] == 0


def test_404_los_metadatos_de_otra_empresa(documentos_client) -> None:
    cli = documentos_client
    _, documento_b = _sembrar(cli, EMPRESA_B)
    respuesta = cli.get(f"{BASE}/{documento_b}", empresa_id=EMPRESA_A)
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["detail"] == NO_EXISTE_DOCUMENTO


def test_404_adjuntar_al_asiento_de_otra_empresa(documentos_client) -> None:
    cli = documentos_client
    asiento_b, _ = _sembrar(cli, EMPRESA_B)
    respuesta = cli.subir(
        f"{BASE}/asiento/{asiento_b}",
        empresa_id=EMPRESA_A,
        files=[_fichero("intento.pdf", "intento")],
        campos={"tipo_documento": "factura"},
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["detail"] == NO_EXISTE_ASIENTO
    # Y el documento ajeno sigue siendo el unico de su tenant.
    assert cli.get(BASE, empresa_id=EMPRESA_B).json()["total"] == 1


def test_404_dar_de_baja_el_documento_de_otra_empresa(documentos_client) -> None:
    cli = documentos_client
    _, documento_b = _sembrar(cli, EMPRESA_B)
    respuesta = cli.delete(
        f"{BASE}/{documento_b}", {"motivo": "intento"}, empresa_id=EMPRESA_A
    )
    assert respuesta.status_code == 404
    # Sigue activo en su empresa: el intento ajeno no lo toco.
    assert cli.get(f"{BASE}/{documento_b}", empresa_id=EMPRESA_B).json()["estado"] == (
        "activo"
    )


def test_un_recurso_inexistente_da_el_mismo_texto(documentos_client) -> None:
    """research D14: el 404 cross-tenant es indistinguible del de inexistente."""
    cli = documentos_client
    _, documento_b = _sembrar(cli, EMPRESA_B)
    fantasma = str(uuid.uuid4())

    ajeno = cli.get(f"{BASE}/{documento_b}", empresa_id=EMPRESA_A)
    inexistente = cli.get(f"{BASE}/{fantasma}", empresa_id=EMPRESA_A)
    assert ajeno.status_code == inexistente.status_code == 404
    assert ajeno.json() == inexistente.json()


def test_cada_empresa_ve_solo_lo_suyo_en_el_listado(documentos_client) -> None:
    cli = documentos_client
    _sembrar(cli, EMPRESA_A)
    _sembrar(cli, EMPRESA_B)

    for empresa, esperado in ((EMPRESA_A, 1), (EMPRESA_B, 1)):
        listado = cli.get(BASE, empresa_id=empresa).json()
        assert listado["total"] == esperado
        for item in listado["items"]:
            assert item["nombre_original"] == f"factura-{empresa}.pdf"


def test_el_usuario_sin_acceso_a_la_empresa_no_puede_ver_sus_documentos(
    documentos_client,
) -> None:
    """constitucion III: la cabecera `X-Empresa-Activa` sin `UserCompany` activa
    es 403 en la capa de contexto, antes incluso de tocar los datos."""
    cli = documentos_client
    _, documento_b = _sembrar(cli, EMPRESA_B)
    # El usuario 3 (READ_ONLY) no tiene relacion con la empresa 99.
    respuesta = cli.get(f"{BASE}/{documento_b}", empresa_id=99)
    assert respuesta.status_code == 403


def test_sin_cabecera_de_empresa_no_hay_acceso(documentos_client) -> None:
    cli = documentos_client
    _, documento_b = _sembrar(cli, EMPRESA_B)
    respuesta = cli.client.get(f"{BASE}/{documento_b}")
    assert respuesta.status_code == 401


@pytest.mark.parametrize("empresa", [EMPRESA_A, EMPRESA_B])
def test_cada_empresa_puede_gestionar_su_propia_evidencia(
    documentos_client, empresa: int
) -> None:
    """Simetria: el aislamiento no es "la empresa A manda sobre la B", es que
    cada una solo manage lo suyo."""
    cli = documentos_client
    asiento, documento = _sembrar(cli, empresa)
    assert cli.get(f"{BASE}/{documento}", empresa_id=empresa).status_code == 200
    assert cli.get(f"{BASE}/{documento}/descarga", empresa_id=empresa).status_code == 200
    assert (
        cli.delete(f"{BASE}/{documento}", {"motivo": "fin"}, empresa_id=empresa).status_code
        == 204
    )
    assert cli.get(f"{BASE}/asiento/{asiento}", empresa_id=empresa).json()["total"] == 1
