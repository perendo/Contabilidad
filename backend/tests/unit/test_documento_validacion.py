"""Validacion de ficheros adjuntos (SPEC-030, research D8/D16/D18/D19).

Cubre el escenario S5 de `quickstart.md` completo: la extension enganosa, el PDF
truncado, el PDF protegido con contrasena, el PDF de 250 paginas, el fichero de
0 bytes, el nombre de 300 caracteres y el TIFF multipagina; mas el camino feliz
de los cuatro formatos.

No necesita sesion ni `TestClient` (research D20): la validacion es logica de
dominio y se comprueba aqui directamente.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.documentos.errores import DocumentoError
from services.documentos.validacion import (
    detectar_formato,
    validar_contenido,
    validar_fichero,
    validar_importe_informativo,
    validar_nombre,
    validar_tamano,
    validar_texto,
    validar_tipo_documento,
)
from tests.unit import documento_support as soporte

# ---------------------------------------------------------------- S5


def test_extension_enganosa_jpeg_renombrado_a_pdf() -> None:
    """FR-014: un JPEG llamado `factura.pdf` NO es evidencia de nada."""
    jpeg = soporte.jpeg_bytes()
    assert jpeg.startswith(b"\xff\xd8\xff")
    with pytest.raises(DocumentoError) as exc:
        validar_fichero("factura.pdf", jpeg, "pdf")
    assert exc.value.code == "documento_ilegible"
    assert exc.value.status_code == 422
    assert "JPG" in exc.value.message


def test_pdf_truncado_se_rechaza() -> None:
    with pytest.raises(DocumentoError) as exc:
        validar_fichero("truncado.pdf", soporte.pdf_truncado(), "pdf")
    assert exc.value.code == "documento_ilegible"


def test_pdf_protegido_con_contrasena_se_rechaza() -> None:
    """research D16: el usuario no puede abrirlo, luego no aporta evidencia."""
    with pytest.raises(DocumentoError) as exc:
        validar_fichero("cifrado.pdf", soporte.pdf_cifrado(), "pdf")
    assert exc.value.code == "documento_protegido"


def test_pdf_de_250_paginas_supera_el_limite() -> None:
    """research D16 + SC-008: 200 paginas es el techo operativo."""
    with pytest.raises(DocumentoError) as exc:
        validar_fichero("largo.pdf", soporte.pdf_bytes(250), "pdf")
    assert exc.value.code == "documento_paginas_excedidas"


def test_fichero_de_cero_bytes() -> None:
    with pytest.raises(DocumentoError) as exc:
        validar_tamano(0)
    assert exc.value.code == "documento_vacio"
    with pytest.raises(DocumentoError) as exc2:
        validar_fichero("vacio.pdf", b"", "pdf")
    assert exc2.value.code == "documento_vacio"


def test_nombre_de_300_caracteres() -> None:
    """research D18: 255 es el tope; con acentos tambien se mide en bytes."""
    with pytest.raises(DocumentoError) as exc:
        validar_nombre("a" * 300)
    assert exc.value.code == "documento_nombre_largo"
    with pytest.raises(DocumentoError) as exc2:
        validar_nombre("á" * 200)
    assert exc2.value.code == "documento_nombre_largo"


def test_tiff_multipagina_es_un_solo_documento() -> None:
    """Supuestos de la spec: una imagen multipagina es un unico documento."""
    datos = soporte.tiff_bytes(3)
    extension, content_type = detectar_formato(datos)
    assert extension == "tif"
    assert content_type == "image/tiff"
    assert validar_contenido(datos, "tif") == 1
    metadatos = validar_fichero("escaneo.tif", datos, "tif")
    # `num_paginas` es NULL en imagenes (data-model.md seccion 3).
    assert metadatos["num_paginas"] is None


def test_extension_no_admitida() -> None:
    """FR-002: cualquier otro formato se rechaza con mensaje explicito."""
    with pytest.raises(DocumentoError) as exc:
        validar_fichero("captura.png.bak", b"\x89PNG\r\n\x1a\n" + b"0" * 40, "bak")
    assert exc.value.code == "formato_no_admitido"
    assert "PDF" in exc.value.message and "TIFF" in exc.value.message
    with pytest.raises(DocumentoError) as exc2:
        validar_fichero("hoja.xlsx", b"PK\x03\x04" + b"0" * 40, "xlsx")
    assert exc2.value.code == "formato_no_admitido"


# ------------------------------------------------- camino feliz por formato


@pytest.mark.parametrize("extension", ["pdf", "jpg", "png", "tif"])
def test_camino_feliz_de_los_cuatro_formatos(extension: str) -> None:
    datos = soporte.FORMATOS_ACTIVOS[extension]
    metadatos = validar_fichero(f"documento.{extension}", datos, extension)
    assert metadatos["extension"] == extension
    assert metadatos["content_type"] == soporte.CONTENT_TYPES[extension]
    if extension == "pdf":
        assert metadatos["num_paginas"] == 1
    else:
        assert metadatos["num_paginas"] is None


def test_el_alias_de_extension_se_normaliza() -> None:
    """.jpeg y .tiff son los mismos formatos que .jpg y .tif: el filtro por
    formato no puede tener dos nombres para lo mismo."""
    assert validar_fichero("a.jpeg", soporte.jpeg_bytes(), "jpeg")["extension"] == "jpg"
    assert validar_fichero("a.tiff", soporte.tiff_bytes(), "tiff")["extension"] == "tif"


def test_sin_extension_declarada_se_deduce_de_la_firma() -> None:
    metadatos = validar_fichero("documento", soporte.png_bytes(), None)
    assert metadatos["extension"] == "png"


def test_el_content_type_se_detecta_y_no_se_confia_en_el_header() -> None:
    """El MIME lo decide la firma, no la extension ni lo que declara el
    navegador (data-model.md seccion 3). Con nombre sin extension, el formato se
    deduce de la firma y el MIME sale de ahi."""
    metadatos = validar_fichero("documento", soporte.jpeg_bytes(), None)
    assert metadatos["extension"] == "jpg"
    assert metadatos["content_type"] == "image/jpeg"


# ------------------------------------------------------ otros limites


def test_tamano_sobre_el_limite() -> None:
    """FR-003: 10 MB por documento. El TIFF de 12 MB del soporte lo dispara."""
    with pytest.raises(DocumentoError) as exc:
        validar_fichero("escaneo.tif", soporte.BYTES_TIFF_12MB, "tif")
    assert exc.value.code == "documento_demasiado_grande"
    assert "10 MB" in exc.value.message


def test_nombre_con_acentos_y_espacios_se_conserva() -> None:
    """Caso limite de la spec: el nombre se conserva tal cual lo subio el usuario."""
    original = "Factura nº 42 - Société Générale (enero 2026).pdf"
    assert validar_nombre(original) == original


def test_el_nombre_no_trae_ruta() -> None:
    """Un `UploadFile` puede traer una ruta; al nombre guardado le sobra."""
    assert validar_nombre("C:\\Users\\conta\\docs\\factura.pdf") == "factura.pdf"
    assert validar_nombre("/tmp/x/factura.pdf") == "factura.pdf"


def test_descripcion_larga() -> None:
    with pytest.raises(DocumentoError) as exc:
        validar_texto("d" * 501, "descripcion", 500)
    assert exc.value.code == "descripcion_largo"
    assert validar_texto("d" * 500, "descripcion", 500) is not None


def test_motivo_largo() -> None:
    with pytest.raises(DocumentoError) as exc:
        validar_texto("m" * 501, "motivo", 500)
    assert exc.value.code == "motivo_largo"


def test_tipo_documento_fuera_del_enum() -> None:
    """research D17: lista cerrada; un valor desconocido es 422, no un 500."""
    with pytest.raises(DocumentoError) as exc:
        validar_tipo_documento("albaran")
    assert exc.value.code == "tipo_documento_invalido"
    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "valor",
    ["factura", "recibo", "extracto", "justificante", "contrato", "otro"],
)
def test_todos_los_tipos_validos(valor: str) -> None:
    assert validar_tipo_documento(valor).value == valor
    assert validar_tipo_documento(valor.upper()).value == valor


def test_importe_informativo_con_decimal() -> None:
    """research D19: `Decimal`, nunca `float`, y 4 decimales."""
    assert validar_importe_informativo("1210") == Decimal(1210)
    assert validar_importe_informativo("1210.0000") == Decimal("1210.0000")
    assert validar_importe_informativo(" 12,5 ".replace(",", ".")) == Decimal("12.5")
    assert validar_importe_informativo("") is None
    assert validar_importe_informativo(None) is None


def test_importe_informativo_invalido() -> None:
    with pytest.raises(DocumentoError) as exc:
        validar_importe_informativo("mil euros")
    assert exc.value.code == "importe_informativo_invalido"
    with pytest.raises(DocumentoError) as exc2:
        validar_importe_informativo("-1.0000")
    assert exc2.value.code == "importe_informativo_invalido"
    with pytest.raises(DocumentoError) as exc3:
        validar_importe_informativo("1.000001")
    assert exc3.value.code == "importe_informativo_invalido"
    with pytest.raises(DocumentoError) as exc4:
        validar_importe_informativo("NaN")
    assert exc4.value.code == "importe_informativo_invalido"


def test_el_importe_never_usa_float() -> None:
    """constitucion: prohibido `float` para importes. El retorno es `Decimal`."""
    importe = validar_importe_informativo("1210.55")
    assert isinstance(importe, Decimal)
    assert not isinstance(importe, float)
