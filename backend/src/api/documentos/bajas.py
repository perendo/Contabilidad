"""DELETE /api/v1/documentos/{documento_id} (SPEC-030 US3).

Guard `acct:baja`, un permiso **distinto** de `acct:crear` que lo de adjuntar:
FR-016 pide que sean diferenciables, y `require_permission` deniega por defecto,
asi que la separacion es real y no nominal.

204 sin cuerpo. No hay ruta de borrado fisico en toda la superficie de la spec.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from api.deps import require_permission
from api.documentos.deps import Actor, Db, Empresa, _http, ip_de, nombre_de
from services.documentos.bajas import dar_de_baja_documento
from services.documentos.errores import DocumentoError

router = APIRouter(prefix="/api/v1/documentos", tags=["documentos"])


class BajaDocumento(BaseModel):
    """Motivo obligatorio (FR-012): una baja sin motivo no es trazable."""

    motivo: Annotated[str, Field(min_length=1, max_length=500)]


@router.delete(
    "/{documento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("acct", "baja"))],
)
async def baja(
    request: Request,
    documento_id: str,
    cuerpo: BajaDocumento,
    db: Db,
    empresa_id: Empresa,
    user: Actor,
) -> Response:
    try:
        await dar_de_baja_documento(
            db,
            empresa_id=empresa_id,
            documento_id=documento_id,
            motivo=cuerpo.motivo,
            actor=nombre_de(user),
            ip=ip_de(request),
        )
    except DocumentoError as exc:
        raise _http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
