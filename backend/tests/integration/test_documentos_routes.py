"""Los seis endpoints de documentos adjuntos (SPEC-030).

Cubre los escenarios S2 (varios de una vez), S3 (rechazos con motivo), S4
(integridad y duplicados), S5 (contenido incoherente), S6 (baja logica), S8
(cuadre intacto), S9 (trazabilidad) y S10 (permisos diferenciados).

Los ficheros de S7 (aislamiento) y S1 (opcionalidad) viven en
`test_documentos_tenant.py` y `test_documentos_opcional.py`: separarlos por
escenario, y no por endpoint, es lo que hace legible un fallo.
"""

from __future__ import annotations

import hashlib
from urllib.parse import unquote

import pytest
from sqlalchemy import select

from models.acct.documento import DocumentoAsiento
from models.audit.audit_log import AuditLog
from services.documentos.consulta import _saneado
from tests.unit import documento_support as soporte

BASE = "/api/v1/documentos"


def _fichero(nombre: str, datos: bytes, mime: str) -> tuple:
    """httpx exige, en una lista, la pareja `(campo, (nombre, bytes, mime))`.
    El campo es siempre `files` (contracts seccion 1)."""
    return ("files", (nombre, datos, mime))


def _adjuntar(cli, asiento: str, ficheros: list[tuple], **campos):
    """`token_key` y `empresa_id` controlan la sesion; el resto son campos del
    formulario. Sin separarlos, un `token_key` acabaria como campo de texto del
    multipart y la prueba creeria estar probando otro usuario."""
    token_key = campos.pop("token_key", "admin")
    empresa_id = campos.pop("empresa_id", 10)
    cuerpo = {"tipo_documento": campos.pop("tipo_documento", "factura")}
    cuerpo.update(campos)
    return cli.subir(
        f"{BASE}/asiento/{asiento}",
        empresa_id=empresa_id,
        token_key=token_key,
        files=ficheros,
        campos=cuerpo,
    )


# ------------------------------------------------------------------ S2


