"""Remittance API endpoints (SPEC-020 US1)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from api.treasury.deps import get_empresa_id
from database import get_db
from models.treasury.recibo_remesa import ReciboRemesa
from models.treasury.remesa import FormatoRemesa, Remesa, RemesaEstado, TipoAdeudo
from services.remittance import emision as emision_svc
from services.remittance.emision import RemesaError
from services.remittance.seleccion import EjercicioCerradoError

router = APIRouter(prefix="/remesas", tags=["remesas"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]


class CrearRemesaBody(BaseModel):
    formato: FormatoRemesa
    tipo_adeudo: TipoAdeudo
    recibo_ids: list[uuid.UUID] = Field(min_length=1)


class ConciliarBody(BaseModel):
    movimiento_id: uuid.UUID
    fecha_cobro: date | None = None


def _http(exc: RemesaError) -> HTTPException:
    extra: dict[str, Any] = {"code": exc.code, "detail": str(exc)}
    if isinstance(exc, emision_svc.InelegibleError):
        extra["excluidos"] = [
            {"vencimiento_id": str(x.vencimiento_id), "motivo": x.motivo}
            for x in exc.excluidos
        ]
    if isinstance(exc, emision_svc.MandatoB2BError):
        extra["tercero_id"] = str(exc.tercero_id)
    return HTTPException(status_code=exc.status_code, detail=extra)


def _http_cerrado(exc: EjercicioCerradoError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "ejercicio_cerrado", "detail": str(exc)},
    )


def _ser_recibo(r: ReciboRemesa) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "recibo_num": r.recibo_num,
        "tercero_id": str(r.tercero_id),
        "iban": r.iban,
        "importe": f"{r.importe:f}",
        "fecha_cargo": r.fecha_cargo.isoformat(),
        "estado": r.estado.value,
        "vencimiento_id": str(r.vencimiento_id),
        "asiento_cobro_id": str(r.asiento_cobro_id) if r.asiento_cobro_id else None,
    }


async def _n_recibos(
    session: AsyncSession, empresa_id: int, remesa_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    filas = (
        await session.execute(
            select(ReciboRemesa.remesa_id, func.count())
            .where(
                ReciboRemesa.empresa_id == empresa_id,
                ReciboRemesa.remesa_id.in_(remesa_ids),
            )
            .group_by(ReciboRemesa.remesa_id)
        )
    ).all()
    return {remesa_id: n for remesa_id, n in filas}


def _ser_remesa(
    remesa: Remesa, n_recibos: int | None = None, recibos: list[ReciboRemesa] | None = None
) -> dict[str, Any]:
    return {
        "id": str(remesa.id),
        "empresa_id": remesa.empresa_id,
        "ejercicio": remesa.ejercicio,
        "numero_remesa": remesa.numero_remesa,
        "estado": remesa.estado.value,
        "formato": remesa.formato.value,
        "tipo_adeudo": remesa.tipo_adeudo.value,
        "fecha_emision": remesa.fecha_emision.isoformat() if remesa.fecha_emision else None,
        "fecha_cargo": remesa.fecha_cargo.isoformat() if remesa.fecha_cargo else None,
        "importe_total": f"{remesa.importe_total:f}",
        "n_recibos": n_recibos,
        "recibos": [_ser_recibo(r) for r in (recibos or [])],
    }


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("treasury", "crear"))])
async def crear_remesa(
    body: CrearRemesaBody, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    try:
        remesa = await emision_svc.crear_remesa(
            session,
            empresa_id,
            formato=body.formato.value,
            tipo_adeudo=body.tipo_adeudo.value,
            vencimiento_ids=body.recibo_ids,
        )
    except EjercicioCerradoError as exc:
        raise _http_cerrado(exc) from exc
    except RemesaError as exc:
        raise _http(exc) from exc
    return _ser_remesa(remesa, n_recibos=len(body.recibo_ids))


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_remesas(
    empresa_id: EmpresaDep,
    session: SessionDep,
    estado: RemesaEstado | None = None,
    formato: FormatoRemesa | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    query = select(Remesa).where(Remesa.empresa_id == empresa_id)
    if estado is not None:
        query = query.where(Remesa.estado == estado)
    if formato is not None:
        query = query.where(Remesa.formato == formato)
    remesas = (
        await session.scalars(
            query.order_by(Remesa.numero_remesa).offset(offset).limit(limit)
        )
    ).all()
    total = (
        await session.execute(
            select(func.count())
            .select_from(Remesa)
            .where(Remesa.empresa_id == empresa_id)
        )
    ).scalar_one()
    conteos = await _n_recibos(
        session, empresa_id, [remesa.id for remesa in remesas]
    )
    return {
        "total": total,
        "items": [
            _ser_remesa(remesa, n_recibos=conteos.get(remesa.id, 0))
            for remesa in remesas
        ],
    }


@router.get("/{remesa_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle_remesa(
    remesa_id: uuid.UUID, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    remesa = await session.scalar(
        select(Remesa).where(Remesa.empresa_id == empresa_id, Remesa.id == remesa_id)
    )
    if remesa is None:
        raise HTTPException(status_code=404, detail="remesa no encontrada")
    recibos = (
        await session.scalars(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == empresa_id,
                ReciboRemesa.remesa_id == remesa_id,
            )
        )
    ).all()
    return _ser_remesa(remesa, n_recibos=len(recibos), recibos=list(recibos))


@router.post("/{remesa_id}/emitir", dependencies=[Depends(require_permission("treasury", "editar"))])
async def emitir_remesa(
    remesa_id: uuid.UUID, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    try:
        remesa, blob, _contenido = await emision_svc.emitir_remesa(
            session, empresa_id, remesa_id
        )
    except RemesaError as exc:
        raise _http(exc) from exc
    recibos_q = (
        await session.scalars(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == empresa_id,
                ReciboRemesa.remesa_id == remesa.id,
            )
        )
    ).all()
    return {
        **_ser_remesa(remesa, n_recibos=len(recibos_q), recibos=list(recibos_q)),
        "sha256": blob.sha256,
        "n_fechas_cargo": len({r.fecha_cargo for r in recibos_q}),
        "exportado": True,
    }


@router.get("/{remesa_id}/fichero", dependencies=[Depends(require_permission("treasury", "ver"))])
async def descargar_fichero(
    remesa_id: uuid.UUID, empresa_id: EmpresaDep, session: SessionDep
) -> Response:
    remesa = await session.scalar(
        select(Remesa).where(Remesa.empresa_id == empresa_id, Remesa.id == remesa_id)
    )
    if remesa is None or remesa.fichero_id is None:
        raise HTTPException(status_code=404, detail="fichero no disponible")
    from models.treasury.blob_fichero import BlobFichero

    blob = await session.scalar(
        select(BlobFichero).where(
            BlobFichero.empresa_id == empresa_id, BlobFichero.id == remesa.fichero_id
        )
    )
    if blob is None:
        raise HTTPException(status_code=404, detail="fichero no disponible")
    media_type = "text/xml" if remesa.formato == FormatoRemesa.SEPA_DD else "text/plain"
    nombre = (
        f"remesa-{remesa.numero_remesa:06d}.xml"
        if remesa.formato == FormatoRemesa.SEPA_DD
        else f"remesa-{remesa.numero_remesa:06d}.19"
    )
    return Response(
        content=blob.contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post("/{remesa_id}/recibos/{recibo_id}/cobrar", dependencies=[Depends(require_permission("treasury", "editar"))])
async def cobrar_recibo(
    remesa_id: uuid.UUID, recibo_id: uuid.UUID, empresa_id: EmpresaDep, session: SessionDep
) -> dict[str, Any]:
    try:
        remesa, recibo = await emision_svc.confirmar_cobro(
            session, empresa_id, remesa_id, recibo_id
        )
    except RemesaError as exc:
        raise _http(exc) from exc
    return {
        "remesa_id": str(remesa.id),
        "recibo": _ser_recibo(recibo),
        "asiento_id": str(recibo.asiento_cobro_id),
    }


@router.post("/{remesa_id}/recibos/{recibo_id}/conciliar", dependencies=[Depends(require_permission("treasury", "editar"))])
async def conciliar_recibo(
    remesa_id: uuid.UUID,
    recibo_id: uuid.UUID,
    body: ConciliarBody,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        recibo, idempotente = await emision_svc.conciliar_cobro(
            session,
            empresa_id,
            remesa_id=remesa_id,
            recibo_id=recibo_id,
            movimiento_id=body.movimiento_id,
            fecha_cobro=body.fecha_cobro,
        )
    except RemesaError as exc:
        raise _http(exc) from exc
    return {
        "recibo": _ser_recibo(recibo),
        "asiento_id": str(recibo.asiento_cobro_id),
        "idempotente": idempotente,
    }