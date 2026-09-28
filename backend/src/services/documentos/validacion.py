"""Validacion de ficheros adjuntos al asiento (SPEC-030, research D8/D16/D18/D19).

Logica de dominio pura: recibe ``bytes`` y no necesita sesion ni ``TestClient``
(research D20), de modo que es comprobable en tests unitarios y reutilizable si
entra una importacion masiva (SPEC-005).

Tres capas, porque ninguna basta sola (research D8):

1. **Firma inicial** (magic bytes): ``%PDF-``, ``\\xFF\\xD8\\xFF`` (JPEG),
   ``\\x89PNG\\r\\n\\x1a\\n`` (PNG), ``II*\\x00`` y ``MM\\x00*`` (TIFF).
   Implementacion propia: son cuatro comparaciones de bytes y una dependencia
   mas no aporta nada (research D8).
2. **PDF**: ``pypdf.PdfReader`` para rechazar cifrados y corruptos y contar
   paginas. Sin esta capa, "PDF truncado" y "PDF con contrasena" —dos casos
   limite explicitos de la spec— no tendrian comportamiento definido (D16).
3. **Imagen**: ``PIL.Image`` con ``.verify()`` y ``n_frames`` (un TIFF
   multipagina es **un** documento, no varios).

La extension que declara el cliente **no** decide nada: se valida que la
firma real corresponda a la extension declarada (FR-014, caso limite de
quickstart S5: un JPEG renombrado a ``.pdf``).
"""

from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation

from config import settings
from models.acct.documento import (
    BAJA_MOTIVO_MAX,
    DESCRIPCION_MAX,
    NOMBRE_MAX,
    TipoDocumento,
)
from services.documentos.errores import DocumentoError, error

#: Firmas)->(extension canonica, MIME). La extension canonica es la que se
#: guarda: `jpeg` y `jpg`, `tif` y `tiff` se normalizan a una sola forma para
#: que el filtro por formato no tenga dos nombres para el mismo formato.
FIRMAS: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF-", "pdf", "application/pdf"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"II*\x00", "tif", "image/tiff"),
    (b"MM\x00*", "tif", "image/tiff"),
)

#: Formatos que admite el producto, para el mensaje de error de FR-002.
MENSAJE_FORMATOS = "Solo se admiten PDF, JPEG, PNG y TIFF"

#: Alias de extension->canonica que el cliente puede usar.
ALIAS: dict[str, str] = {
    "pdf": "pdf",
    "jpg": "jpg",
    "jpeg": "jpg",
    "png": "png",
    "tif": "tif",
    "tiff": "tif",
}


def extension_declarada(nombre: str) -> str:
    """Extension en minusculas y sin punto, tal y como llega del `UploadFile`."""
    if "." not in nombre:
        return ""
    return nombre.rsplit(".", 1)[1].strip().lower()


def detectar_formato(contenido: bytes) -> tuple[str, str]:
    """Devuelve ``(extension, content_type)`` segun la **firma** del contenido.

    La `content_type` guardada es la detectada aqui, nunca la que declara el
    navegador en la cabecera: es la que se usa en la descarga y la que el
    visor del frontend decide mostrar como ``<iframe>`` o como ``<img>``.

    Lanza `formato_no_admitido` (422) si ninguna firma coincide, y
    `documento_ilegible` (422) si el contenido esta vacio.
    """
    if not contenido:
        raise error("documento_vacio", "El fichero esta vacio")
    for firma, extension, content_type in FIRMAS:
        if contenido.startswith(firma):
            return extension, content_type
    raise error("formato_no_admitido", MENSAJE_FORMATOS)


def validar_tamano(size_bytes: int) -> None:
    """FR-003: 10 MB por documento. Un fichero de 0 bytes es `documento_vacio`."""
    if size_bytes <= 0:
        raise error("documento_vacio", "El fichero esta vacio")
    if size_bytes > settings.documento_max_bytes:
        limite_mb = settings.documento_max_bytes // (1024 * 1024)
        raise error(
            "documento_demasiado_grande",
            f"El documento supera el tamano maximo de {limite_mb} MB",
        )