def test_s2_adjuntar_varios_documentos_de_una_vez(documentos_client) -> None:
    """S2/FR-001..FR-005: 3 aceptados, rechazo vacio y cuadre identico."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    antes = cli.cuadre(asiento, 10)

    respuesta = _adjuntar(
        cli,
        asiento,
        [
            _fichero("factura.pdf", soporte.pdf_bytes(3), "application/pdf"),
            _fichero("foto.jpg", soporte.jpeg_bytes(), "image/jpeg"),
            _fichero("escaneo.png", soporte.png_bytes(), "image/png"),
        ],
        descripcion="Factura del proveedor, pagina 1 de 3",
        importe_informativo="1210.0000",
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert len(cuerpo["aceptados"]) == 3
    assert cuerpo["rechazados"] == []

    for item in cuerpo["aceptados"]:
        assert item["nombre_original"]
        assert item["extension"] in ("pdf", "jpg", "png")
        assert item["content_type"] in (
            "application/pdf",
            "image/jpeg",
            "image/png",
        )
        assert item["size_bytes"] > 0
        assert len(item["sha256"]) == 64
        assert item["tipo_documento"] == "factura"
        assert item["estado"] == "activo"
        assert item["created_by"] == "1"
        assert item["created_at"].endswith("Z")
        assert len(item["asiento_id"]) == 36
    # El PDF trae paginas; las imagenes, `null` (data-model.md seccion 3).
    por_nombre = {i["nombre_original"]: i for i in cuerpo["aceptados"]}
    assert por_nombre["factura.pdf"]["num_paginas"] == 3
    assert por_nombre["foto.jpg"]["num_paginas"] is None
    # research D19: el importe viaja como string de 4 decimales.
    assert por_nombre["factura.pdf"]["importe_informativo"] == "1210.0000"

    # SC-007 / FR-015: constitution I intacta y estado contable sin cambios.
    assert cli.cuadre(asiento, 10) == antes
    assert antes["debe"] == antes["haber"] == "1210.0000"
    assert antes["estado"] == "DRAFT"


def test_s2_el_importe_informativo_no_altera_el_asiento(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    antes = cli.cuadre(asiento, 10)
    respuesta = _adjuntar(
        cli,
        asiento,
        [_fichero("f.pdf", soporte.pdf_bytes(), "application/pdf")],
        importe_informativo="999999.9999",
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["aceptados"][0]["importe_informativo"] == "999999.9999"
    assert cli.cuadre(asiento, 10) == antes


# ------------------------------------------------------------------ S3


def test_s3_rechazos_con_motivo_sin_dejar_nada_a_medias(documentos_client) -> None:
    """FR-018: el valido se conserva y los otros dos vuelven con su `code`."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")

    respuesta = _adjuntar(
        cli,
        asiento,
        [
            _fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf"),
            _fichero("captura.png.bak", soporte.png_bytes(), "application/octet-stream"),
            _fichero("escaneo.tif", soporte.BYTES_TIFF_12MB, "image/tiff"),
        ],
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert [i["nombre_original"] for i in cuerpo["aceptados"]] == ["factura.pdf"]
    rechazos = {r["nombre"]: r for r in cuerpo["rechazados"]}
    assert rechazos["captura.png.bak"]["code"] == "formato_no_admitido"
    assert rechazos["escaneo.tif"]["code"] == "documento_demasiado_grande"
    assert rechazos["escaneo.tif"]["detail"]
    # El listado muestra 1 documento, ni 2 ni 0.
    listado = cli.get(f"{BASE}/asiento/{asiento}").json()
    assert listado["total"] == 1
    assert len(documentos_client.documentos(asiento, 10)) == 1


def test_s3_201_aunque_no_se_acepte_ninguno(documentos_client) -> None:
    """contracts seccion 1: 201 siempre; el rechazo va en el cuerpo."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    respuesta = _adjuntar(
        cli,
        asiento,
        [_fichero("hoja.xlsx", b"PK\x03\x04" + b"0" * 40, "application/vnd.ms-excel")],
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["aceptados"] == []
    assert cuerpo["rechazados"][0]["code"] == "formato_no_admitido"
    assert cli.get(f"{BASE}/asiento/{asiento}").json()["total"] == 0


# ------------------------------------------------------------------ S4


def test_s4_la_huella_del_cuerpo_descargado_coincide(documentos_client) -> None:
    """SC-002/SC-004: el binario servido es byte a byte el del alta."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    original = soporte.pdf_bytes(2)
    creado = _adjuntar(
        cli,
        asiento,
        [_fichero("factura.pdf", original, "application/pdf")],
    ).json()["aceptados"][0]

    descarga = cli.get(f"{BASE}/{creado['id']}/descarga")
    assert descarga.status_code == 200
    assert descarga.headers["X-Documento-SHA256"] == creado["sha256"]
    assert descarga.headers["Cache-Control"] == "no-store"
    assert descarga.headers["Content-Type"] == "application/pdf"
    assert hashlib.sha256(descarga.content).hexdigest() == creado["sha256"]
    assert descarga.content == original


def test_s4_reenviar_el_mismo_fichero_es_duplicado(documentos_client) -> None:
    """FR-006: mismo contenido, mismo asiento -> 409 y **no** una segunda fila."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    datos = soporte.pdf_bytes()
    _adjuntar(cli, asiento, [_fichero("factura.pdf", datos, "application/pdf")])
    segunda = _adjuntar(cli, asiento, [_fichero("copia.pdf", datos, "application/pdf")])
    assert segunda.status_code == 201
    cuerpo = segunda.json()
    assert cuerpo["aceptados"] == []
    assert cuerpo["rechazados"][0]["code"] == "documento_duplicado"
    assert len(cli.documentos(asiento, 10)) == 1


def test_s4_el_mismo_fichero_sirve_en_otro_asiento(documentos_client) -> None:
    """FR-006: la duplicidad es por asiento, no global."""
    cli = documentos_client
    datos = soporte.pdf_bytes()
    for estado in ("DRAFT", "POSTED"):
        asiento = cli.asiento(empresa_id=10, estado=estado)
        respuesta = _adjuntar(
            cli, asiento, [_fichero("factura.pdf", datos, "application/pdf")]
        )
        assert respuesta.status_code == 201
        assert len(respuesta.json()["aceptados"]) == 1


def test_s4_no_existe_ninguna_ruta_para_sobrescribir(documentos_client) -> None:
    """S4 paso 4: no hay PUT ni PATCH; el trigger cierra la via directa."""
    cli = documentos_client
    for metodo in ("put", "patch"):
        respuesta = getattr(cli.client, metodo)(
            f"{BASE}/{DocumentoAsiento.__tablename__}",
            headers=cli.headers(),
        )
        assert respuesta.status_code in (404, 405)


# ------------------------------------------------------------------ S5


@pytest.mark.parametrize(
    ("nombre", "datos", "mime", "codigo"),
    [
        ("factura.pdf", "jpeg", "application/pdf", "documento_ilegible"),
        ("truncado.pdf", "truncado", "application/pdf", "documento_ilegible"),
        ("cifrado.pdf", "cifrado", "application/pdf", "documento_protegido"),
        ("largo.pdf", "largo", "application/pdf", "documento_paginas_excedidas"),
        ("vacio.pdf", "vacio", "application/pdf", "documento_vacio"),
    ],
)
def test_s5_contenido_incoherente_con_el_formato(
    documentos_client, nombre: str, datos: str, mime: str, codigo: str
) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    contenidos = {
        "jpeg": soporte.jpeg_bytes(),
        "truncado": soporte.pdf_truncado(),
        "cifrado": soporte.pdf_cifrado(),
        "largo": soporte.pdf_bytes(250),
        "vacio": b"",
    }
    respuesta = _adjuntar(cli, asiento, [_fichero(nombre, contenidos[datos], mime)])
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["aceptados"] == []
    assert cuerpo["rechazados"][0]["code"] == codigo
    # Ninguno se persiste.
    assert len(cli.documentos(asiento, 10)) == 0


# ------------------------------------------------------------------ S8


def test_s8_el_cuadre_no_cambia_al_adjuntar(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    antes = cli.cuadre(asiento, 10)
    _adjuntar(
        cli,
        asiento,
        [
            _fichero("a.pdf", soporte.pdf_bytes(), "application/pdf"),
            _fichero("b.png", soporte.png_bytes(), "image/png"),
            _fichero("c.tif", soporte.tiff_bytes(2), "image/tiff"),
        ],
    )
    despues = cli.cuadre(asiento, 10)
    assert despues == antes
    assert despues["debe"] == despues["haber"]


# ------------------------------------------------------------------ S9


def test_s9_cada_alta_queda_auditada(documentos_client) -> None:
    """FR-011: usuario, timestamp UTC, IP, operacion, documento y payload."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    _adjuntar(
        cli,
        asiento,
        [_fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf")],
    )

    async def _leer(session):
        return (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entidad == "documento_asiento",
                    AuditLog.operacion == "ADJUNTAR_DOCUMENTO",
                )
            )
        ).scalars().all()

    filas = cli.run(cli.consultar(_leer))
    assert len(filas) == 1
    traza = filas[0]
    assert traza.empresa_id == 10
    assert traza.usuario == "1"
    assert traza.ip is not None
    assert traza.timestamp is not None
    assert len(traza.entidad_id) == 36
    assert "sha256" in traza.payload
    assert "factura.pdf" in traza.payload
    assert "size_bytes" in traza.payload
    # La traza y la fila del documento viajan en la misma transaccion: este
    # test lee fuera del request, asi que prueba que el commit fue atomico.
    assert len(cli.documentos(asiento, 10)) == 1


