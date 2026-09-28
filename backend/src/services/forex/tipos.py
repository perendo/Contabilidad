"""Tipos de cambio (SPEC-016 US1/US3): histórico por (empresa, divisa, fecha).

Un solo tipo por (empresa, divisa, fecha). Un tipo usado por un asiento POSTED
queda sellado (``usos_posteados > 0``, ``sellado = true``); sobre sellados solo
se permite incrementar ``usos_posteados`` (también protegido por triggers a
nivel DB, constitución II). Corrección de un no-sellado requiere ``motivo``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.monedas.asiento_divisa import AsientoDivisa
from models.monedas.moneda import Moneda
from models.monedas.tipo_cambio import TipoCambio
from services.audit.writer import audit_escribir
from services.forex.errores import ForexError
from services.forex.monedas import divisa_de_empresa

PAGINA_MIN, PAGINA_MAX = 1, 100


def _cuatro(value: Decimal) -> str:
    return f"{value:0.4f}"


def _ocho(value: Decimal) -> str:
    return f"{value:0.8f}"


def serializar_tipo(tipo: TipoCambio, codigo_iso: str | None = None) -> dict:
    return {
        "id": str(tipo.id),
        "divisa_id": str(tipo.divisa_id),
        "codigo_iso": codigo_iso,
        "fecha": tipo.fecha.isoformat(),
        "ratio": _ocho(tipo.ratio),
        "usos_posteados": tipo.usos_posteados,
        "sellado": tipo.sellado,
    }


def _validar_ratio(valor: str | int | Decimal) -> Decimal:
    try:
        ratio = Decimal(str(valor))
    except InvalidOperation:
        raise ForexError("ratio_invalido", "El ratio no es un número válido")
    if ratio <= 0:
        raise ForexError("ratio_invalido", "El ratio debe ser mayor que 0")
    exponente = ratio.as_tuple().exponent
    if not isinstance(exponente, int) or exponente < -8:
        raise ForexError(
            "ratio_precision_invalida",
            "El ratio admite como máximo 8 decimales",
        )
    return ratio


async def _tipo_por_id(
    db: AsyncSession, empresa_id: int, tipo_id: uuid.UUID
) -> TipoCambio | None:
    return await db.scalar(
        select(TipoCambio).where(
            TipoCambio.empresa_id == empresa_id,
            TipoCambio.id == tipo_id,
        )
    )


async def obtener_tipo(
    db: AsyncSession,
    empresa_id: int,
    divisa_id: uuid.UUID,
    fecha: date,
) -> TipoCambio | None:
    """Tipo vigente de la fecha (coincidencia exacta)."""
    return await db.scalar(
        select(TipoCambio).where(
            TipoCambio.empresa_id == empresa_id,
            TipoCambio.divisa_id == divisa_id,
            TipoCambio.fecha == fecha,
        )
    )


async def registrar_tipo(
    db: AsyncSession,
    *,
    empresa_id: int,
    divisa_id: uuid.UUID,
    ratio: str | int | Decimal,
    fecha: date,
    actor: str | None = None,
) -> dict:
    """Alta de un tipo de cambio (POST /api/v1/tipos-cambio)."""
    moneda = await divisa_de_empresa(db, empresa_id, divisa_id)
    if moneda is None:
        raise ForexError(
            "divisa_no_encontrada",
            "La divisa no pertenece a la empresa activa o no está activa",
        )
    if moneda.es_funcional:
        raise ForexError(
            "divisa_funcional",
            "La moneda funcional no tiene tipo de cambio",
        )
    ratio_dec = _validar_ratio(ratio)
    duplicado = await db.scalar(
        select(TipoCambio.id).where(
            TipoCambio.empresa_id == empresa_id,
            TipoCambio.divisa_id == divisa_id,
            TipoCambio.fecha == fecha,
        )
    )
    if duplicado is not None:
        raise ForexError(
            "tipo_ya_existe",
            "Ya existe un tipo de cambio para esa divisa y fecha",
        )
    tipo = TipoCambio(
        empresa_id=empresa_id,
        divisa_id=divisa_id,
        fecha=fecha,
        ratio=ratio_dec,
        usos_posteados=0,
        sellado=False,
    )
    if tipo.id is None:
        tipo.id = uuid.uuid4()
    db.add(tipo)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREAR_TIPO_CAMBIO",
        entity="tipo_cambio",
        entity_id=str(tipo.id),
        payload={
            "divisa_id": str(divisa_id),
            "fecha": fecha.isoformat(),
            "ratio": _ocho(ratio_dec),
        },
    )
    await db.flush()
    return serializar_tipo(tipo, moneda.codigo_iso)


async def corregir_tipo(
    db: AsyncSession,
    *,
    empresa_id: int,
    tipo_id: uuid.UUID,
    ratio: str | int | Decimal,
    motivo: str,
    actor: str | None = None,
) -> dict:
    """Corrección de un tipo no sellado (PATCH /api/v1/tipos-cambio/{id})."""
    tipo = await _tipo_por_id(db, empresa_id, tipo_id)
    if tipo is None:
        raise ForexError(
            "tipo_no_encontrado",
            "El tipo de cambio no existe en la empresa activa",
        )
    if tipo.sellado:
        raise ForexError(
            "tipo_sellado_inmutable",
            "El tipo de cambio ya está sellado: se usa un nuevo tipo para corregir",
        )
    if not motivo or not motivo.strip():
        raise ForexError("motivo_obligatorio", "La corrección requiere un motivo")
    ratio_dec = _validar_ratio(ratio)
    anterior = tipo.ratio
    tipo.ratio = ratio_dec
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CORREGIR_TIPO_CAMBIO",
        entity="tipo_cambio",
        entity_id=str(tipo.id),
        payload={
            "ratio_anterior": _ocho(anterior),
            "ratio_nuevo": _ocho(ratio_dec),
            "motivo": motivo,
        },
    )
    await db.flush()
    return serializar_tipo(tipo)


async def listar_tipos(
    db: AsyncSession,
    *,
    empresa_id: int,
    divisa_id: uuid.UUID | None = None,
    fecha_gte: date | None = None,
    fecha_lte: date | None = None,
    sellado: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Listado de tipos con filtros (GET /api/v1/tipos-cambio)."""
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise ForexError("page_size_invalido", "page_size debe estar entre 1 y 100")
    filtros = [TipoCambio.empresa_id == empresa_id]
    if divisa_id is not None:
        filtros.append(TipoCambio.divisa_id == divisa_id)
    if fecha_gte is not None:
        filtros.append(TipoCambio.fecha >= fecha_gte)
    if fecha_lte is not None:
        filtros.append(TipoCambio.fecha <= fecha_lte)
    if sellado is not None:
        filtros.append(TipoCambio.sellado.is_(sellado))
    base = select(TipoCambio, Moneda.codigo_iso).join(
        Moneda,
        (Moneda.empresa_id == TipoCambio.empresa_id)
        & (Moneda.id == TipoCambio.divisa_id),
    ).where(*filtros)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    filas = (
        await db.execute(
            base.order_by(TipoCambio.fecha.desc(), Moneda.codigo_iso)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            serializar_tipo(tipo, codigo_iso)
            for tipo, codigo_iso in filas
        ],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


async def historial_tipos(
    db: AsyncSession,
    *,
    empresa_id: int,
    divisa_id: uuid.UUID | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    sellado: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Histórico de tipos por rango de fechas (GET /api/v1/tipos-cambio/historial)."""
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise ForexError("page_size_invalido", "page_size debe estar entre 1 y 100")
    filtros = [TipoCambio.empresa_id == empresa_id]
    if divisa_id is not None:
        filtros.append(TipoCambio.divisa_id == divisa_id)
    if fecha_desde is not None:
        filtros.append(TipoCambio.fecha >= fecha_desde)
    if fecha_hasta is not None:
        filtros.append(TipoCambio.fecha <= fecha_hasta)
    if sellado is not None:
        filtros.append(TipoCambio.sellado.is_(sellado))
    base = select(TipoCambio, Moneda.codigo_iso).join(
        Moneda,
        (Moneda.empresa_id == TipoCambio.empresa_id)
        & (Moneda.id == TipoCambio.divisa_id),
    ).where(*filtros)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    filas = (
        await db.execute(
            base.order_by(TipoCambio.fecha.desc(), Moneda.codigo_iso)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            serializar_tipo(tipo, codigo_iso)
            for tipo, codigo_iso in filas
        ],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


async def obtener_historial_asiento(
    db: AsyncSession,
    empresa_id: int,
    asiento_id: uuid.UUID,
) -> dict | None:
    """Tipo de cambio usado por un asiento registrado en divisa (US3)."""
    ad = await db.scalar(
        select(AsientoDivisa).where(
            AsientoDivisa.empresa_id == empresa_id,
            AsientoDivisa.asiento_id == asiento_id,
        )
    )
    if ad is None:
        return None
    tipo = await _tipo_por_id(db, empresa_id, ad.tipo_cambio_id)
    if tipo is None:
        return None
    return {
        "asiento_id": str(ad.asiento_id),
        "tipo_cambio_id": str(tipo.id),
        "fecha": ad.fecha.isoformat(),
        "ratio": _ocho(tipo.ratio),
        "sellado": tipo.sellado,
    }


async def sellar_tipo(db: AsyncSession, tipo: TipoCambio) -> TipoCambio:
    """Marca un tipo como sellado tras ser usado por un asiento POSTED."""
    tipo.usos_posteados = (tipo.usos_posteados or 0) + 1
    tipo.sellado = True
    await db.flush()
    return tipo


async def obtener_tipo_asiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    divisa_id: uuid.UUID,
    fecha: date,
    tipo_cambio_id: uuid.UUID | None = None,
    ratio_explicito: str | int | Decimal | None = None,
) -> TipoCambio:
    """Resuelve el tipo de cambio para un asiento en divisa.

    Prioridad (documentada en research D2):
    1. ``tipo_cambio_id`` (debe existir y pertenecer a la empresa).
    2. Tipo registrado en la fecha exacta del asiento.
    3. ``ratio_explicito``: si no existe tipo en la fecha, se registra uno nuevo
       con ese ratio (el asiento lo sellará).
    4. Último tipo anterior a la fecha (fallback para operaciones puntuales).
    Si nada existe -> ``sin_tipo_divisa``.
    """
    if tipo_cambio_id is not None:
        tipo = await _tipo_por_id(db, empresa_id, tipo_cambio_id)
        if tipo is None:
            raise ForexError(
                "tipo_invalido",
                "El tipo de cambio indicado no existe en la empresa activa",
            )
        return tipo

    exacto = await obtener_tipo(db, empresa_id, divisa_id, fecha)
    if exacto is not None:
        return exacto

    if ratio_explicito is not None:
        ratio = _validar_ratio(ratio_explicito)
        tipo = TipoCambio(
            empresa_id=empresa_id,
            divisa_id=divisa_id,
            fecha=fecha,
            ratio=ratio,
            usos_posteados=0,
            sellado=False,
        )
        if tipo.id is None:
            tipo.id = uuid.uuid4()
        db.add(tipo)
        await db.flush()
        return tipo

    anterior = await db.scalar(
        select(TipoCambio)
        .where(
            TipoCambio.empresa_id == empresa_id,
            TipoCambio.divisa_id == divisa_id,
            TipoCambio.fecha < fecha,
        )
        .order_by(TipoCambio.fecha.desc())
        .limit(1)
    )
    if anterior is not None:
        return anterior
    raise ForexError(
        "sin_tipo_divisa",
        "No hay tipo de cambio registrado para la divisa en esa fecha",
    )