def validar_nombre(nombre: str) -> str:
    """research D18: nombre no vacio, <= 255 caracteres y <= 255 bytes.

    Con acentos, 255 caracteres pueden exceder el limite de bytes de la
    columna, de ahi la segunda comprobacion. Se devuelve el nombre ya limpio
    (sin barras ni rutas), tal y como se guardara y se entregara en la descarga.

    Se eliminan tambien las comillas dobles y los caracteres de control: `"` no
    es un caracter valido de nombre de fichero en Windows ni macOS y es
    precisamente el que permitiria inyectar cabeceras en la descarga
    (research D14/D18). No es solo defensa propia: un cliente que codifica el
    nombre con RFC 2231 deja una `"` colgante al deserializarlo, y sin este
    recorte el nombre almacenado —y por tanto el que ve el usuario— llevaria
    un caracter fantasma que el usuario nunca escribio.
    """
    limpio = nombre.replace("\\", "/").rsplit("/", 1)[-1]
    limpio = "".join(
        c for c in limpio if c != '"' and (c.isprintable() or c == " ")
    ).strip()
    if not limpio:
        raise error("documento_nombre_largo", "El nombre del fichero esta vacio")
    if len(limpio) > NOMBRE_MAX:
        raise error(
            "documento_nombre_largo",
            f"El nombre supera los {NOMBRE_MAX} caracteres",
        )
    if len(limpio.encode("utf-8")) > NOMBRE_MAX:
        raise error(
            "documento_nombre_largo",
            f"El nombre supera los {NOMBRE_MAX} bytes",
        )
    return limpio


def validar_texto(valor: str | None, campo: str, maximo: int) -> str | None:
    """Texto libre de longitud acotada (research D18). Vacio se normaliza a None."""
    if valor is None:
        return None
    limpio = valor.strip()
    if not limpio:
        return None
    if len(limpio) > maximo:
        raise error(f"{campo}_largo", f"El campo {campo} supera los {maximo} caracteres")
    return limpio


def validar_tipo_documento(valor: str) -> TipoDocumento:
    """research D17: lista cerrada. Un valor desconocido es 422, no un 500."""
    try:
        return TipoDocumento(valor.strip().lower())
    except ValueError as exc:
        admitidos = ", ".join(m.value for m in TipoDocumento)
        raise error(
            "tipo_documento_invalido",
            f"El tipo '{valor}' no es valido. Valores admitidos: {admitidos}",
        ) from exc


def validar_importe_informativo(valor: str | None) -> Decimal | None:
    """research D19: ``Decimal`` con 4 decimales, nunca ``float``.

    El importe es solo referencia visual (un escaneo que el usuario concilia a
    mano). Si no cuadra con el asiento es un dato erroneo del usuario, no un
    descuadre: por eso no se contrasta con las cifras del asiento y por eso un
    valor incoherente se acepta y se muestra tal cual.
    """
    if valor is None:
        return None
    texto = valor.strip().replace(" ", "").replace("\u00a0", "")
    if not texto:
        return None
    try:
        importe = Decimal(texto)
    except InvalidOperation as exc:
        raise error(
            "importe_informativo_invalido",
            "El importe informativo no es un numero valido",
        ) from exc
    if not importe.is_finite():
        raise error(
            "importe_informativo_invalido",
            "El importe informativo no es un numero valido",
        )
    if importe < 0:
        raise error(
            "importe_informativo_invalido",
            "El importe informativo no puede ser negativo",
        )
    if "." in texto and len(texto.split(".")[-1]) > 4:
        raise error(
            "importe_informativo_invalido",
            "El importe informativo admite como mucho 4 decimales",
        )
    return importe


