"""Conciliación bancaria API (SPEC-013)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, NoReturn

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_empresa_id, require_permission
from database import get_db
from models.iam.user import User
from models.treasury.alerta_conciliacion import AlertaConciliacion, EstadoAlerta
from models.treasury.conciliacion import Conciliacion, CruceOrigen
from models.treasury.extracto_bancario import ExtractoBancario
from models.treasury.movimiento_bancario import MovimientoBancario
from models.treasury.periodo_conciliado import PeriodoConciliado
from services.reconciliation.cierre import CierreError, cerrar_periodo
from services.reconciliation.conciliacion import (
    ConciliacionError,
    abrir_conciliacion,
)
from services.reconciliation.cruce import CruceError, confirmar_cruce, deshacer_cruce
from services.reconciliation.importacion import ImportacionError, importar_extracto
from services.reconciliation.layouts import LAYOUTS
from services.reconciliation.matching import generar_propuestas
from services.reconciliation.parsers import LayoutError
from services.reconciliation.saldos import generar_alertas, informe

router = APIRouter(prefix="/api/v1", tags=["reconciliation"])

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
SesionDep = Annotated[AsyncSession, Depends(get_db)]


class ConciliacionCreate(BaseModel):
    cuenta_id: int
    fecha_inicio: date
    fecha_fin: date
    extracto_id: uuid.UUID | None = None


class CruceItem(BaseModel):
    movimiento_id: uuid.UUID
    apunte_id: uuid.UUID
    origen: str = Field(pattern="^(auto|manual)$")


class CrucesBody(BaseModel):
    cruces: list[CruceItem]


def _fail(exc: Exception) -> NoReturn:
    code = getattr(exc, "code", "")
    extra = getattr(exc, "extra", {})
    if code in ("cuenta_no_encontrada", "extracto_no_encontrado", "movimiento_no_encontrado", "apunte_no_encontrado", "cruce_no_encontrado"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": code, "detail": str(exc)})
    if code in ("extracto_duplicado", "ejercicio_cerrado", "periodo_archivado", "periodo_cerrado", "conciliacion_previa", "movimiento_ya_conciliado", "diferencia_no_cero"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": code, "detail": str(exc), **extra})
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"error": code, "detail": str(exc)})


def _validar_layout(layout: str) -> str:
    """Comprueba el `layout` contra el catalogo antes de leer el fichero.

    Se valida aqui y no solo en el parser para que un formato desconocido se
    responda con la lista de los que si valen. Sin esto el usuario recibia
    "Linea 1: longitud 22 != 100", que habla de ancho fijo de un fichero que
    ni de ancho fijo es, y no de que el desplegable mande otra cosa.
    """
    if layout not in LAYOUTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "layout_desconocido",
                "detail": f"Formato no soportado: {layout or '(vacio)'}",
                "soportados": LAYOUTS,
            },
        )
    return layout


async def _extracto(db: AsyncSession, empresa_id: int, extracto_id: uuid.UUID) -> ExtractoBancario:
    ex = await db.scalar(
        select(ExtractoBancario).where(
            ExtractoBancario.empresa_id == empresa_id, ExtractoBancario.id == extracto_id
        )
    )
    if ex is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extracto inexistente")
    return ex


async def _conciliacion(db: AsyncSession, empresa_id: int, cid: uuid.UUID) -> Conciliacion:
    c = await db.scalar(
        select(Conciliacion).where(
            Conciliacion.empresa_id == empresa_id, Conciliacion.id == cid
        )
    )
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conciliación inexistente")
    return c


def _extracto_out(ex: ExtractoBancario) -> dict:
    return {
        "id": str(ex.id),
        "cuenta_id": ex.cuenta_id,
        "fecha_inicio": ex.fecha_inicio.isoformat(),
        "fecha_fin": ex.fecha_fin.isoformat(),
        "saldo_inicial": f"{ex.saldo_inicial:0.4f}",
        "saldo_final": f"{ex.saldo_final:0.4f}",
        "n_movimientos": ex.n_movimientos,
        "estado": ex.estado.value,
    }


@router.post("/extractos", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("treasury", "crear"))])
async def subir_extracto(
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(...)],
    layout: Annotated[str, Form()] = "norma_43_1919",
    cuenta: Annotated[str | None, Form()] = None,
):
    contenido = await file.read()
    _validar_layout(layout)
    try:
        extracto = await importar_extracto(
            session, empresa_id=empresa_id, file_bytes=contenido,
            nombre_fichero=file.filename or "extracto.txt", layout=layout,
            cuenta_codigo=cuenta, actor=user.full_name,
        )
    except (ImportacionError, LayoutError) as exc:
        _fail(exc)
    return _extracto_out(extracto)


@router.get("/extractos", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_extractos(
    empresa_id: EmpresaDep,
    session: SesionDep,
    cuenta_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    condiciones = [ExtractoBancario.empresa_id == empresa_id]
    if cuenta_id is not None:
        condiciones.append(ExtractoBancario.cuenta_id == cuenta_id)
    total = await session.scalar(select(func.count(ExtractoBancario.id)).where(*condiciones))
    filas = (
        await session.scalars(
            select(ExtractoBancario)
            .where(*condiciones)
            .order_by(ExtractoBancario.fecha_fin.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {"total": total or 0, "items": [_extracto_out(e) for e in filas]}


@router.get("/extractos/{extracto_id}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle_extracto(extracto_id: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    ex = await _extracto(session, empresa_id, extracto_id)
    movimientos = (
        await session.scalars(
            select(MovimientoBancario)
            .where(MovimientoBancario.empresa_id == empresa_id, MovimientoBancario.extracto_id == ex.id)
            .order_by(MovimientoBancario.orden)
        )
    ).all()
    return {
        **_extracto_out(ex),
        "movimientos": [
            {
                "id": str(m.id),
                "orden": m.orden,
                "fecha_operacion": m.fecha_operacion.isoformat(),
                "concepto": m.concepto,
                "importe": f"{m.importe:0.4f}",
                "signo": m.signo.value,
                "estado": m.estado.value,
            }
            for m in movimientos
        ],
    }


@router.post("/conciliaciones", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("treasury", "crear"))])
async def crear_conciliacion(
    body: ConciliacionCreate,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        c = await abrir_conciliacion(
            session, empresa_id=empresa_id, cuenta_id=body.cuenta_id,
            fecha_inicio=body.fecha_inicio, fecha_fin=body.fecha_fin,
            extracto_id=body.extracto_id, actor=user.full_name,
        )
    except ConciliacionError as exc:
        _fail(exc)
    return {
        "id": str(c.id), "cuenta_id": c.cuenta_id,
        "saldo_banco": f"{c.saldo_banco:0.4f}", "saldo_libros": f"{c.saldo_libros:0.4f}",
        "diferencia": f"{c.diferencia:0.4f}", "estado": c.estado.value,
    }


@router.get("/conciliaciones", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_conciliaciones(
    empresa_id: EmpresaDep, session: SesionDep,
    estado: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    condiciones = [Conciliacion.empresa_id == empresa_id]
    if estado:
        condiciones.append(Conciliacion.estado == estado)
    total = await session.scalar(select(func.count(Conciliacion.id)).where(*condiciones))
    filas = (
        await session.scalars(
            select(Conciliacion).where(*condiciones).order_by(Conciliacion.fecha_inicio.desc()).limit(limit).offset(offset)
        )
    ).all()
    return {
        "total": total or 0,
        "items": [
            {
                "id": str(c.id), "cuenta_id": c.cuenta_id, "estado": c.estado.value,
                "saldo_banco": f"{c.saldo_banco:0.4f}", "saldo_libros": f"{c.saldo_libros:0.4f}",
                "diferencia": f"{c.diferencia:0.4f}",
            }
            for c in filas
        ],
    }


@router.get("/conciliaciones/{cid}", dependencies=[Depends(require_permission("treasury", "ver"))])
async def detalle_conciliacion(cid: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    c = await _conciliacion(session, empresa_id, cid)
    return await informe(session, empresa_id, c)


@router.post("/conciliaciones/{cid}/propuestas", dependencies=[Depends(require_permission("treasury", "editar"))])
async def proponer(cid: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    c = await _conciliacion(session, empresa_id, cid)
    propuestas = await generar_propuestas(session, empresa_id=empresa_id, conciliacion=c)
    return {
        "n_propuestas": len(propuestas),
        "propuestas": [
            {
                "id": str(p.id), "movimiento_id": str(p.movimiento_id),
                "apunte_id": str(p.apunte_id), "importe": f"{p.importe:0.4f}",
                "signo": p.signo, "prioridad": p.prioridad.value,
            }
            for p in propuestas
        ],
    }


@router.post("/conciliaciones/{cid}/cruces", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("treasury", "editar"))])
async def crear_cruces(
    cid: uuid.UUID,
    body: CrucesBody,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: Annotated[User, Depends(get_current_user)],
):
    c = await _conciliacion(session, empresa_id, cid)
    confirmados = []
    rechazados = []
    for item in body.cruces:
        try:
            cruce = await confirmar_cruce(
                session, empresa_id=empresa_id, conciliacion=c,
                movimiento_id=item.movimiento_id, apunte_id=item.apunte_id,
                origen=CruceOrigen(item.origen), actor=user.full_name,
            )
        except CruceError as exc:
            rechazados.append({"motivo": str(exc), "error": exc.code})
            continue
        confirmados.append(
            {
                "cruce_id": str(cruce.id), "movimiento_id": str(cruce.movimiento_id),
                "apunte_id": str(cruce.apunte_id),
                "fecha_cruce": cruce.fecha_cruce.isoformat() if cruce.fecha_cruce else None,
                "confirmado_por_remesa": cruce.confirmado_por_remesa,
            }
        )
    if not confirmados and rechazados:
        _fail(CruceError(rechazados[0].get("error", "cruce_invalido"), rechazados[0]["motivo"]))
    return {"confirmados": confirmados, "rechazados": rechazados}


@router.delete("/conciliaciones/{cid}/cruces/{cruce_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("treasury", "baja"))])
async def borrar_cruce(
    cid: uuid.UUID,
    cruce_id: uuid.UUID,
    empresa_id: EmpresaDep,
    session: SesionDep,
):
    c = await _conciliacion(session, empresa_id, cid)
    try:
        await deshacer_cruce(session, empresa_id=empresa_id, conciliacion=c, cruce_id=cruce_id)
    except CruceError as exc:
        _fail(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conciliaciones/{cid}/cerrar", dependencies=[Depends(require_permission("treasury", "cerrar"))])
async def cerrar(cid: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    c = await _conciliacion(session, empresa_id, cid)
    try:
        periodo = await cerrar_periodo(session, empresa_id=empresa_id, conciliacion=c)
    except CierreError as exc:
        _fail(exc)
    return {
        "periodo_id": str(periodo.id),
        "numero_periodo": periodo.numero_periodo,
        "fecha_inicio": periodo.fecha_inicio.isoformat(),
        "fecha_fin": periodo.fecha_fin.isoformat(),
        "saldo_banco": f"{periodo.saldo_banco:0.4f}",
        "saldo_libros": f"{periodo.saldo_libros:0.4f}",
        "diferencia": "0.0000",
    }


@router.get("/periodos-conciliados", dependencies=[Depends(require_permission("treasury", "ver"))])
async def listar_periodos(
    empresa_id: EmpresaDep, session: SesionDep,
    ejercicio: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    condiciones = [PeriodoConciliado.empresa_id == empresa_id]
    if ejercicio is not None:
        condiciones.append(PeriodoConciliado.ejercicio == ejercicio)
    total = await session.scalar(select(func.count(PeriodoConciliado.id)).where(*condiciones))
    filas = (
        await session.scalars(
            select(PeriodoConciliado).where(*condiciones).order_by(PeriodoConciliado.numero_periodo).limit(limit).offset(offset)
        )
    ).all()
    return {
        "total": total or 0,
        "items": [
            {
                "id": str(p.id), "numero_periodo": p.numero_periodo, "ejercicio": p.ejercicio,
                "cuenta_id": p.cuenta_id, "fecha_inicio": p.fecha_inicio.isoformat(),
                "fecha_fin": p.fecha_fin.isoformat(),
                "saldo_banco": f"{p.saldo_banco:0.4f}", "saldo_libros": f"{p.saldo_libros:0.4f}",
            }
            for p in filas
        ],
    }


@router.post("/conciliaciones/{cid}/alertas/{alerta_id}/resolver", dependencies=[Depends(require_permission("treasury", "editar"))])
async def resolver_alerta(cid: uuid.UUID, alerta_id: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    alerta = await session.scalar(
        select(AlertaConciliacion).where(
            AlertaConciliacion.empresa_id == empresa_id,
            AlertaConciliacion.conciliacion_id == cid,
            AlertaConciliacion.id == alerta_id,
        )
    )
    if alerta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta inexistente")
    alerta.estado = EstadoAlerta.resuelta
    await session.flush()
    return {"alerta_id": str(alerta.id), "estado": alerta.estado.value}


@router.post("/conciliaciones/{cid}/alertas", dependencies=[Depends(require_permission("treasury", "editar"))])
async def crear_alertas(cid: uuid.UUID, empresa_id: EmpresaDep, session: SesionDep):
    c = await _conciliacion(session, empresa_id, cid)
    creadas = await generar_alertas(session, empresa_id, c)
    return {"n_alertas": len(creadas)}
