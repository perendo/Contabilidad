"""Ficheros de prueba para SPEC-030 (documentos adjuntos al asiento).

Genera bytes reales y validos de cada formato admitido, mas los casos limite de
`quickstart.md` S5 (extension enganosa, PDF truncado, PDF protegido, PDF de 250
paginas, fichero de 0 bytes, TIFF multipagina).

Es un modulo de soporte, no un test: los tests lo importan. No se importa un
modulo de test desde otro test, que rompe la recoleccion de pytest en modo
`prepend`.
"""

from __future__ import annotations

import io

#: Valor arbitrario pero > 10 MB: dispara `documento_demasiado_grande` sin que
#: el fichero ocupe 12 MB de verdad en cada prueba. Es un TIFF de 12 MB nominales
#: porque la validacion de tamano va ANTES de la de contenido (data-model.md
#: seccion 5), luego no hace falta que sea una imagen valida.
BYTES_TIFF_12MB = b"II*\x00" + b"\x00" * (12 * 1024 * 1024)


def pdf_bytes(paginas: int = 1, marcador: str | None = None) -> bytes:
    """PDF valido de `paginas` paginas en blanco (pypdf, ya dependencia runtime).

    `marcador` se graba en los metadatos del PDF para que dos ficheros con el
    mismo numero de paginas sigan teniendo **bytes distintos**: sin el, dos
    llamadas devuelven el mismo contenido y el segundo alta cae en
    `documento_duplicado` (FR-006), que es lo que tiene que pasar.
    """
    from pypdf import PdfWriter

    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=200, height=200)
    if marcador is not None:
        escritor.add_metadata({"/Producer": marcador, "/Title": marcador})
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def pdf_cifrado(password: str = "secreto") -> bytes:
    """PDF protegido con contrasena (research D16 -> `documento_protegido`)."""
    from pypdf import PdfWriter

    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    escritor.encrypt(password)
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def pdf_truncado() -> bytes:
    """PDF con cabecera `%PDF-` valida pero cuerpo cortado a la mitad."""
    return pdf_bytes(2)[: len(pdf_bytes(2)) // 2]


def _imagen(formato: str) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), "white").save(buffer, format=formato)
    return buffer.getvalue()


def jpeg_bytes() -> bytes:
    return _imagen("JPEG")


def png_bytes() -> bytes:
    return _imagen("PNG")


def tiff_bytes(paginas: int = 1) -> bytes:
    """TIFF de `paginas` fotogramas. Un TIFF multipagina es **un** documento
    (supuestos de la spec), no `paginas` documentos."""
    from PIL import Image

    buffer = io.BytesIO()
    base = Image.new("RGB", (12, 12), "white")
    if paginas <= 1:
        base.save(buffer, format="TIFF")
    else:
        base.save(
            buffer,
            format="TIFF",
            save_all=True,
            append_images=[Image.new("RGB", (12, 12), "black") for _ in range(paginas - 1)],
        )
    return buffer.getvalue()


def imagen_truncada() -> bytes:
    """PNG con firma y cabecera IEND validas pero bloques de datos truncados."""
    datos = png_bytes()
    return datos[: len(datos) // 2]


#: Catalogo de formatos admitidos por FR-002. Los tests de camino feliz
#: recorren este diccionario, de modo que anadir un formato obliga a decidir si
#: entra en la spec o no.
FORMATOS_ACTIVOS: dict[str, bytes] = {
    "pdf": pdf_bytes(),
    "jpg": jpeg_bytes(),
    "png": png_bytes(),
    "tif": tiff_bytes(2),
}

#: MIME que el servicio debe derivar de la firma (no del header del navegador).
CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "png": "image/png",
    "tif": "image/tiff",
}