def _validar_pdf(contenido: bytes) -> int:
    """research D16: rechaza cifrado y corrupcion, y cuenta paginas (D8)."""
    from pypdf import PdfReader
    from pypdf.errors import DependencyError, EmptyFileError, PdfReadError

    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted:
            raise error(
                "documento_protegido",
                "El PDF esta protegido con contrasena y no se puede abrir",
            )
        paginas = len(lector.pages)
    except DocumentoError:
        raise
    except (PdfReadError, EmptyFileError, DependencyError, OSError, ValueError) as exc:
        # PDF truncado, cabecera `%PDF-` sin estructura, etc.
        raise error(
            "documento_ilegible",
            "El PDF esta danado o incompleto y no se puede leer",
        ) from exc
    if paginas <= 0:
        raise error("documento_ilegible", "El PDF no contiene ninguna pagina")
    if paginas > settings.documento_max_paginas:
        raise error(
            "documento_paginas_excedidas",
            f"El PDF supera el maximo de {settings.documento_max_paginas} paginas",
        )
    return paginas


def _validar_imagen(contenido: bytes) -> int:
    """research D8: ``verify()`` para descartar ficheros truncados, ``n_frames``
    para confirmar que el TIFF se lee entero. Un TIFF multipagina es un
    documento: se devuelve 1."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            imagen.verify()
        # `verify()` invalida el objeto: hay que reabrirlo para `n_frames`.
        with Image.open(io.BytesIO(contenido)) as imagen:
            if getattr(imagen, "n_frames", 1) < 1:
                raise error("documento_ilegible", "La imagen no tiene fotogramas")
    except DocumentoError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise error(
            "documento_ilegible",
            "La imagen esta danada o incompleta y no se puede leer",
        ) from exc
    return 1


def validar_contenido(contenido: bytes, extension: str) -> int:
    """Valida que el contenido corresponda al formato y devuelve ``num_paginas``.

    `num_paginas` es el numero real de paginas del PDF y ``None`` para imagenes
    (data-model.md seccion 3). El cliente recibe ``1`` para las imagenes
    porque un TIFF multipagina cuenta como un solo documento.
    """
    if extension == "pdf":
        return _validar_pdf(contenido)
    if extension in ("jpg", "png", "tif"):
        return _validar_imagen(contenido)
    raise error("formato_no_admitido", MENSAJE_FORMATOS)


def validar_fichero(
    nombre: str, contenido: bytes, extension_declarada_: str | None = None
) -> dict[str, object]:
    """Valida un fichero completo y devuelve sus metadatos derivados.

    Orden de comprobaciones (data-model.md seccion 5):

    1. Tamano (barato, y un fichero de 0 bytes no tiene firma que mirar).
    2. Extension declarada admitida.
    3. Firma real del contenido, y que coincida con la declarada (FR-014).
    4. Estructura interna: `pypdf` o Pillow, con los limites de D16.

    La extension declarada puede no existir (``extension_declarada_``): si el
    cliente no la envia, se deduce de la firma. Si la envia y contradice la
    firma, el fichero se rechaza: un JPEG renombrado a ``.pdf`` no es
    evidencia de nada.
    """
    validar_tamano(len(contenido))

    declarada = (extension_declarada_ or "").strip().lower().lstrip(".")
    if not declarada:
        declarada = extension_declarada(nombre)
    canonica_declarada = ALIAS.get(declarada)
    if declarada and canonica_declarada is None:
        raise error("formato_no_admitido", MENSAJE_FORMATOS)

    detectada, content_type = detectar_formato(contenido)
    if canonica_declarada is not None and canonica_declarada != detectada:
        raise error(
            "documento_ilegible",
            f"El contenido es {detectada.upper()} pero el fichero declara .{declarada}",
        )

    num_paginas = validar_contenido(contenido, detectada)
    return {
        "extension": detectada,
        "content_type": content_type,
        "num_paginas": num_paginas if detectada == "pdf" else None,
    }


#: Reexportado para que los tests y los servicios importen los limites desde un
#: solo sitio, sin duplicar los numeros.
__all__ = [
    "ALIAS",
    "BAJA_MOTIVO_MAX",
    "DESCRIPCION_MAX",
    "FIRMAS",
    "MENSAJE_FORMATOS",
    "NOMBRE_MAX",
    "DocumentoError",
    "detectar_formato",
    "extension_declarada",
    "validar_contenido",
    "validar_fichero",
    "validar_importe_informativo",
    "validar_nombre",
    "validar_tamano",
    "validar_texto",
    "validar_tipo_documento",
]
