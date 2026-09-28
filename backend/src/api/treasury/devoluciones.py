"""Devolution API endpoints (SPEC-020 US3)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_permission
from api.treasury.deps import get_empresa_id
from database import get_db
from models.treasury.devolucion import DevolucionRecibo, Reclamacion
from models.treasury.recibo_remesa import ReciboRemesa
from services.remittance import refund_r19

router = APIRouter(prefix="/devoluciones", tags=["devoluciones"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
EmpresaDep = Annotated[int, Depends(get_empresa_id)]

_FileNone = File(default=None)


class DevolucionEntradaBody(BaseModel):
    recibo_id: uuid.UUID
    tipo: Literal["R19", "C19"] = "R19"
    codigo: str
    motivo: str
    importe: Decimal
    importe_gastos: Decimal = Decimal(0)
    fecha_registro: date


class ImportDevolucionesBody(BaseModel):
    devoluciones: list[DevolucionEntradaBody]


class ReclamacionBody(BaseModel):
    accion: str
    observaciones: str | None = None


def _hoy() -> date:
    return datetime.now(timezone.utc).date()


def _http(exc: refund_r19.DevolucionError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code, detail={"code": exc.code, "detail": str(exc)}
    )


def _identificador_entrada(entrada: DevolucionEntradaBody) -> str:
    cents = int(entrada.importe * 100)
    gastos_cents = int(entrada.importe_gastos * 100)
    return (
        f"{entrada.tipo}:{entrada.codigo}:{entrada.recibo_id}:"
        f"{entrada.fecha_registro.isoformat()}:{cents}:{gastos_cents}"
    )


def _ser_devolucion(d: DevolucionRecibo) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "empresa_id": d.empresa_id,
        "recibo_remesa_id": str(d.recibo_remesa_id),
        "codigo": d.codigo,
        "identificador_externo": d.identificador_externo,
        "motivo": d.motivo,
        "fecha_registro": d.fecha_registro.isoformat(),
        "fecha_cargo_original": d.fecha_cargo_original.isoformat(),
        "importe": f"{d.importe:0.4f}",
        "importe_gastos": f"{d.importe_gastos:0.4f}",
        "asiento_reversal_id": str(d.asiento_reversal_id) if d.asiento_reversal_id else None,
        "estado_reclamacion": d.estado_reclamacion.value,
    }


def _rechazada(exc: BaseException) -> dict[str, str]:
    return {"motivo": str(exc), "code": getattr(exc, "code", "error")}


@router.post("/import", dependencies=[Depends(require_permission("treasury", "crear"))])
async def importar_devoluciones(
    empresa_id: EmpresaDep,
    session: SessionDep,
    request: Request,
    file: UploadFile | None = _FileNone,
    tipo: Literal["R19", "C19"] = "R19",
) -> dict[str, Any]:
    if file is None and (await request.body()) in (b"", b"null"):
        raise HTTPException(
            status_code=422,
            detail={"code": "formato_retorno_invalido", "detail": "se requiere fichero o body JSON"},
        )

    entradas: list = []
    if file is not None:
        contenido = await file.read()
        try:
            retornos = refund_r19.parsear_retorno_aeb19(contenido, tipo=tipo)
        except refund_r19.FormatoRetornoError as exc:
            raise _http(exc) from exc
        for retorno in retornos:
            entradas.append({"retorno": retorno, "identificador": retorno.identificador_externo})
    else:
        try:
            cuerpo = ImportDevolucionesBody.model_validate(await request.json())
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "formato_retorno_invalido", "detail": str(exc)},
            ) from exc
        for entrada in cuerpo.devoluciones:
            entradas.append(
                {
                    "entrada": entrada,
                    "identificador": _identificador_entrada(entrada),
                }
            )

    procesadas = 0
    rechazadas: list[dict[str, str]] = []
    for item in entradas:
        try:
            retorno = item.get("retorno")
            if retorno is not None:
                recibo = await refund_r19.resolver_recibo_por_ref(
                    session, empresa_id, retorno.recibo_ref
                )
                if recibo is None:
                    raise refund_r19.ReciboDevolucionNotFoundError(
                        f"recibo {retorno.recibo_ref!r} no encontrado"
                    )
                devolucion = await refund_r19.procesar_devolucion(
                    session,
                    empresa_id,
                    recibo_id=recibo.id,
                    codigo=retorno.codigo,
                    motivo=retorno.motivo,
                    importe=retorno.importe,
                    importe_gastos=retorno.importe_gastos,
                    fecha_registro=_hoy(),
                    fecha_cargo_original=retorno.fecha_cargo,
                    identificador_externo=item["identificador"],
                )
            else:
                entrada = item["entrada"]
                devolucion = await refund_r19.procesar_devolucion(
                    session,
                    empresa_id,
                    recibo_id=entrada.recibo_id,
                    codigo=entrada.codigo,
                    motivo=entrada.motivo,
                    importe=entrada.importe,
                    importe_gastos=entrada.importe_gastos,
                    fecha_registro=entrada.fecha_registro,
                    identificador_externo=item["identificador"],
                )
            procesadas += 1
            item["devolucion"] = devolucion
        except refund_r19.DevolucionError as exc:
            rechazadas.append(_rechazada(exc))
    await session.flush()
    return {
        "procesadas": procesadas,
        "rechazadas": rechazadas,
        "total": len(entradas),
    }


@router.get("", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_devoluciones(
    empresa_id: EmpresaDep,
    session: SessionDep,
    codigo: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    query = select(DevolucionRecibo).where(DevolucionRecibo.empresa_id == empresa_id)
    if codigo:
        query = query.where(DevolucionRecibo.codigo == codigo)
    devoluciones = (
        await session.scalars(
            query.order_by(DevolucionRecibo.fecha_registro.desc()).offset(offset).limit(limit)
        )
    ).all()
    return {"items": [_ser_devolucion(d) for d in devoluciones], "total": len(devoluciones)}


@router.get("/{devolucion_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle_devolucion(
    devolucion_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    devolucion = await session.scalar(
        select(DevolucionRecibo).where(
            DevolucionRecibo.empresa_id == empresa_id,
            DevolucionRecibo.id == devolucion_id,
        )
    )
    if devolucion is None:
        raise HTTPException(status_code=404, detail="devolución no encontrada")
    recibo = await session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id,
            ReciboRemesa.id == devolucion.recibo_remesa_id,
        )
    )
    reclamaciones = list(
        (
            await session.scalars(
                select(Reclamacion).where(
                    Reclamacion.empresa_id == empresa_id,
                    Reclamacion.devolucion_id == devolucion.id,
                )
            )
        ).all()
    )
    return {
        **_ser_devolucion(devolucion),
        "recibo": {
            "id": str(recibo.id) if recibo else None,
            "recibo_num": recibo.recibo_num if recibo else None,
            "estado": recibo.estado.value if recibo else None,
            "asiento_cobro_id": str(recibo.asiento_cobro_id) if recibo and recibo.asiento_cobro_id else None,
        },
        "reclamaciones": [
            {
                "id": str(r.id),
                "estado": r.estado.value,
                "fecha_registro": r.fecha_registro.isoformat(),
                "observaciones": r.observaciones,
            }
            for r in reclamaciones
        ],
    }


@router.post("/{devolucion_id}/reclamaciones", dependencies=[Depends(require_permission("treasury", "crear"))])
async def crear_reclamacion(
    devolucion_id: uuid.UUID,
    body: ReclamacionBody,
    empresa_id: EmpresaDep,
    session: SessionDep,
) -> dict[str, Any]:
    try:
        reclamacion = await refund_r19.gestionar_reclamacion(
            session,
            empresa_id,
            devolucion_id,
            body.accion,
            body.observaciones,
        )
    except refund_r19.DevolucionError as exc:
        raise _http(exc) from exc
    return {
        "reclamacion_id": str(reclamacion.id),
        "estado": reclamacion.estado.value,
    }