# ----------------------------------------------------------------- S10


def test_s10_read_only_no_puede_adjuntar(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    respuesta = _adjuntar(
        cli,
        asiento,
        [_fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf")],
        token_key="readonly",
    )
    assert respuesta.status_code == 403
    assert len(cli.documentos(asiento, 10)) == 0


def test_s10_read_only_si_puede_listar(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    _adjuntar(
        cli, asiento, [_fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf")]
    )
    assert (
        cli.get(f"{BASE}/asiento/{asiento}", token_key="readonly").status_code == 200
    )


def test_s10_accountant_adjunta(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    respuesta = _adjuntar(
        cli,
        asiento,
        [_fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf")],
        token_key="accountant",
    )
    assert respuesta.status_code == 201


def test_s10_crear_y_baja_son_permisos_distintos(documentos_client) -> None:
    """FR-016: `acct:crear` y `acct:baja` no son intercambiables. El catalogo
    base concede `baja` a ACCOUNTANT, asi que la separacion se demuestra
    revocando `acct:baja` en la matriz de la empresa: si `crear` y `baja` fueran
    el mismo permiso, la revocacion afectaria a los dos."""
    cli = documentos_client

    def _revocar_baja():
        from models.rbac.matriz_permiso import MatrizPermiso
        from models.rbac.permiso_operacion import PermisoOperacion
        from models.rbac.rol import Rol

        async def _op(session):
            permiso = await session.scalar(
                select(PermisoOperacion).where(
                    PermisoOperacion.modulo == "acct",
                    PermisoOperacion.operacion == "baja",
                )
            )
            rol = await session.scalar(
                select(Rol).where(Rol.empresa_id == 10, Rol.nombre == "ACCOUNTANT")
            )
            concesion = await session.scalar(
                select(MatrizPermiso).where(
                    MatrizPermiso.empresa_id == 10,
                    MatrizPermiso.rol_id == rol.id,
                    MatrizPermiso.permiso_id == permiso.id,
                )
            )
            await session.delete(concesion)
            await session.flush()

        return _op

    cli.run(cli.mutar(_revocar_baja()))

    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    # Adjuntar sigue funcionando: `acct:crear` sigue concedido.
    creada = _adjuntar(
        cli,
        asiento,
        [_fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf")],
        token_key="accountant",
    )
    assert creada.status_code == 201
    documento_id = creada.json()["aceptados"][0]["id"]

    # Dar de baja ya no: `acct:baja` revocado.
    baja = cli.delete(
        f"{BASE}/{documento_id}", {"motivo": "prueba"}, token_key="accountant"
    )
    assert baja.status_code == 403


# ------------------------------------------------------ errores de peticion


def test_404_para_un_asiento_de_otra_empresa(documentos_client) -> None:
    """FR-013 + research D14: 404 con el texto de un recurso inexistente."""
    cli = documentos_client
    asiento_b = cli.asiento(empresa_id=20, estado="DRAFT")
    respuesta = _adjuntar(
        cli,
        asiento_b,
        [_fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf")],
        empresa_id=10,
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "asiento_no_encontrado"
    assert respuesta.json()["detail"]["detail"] == "El asiento no existe"
    assert len(cli.documentos(asiento_b, 20)) == 0


def test_422_para_un_tipo_documento_fuera_del_enum(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    respuesta = _adjuntar(
        cli,
        asiento,
        [_fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf")],
        tipo_documento="albaran",
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "tipo_documento_invalido"
    assert "factura" in respuesta.json()["detail"]["detail"]
    assert len(cli.documentos(asiento, 10)) == 0


def test_422_para_un_importe_informativo_mal_formado(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    respuesta = _adjuntar(
        cli,
        asiento,
        [_fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf")],
        importe_informativo="mil euros",
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "importe_informativo_invalido"


def test_422_para_una_descripcion_larga(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    respuesta = _adjuntar(
        cli,
        asiento,
        [_fichero("factura.pdf", soporte.pdf_bytes(), "application/pdf")],
        descripcion="d" * 501,
    )
    assert respuesta.status_code == 422
    assert len(cli.documentos(asiento, 10)) == 0


def test_el_nombre_hostil_se_sanea_antes_de_la_cabecera() -> None:
    """research D14/D18: comillas, `;` y saltos de linea se eliminan antes de
    interpolar el nombre en `Content-Disposition`, para que un nombre hostil no
    pueda inyectar cabeceras.

    Se prueba el saneado directamente porque el parser multipart de FastAPI
    (`python-multipart`) ya trata la cabecera `filename=` como cadena entre
    comillas y recorta el resto: por HTTP el nombre hostil ni siquiera llega. Un
    cliente que no respete el entrecomillado si lo enviaria, y ahi el saneado de
    la aplicacion es el que evita la inyeccion."""

    assert _saneado('fact"; rm -rf /.pdf') == "fact rm -rf /.pdf"
    assert _saneado("factura\r\nX-Inyectado: 1.pdf") == "facturaX-Inyectado: 1.pdf"
    assert _saneado('";\r\n') == "documento"
    assert len(_saneado("a" * 400)) == 255
    for caracter in ('"', ";", "\r", "\n"):
        assert caracter not in _saneado(f'fact{caracter}ura.pdf')


def test_la_cabecera_de_descarga_no_admite_inyeccion(documentos_client) -> None:
    """La cabecera real que sale por HTTP esta bien formada: ASCII puro y forma
    RFC 6266. Un nombre con acentos llega al navegador sin corromper (caso limite
    de la spec)."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    nombre = "Factura nº 42 - Société (2026).pdf"
    creado = _adjuntar(
        cli, asiento, [_fichero(nombre, soporte.pdf_bytes(), "application/pdf")]
    ).json()["aceptados"][0]
    disposicion = cli.get(f"{BASE}/{creado['id']}/descarga").headers[
        "Content-Disposition"
    ]
    assert disposicion.startswith("attachment; filename=")
    # Una cabecera HTTP solo admite ASCII: si se cuela un byte UTF-8, el cliente
    # estricto no puede ni leerla.
    disposicion.encode("ascii")
    assert "\r" not in disposicion and "\n" not in disposicion
    # RFC 6266: forma ASCII de reserva + forma UTF-8 percent-encoded.
    assert "; filename*=UTF-8''" in disposicion
    percent = disposicion.split("filename*=UTF-8''", 1)[1]
    assert unquote(percent) == nombre
    # Y el nombre original sigue intacto en la base de datos.
    assert creado["nombre_original"] == nombre


def test_el_nombre_original_se_conserva_tal_cual(documentos_client) -> None:
    """Caso limite de la spec: acentos, enes y espacios se guardan tal cual."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    nombre = "Factura nº 42 - Société Générale (enero 2026).pdf"
    creado = _adjuntar(
        cli, asiento, [_fichero(nombre, soporte.pdf_bytes(), "application/pdf")]
    ).json()["aceptados"][0]
    assert creado["nombre_original"] == nombre
    assert cli.get(f"{BASE}/{creado['id']}").json()["nombre_original"] == nombre


# ==================================================================
#  US2: consulta y descarga (S4, S11). El aislamiento de lectura vive en
#  test_documentos_tenant.py y la opcionalidad en test_documentos_opcional.py.
# ==================================================================


def _un_documento(
    cli,
    asiento: str,
    nombre: str = "factura.pdf",
    tipo: str = "factura",
    **sesion,
) -> dict:
    """Adjunta un PDF **unico** por llamada: `pdf_bytes` con marcador, porque dos
    PDFs identicos en el mismo asiento serian `documento_duplicado` (FR-006).
    `**sesion` admite `token_key` y `empresa_id`."""
    respuesta = _adjuntar(
        cli,
        asiento,
        [_fichero(nombre, soporte.pdf_bytes(marcador=nombre), "application/pdf")],
        tipo_documento=tipo,
        **sesion,
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["aceptados"][0]


def test_s11_listar_del_asiento_devuelve_total_y_opcionalidad(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    _un_documento(cli, asiento, "a.pdf")
    _un_documento(cli, asiento, "b.pdf", tipo="recibo")

    respuesta = cli.get(f"{BASE}/asiento/{asiento}")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 2
    assert len(cuerpo["items"]) == 2
    # research D11: la bandera viaja siempre en false.
    assert cuerpo["documentos_obligatorios"] is False
    # research D15: el orden es `created_at, id`. Los dos documentos se crean
    # en el mismo segundo, asi que desempata el UUID, que es estable: lo que
    # exige el spec es que **dos llamadas devuelvan el mismo orden**, no que
    # coincida con el orden de subida (ver `test_el_orden_del_listado_...`).
    orden = [i["id"] for i in cuerpo["items"]]
    repetido = [i["id"] for i in cli.get(f"{BASE}/asiento/{asiento}").json()["items"]]
    assert orden == repetido
    assert {i["nombre_original"] for i in cuerpo["items"]} == {"a.pdf", "b.pdf"}


def test_el_listado_del_asiento_ignora_las_bajas_si_se_pide(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    _un_documento(cli, asiento, "a.pdf")
    segundo = _un_documento(cli, asiento, "b.pdf")
    cli.delete(f"{BASE}/{segundo['id']}", {"motivo": "ilegible"})

    assert cli.get(f"{BASE}/asiento/{asiento}").json()["total"] == 2
    sin_bajas = cli.get(f"{BASE}/asiento/{asiento}", incluir_bajas=False).json()
    assert sin_bajas["total"] == 1
    assert sin_bajas["items"][0]["nombre_original"] == "a.pdf"


def test_los_metadatos_no_incluyen_el_contenido(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    creado = _un_documento(cli, asiento)
    respuesta = cli.get(f"{BASE}/{creado['id']}")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo == creado
    # El binario viaja solo por la descarga, no en los metadatos.
    assert "contenido" not in cuerpo


def test_el_listado_global_filtra_por_tipo(documentos_client) -> None:
    cli = documentos_client
    borrador = cli.asiento(empresa_id=10, estado="DRAFT")
    posted = cli.asiento(empresa_id=10, estado="POSTED")
    _un_documento(cli, borrador, "factura.pdf", tipo="factura")
    _un_documento(cli, borrador, "recibo.pdf", tipo="recibo")
    _un_documento(cli, posted, "extracto.pdf", tipo="extracto")

    todas = cli.get(BASE).json()
    assert todas["total"] == 3
    facturas = cli.get(BASE, tipo_documento="factura").json()
    assert facturas["total"] == 1
    assert facturas["items"][0]["nombre_original"] == "factura.pdf"
    # Cada item trae el encabezado del asiento (FR-019).
    asiento = facturas["items"][0]["journal_entry"]
    assert asiento["id"] == borrador
    assert asiento["ejercicio"] == 2026
    assert asiento["estado"] == "DRAFT"
    assert asiento["concepto"]


def test_el_listado_global_filtra_por_ejercicio_del_asiento(documentos_client) -> None:
    """El ejercicio es columna del ASIENTO: los documentos de un asiento de un
    ejercicio aparecen al filtrar por ese ejercicio, no por cuando se
    adjuntaron (contracts seccion 3)."""
    cli = documentos_client
    borrador = cli.asiento(empresa_id=10, estado="DRAFT")
    _un_documento(cli, borrador, "a.pdf")

    assert cli.get(BASE, ejercicio=2026).json()["total"] == 1
    assert cli.get(BASE, ejercicio=2025).json()["total"] == 0


def test_el_listado_global_busca_por_texto(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    _un_documento(cli, asiento, "Factura Proveedor XYZ.pdf")
    _un_documento(cli, asiento, "Extracto bancario.pdf")
    encontrados = cli.get(BASE, q="proveedor").json()
    assert encontrados["total"] == 1
    assert encontrados["items"][0]["nombre_original"] == "Factura Proveedor XYZ.pdf"
    assert cli.get(BASE, q="bancario").json()["total"] == 1
    assert cli.get(BASE, q="nada-de-esto").json()["total"] == 0


def test_el_orden_del_listado_global_es_estable(documentos_client) -> None:
    """research D15: dos peticiones seguidas devuelven el mismo orden."""
    cli = documentos_client
    borrador = cli.asiento(empresa_id=10, estado="DRAFT")
    posted = cli.asiento(empresa_id=10, estado="POSTED")
    for i in range(3):
        _un_documento(cli, borrador, f"d{i}.pdf")
    _un_documento(cli, posted, "otro.pdf")

    primero = [i["id"] for i in cli.get(BASE).json()["items"]]
    segundo = [i["id"] for i in cli.get(BASE).json()["items"]]
    assert primero == segundo
    assert len(primero) == 4


def test_el_listado_global_pagina(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    for i in range(5):
        _un_documento(cli, asiento, f"d{i}.pdf")

    pagina = cli.get(BASE, page=1, page_size=2).json()
    assert pagina["total"] == 5
    assert pagina["page"] == 1
    assert pagina["page_size"] == 2
    assert len(pagina["items"]) == 2
    assert len(cli.get(BASE, page=3, page_size=2).json()["items"]) == 1
    assert cli.get(BASE, page=4, page_size=2).json()["items"] == []


def test_el_listado_global_rechaza_un_page_size_fuera_de_rango(documentos_client) -> None:
    cli = documentos_client
    assert cli.get(BASE, page_size=0).status_code == 422
    assert cli.get(BASE, page_size=101).status_code == 422
    assert cli.get(BASE, page=0).status_code == 422
    assert cli.get(BASE, page_size=100).status_code == 200


def test_el_listado_global_rechaza_filtros_invalidos(documentos_client) -> None:
    cli = documentos_client
    assert cli.get(BASE, tipo_documento="albaran").status_code == 422
    assert cli.get(BASE, estado="inventado").status_code == 422
    assert cli.get(BASE, ejercicio=99).status_code == 422


def test_la_descarga_informa_del_tipo_y_el_tamano(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    respuesta = _adjuntar(
        cli, asiento, [_fichero("foto.png", soporte.png_bytes(), "image/png")]
    )
    creado = respuesta.json()["aceptados"][0]
    descarga = cli.get(f"{BASE}/{creado['id']}/descarga")
    assert descarga.status_code == 200
    # El MIME sale de la firma detectada, no del header del navegador.
    assert descarga.headers["Content-Type"] == "image/png"
    assert descarga.content == soporte.png_bytes()
    assert descarga.headers["X-Documento-SHA256"] == creado["sha256"]


def test_read_only_puede_descargar(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    creado = _un_documento(cli, asiento)
    descarga = cli.get(f"{BASE}/{creado['id']}/descarga", token_key="readonly")
    assert descarga.status_code == 200
    assert descarga.headers["Cache-Control"] == "no-store"


# ==================================================================
#  US3: baja logica, recuperacion y trazabilidad (S6, S9)
# ==================================================================


def test_s6_baja_logica_en_un_asiento_en_borrador(documentos_client) -> None:
    """FR-012: 204, estado `dado_de_baja` con motivo, responsable y fecha; el
    contenido y la huella siguen ahi."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    original = soporte.pdf_bytes(marcador="factura.pdf")
    creado = _adjuntar(
        cli,
        asiento,
        [_fichero("factura.pdf", original, "application/pdf")],
    ).json()["aceptados"][0]

    respuesta = cli.delete(f"{BASE}/{creado['id']}", {"motivo": "Escaneo ilegible"})
    assert respuesta.status_code == 204
    assert respuesta.content == b""

    detalle = cli.get(f"{BASE}/{creado['id']}").json()
    assert detalle["estado"] == "dado_de_baja"
    assert detalle["baja_motivo"] == "Escaneo ilegible"
    assert detalle["baja_usuario"] == "1"
    assert detalle["baja_at"].endswith("Z")
    # FR-012: contenido y huella intactos y recuperables.
    assert detalle["sha256"] == creado["sha256"]
    descarga = cli.get(f"{BASE}/{creado['id']}/descarga")
    assert descarga.status_code == 200
    assert descarga.headers["X-Documento-SHA256"] == creado["sha256"]
    assert descarga.content == original


def test_s6_la_baja_no_altera_el_cuadre_del_asiento(documentos_client) -> None:
    """FR-015 / SC-007: constitution I intacta tras dar de baja."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    antes = cli.cuadre(asiento, 10)
    creado = _un_documento(cli, asiento)
    assert cli.cuadre(asiento, 10) == antes

    cli.delete(f"{BASE}/{creado['id']}", {"motivo": "ilegible"})
    despues = cli.cuadre(asiento, 10)
    assert despues == antes
    assert despues["debe"] == despues["haber"]
    assert despues["estado"] == "DRAFT"


def test_s6_la_baja_es_idempotente_por_deteccion(documentos_client) -> None:
    """contracts seccion 6: el segundo DELETE da 404, no 409."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    creado = _un_documento(cli, asiento)
    assert cli.delete(f"{BASE}/{creado['id']}", {"motivo": "primera"}).status_code == 204
    segunda = cli.delete(f"{BASE}/{creado['id']}", {"motivo": "segunda"})
    assert segunda.status_code == 404
    assert segunda.json()["detail"]["code"] == "documento_no_encontrado"


def test_s6_sobre_un_asiento_contabilizado_la_baja_se_rechaza(documentos_client) -> None:
    """FR-010 / SC-011: la evidencia de un asiento asentado no se retira. La via
    correcta es anular o rectificar el asiento."""
    cli = documentos_client
    posted = cli.asiento(empresa_id=10, estado="POSTED")
    creado = _un_documento(cli, posted)

    respuesta = cli.delete(f"{BASE}/{creado['id']}", {"motivo": "retirar"})
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "baja_no_permitida"
    # Sigue activo y descargable: el rechazo no toco nada.
    assert cli.get(f"{BASE}/{creado['id']}").json()["estado"] == "activo"
    assert cli.get(f"{BASE}/{creado['id']}/descarga").status_code == 200


def test_s6_el_motivo_es_obligatorio(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    creado = _un_documento(cli, asiento)

    vacio = cli.delete(f"{BASE}/{creado['id']}", {"motivo": "   "})
    assert vacio.status_code == 422
    assert vacio.json()["detail"]["code"] == "baja_motivo_obligatorio"
    # Sigue activo: el rechazo no lo dio de baja.
    assert cli.get(f"{BASE}/{creado['id']}").json()["estado"] == "activo"


def test_s6_un_motivo_largo_lo_rechaza_el_modelo(documentos_client) -> None:
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    creado = _un_documento(cli, asiento)
    respuesta = cli.delete(f"{BASE}/{creado['id']}", {"motivo": "m" * 501})
    assert respuesta.status_code == 422


def test_s6_la_baja_de_un_documento_inexistente_da_404(documentos_client) -> None:
    import uuid

    cli = documentos_client
    respuesta = cli.delete(f"{BASE}/{uuid.uuid4()}", {"motivo": "nada"})
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "documento_no_encontrado"


def test_s6_el_documento_dado_de_baja_no_se_puede_readjuntar(documentos_client) -> None:
    """research D6: la unicidad de la huella sigue vigente tras la baja, porque
    la baja es logica y la huella sigue ocupando su sitio."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    creado = _un_documento(cli, asiento)
    cli.delete(f"{BASE}/{creado['id']}", {"motivo": "ilegible"})

    repetido = cli.subir(
        f"{BASE}/asiento/{asiento}",
        files=[
            (
                "files",
                (
                    creado["nombre_original"],
                    soporte.pdf_bytes(marcador=creado["nombre_original"]),
                    "application/pdf",
                ),
            )
        ],
        campos={"tipo_documento": "factura"},
    )
    assert repetido.status_code == 201
    assert repetido.json()["aceptados"] == []
    assert repetido.json()["rechazados"][0]["code"] == "documento_duplicado"


def test_s6_dar_de_baja_no_requiere_permiso_de_crear(documentos_client) -> None:
    """FR-016: `acct:baja` es el permiso de la baja; `acct:crear` el del alta.
    Un ADMIN puede dar de baja sin haber adjuntado nunca nada personally."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    creado = _un_documento(cli, asiento, token_key="accountant")
    # El ADMIN, que no lo adjunto, lo puede dar de baja.
    assert cli.delete(f"{BASE}/{creado['id']}", {"motivo": "revision"}).status_code == 204


def test_s9_la_baja_queda_auditada(documentos_client) -> None:
    """FR-011: una entrada por operacion, con usuario, timestamp UTC, IP,
    operacion, documento, asiento y payload."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    creado = _un_documento(cli, asiento)
    cli.delete(f"{BASE}/{creado['id']}", {"motivo": "Escaneo ilegible"})

    async def _leer(session):
        return (
            await session.execute(
                select(AuditLog).where(AuditLog.entidad == "documento_asiento")
            )
        ).scalars().all()

    filas = cli.run(cli.consultar(_leer))
    # `audit_log` no tiene columna de secuencia y su `id` es un UUID, de modo que
    # dos entradas del mismo segundo no tienen orden total. Se comprueba que
    # existen las dos operaciones, no que la alta venga antes que la baja.
    operaciones = sorted(f.operacion for f in filas)
    assert operaciones == ["ADJUNTAR_DOCUMENTO", "DAR_DE_BAJA_DOCUMENTO"]
    por_operacion = {f.operacion: f for f in filas}

    for operacion, traza in por_operacion.items():
        assert traza.empresa_id == 10, operacion
        assert traza.usuario == "1", operacion
        assert traza.ip is not None, operacion
        assert traza.timestamp is not None, operacion
        assert traza.entidad_id == creado["id"], operacion
        assert traza.payload, operacion
        assert "sha256" in traza.payload, operacion
        assert "factura.pdf" in traza.payload, operacion
        assert "size_bytes" in traza.payload, operacion
        assert asiento in traza.payload, operacion
    # El motivo es lo propio de la baja; el alta no lo lleva.
    assert "Escaneo ilegible" in por_operacion["DAR_DE_BAJA_DOCUMENTO"].payload
    assert "Escaneo ilegible" not in por_operacion["ADJUNTAR_DOCUMENTO"].payload
    # Las dos trazas apuntan al mismo documento y a la misma huella.
    assert (
        por_operacion["ADJUNTAR_DOCUMENTO"].entidad_id
        == por_operacion["DAR_DE_BAJA_DOCUMENTO"].entidad_id
    )


def test_s9_la_trazabilidad_sobrevive_a_la_baja(documentos_client) -> None:
    """FR-011: el rastro se conserva aunque el documento se de de baja. La baja
    es logica, asi que la entrada sigue ahi; y el `audit_log` es WORM."""
    cli = documentos_client
    asiento = cli.asiento(empresa_id=10, estado="DRAFT")
    creado = _un_documento(cli, asiento)
    cli.delete(f"{BASE}/{creado['id']}", {"motivo": "fin de prueba"})

    async def _intentar_borrar(session):
        from sqlalchemy import delete as borrar
        from sqlalchemy.exc import IntegrityError as IE

        try:
            await session.execute(
                borrar(AuditLog).where(
                    AuditLog.entidad == "documento_asiento",
                    AuditLog.operacion == "DAR_DE_BAJA_DOCUMENTO",
                )
            )
            await session.flush()
        except IE:
            await session.rollback()
            return "rechazado"
        return "permitido"

    assert cli.run(cli.consultar(_intentar_borrar)) == "rechazado"
