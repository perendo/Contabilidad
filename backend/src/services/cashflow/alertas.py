"""Alertas de liquidez (SPEC-027 US3, T034/T035).

research.md D6: al generar (o regenerar) la prevision se recorre cada bucket y
se crea una `AlertaLiquidez` para todo `saldo_acumulado < 0`. El saldo
exactamente cero NO genera alerta: el spec lo define como "limite de
solvencia" (edge case, SC-004).

La accion sugerida orienta al usuario: `reprogramar_pago` cuando el bucket
negativo tiene un pago que se puede trasladar, `incluir_ingreso` cuando lo que
falta es un ingreso previsto. Ambas acciones se auditan.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.treasury.alerta_liquidez import (
    AccionSugeridaLiquidez,
    AlertaLiquidez,
    EstadoAlertaLiquidez,
)
from models.treasury.movimiento_prevision import (
    MovimientoPrevision,
    OrigenMovimientoPrevision,
    TipoMovimientoPrevision,
)
from models.treasury.prevision import PrevisionTesoreria
from services.audit import registrar_auditoria
from services.cashflow.errores import error
from services.cashflow.utils import c4, fmt

__all__ = [
    "ACCIONES",
    "detectar_alertas",
    "gestionar_alerta",
    "ignorar_alerta",
    "listar_alertas",
    "obtener_alerta",
]

ACCIONES: frozenset[str] = frozenset(
    {a.value for a in AccionSugeridaLiquidez}
)


# --- US3 / T034: deteccion ---------------------------------------------------


async def detectar_alertas(
    db: AsyncSession,
    *,
    empresa_id: int,
    prevision: PrevisionTesoreria,
    buckets: list[dict[str, Any]],
) -> list[AlertaLiquidez]:
    """Crea una alerta por cada bucket con saldo proyectado negativo (FR-003).

    Se invoca dentro de la misma transaccion que genera la prevision, de modo
    que cabecera, movimientos y alertas son indivisibles. El saldo exactamente
    cero no alerta.
    """
    granularidad = prevision.granularidad.value
    creadas: list[AlertaLiquidez] = []
    for bucket in buckets:
        saldo = c4(bucket["saldo_acumulado"])
        if saldo >= 0:
            continue
        pago = await _pago_mayor_del_bucket(
            db,
            empresa_id=empresa_id,
            prevision_id=prevision.id,
            granularidad=granularidad,
            fecha_bucket=bucket["fecha"],
        )
        alerta = AlertaLiquidez(
            empresa_id=empresa_id,
            prevision_id=prevision.id,
            fecha=bucket["fecha"],
            saldo_proyectado=saldo,
            importe_deficit=c4(-saldo),
            estado=EstadoAlertaLiquidez.abierta,
            accion_sugerida=(
                AccionSugeridaLiquidez.reprogramar_pago
                if pago is not None
                else AccionSugeridaLiquidez.incluir_ingreso
            ),
            movimiento_origen_id=pago.id if pago is not None else None,
        )
        db.add(alerta)
        creadas.append(alerta)
    if creadas:
        await db.flush()
    return creadas


async def _pago_mayor_del_bucket(
    db: AsyncSession,
    *,
    empresa_id: int,
    prevision_id: uuid.UUID,
    granularidad: str,
    fecha_bucket: date,
) -> MovimientoPrevision | None:
    """Pago de mayor importe dentro del bucket negativo, o `None`."""
    from services.cashflow.utils import clave_bucket

    pagos = (
        await db.scalars(
            select(MovimientoPrevision)
            .where(
                MovimientoPrevision.empresa_id == empresa_id,
                MovimientoPrevision.prevision_id == prevision_id,
                MovimientoPrevision.incluido.is_(True),
                MovimientoPrevision.tipo == TipoMovimientoPrevision.pago,
            )
            .order_by(MovimientoPrevision.importe.desc(), MovimientoPrevision.id)
        )
    ).all()
    for pago in pagos:
        if pago.fecha_prevista is None:
            continue
        if clave_bucket(pago.fecha_prevista, granularidad) == fecha_bucket:
            return pago
    return None


# --- US3 / T035: gestion de la alerta ---------------------------------------


async def obtener_alerta(
    db: AsyncSession, *, empresa_id: int, alerta_id: uuid.UUID | str
) -> AlertaLiquidez | None:
    """Alerta por id **dentro de la empresa activa** (constitucion III)."""
    return await db.scalar(
        select(AlertaLiquidez).where(
            AlertaLiquidez.empresa_id == empresa_id,
            AlertaLiquidez.id == uuid.UUID(str(alerta_id)),
        )
    )


async def listar_alertas(
    db: AsyncSession,
    *,
    empresa_id: int,
    prevision_id: uuid.UUID | str | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Listado de alertas con filtros, acotado a la empresa activa."""
    consulta = select(AlertaLiquidez).where(AlertaLiquidez.empresa_id == empresa_id)
    if prevision_id is not None:
        consulta = consulta.where(
            AlertaLiquidez.prevision_id == uuid.UUID(str(prevision_id))
        )
    if estado:
        try:
            consulta = consulta.where(AlertaLiquidez.estado == EstadoAlertaLiquidez(estado))
        except ValueError as exc:
            raise error("estado_invalido", f"Estado no soportado: {estado!r}", 422) from exc
    total = int(await db.scalar(select(func.count()).select_from(consulta.subquery())) or 0)
    pagina = max(1, int(page))
    tamano = max(1, int(page_size))
    filas = (
        await db.scalars(
            consulta.order_by(AlertaLiquidez.fecha, AlertaLiquidez.id)
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    return {"items": list(filas), "total": total, "page": pagina}


async def _exigir_abierta(alerta: AlertaLiquidez) -> None:
    if alerta.estado is not EstadoAlertaLiquidez.abierta:
        raise error(
            "alerta_ya_resuelta",
            f"La alerta ya esta {alerta.estado.value}",
            409,
        )


async def _cerrar_alerta(
    db: AsyncSession,
    *,
    alerta: AlertaLiquidez,
    estado: EstadoAlertaLiquidez,
    movimiento_id: uuid.UUID | None,
    actor: str,
    operacion: str,
    payload: dict[str, Any],
) -> AlertaLiquidez:
    alerta.estado = estado
    alerta.movimiento_origen_id = movimiento_id or alerta.movimiento_origen_id
    alerta.atendida_por = actor
    alerta.fecha_atencion = datetime.now(timezone.utc)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=alerta.empresa_id,
        operacion=operacion,
        entidad="alerta_liquidez",
        entidad_id=alerta.id,
        payload={
            "prevision_id": str(alerta.prevision_id),
            "fecha": alerta.fecha.isoformat(),
            "saldo_proyectado": fmt(alerta.saldo_proyectado),
            "importe_deficit": fmt(alerta.importe_deficit),
            "estado": estado.value,
            "movimiento_id": str(alerta.movimiento_origen_id)
            if alerta.movimiento_origen_id
            else None,
            **payload,
        },
        usuario=actor,
    )
    return alerta


async def _reprogramar(
    db: AsyncSession,
    *,
    empresa_id: int,
    alerta: AlertaLiquidez,
    movimiento_id: str | None,
    nueva_fecha: str | None,
    actor: str,
) -> uuid.UUID:
    """Traslada el pago a `nueva_fecha` (research D6, transicion documentada)."""
    if not movimiento_id:
        raise error(
            "movimiento_requerido",
            "La accion reprogramar_pago necesita 'movimiento_id'",
            422,
        )
    if not nueva_fecha:
        raise error(
            "fecha_requerida", "La accion reprogramar_pago necesita 'nueva_fecha'", 422
        )
    movimiento = await db.scalar(
        select(MovimientoPrevision).where(
            MovimientoPrevision.empresa_id == empresa_id,
            MovimientoPrevision.id == uuid.UUID(str(movimiento_id)),
        )
    )
    if movimiento is None:
        raise error(
            "movimiento_no_encontrado",
            "Movimiento de la prevision inexistente en la empresa activa",
            404,
        )
    if movimiento.tipo is not TipoMovimientoPrevision.pago:
        raise error(
            "movimiento_no_pago",
            "Solo un movimiento de tipo 'pago' puede reprogramarse",
            422,
        )
    if movimiento.prevision_id is not None and movimiento.prevision_id != alerta.prevision_id:
        raise error(
            "movimiento_ajeno_a_la_alerta",
            "El movimiento pertenece a otra prevision",
            422,
        )
    try:
        destino = date.fromisoformat(str(nueva_fecha))
    except ValueError as exc:
        raise error("fecha_invalida", f"Fecha no valida: {nueva_fecha!r}", 422) from exc
    anterior = movimiento.fecha_prevista
    movimiento.fecha_prevista = destino
    await db.flush()
    from services.cashflow.proyeccion import reprogramar_en_plan

    prevision = await db.get(PrevisionTesoreria, movimiento.prevision_id)
    if prevision is not None:
        await reprogramar_en_plan(
            db,
            prevision,
            tipo=movimiento.tipo.value,
            importe=c4(movimiento.importe),
            frecuencia=movimiento.frecuencia.value,
            concepto=movimiento.concepto,
            nueva_fecha=destino,
        )
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion="REPROGRAMAR_PAGO",
        entidad="movimiento_prevision",
        entidad_id=movimiento.id,
        payload={
            "fecha_anterior": anterior.isoformat() if anterior else None,
            "fecha_nueva": destino.isoformat(),
            "importe": fmt(movimiento.importe),
        },
        usuario=actor,
    )
    return movimiento.id


