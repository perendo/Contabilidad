"""Reapertura controlada de periodos cerrados (SPEC-028 T044-T046, US3).

Research D6/D7: la reapertura es un flujo con estados y trazabilidad completa

    pendiente -> aprobada -> reabierta -> cerrada   (o -> rechazada)

y exige justificacion (FR-006), una sola solicitud activa por periodo (FR-005)
y la publicacion de un asiento `ADJUSTMENT`/`REVERSAL` **balanceado** cuya
fecha cae en el rango reabierto (FR-004). El asiento original nunca se
modifica: la correccion es un asiento nuevo enlazado (constitucion II).

Al aprobarse, el periodo pasa a `reabierto_ajuste`, que deja de ser bloqueante
para que el asiento rectificativo pueda asentarse; al cerrar el ajuste, el
periodo vuelve a `cerrado_ajustado` con `n_reaperturas + 1`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.closing.cierre_ejercicio import CierreEjercicio, EstadoCierreEjercicio
from models.closing.periodo_cerrado import (
    ESTADOS_BLOQUEANTES,
    EstadoPeriodo,
    PeriodoCerrado,
)
from models.closing.solicitud_reapertura import (
    ESTADOS_ACTIVOS,
    EstadoSolicitud,
    SolicitudReapertura,
    TipoPeriodoReapertura,
)
from services.audit.writer import audit_escribir
from services.cashflow.utils import c4
from services.closing.errores import error
from services.closing.reglas_cierre import (
    rango_periodo,
    validar_ejercicio_cerrado,
    validar_motivo,
    validar_reapertura_autorizada,
)
from services.closing.secuencia import next_numero_solicitud

#: Tipos de asiento admitidos como rectificacion (FR-004 / research D7).
TIPOS_RECTIFICACION: frozenset[JournalEntryTipo] = frozenset(
    {JournalEntryTipo.ADJUSTMENT, JournalEntryTipo.REVERSAL}
)


async def _periodo_de_solicitud(
    db: AsyncSession,
    empresa_id: int,
    ejercicio: int,
    tipo_periodo: TipoPeriodoReapertura,
    periodo: int | None,
) -> PeriodoCerrado | None:
    """Periodo cerrado de la empresa al que aplica la solicitud."""
    if tipo_periodo is TipoPeriodoReapertura.ANUAL:
        return None
    if periodo is None:
        raise error("periodo_invalido", "La solicitud de un periodo necesita su numero", 422)
    from models.closing.periodo_cerrado import TipoPeriodo

    # El rango se valida contra el calendario antes de buscar la fila, para que un
    # `periodo` fuera de rango sea 422 y no un 404 de recurso inexistente.
    tipo = TipoPeriodo(tipo_periodo.value)
    rango_periodo(ejercicio, tipo, periodo)
    fila = await db.scalar(
        select(PeriodoCerrado).where(
            PeriodoCerrado.empresa_id == empresa_id,
            PeriodoCerrado.ejercicio == ejercicio,
            PeriodoCerrado.tipo == tipo,
            PeriodoCerrado.periodo == periodo,
        )
    )
    if fila is None:
        raise error(
            "periodo_no_cerrado",
            f"El periodo {tipo.value} {periodo} de {ejercicio} no existe en la empresa activa",
            404,
        )
    return fila


async def _solicitud_activa(
    db: AsyncSession, empresa_id: int, periodo_id: uuid.UUID
) -> SolicitudReapertura | None:
    """Solicitud viva del periodo (FR-005: una a la vez)."""
    return await db.scalar(
        select(SolicitudReapertura)
        .where(
            SolicitudReapertura.empresa_id == empresa_id,
            SolicitudReapertura.periodo_id == periodo_id,
            SolicitudReapertura.estado.in_(sorted(ESTADOS_ACTIVOS)),
        )
        .order_by(SolicitudReapertura.numero_solicitud)
        .limit(1)
    )


async def _solicitud_anual_activa(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> SolicitudReapertura | None:
    return await db.scalar(
        select(SolicitudReapertura)
        .where(
            SolicitudReapertura.empresa_id == empresa_id,
            SolicitudReapertura.ejercicio == ejercicio,
            SolicitudReapertura.tipo_periodo == TipoPeriodoReapertura.ANUAL,
            SolicitudReapertura.estado.in_(sorted(ESTADOS_ACTIVOS)),
        )
        .order_by(SolicitudReapertura.numero_solicitud)
        .limit(1)
    )


async def solicitar_reapertura(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipo_periodo: str | TipoPeriodoReapertura,
    periodo: int | None = None,
    motivo: str | None = None,
    nota_impacto: str | None = None,
    actor: str | None = None,
    ip: str | None = None,
) -> SolicitudReapertura:
    """Registra la solicitud en `pendiente` con justificacion y numero correlativo."""
    try:
        tipo = (
            tipo_periodo
            if isinstance(tipo_periodo, TipoPeriodoReapertura)
            else TipoPeriodoReapertura(str(tipo_periodo).strip().upper())
        )
    except ValueError:
        raise error(
            "tipo_periodo_invalido", f"Tipo de periodo no soportado: {tipo_periodo!r}", 422
        ) from None
    texto_motivo = await validar_motivo(motivo)

    if tipo is TipoPeriodoReapertura.ANUAL:
        await validar_ejercicio_cerrado(db, empresa_id, ejercicio)
        existente = await _solicitud_anual_activa(db, empresa_id, ejercicio)
        if existente is not None:
            raise error(
                "solicitud_activa",
                f"Ya existe una solicitud activa para el ejercicio {ejercicio}",
                409,
            )
        periodo_fila = None
    else:
        periodo_fila = await _periodo_de_solicitud(db, empresa_id, ejercicio, tipo, periodo)
        assert periodo_fila is not None
        if periodo_fila.estado not in ESTADOS_BLOQUEANTES:
            raise error(
                "periodo_no_cerrado",
                (
                    f"El periodo {tipo.value} {periodo} esta en estado "
                    f"{periodo_fila.estado.value}: no procede la reapertura"
                ),
                409,
            )
        existente = await _solicitud_activa(db, empresa_id, periodo_fila.id)
        if existente is not None:
            raise error(
                "solicitud_activa",
                (
                    f"El periodo ya tiene la solicitud {existente.numero_solicitud} "
                    f"en estado {existente.estado.value}"
                ),
                409,
            )

    await validar_reapertura_autorizada(db, empresa_id, ejercicio, nota_impacto)

    numero = await next_numero_solicitud(db, empresa_id, ejercicio)
    fila = SolicitudReapertura(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        numero_solicitud=numero,
        periodo_id=periodo_fila.id if periodo_fila is not None else None,
        tipo_periodo=tipo,
        periodo=periodo,
        motivo=texto_motivo,
        estado=EstadoSolicitud.pendiente,
        usuario_solicitante=actor,
        fecha_solicitud=datetime.now(timezone.utc),
        nota_impacto=nota_impacto,
    )
    db.add(fila)
    await db.flush()

    if tipo is TipoPeriodoReapertura.ANUAL:
        cierre = await db.scalar(
            select(CierreEjercicio).where(
                CierreEjercicio.empresa_id == empresa_id,
                CierreEjercicio.ejercicio == ejercicio,
            )
        )
        if cierre is not None and cierre.estado == EstadoCierreEjercicio.completado:
            cierre.estado = EstadoCierreEjercicio.reapertura_pendiente
            await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="SOLICITAR_REAPERTURA",
        entity="solicitud_reapertura",
        entity_id=str(fila.id),
        ip=ip,
        payload={
            "numero_solicitud": numero,
            "ejercicio": ejercicio,
            "tipo_periodo": tipo.value,
            "periodo": periodo,
            "motivo": texto_motivo,
            "nota_impacto": nota_impacto,
        },
    )
    await db.flush()
    return fila


async def obtener_solicitud(
    db: AsyncSession, *, empresa_id: int, solicitud_id: uuid.UUID
) -> SolicitudReapertura:
    """Solicitud de la empresa activa; 404 si no existe (aislamiento III)."""
    fila = await db.scalar(
        select(SolicitudReapertura).where(
            SolicitudReapertura.empresa_id == empresa_id,
            SolicitudReapertura.id == solicitud_id,
        )
    )
    if fila is None:
        raise error(
            "solicitud_no_encontrada",
            "Solicitud de reapertura inexistente en la empresa activa",
            404,
        )
    return fila


async def _periodo_bloqueado(
    db: AsyncSession, empresa_id: int, periodo_id: uuid.UUID | None
) -> PeriodoCerrado:
    assert periodo_id is not None
    fila = await db.scalar(
        select(PeriodoCerrado).where(
            PeriodoCerrado.empresa_id == empresa_id, PeriodoCerrado.id == periodo_id
        )
    )
    if fila is None:
        raise error(
            "periodo_no_encontrado", "Periodo de cierre inexistente en la empresa activa", 404
        )
    return fila


async def aprobar_reapertura(
    db: AsyncSession,
    *,
    empresa_id: int,
    solicitud_id: uuid.UUID,
    actor: str | None = None,
    ip: str | None = None,
) -> SolicitudReapertura:
    """Aprueba la solicitud y desbloquea temporalmente el periodo (T045)."""
    fila = await obtener_solicitud(db, empresa_id=empresa_id, solicitud_id=solicitud_id)
    if fila.estado != EstadoSolicitud.pendiente:
        raise error(
            "estado_invalido",
            f"La solicitud {fila.numero_solicitud} esta en estado {fila.estado.value}",
            409,
        )
    await validar_reapertura_autorizada(db, empresa_id, fila.ejercicio, fila.nota_impacto)
    fila.estado = EstadoSolicitud.aprobada
    fila.aprobada_por = actor
    fila.fecha_aprobacion = datetime.now(timezone.utc)
    await db.flush()

    if fila.periodo_id is not None:
        periodo = await _periodo_bloqueado(db, empresa_id, fila.periodo_id)
        if periodo.estado not in ESTADOS_BLOQUEANTES:
            raise error(
                "estado_invalido",
                f"El periodo esta en estado {periodo.estado.value} y no admite reapertura",
                409,
            )
        # Estado no bloqueante: el asiento rectificativo ya puede asentarse.
        periodo.estado = EstadoPeriodo.reabierto_ajuste
        await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="APROBAR_REAPERTURA",
        entity="solicitud_reapertura",
        entity_id=str(fila.id),
        ip=ip,
        payload={
            "numero_solicitud": fila.numero_solicitud,
            "periodo_id": str(fila.periodo_id) if fila.periodo_id is not None else None,
        },
    )
    await db.flush()
    return fila


async def rechazar_reapertura(
    db: AsyncSession,
    *,
    empresa_id: int,
    solicitud_id: uuid.UUID,
    actor: str | None = None,
    ip: str | None = None,
) -> SolicitudReapertura:
    """Rechaza la solicitud; el periodo permanece bloqueado."""
    fila = await obtener_solicitud(db, empresa_id=empresa_id, solicitud_id=solicitud_id)
    if fila.estado != EstadoSolicitud.pendiente:
        raise error(
            "estado_invalido",
            f"La solicitud {fila.numero_solicitud} esta en estado {fila.estado.value}",
            409,
        )
    fila.estado = EstadoSolicitud.rechazada
    fila.aprobada_por = actor
    fila.fecha_aprobacion = datetime.now(timezone.utc)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="RECHAZAR_REAPERTURA",
        entity="solicitud_reapertura",
        entity_id=str(fila.id),
        ip=ip,
        payload={"numero_solicitud": fila.numero_solicitud},
    )
    await db.flush()
    return fila


async def marcar_reabierta(
    db: AsyncSession,
    *,
    empresa_id: int,
    solicitud_id: uuid.UUID,
    actor: str | None = None,
    ip: str | None = None,
) -> SolicitudReapertura:
    """Aprueba y ejecuta la reapertura: el periodo queda abierto al ajuste.

    La aprobacion y la ejecucion se emiten como dos acciones separadas para que
    la UI pueda exigir la confirmacion del responsable (FR-003) antes de
    desbloquear el periodo.
    """
    fila = await aprobar_reapertura(
        db, empresa_id=empresa_id, solicitud_id=solicitud_id, actor=actor, ip=ip
    )
    fila.estado = EstadoSolicitud.reabierta
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="REABRIR_PERIODO",
        entity="solicitud_reapertura",
        entity_id=str(fila.id),
        ip=ip,
        payload={"numero_solicitud": fila.numero_solicitud},
    )
    await db.flush()
    return fila


def _sumas_asiento(
    filas: list[tuple[Any, Any]],
) -> tuple[Decimal, Decimal]:
    debe = c4(sum((c4(fila[0]) for fila in filas), Decimal(0)))
    haber = c4(sum((c4(fila[1]) for fila in filas), Decimal(0)))
    return debe, haber


async def rectificar_reapertura(
    db: AsyncSession,
    *,
    empresa_id: int,
    solicitud_id: uuid.UUID,
    asiento_id: uuid.UUID,
    actor: str | None = None,
    ip: str | None = None,
) -> SolicitudReapertura:
    """Enlaza el asiento rectificativo y re-cierra el periodo (T046)."""
    fila = await obtener_solicitud(db, empresa_id=empresa_id, solicitud_id=solicitud_id)
    if fila.estado not in (EstadoSolicitud.reabierta, EstadoSolicitud.aprobada):
        raise error(
            "solicitud_no_reabierta",
            (
                f"La solicitud {fila.numero_solicitud} esta en estado {fila.estado.value}: "
                "no se puede rectificar"
            ),
            409,
        )
    if fila.periodo_id is None:
        raise error(
            "reapertura_anual_no_rectificable",
            "La reapertura del ejercicio completo no se cierra con un asiento rectificativo",
            409,
        )
    periodo = await _periodo_bloqueado(db, empresa_id, fila.periodo_id)

    asiento = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id, JournalEntry.id == asiento_id
        )
    )
    if asiento is None:
        raise error(
            "asiento_no_encontrado", "Asiento rectificativo inexistente en la empresa activa", 404
        )
    if asiento.estado != JournalEntryEstado.POSTED:
        raise error(
            "asiento_no_asentado", "El asiento rectificativo debe estar POSTED", 409
        )
    if asiento.tipo not in TIPOS_RECTIFICACION:
        raise error(
            "asiento_tipo_invalido",
            (
                f"El asiento es de tipo {asiento.tipo.value}; la rectificacion exige "
                "ADJUSTMENT o REVERSAL"
            ),
            409,
        )
    if not (periodo.fecha_ini <= asiento.fecha <= periodo.fecha_fin):
        raise error(
            "fecha_fuera_de_rango",
            (
                f"La fecha {asiento.fecha.isoformat()} del asiento cae fuera del periodo "
                f"reabierto ({periodo.fecha_ini.isoformat()}..{periodo.fecha_fin.isoformat()})"
            ),
            409,
        )
    await _cuadrar_asiento(db, empresa_id, asiento.id)

    fila.asiento_rectificacion_id = asiento.id
    fila.fecha_cierre_efectivo = datetime.now(timezone.utc)
    fila.estado = EstadoSolicitud.cerrada
    periodo.estado = EstadoPeriodo.cerrado_ajustado
    periodo.n_reaperturas = (periodo.n_reaperturas or 0) + 1
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="RECTIFICAR_REAPERTURA",
        entity="solicitud_reapertura",
        entity_id=str(fila.id),
        ip=ip,
        payload={
            "numero_solicitud": fila.numero_solicitud,
            "asiento_rectificacion_id": str(asiento.id),
            "periodo_id": str(periodo.id),
            "n_reaperturas": periodo.n_reaperturas,
        },
    )
    await db.flush()
    return fila


async def _cuadrar_asiento(
    db: AsyncSession, empresa_id: int, asiento_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    """Re-verifica la partida doble del asiento enlazado (research D7)."""
    from models.acct.journal import JournalEntryLine

    filas = (
        await db.execute(
            select(JournalEntryLine.debe, JournalEntryLine.haber).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == asiento_id,
            )
        )
    ).all()
    debe, haber = _sumas_asiento([(fila[0], fila[1]) for fila in filas])
    if debe != haber or debe <= 0:
        raise error(
            "asiento_desbalanceado",
            f"Asiento rectificativo desbalanceado: Debe {debe:0.4f} != Haber {haber:0.4f}",
            409,
        )
    return debe, haber


async def listar_solicitudes(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    estado: str | None = None,
    tipo_periodo: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Listado tenant-scoped con filtros y paginacion (FR-006)."""
    filtros: list[Any] = [SolicitudReapertura.empresa_id == empresa_id]
    if ejercicio is not None:
        filtros.append(SolicitudReapertura.ejercicio == ejercicio)
    if estado:
        filtros.append(SolicitudReapertura.estado == EstadoSolicitud(str(estado).lower()))
    if tipo_periodo:
        filtros.append(
            SolicitudReapertura.tipo_periodo
            == TipoPeriodoReapertura(str(tipo_periodo).upper())
        )
    total = await db.scalar(
        select(func.count()).select_from(SolicitudReapertura).where(*filtros)
    )
    filas = (
        await db.scalars(
            select(SolicitudReapertura)
            .where(*filtros)
            .order_by(SolicitudReapertura.ejercicio.desc(), SolicitudReapertura.numero_solicitud)
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
        )
    ).all()
    return {"items": list(filas), "total": int(total or 0), "page": page}


def rango_solicitud(tipo: TipoPeriodoReapertura, ejercicio: int, periodo: int | None):
    """Rango de fechas del tipo de periodo de la solicitud (`ANUAL` -> año)."""
    if tipo is TipoPeriodoReapertura.ANUAL:
        return date(ejercicio, 1, 1), date(ejercicio, 12, 31)
    from models.closing.periodo_cerrado import TipoPeriodo

    assert periodo is not None
    return rango_periodo(ejercicio, TipoPeriodo(tipo.value), periodo)


__all__ = [
    "ESTADOS_ACTIVOS",
    "TIPOS_RECTIFICACION",
    "aprobar_reapertura",
    "listar_solicitudes",
    "marcar_reabierta",
    "obtener_solicitud",
    "rango_solicitud",
    "rechazar_reapertura",
    "rectificar_reapertura",
    "solicitar_reapertura",
]
