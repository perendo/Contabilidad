"""Cesión de cobros (SPEC-022 US3): factoring/confirming con comisión.

Una cesión transfiere el derecho de cobro de vencimientos ``pendientes`` a una
entidad financiera. Se registra con su comisión (importe fijo o porcentaje y
el asiento Debe 572 (neto) + 662 (comisión) | Haber 430 (total)), los
vencimientos pasan a ``cedido`` (FR-005: no pueden cobrarse de nuevo) y se
puede registrar la notificación al deudor (FR-004). ``saldar_cesion``
reconcilia la operación cuando la entidad cobra al cliente sin generar asiento
adicional (la deuda ya está saldada en la cesión).

Multi-tenant estricto (constitución III): la empresa activa se pasa como
parámetro y nunca proviene del cliente.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.cesion import (
    CesionCobro,
    CesionCobroDetalle,
    EstadoCesion,
    TipoComisionCesion,
)
from models.treasury.notificacion_cesion import (
    EstadoNotificacion,
    MedioNotificacion,
    NotificacionCesion,
)
from services.accounting import verificar_balance
from services.audit import registrar_auditoria
from services.treasury.common import (
    CUENTA_BANCO,
    CUENTA_CLIENTES,
    CUENTA_INTERESES_DEUDAS,
    TesoreriaError,
    ejercicio_abierto,
)


class CesionError(TesoreriaError):
    pass


def _cuantizar(valor: Decimal | str) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.0000"))


def _calcular_comision(
    tipo_comision: TipoComisionCesion,
    comision: str,
    total: Decimal,
) -> tuple[Decimal, Decimal]:
    if tipo_comision == TipoComisionCesion.IMPORTE_FIJO:
        comision_d = _cuantizar(comision)
    else:
        porcentaje = _cuantizar(comision)
        comision_d = (total * porcentaje / Decimal("100.0000")).quantize(
            Decimal("0.0000")
        )
    if comision_d < 0:
        raise CesionError("comision_invalida", 422, "La comisión no puede ser negativa")
    neto = (total - comision_d).quantize(Decimal("0.0000"))
    if neto < 0:
        raise CesionError(
            "comision_invalida", 422, "La comisión supera el importe total cedido"
        )
    return comision_d, neto


def _asiento_cesion(
    *,
    empresa_id: int,
    ejercicio: int,
    fecha: date,
    total: Decimal,
    comision: Decimal,
    entidad: str,
) -> tuple[JournalEntry, list[JournalEntryLine]]:
    neto = (total - comision).quantize(Decimal("0.0000"))
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=JournalEntryTipo.COBRO,
        concepto=f"Cesión de cobros a {entidad}",
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    lineas = [
        JournalEntryLine(
            empresa_id=empresa_id, journal_entry_id=asiento.id,
            cuenta=CUENTA_BANCO, debe=neto, haber=Decimal(0),
        ),
    ]
    if comision > 0:
        lineas.append(
            JournalEntryLine(
                empresa_id=empresa_id, journal_entry_id=asiento.id,
                cuenta=CUENTA_INTERESES_DEUDAS, debe=comision, haber=Decimal(0),
            )
        )
    lineas.append(
        JournalEntryLine(
            empresa_id=empresa_id, journal_entry_id=asiento.id,
            cuenta=CUENTA_CLIENTES, debe=Decimal(0), haber=total,
        )
    )
    verificar_balance(lineas)
    return asiento, lineas


async def _persistir_asiento(
    db: AsyncSession,
    asiento: JournalEntry,
    lineas: list[JournalEntryLine],
) -> None:
    db.add(asiento)
    await db.flush()
    for linea in lineas:
        db.add(linea)
    await db.flush()


async def registrar_cesion(
    db: AsyncSession,
    *,
    empresa_id: int,
    entidad_financiera: str,
    fecha_cesion: date,
    vencimiento_ids: list[uuid.UUID],
    comision: str,
    tipo_comision: TipoComisionCesion,
    notas: str | None = None,
    actor: str | None = None,
) -> CesionCobro:
    if not vencimiento_ids:
        raise CesionError("sin_vencimientos", 422, "Debe indicar al menos un vencimiento")
    if len(set(vencimiento_ids)) != len(vencimiento_ids):
        raise CesionError(
            "vencimientos_duplicados", 422, "No se puede ceder un vencimiento repetido"
        )
    await ejercicio_abierto(db, empresa_id, fecha_cesion, CesionError)

    vencimientos: list[Vencimiento] = []
    for vid in vencimiento_ids:
        v = await db.scalar(
            select(Vencimiento).where(
                Vencimiento.empresa_id == empresa_id, Vencimiento.id == vid
            )
        )
        if v is None:
            raise CesionError(
                "vencimiento_no_encontrado", 422, "Vencimiento inexistente para la empresa activa"
            )
        if v.estado != EstadoVencimiento.pendiente:
            raise CesionError(
                "vencimiento_no_pendiente",
                409,
                f"El vencimiento {v.recibo_num} no está pendiente",
            )
        vencimientos.append(v)

    total = sum((v.importe for v in vencimientos), Decimal(0)).quantize(Decimal("0.0000"))
    comision_d, neto = _calcular_comision(tipo_comision, comision, total)

    asiento, lineas = _asiento_cesion(
        empresa_id=empresa_id,
        ejercicio=fecha_cesion.year,
        fecha=fecha_cesion,
        total=total,
        comision=comision_d,
        entidad=entidad_financiera,
    )
    await _persistir_asiento(db, asiento, lineas)

    cesion = CesionCobro(
        empresa_id=empresa_id,
        entidad_financiera=entidad_financiera,
        fecha_cesion=fecha_cesion,
        comision=comision_d,
        tipo_comision=tipo_comision,
        importe_total_cedido=total,
        importe_neto_recibido=neto,
        estado=EstadoCesion.activa,
        asiento_id=asiento.id,
        notas=notas,
        created_by=actor,
    )
    db.add(cesion)
    await db.flush()

    for v in vencimientos:
        db.add(
            CesionCobroDetalle(
                empresa_id=empresa_id,
                cesion_id=cesion.id,
                vencimiento_id=v.id,
                importe=v.importe,
            )
        )
        v.estado = EstadoVencimiento.cedido
    await db.flush()

    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        operacion="REGISTRAR_CESION",
        entidad="cesion_cobro",
        entidad_id=cesion.id,
        payload={
            "entidad_financiera": entidad_financiera,
            "fecha_cesion": fecha_cesion.isoformat(),
            "importe_total_cedido": f"{total:0.4f}",
            "comision": f"{comision_d:0.4f}",
            "importe_neto_recibido": f"{neto:0.4f}",
            "n_vencimientos": len(vencimientos),
            "asiento_id": str(asiento.id),
        },
    )
    await db.flush()
    return cesion


async def contar_vencimientos(
    db: AsyncSession, *, empresa_id: int, cesion_id: uuid.UUID
) -> int:
    n = await db.scalar(
        select(func.count()).select_from(CesionCobroDetalle).where(
            CesionCobroDetalle.empresa_id == empresa_id,
            CesionCobroDetalle.cesion_id == cesion_id,
        )
    )
    return int(n or 0)


async def registrar_notificacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    cesion_id: uuid.UUID,
    cliente_id: uuid.UUID,
    medio: MedioNotificacion,
    fecha_notificacion: date,
    notas: str | None = None,
    actor: str | None = None,
) -> NotificacionCesion:
    cesion = await db.scalar(
        select(CesionCobro).where(
            CesionCobro.empresa_id == empresa_id, CesionCobro.id == cesion_id
        )
    )
    if cesion is None:
        raise CesionError("cesion_no_encontrada", 404, "Cesión inexistente")
    cliente = await db.scalar(
        select(Tercero).where(Tercero.empresa_id == empresa_id, Tercero.id == cliente_id)
    )
    if cliente is None:
        raise CesionError("cliente_no_encontrado", 404, "Cliente inexistente para la empresa activa")

    detalle_vencimientos = select(CesionCobroDetalle.vencimiento_id).where(
        CesionCobroDetalle.empresa_id == empresa_id,
        CesionCobroDetalle.cesion_id == cesion_id,
    )
    n = await db.scalar(
        select(func.count()).select_from(Vencimiento).where(
            Vencimiento.empresa_id == empresa_id,
            Vencimiento.id.in_(detalle_vencimientos),
            Vencimiento.tercero_id == cliente_id,
        )
    )
    if not n:
        raise CesionError(
            "cliente_no_asociado", 422, "El cliente no está asociado a los vencimientos de la cesión"
        )

    notificacion = NotificacionCesion(
        empresa_id=empresa_id,
        cesion_id=cesion.id,
        cliente_id=cliente_id,
        fecha_notificacion=fecha_notificacion,
        medio=medio,
        estado=EstadoNotificacion.enviada,
        notas=notas,
        created_by=actor,
    )
    db.add(notificacion)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        operacion="NOTIFICAR_CESION",
        entidad="notificacion_cesion",
        entidad_id=notificacion.id,
        payload={
            "cesion_id": str(cesion.id),
            "cliente_id": str(cliente_id),
            "medio": medio.value,
            "fecha_notificacion": fecha_notificacion.isoformat(),
        },
    )
    await db.flush()
    return notificacion


async def saldar_cesion(
    db: AsyncSession,
    *,
    empresa_id: int,
    cesion_id: uuid.UUID,
    fecha_saldado: date,
    actor: str | None = None,
) -> CesionCobro:
    cesion = await db.scalar(
        select(CesionCobro).where(
            CesionCobro.empresa_id == empresa_id, CesionCobro.id == cesion_id
        )
    )
    if cesion is None:
        raise CesionError("cesion_no_encontrada", 404, "Cesión inexistente")
    if cesion.estado != EstadoCesion.activa:
        raise CesionError("cesion_no_activa", 409, "La cesión no está activa")
    await ejercicio_abierto(db, empresa_id, fecha_saldado, CesionError)

    cesion.estado = EstadoCesion.saldada
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        operacion="SALDAR_CESION",
        entidad="cesion_cobro",
        entidad_id=cesion.id,
        payload={"fecha_saldado": fecha_saldado.isoformat()},
    )
    await db.flush()
    return cesion


async def listar_cesiones(
    db: AsyncSession,
    *,
    empresa_id: int,
    estado: str | None = None,
    entidad_financiera: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    pagina: int = 1,
    tamano: int = 20,
) -> tuple[list[dict], int]:
    filtros = [CesionCobro.empresa_id == empresa_id]
    if estado is not None:
        filtros.append(CesionCobro.estado == estado)
    if entidad_financiera:
        filtros.append(CesionCobro.entidad_financiera.ilike(f"%{entidad_financiera}%"))
    if fecha_desde is not None:
        filtros.append(CesionCobro.fecha_cesion >= fecha_desde)
    if fecha_hasta is not None:
        filtros.append(CesionCobro.fecha_cesion <= fecha_hasta)

    total = await db.scalar(
        select(func.count()).select_from(CesionCobro).where(*filtros)
    )
    cesiones = (
        await db.scalars(
            select(CesionCobro)
            .where(*filtros)
            .order_by(CesionCobro.fecha_cesion.desc(), CesionCobro.created_at.desc())
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    items = []
    for c in cesiones:
        n = await db.scalar(
            select(func.count()).select_from(CesionCobroDetalle).where(
                CesionCobroDetalle.empresa_id == empresa_id,
                CesionCobroDetalle.cesion_id == c.id,
            )
        )
        items.append(
            {
                "id": c.id,
                "entidad_financiera": c.entidad_financiera,
                "fecha_cesion": c.fecha_cesion.isoformat(),
                "importe_total_cedido": f"{c.importe_total_cedido:0.4f}",
                "comision": f"{c.comision:0.4f}",
                "estado": c.estado.value,
                "n_vencimientos": int(n or 0),
            }
        )
    return items, int(total or 0)


async def detalle_cesion(
    db: AsyncSession, *, empresa_id: int, cesion_id: uuid.UUID
) -> dict:
    cesion = await db.scalar(
        select(CesionCobro).where(
            CesionCobro.empresa_id == empresa_id, CesionCobro.id == cesion_id
        )
    )
    if cesion is None:
        raise CesionError("cesion_no_encontrada", 404, "Cesión inexistente")

    vencimientos = (
        await db.execute(
            select(Vencimiento, Tercero.nombre)
            .select_from(CesionCobroDetalle)
            .join(
                Vencimiento,
                (Vencimiento.empresa_id == CesionCobroDetalle.empresa_id)
                & (Vencimiento.id == CesionCobroDetalle.vencimiento_id),
            )
            .outerjoin(
                Tercero,
                (Tercero.empresa_id == Vencimiento.empresa_id)
                & (Tercero.id == Vencimiento.tercero_id),
            )
            .where(
                CesionCobroDetalle.empresa_id == empresa_id,
                CesionCobroDetalle.cesion_id == cesion.id,
            )
        )
    ).all()
    notificaciones = (
        await db.scalars(
            select(NotificacionCesion)
            .where(
                NotificacionCesion.empresa_id == empresa_id,
                NotificacionCesion.cesion_id == cesion.id,
            )
            .order_by(NotificacionCesion.fecha_notificacion)
        )
    ).all()

    return {
        "id": cesion.id,
        "entidad_financiera": cesion.entidad_financiera,
        "fecha_cesion": cesion.fecha_cesion.isoformat(),
        "comision": f"{cesion.comision:0.4f}",
        "tipo_comision": cesion.tipo_comision.value,
        "importe_total_cedido": f"{cesion.importe_total_cedido:0.4f}",
        "importe_neto_recibido": f"{cesion.importe_neto_recibido:0.4f}",
        "estado": cesion.estado.value,
        "asiento_id": cesion.asiento_id,
        "notas": cesion.notas,
        "vencimientos": [
            {
                "vencimiento_id": v.id,
                "recibo_num": v.recibo_num,
                "tercero_id": v.tercero_id,
                "tercero_nombre": nombre or "",
                "importe": f"{v.importe:0.4f}",
                "estado": f"{v.estado.value}",
            }
            for v, nombre in vencimientos
        ],
        "notificaciones": [
            {
                "id": n.id,
                "cliente_id": n.cliente_id,
                "fecha_notificacion": n.fecha_notificacion.isoformat(),
                "medio": n.medio.value,
                "estado": n.estado.value,
            }
            for n in notificaciones
        ],
    }