async def _incluir_ingreso(
    db: AsyncSession,
    *,
    alerta: AlertaLiquidez,
    importe: str | None,
    nueva_fecha: str | None,
    actor: str,
) -> uuid.UUID:
    """Crea un cobro previsto que cubre el deficit (research D6)."""
    if importe in (None, ""):
        objetivo = alerta.importe_deficit
    else:
        try:
            objetivo = c4(Decimal(str(importe)))
        except ArithmeticError as exc:
            raise error("importe_invalido", f"Importe no decimal: {importe!r}", 422) from exc
        if objetivo <= 0:
            raise error("importe_invalido", "El importe debe ser mayor que cero", 422)
    if nueva_fecha:
        try:
            destino = date.fromisoformat(str(nueva_fecha))
        except ValueError as exc:
            raise error("fecha_invalida", f"Fecha no valida: {nueva_fecha!r}", 422) from exc
    else:
        destino = alerta.fecha
    movimiento = MovimientoPrevision(
        empresa_id=alerta.empresa_id,
        prevision_id=alerta.prevision_id,
        origen=OrigenMovimientoPrevision.cobro_estimado,
        tipo=TipoMovimientoPrevision.cobro,
        importe=c4(objetivo),
        fecha_prevista=destino,
        concepto="Ingreso previsto para cubrir el deficit",
        incluido=True,
    )
    db.add(movimiento)
    await db.flush()
    from services.cashflow.proyeccion import registrar_en_plan

    prevision = await db.get(PrevisionTesoreria, alerta.prevision_id)
    if prevision is not None:
        await registrar_en_plan(
            db,
            prevision,
            {
                "tipo": "cobro",
                "importe": c4(movimiento.importe),
                "frecuencia": "unico",
                "concepto": movimiento.concepto,
                "fecha_prevista": destino,
            },
        )
    await registrar_auditoria(
        db,
        empresa_id=alerta.empresa_id,
        operacion="INCLUIR_INGRESO",
        entidad="movimiento_prevision",
        entidad_id=movimiento.id,
        payload={
            "alerta_id": str(alerta.id),
            "importe": fmt(movimiento.importe),
            "fecha_prevista": destino.isoformat(),
        },
        usuario=actor,
    )
    return movimiento.id


