"""Fiscal-year router (SPEC-004 US3): listing and exercise closing."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.acct.fiscal_year import FiscalYear
from models.iam.user import User
from services.closing.close_year import CierreError, cerrar_ejercicio

router = APIRouter(prefix="/api/v1/fiscal-years", tags=["fiscal-years"])

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
SesionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", dependencies=[Depends(require_permission("reporting", "ver"))])
async def listar_ejercicios(empresa_id: EmpresaDep, session: SesionDep):
    filas = (
        await session.scalars(
            select(FiscalYear)
            .where(FiscalYear.empresa_id == empresa_id)
            .order_by(FiscalYear.year)
        )
    ).all()
    return {
        "items": [
            {
                "year": fy.year,
                "date_start": fy.date_start.isoformat(),
                "date_end": fy.date_end.isoformat(),
                "is_closed": fy.is_closed,
                "closed_at": fy.closed_at.isoformat() if fy.closed_at else None,
            }
            for fy in filas
        ]
    }


@router.post(
    "/{year}/close",
    dependencies=[Depends(require_permission("acct", "cerrar"))],
)
async def cerrar(
    year: int,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
    request: Request,
):
    ip = request.client.host if request.client else None
    try:
        return await cerrar_ejercicio(
            session, empresa_id=empresa_id, year=year,
            actor=user.full_name, ip=ip,
        )
    except CierreError as exc:
        if exc.code == "ejercicio_no_encontrado":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        if exc.code == "ejercicio_cerrado":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
