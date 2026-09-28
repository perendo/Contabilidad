"""POST /api/v1/documentos/asiento/{asiento_id} (SPEC-030 US1).

Adjunta uno o varios ficheros PDF o imagen a un asiento del diario. Es la unica
operacion de escritura que anade contenido; el resto de rutas de la spec son de
lectura y la de US3 solo hace una baja logica.

Guard `acct:crear` (FR-016, research D4): reutiliza el modulo RBAC ya existente en
lugar de crear uno nuevo.

Multipart con `UploadFile` + `Form` (research D9), no despacho manual de
`request.form()`: esa via existe en `api/presupuestos.py` porque esas rutas
aceptan CSV o JSON ademas de multipart; aqui no aplica. Mezclar `File()` con un
modelo pydantic de body esta prohibido: FastAPI lo trataria como multipart y el
JSON llegaria como `None`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from api.deps import require_permission
from api.documentos.deps import Actor, Db, Empresa, _http, ip_de, nombre_de
from services.documentos.adjuntos import adjuntar_documentos
from services.documentos.errores import DocumentoError

router = APIRouter(prefix="/api/v1/documentos", tags=["documentos"])


@router.post(
    "/asiento/{asiento_id}",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("acct", "crear"))],
)
async def adjuntar(
    request: Request,
    asiento_id: str,
    files: Annotated[list[UploadFile], File(description="PDF, JPEG, PNG o TIFF")],
    tipo_documento: Annotated[str, Form(description="Uno de documento_tipo")],
    db: Db,
    empresa_id: Empresa,
    user: Actor,
    descripcion: Annotated[str | None, Form(max_length=500)] = None,
    importe_informativo: Annotated[str | None, Form()] = None,
) -> dict:
    """201 aunque `aceptados` quede vacio: el detalle de los rechazos viaja en el
    cuerpo, no en el codigo (contracts/api-contracts.md seccion 1).

    El tope real de ficheros es `documento_max_por_asiento` (50) y el de peso es
    `documento_max_bytes` (10 MB) por documento; los dos los aplica el servicio
    por cada fichero, no la capa de transporte.
    """
    try:
        ficheros = []
        for fichero in files:
            nombre = fichero.filename or "documento"
            ficheros.append(
                {
                    "nombre": nombre,
                    "contenido": await fichero.read(),
                    "extension": (
                        nombre.rsplit(".", 1)[-1].strip().lower()
                        if "." in nombre
                        else None
                    ),
                }
            )
        return await adjuntar_documentos(
            db,
            empresa_id=empresa_id,
            asiento_id=asiento_id,
            ficheros=ficheros,
            tipo_documento=tipo_documento,
            descripcion=descripcion,
            importe_informativo=importe_informativo,
            actor=nombre_de(user),
            ip=ip_de(request),
        )
    except DocumentoError as exc:
        raise _http(exc) from exc
