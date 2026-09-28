"""Servicios de subvenciones (SPEC-019 US1).

La subvención es una entidad de control de gasto (no genera asientos por sí
misma): centraliza `importe_concedido`, la trazabilidad por referencia y el
ciclo de estados concedida → en_curso → justificada → reintegrada. El gasto
real se imputa línea a línea del diario (SPEC-002) vía `justificacion.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ngo.gasto_imputado import GastoImputado
from models.ngo.subvencion import Subvencion, SubvencionEstado
from services.audit.writer import audit_escribir
from services.ngo.errores import NgoError

AÑO_MIN, AÑO_MAX = 2000, 2100
PAGINA_MIN, PAGINA_MAX = 1, 100

_TRANSICIONES = {
    SubvencionEstado.concedida: {SubvencionEstado.en_curso},
    SubvencionEstado.en_curso: {SubvencionEstado.justificada},
    SubvencionEstado.justificada: {SubvencionEstado.reintegrada},
    SubvencionEstado.reintegrada: set(),
}


def _cuatro(value: Decimal) -> str:
    return f"{value:0.4f}"


async def _gastado(db: AsyncSession, empresa_id: int, subvencion_id: uuid.UUID) -> Decimal:
    return Decimal(
        await db.scalar(
            select(func.coalesce(func.sum(GastoImputado.importe_asignado), 0)).where(
                GastoImputado.empresa_id == empresa_id,
                GastoImputado.subvencion_id == subvencion_id,
            )
        )
        or 0
    )


def _resumen(sub: Subvencion, gastado: Decimal) -> dict:
    return {
        "id": str(sub.id),
        "entidad_concedente": sub.entidad_concedente,
        "programa": sub.programa,
        "referencia": sub.referencia,
        "importe_concedido": _cuatro(sub.importe_concedido),
        "ejercicio": sub.ejercicio,
        "estado": sub.estado.value,
        "partidas": sub.partidas,
        "observaciones": sub.observaciones,
        "gastado": _cuatro(gastado),
        "pendiente": _cuatro(sub.importe_concedido - gastado),
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
    }


async def crear_subvencion(
    db: AsyncSession,
    *,
    empresa_id: int,
    entidad_concedente: str,
    programa: str,
    referencia: str | None,
    importe_concedido: Decimal,
    ejercicio: int,
    partidas: list[str] | None = None,
    observaciones: str | None = None,
    actor: str | None = None,
) -> dict:
    if importe_concedido <= 0:
        raise NgoError("importe_invalido", "El importe concedido debe ser positivo")
    if not (AÑO_MIN <= ejercicio <= AÑO_MAX):
        raise NgoError("ejercicio_invalido", "El ejercicio no es válido")
    if referencia:
        existente = await db.scalar(
            select(Subvencion).where(
                Subvencion.empresa_id == empresa_id,
                Subvencion.referencia == referencia,
            )
        )
        if existente is not None:
            raise NgoError("referencia_duplicada", f"Ya existe una subvención con referencia {referencia!r}")

    sub = Subvencion(
        empresa_id=empresa_id,
        entidad_concedente=entidad_concedente.strip(),
        programa=programa.strip(),
        referencia=referencia.strip() if referencia else None,
        importe_concedido=importe_concedido,
        ejercicio=ejercicio,
        estado=SubvencionEstado.concedida,
        partidas=partidas or [],
        observaciones=observaciones.strip() if observaciones else None,
    )
    if sub.id is None:
        sub.id = uuid.uuid4()
    db.add(sub)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREAR_SUBVENCION",
        entity="subvencion",
        entity_id=str(sub.id),
        payload={
            "referencia": sub.referencia,
            "importe": str(sub.importe_concedido),
            "ejercicio": ejercicio,
        },
    )
    await db.flush()
    return _resumen(sub, Decimal(0))


async def listar_subvenciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    estado: str | None = None,
    ejercicio: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise NgoError("page_size_invalido", "page_size debe estar entre 1 y 100")

    filtros = [Subvencion.empresa_id == empresa_id]
    if estado is not None:
        valores = [e.value for e in SubvencionEstado]
        if estado.lower() not in valores:
            raise NgoError("estado_invalido", f"Estado desconocido: {estado}")
        filtros.append(Subvencion.estado == estado.lower())
    if ejercicio is not None:
        filtros.append(Subvencion.ejercicio == ejercicio)

    base = select(Subvencion).where(*filtros)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    subs = (
        await db.scalars(
            base.order_by(Subvencion.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items = []
    for sub in subs:
        gastado = await _gastado(db, empresa_id, sub.id)
        items.append(_resumen(sub, gastado))
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


async def obtener_subvencion(
    db: AsyncSession,
    *,
    empresa_id: int,
    subvencion_id: uuid.UUID,
) -> dict | None:
    sub = await db.scalar(
        select(Subvencion).where(
            Subvencion.empresa_id == empresa_id,
            Subvencion.id == subvencion_id,
        )
    )
    if sub is None:
        return None
    gastado = await _gastado(db, empresa_id, sub.id)
    return _resumen(sub, gastado)


async def editar_subvencion(
    db: AsyncSession,
    *,
    empresa_id: int,
    subvencion_id: uuid.UUID,
    entidad_concedente: str | None,
    programa: str | None,
    referencia: str | None,
    observaciones: str | None,
    partidas: list[str] | None,
    actor: str | None = None,
) -> dict:
    sub = await db.scalar(
        select(Subvencion).where(
            Subvencion.empresa_id == empresa_id,
            Subvencion.id == subvencion_id,
        )
    )
    if sub is None:
        raise NgoError("subvencion_no_encontrada", "La subvención no existe en la empresa activa")

    if referencia is not None and referencia.strip():
        nuevo = referencia.strip()
        existente = await db.scalar(
            select(Subvencion).where(
                Subvencion.empresa_id == empresa_id,
                Subvencion.referencia == nuevo,
                Subvencion.id != sub.id,
            )
        )
        if existente is not None:
            raise NgoError("referencia_duplicada", f"Ya existe una subvención con referencia {nuevo!r}")
        sub.referencia = nuevo
    if entidad_concedente is not None:
        sub.entidad_concedente = entidad_concedente.strip()
    if programa is not None:
        sub.programa = programa.strip()
    if observaciones is not None:
        sub.observaciones = observaciones.strip() or None
    if partidas is not None:
        sub.partidas = partidas
    sub.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="EDITAR_SUBVENCION",
        entity="subvencion",
        entity_id=str(sub.id),
        payload={"referencia": sub.referencia},
    )
    await db.flush()
    gastado = await _gastado(db, empresa_id, sub.id)
    return _resumen(sub, gastado)


async def cambiar_estado_subvencion(
    db: AsyncSession,
    *,
    empresa_id: int,
    subvencion_id: uuid.UUID,
    estado: str,
    asiento_rectificativo_id: uuid.UUID | None = None,
    actor: str | None = None,
) -> dict:
    sub = await db.scalar(
        select(Subvencion).where(
            Subvencion.empresa_id == empresa_id,
            Subvencion.id == subvencion_id,
        )
    )
    if sub is None:
        raise NgoError("subvencion_no_encontrada", "La subvención no existe en la empresa activa")

    destino = estado.lower()
    if destino not in [e.value for e in SubvencionEstado]:
        raise NgoError("estado_invalido", f"Estado desconocido: {estado}")

    destino_enum = SubvencionEstado(destino)
    if destino_enum == sub.estado:
        raise NgoError("transicion_no_permitida", "La subvención ya está en ese estado")
    permitidos = _TRANSICIONES.get(sub.estado, set())
    if destino_enum not in permitidos:
        raise NgoError(
            "transicion_no_permitida",
            f"No se puede pasar de {sub.estado.value} a {destino_enum.value}",
        )
    if destino_enum == SubvencionEstado.reintegrada and asiento_rectificativo_id is None:
        raise NgoError("falta_rectificativo", "Reintegrar exige asiento_rectificativo_id")

    anterior = sub.estado.value
    sub.estado = destino_enum
    sub.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CAMBIAR_ESTADO_SUBVENCION",
        entity="subvencion",
        entity_id=str(sub.id),
        payload={
            "anterior": anterior,
            "estado": destino_enum.value,
            "asiento_rectificativo_id": str(asiento_rectificativo_id)
            if asiento_rectificativo_id
            else None,
        },
    )
    await db.flush()
    gastado = await _gastado(db, empresa_id, sub.id)
    return _resumen(sub, gastado)