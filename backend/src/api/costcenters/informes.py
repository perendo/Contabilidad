"""Endpoints del informe de costes por centro (SPEC-017 US3).

Agrega líneas de asientos POSTED de la empresa activa con ``Decimal`` (nunca
float) y devuelve subtotales por jerarquía (closure). Exportación CSV
(delimitador `;`) / JSON con 4 decimales. Contrato:
`contracts/api-contracts.md`.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.costcenters.deps import get_empresa_activa, require_permission
from database import get_db
from services.costcenters.errores import CostcenterError
from services.costcenters.informes import exportar_informe, informe_costes

router = APIRouter(prefix="/api/v1", tags=["informes-costes"])

Db = Annotated[AsyncSession, Depends(get_db)]


def _manejar(exc: CostcenterError) -> HTTPException:
    if exc.code in ("centro_no_encontrado",):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code in ("periodo_invalido", "tipo_invalido", "formato_invalido"):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)


@router.get(
    "/informes/costes",
    dependencies=[Depends(require_permission("centros", "ver"))],
)
async def informe_costes_ep(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    ejercicio: Annotated[int, Query(gt=2000, lt=2100)],
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    centro_id: uuid.UUID | None = None,
    tipo: Annotated[str, Query(max_length=10)] = "todos",
) -> dict:
    try:
        return await informe_costes(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            centro_id=centro_id,
            tipo=tipo,
        )
    except CostcenterError as exc:
        raise _manejar(exc) from exc


@router.get(
    "/informes/costes/exportar",
    dependencies=[Depends(require_permission("centros", "ver"))],
)
async def exportar_informe_ep(
    db: Db,
    empresa_id: Annotated[int, Depends(get_empresa_activa)],
    ejercicio: Annotated[int, Query(gt=2000, lt=2100)],
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    centro_id: uuid.UUID | None = None,
    tipo: Annotated[str, Query(max_length=10)] = "todos",
    format: Annotated[str, Query(max_length=4)] = "csv",
) -> Response:
    try:
        datos = await informe_costes(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            centro_id=centro_id,
            tipo=tipo,
        )
        contenido, media_type = exportar_informe(datos, formato=format)
    except CostcenterError as exc:
        raise _manejar(exc) from exc
    nombre = f"informe_costes_{ejercicio}.{format}"
    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )