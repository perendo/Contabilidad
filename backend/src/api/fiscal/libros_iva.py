"""Endpoint del libro de IVA (SPEC-012 US1)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from api.fiscal.comun import http_error
from database import get_db
from services.vat.errores import VatError
from services.vat.libros_iva import construir_libro
from services.vat.periodo import rango_periodo

router = APIRouter(prefix="/api/v1/libros-iva", tags=["fiscal"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


@router.get("/{tipo_libro}", dependencies=[Depends(require_permission("fiscal", "ver"))])
async def consultar_libro(
    tipo_libro: str,
    empresa_id: EmpresaDep,
    session: SessionDep,
    ejercicio: Annotated[int, Query()],
    periodo: Annotated[int | None, Query()] = None,
    tipo_periodo: Annotated[str, Query()] = "TRIMESTRE",
    fecha_desde: Annotated[date | None, Query()] = None,
    fecha_hasta: Annotated[date | None, Query()] = None,
    clave_operacion: Annotated[str | None, Query()] = None,
    tercero_id: Annotated[uuid.UUID | None, Query()] = None,
) -> dict:
    try:
        if periodo is not None:
            inicio, fin = rango_periodo(ejercicio, tipo_periodo, periodo)
        else:
            inicio = fecha_desde or date(ejercicio, 1, 1)
            fin = fecha_hasta or date(ejercicio, 12, 31)
        libro = await construir_libro(
            session,
            empresa_id=empresa_id,
            tipo_libro=tipo_libro,
            ejercicio=ejercicio,
            inicio=inicio,
            fin=fin,
            tercero_id=tercero_id,
            clave_operacion=clave_operacion,
        )
    except VatError as exc:
        raise http_error(exc) from exc
    return {"ejercicio": ejercicio, "periodo": periodo, **libro}