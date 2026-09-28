"""Derived reports router (SPEC-004 US1/US2): trial balance and ledger."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_empresa_id, require_permission
from database import get_db
from services.reports.ledger import LedgerError, ledger
from services.reports.trial_balance import BalanceError, trial_balance

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
SesionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/trial-balance", dependencies=[Depends(require_permission("reporting", "ver"))])
async def balance_sumas_saldos(
    empresa_id: EmpresaDep,
    session: SesionDep,
    date_from: Annotated[date, Query(description="Inicio del rango")],
    date_to: Annotated[date, Query(description="Fin del rango")],
    level: Annotated[int, Query(ge=1, description="Profundidad de agregación")] = 4,
):
    try:
        return await trial_balance(
            session, empresa_id=empresa_id,
            date_from=date_from, date_to=date_to, level=level,
        )
    except BalanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )


@router.get("/ledger/{account_id}", dependencies=[Depends(require_permission("reporting", "ver"))])
async def libro_mayor(
    account_id: int,
    empresa_id: EmpresaDep,
    session: SesionDep,
    date_from: Annotated[date | None, Query(description="Inicio del rango")] = None,
    date_to: Annotated[date | None, Query(description="Fin del rango")] = None,
):
    try:
        return await ledger(
            session, empresa_id=empresa_id, account_id=account_id,
            date_from=date_from, date_to=date_to,
        )
    except LedgerError as exc:
        if exc.code == "cuenta_no_encontrada":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
