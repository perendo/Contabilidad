"""Dependencias y traduccion de errores del router de documentos (SPEC-030)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id
from database import get_db
from models.iam.user import User
from services.documentos.errores import DocumentoError

#: La sesion transaccional. El boundary ACID real es `get_db` (commit al final
#: de la peticion, rollback ante excepcion); los servicios hacen `flush()` dentro
#: de el y **nunca** abren su propia transaccion (desviacion V1 de plan.md).
Db = Annotated[AsyncSession, Depends(get_db)]

#: Empresa activa de la sesion. El cliente nunca la envia (constitucion III).
Empresa = Annotated[int, Depends(get_empresa_id)]

#: Usuario autenticado, para `created_by`, `baja_usuario` y la auditoria.
Actor = Annotated[User, Depends(get_current_user)]


def _http(exc: DocumentoError) -> HTTPException:
    """Traduce un `DocumentoError` al `HTTPException` del contrato.

    Cuerpo: ``{"code", "detail", **extra}``. El `status_code` lo fija el propio
    error (404 para `asiento_no_encontrado` y `documento_no_encontrado`, 409 para
    `documento_duplicado`, `limite_documentos_alcanzado` y `baja_no_permitida`,
    422 para el resto), de modo que el mapeo no se duplica por endpoint.
    """
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "detail": exc.message, **exc.extra},
    )


def ip_de(request: Request) -> str | None:
    """IP de origen para la auditoria (FR-011)."""
    return request.client.host if request.client is not None else None


def nombre_de(usuario: User | None) -> str | None:
    """Identificador del autor en la traza: `users.id` (BIGINT) como texto.

    Se usa el id y no el correo porque es lo que el resto del repositorio graba
    y porque el correo es un dato personal que no necesita viajar en la
    auditoria.
    """
    return str(usuario.id) if usuario is not None else None


__all__ = ["Actor", "Db", "Empresa", "ip_de", "nombre_de"]