async def gestionar_alerta(
    db: AsyncSession,
    *,
    empresa_id: int,
    alerta_id: uuid.UUID | str,
    accion: str,
    movimiento_id: str | None = None,
    nueva_fecha: str | None = None,
    importe: str | None = None,
    actor: str = "sistema",
) -> AlertaLiquidez:
    """Aplica la accion sugerida y marca la alerta como `atendida` (T035).

    `reprogramar_pago` traslada el `MovimientoPrevision` a `nueva_fecha`;
    `incluir_ingreso` crea un cobro previsto por el deficit. Una alerta ya
    atendida o ignorada devuelve 409 `alerta_ya_resuelta`.
    """
    if accion not in ACCIONES:
        raise error(
            "accion_invalida",
            f"Accion no soportada: {accion!r}. Use {sorted(ACCIONES)}",
            422,
        )
    alerta = await obtener_alerta(db, empresa_id=empresa_id, alerta_id=alerta_id)
    if alerta is None:
        raise error(
            "alerta_no_encontrada",
            "Alerta de liquidez inexistente en la empresa activa",
            404,
        )
    await _exigir_abierta(alerta)

    if accion == AccionSugeridaLiquidez.reprogramar_pago.value:
        nuevo_id = await _reprogramar(
            db,
            empresa_id=empresa_id,
            alerta=alerta,
            movimiento_id=movimiento_id or str(alerta.movimiento_origen_id or ""),
            nueva_fecha=nueva_fecha,
            actor=actor,
        )
        extra = {"accion": accion, "nueva_fecha": nueva_fecha}
    else:
        nuevo_id = await _incluir_ingreso(
            db, alerta=alerta, importe=importe, nueva_fecha=nueva_fecha, actor=actor
        )
        extra = {"accion": accion, "importe": importe or fmt(alerta.importe_deficit)}
    return await _cerrar_alerta(
        db,
        alerta=alerta,
        estado=EstadoAlertaLiquidez.atendida,
        movimiento_id=nuevo_id,
        actor=actor,
        operacion="ATENDER_ALERTA",
        payload=extra,
    )


async def ignorar_alerta(
    db: AsyncSession,
    *,
    empresa_id: int,
    alerta_id: uuid.UUID | str,
    actor: str = "sistema",
) -> AlertaLiquidez:
    """Desestima la alerta de forma trazable (`abierta -> ignorada`)."""
    alerta = await obtener_alerta(db, empresa_id=empresa_id, alerta_id=alerta_id)
    if alerta is None:
        raise error(
            "alerta_no_encontrada",
            "Alerta de liquidez inexistente en la empresa activa",
            404,
        )
    await _exigir_abierta(alerta)
    return await _cerrar_alerta(
        db,
        alerta=alerta,
        estado=EstadoAlertaLiquidez.ignorada,
        movimiento_id=alerta.movimiento_origen_id,
        actor=actor,
        operacion="IGNORAR_ALERTA",
        payload={},
    )
