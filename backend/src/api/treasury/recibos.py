"""Receivable liquidation API endpoints (SPEC-020 US2)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from api.treasury.deps import get_empresa_id
from database import get_db
from services import discount
from services.discount import LiquidacionError
from services.remittance.emision import ReciboNotFoundError

router = APIRouter(prefix="/recibos", tags=["recibos"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class LiquidarBody(BaseModel):
    fecha_pago: date
    cuenta: str = discount.CUENTA_BANCO_DEFECTO
    override_condicion_id: uuid.UUID | None = None


def _http(exc: LiquidacionError | ReciboNotFoundError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "detail": str(exc)})


@router.post("/{recibo_id}/liquidar", dependencies=[Depends(require_permission("treasury", "editar"))])
async def liquidar_recibo(
    recibo_id: uuid.UUID,
    body: LiquidarBody,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        resultado = await discount.liquidar_con_descuento(
            session,
            empresa_id,
            recibo_id,
            fecha_pago=body.fecha_pago,
            cuenta_banco=body.cuenta or discount.CUENTA_BANCO_DEFECTO,
            override_condicion_id=body.override_condicion_id,
        )
    except ReciboNotFoundError as exc:
        raise _http(exc) from exc
    except LiquidacionError as exc:
        raise _http(exc) from exc
    return {
        "importe_neto": f"{resultado.neto:0.4f}",
        "descuento": f"{resultado.descuento:0.4f}",
        "asiento_id": str(resultado.asiento_id),
        "descuento_aplicado": resultado.descuento_aplicado,
        "recibo_id": str(resultado.recibo.id),
        "estado": resultado.recibo.estado.value,
    }