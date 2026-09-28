"""Import/export de asientos API (SPEC-005)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.iam.user import User
from services.importexport.exportador import exportar_diario
from services.importexport.importador import (
    importar_asientos,
    previsualizar_importacion,
)
from services.importexport.parseador import ParseError

router = APIRouter(prefix="/api/v1/asientos", tags=["import-export"])

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
SesionDep = Annotated[AsyncSession, Depends(get_db)]
ArchivoDep = Annotated[UploadFile, File(...)]

MAX_BYTES = 5 * 1024 * 1024


async def _leer(archivo: UploadFile) -> tuple[bytes, str]:
    contenido = await archivo.read()
    if len(contenido) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El archivo supera el tamaño máximo (5 MB)",
        )
    return contenido, archivo.filename or "asientos.csv"


@router.post("/importar/previsualizar", dependencies=[Depends(require_permission("acct", "importar_exportar"))])
async def previsualizar(empresa_id: EmpresaDep, session: SesionDep, archivo: ArchivoDep):
    contenido, nombre = await _leer(archivo)
    try:
        return await previsualizar_importacion(
            session, empresa_id=empresa_id, file_bytes=contenido, nombre=nombre
        )
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "detail": str(exc)},
        )


@router.post(
    "/importar/confirmar",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("acct", "importar_exportar"))],
)
async def confirmar(
    empresa_id: EmpresaDep,
    session: SesionDep,
    archivo: ArchivoDep,
    user: Annotated[User, Depends(get_current_user)],
):
    contenido, nombre = await _leer(archivo)
    try:
        resultado = await importar_asientos(
            session, empresa_id=empresa_id, file_bytes=contenido, nombre=nombre,
            actor=user.full_name,
        )
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "detail": str(exc)},
        )
    if resultado["asientos_importados"] == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No hay asientos válidos que importar",
        )
    return resultado


@router.get("/exportar", dependencies=[Depends(require_permission("acct", "importar_exportar"))])
async def exportar(
    empresa_id: EmpresaDep,
    session: SesionDep,
    fecha_desde: Annotated[date, Query(description="Inicio del rango")],
    fecha_hasta: Annotated[date, Query(description="Fin del rango")],
    formato: Annotated[str, Query(pattern="^(CSV|xlsx|XLSX|csv)$")] = "CSV",
):
    contenido, nombre, media_type = await exportar_diario(
        session, empresa_id=empresa_id,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, formato=formato,
    )
    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
