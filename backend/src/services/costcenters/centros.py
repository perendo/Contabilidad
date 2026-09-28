"""Servicios CRUD del catálogo de centros de coste (SPEC-017 US1).

Crea/edita/inactiva/reactiva centros jerárquicos exclusivos de la empresa
activa (constitución III) y mantiene la closure table ``jerarquia_centro`` en
la misma transacción ACID (decisión D1). La inactivación bloquea nuevas
imputaciones; el borrado físico queda impedido a nivel DB (FR-005): un centro
con imputaciones o descendientes solo puede inactivarse.

``subvencion_id`` es un UUID libre (SPEC-019 sin implementar): se persiste sin
FK y sin validación cross-empresa; la validación real queda diferida a SPEC-019.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.costcenters.centro_coste import CentroCoste, CentroEstado, CentroTipo
from models.costcenters.jerarquia import JerarquiaCentro
from services.audit.writer import audit_escribir
from services.costcenters.errores import CostcenterError


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


async def _ancestros(db: AsyncSession, empresa_id: int, nodo_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
    """Paquetes (ancestro_id, profundidad) desde el propio nodo hasta la raíz."""
    filas = (
        await db.scalars(
            select(JerarquiaCentro).where(
                JerarquiaCentro.empresa_id == empresa_id,
                JerarquiaCentro.descendiente_id == nodo_id,
            )
        )
    ).all()
    return [(f.ancestro_id, f.profundidad) for f in filas]


async def _descendientes(db: AsyncSession, empresa_id: int, nodo_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
    """Paquetes (descendiente_id, profundidad relativa) del subárbol del nodo."""
    filas = (
        await db.scalars(
            select(JerarquiaCentro).where(
                JerarquiaCentro.empresa_id == empresa_id,
                JerarquiaCentro.ancestro_id == nodo_id,
            )
        )
    ).all()
    return [(f.descendiente_id, f.profundidad) for f in filas]


async def _insertar_closure_nodo(
    db: AsyncSession, empresa_id: int, nodo_id: uuid.UUID, parent_id: uuid.UUID | None
) -> None:
    """Closure inicial de un nodo nuevo: (nodo, nodo, 0) + ancestros del padre."""
    db.add(
        JerarquiaCentro(
            empresa_id=empresa_id, ancestro_id=nodo_id, descendiente_id=nodo_id, profundidad=0
        )
    )
    if parent_id is not None:
        parent_ancestros = await _ancestros(db, empresa_id, parent_id)
        for ancestro, profundidad in parent_ancestros:
            db.add(
                JerarquiaCentro(
                    empresa_id=empresa_id,
                    ancestro_id=ancestro,
                    descendiente_id=nodo_id,
                    profundidad=profundidad + 1,
                )
            )


async def _reinsertar_closure_reasignado(
    db: AsyncSession, empresa_id: int, nodo_id: uuid.UUID, parent_id: uuid.UUID | None
) -> None:
    """Reconstruye la closure del subárbol de un nodo reasignado de padre."""
    subarbol = await _descendientes(db, empresa_id, nodo_id)
    if not subarbol:
        return
    ids_subarbol = {d for d, _ in subarbol}
    cadena = [(nodo_id, 0)]
    if parent_id is not None:
        cadena += [(ancestro, profundidad + 1) for ancestro, profundidad in await _ancestros(db, empresa_id, parent_id)]
    await db.execute(
        delete(JerarquiaCentro).where(
            JerarquiaCentro.empresa_id == empresa_id,
            JerarquiaCentro.descendiente_id.in_(ids_subarbol),
        )
    )
    for ancestro, profundidad_ancestro in cadena:
        for descendiente, profundidad_rel in subarbol:
            db.add(
                JerarquiaCentro(
                    empresa_id=empresa_id,
                    ancestro_id=ancestro,
                    descendiente_id=descendiente,
                    profundidad=profundidad_ancestro + profundidad_rel,
                )
            )


async def _recalcular_hojas(db: AsyncSession, empresa_id: int, centro_id: uuid.UUID) -> None:
    """Actualiza es_hoja del nodo y, si procede, de su padre (reparenting)."""
    hijo = await db.scalar(
        select(CentroCoste).where(
            CentroCoste.empresa_id == empresa_id, CentroCoste.id == centro_id
        )
    )
    if hijo is None:
        return
    tiene_sub = (
        await db.scalar(
            select(JerarquiaCentro).where(
                JerarquiaCentro.empresa_id == empresa_id,
                JerarquiaCentro.ancestro_id == centro_id,
                JerarquiaCentro.descendiente_id != centro_id,
            )
        )
    ) is not None
    hijo.es_hoja = not tiene_sub
    hijo.updated_at = _ahora()
    if hijo.parent_id is not None:
        padre = await db.scalar(
            select(CentroCoste).where(
                CentroCoste.empresa_id == empresa_id, CentroCoste.id == hijo.parent_id
            )
        )
        if padre is not None:
            padre.es_hoja = False
            padre.updated_at = _ahora()


def _centro_dto(centro: CentroCoste) -> dict:
    return {
        "id": str(centro.id),
        "codigo": centro.codigo,
        "nombre": centro.nombre,
        "tipo": centro.tipo.value,
        "parent_id": str(centro.parent_id) if centro.parent_id else None,
        "subvencion_id": str(centro.subvencion_id) if centro.subvencion_id else None,
        "estado": centro.estado.value,
        "es_hoja": centro.es_hoja,
        "created_at": centro.created_at.isoformat() if centro.created_at else None,
    }


async def crear_centro(
    db: AsyncSession,
    *,
    empresa_id: int,
    codigo: str,
    nombre: str,
    tipo: str,
    parent_id: uuid.UUID | None = None,
    subvencion_id: uuid.UUID | None = None,
    actor: str | None = None,
) -> dict:
    """Alta de un centro de coste con su closure inicial (transacción ACID)."""
    try:
        tipo_enum = CentroTipo(tipo)
    except ValueError:
        raise CostcenterError("tipo_invalido", f"Tipo de centro desconocido: {tipo}")

    duplicado = await db.scalar(
        select(CentroCoste).where(
            CentroCoste.empresa_id == empresa_id, CentroCoste.codigo == codigo.strip()
        )
    )
    if duplicado is not None:
        raise CostcenterError("codigo_duplicado", f"El código {codigo} ya existe en la empresa")

    padre: CentroCoste | None = None
    if parent_id is not None:
        padre = await db.scalar(
            select(CentroCoste).where(
                CentroCoste.empresa_id == empresa_id, CentroCoste.id == parent_id
            )
        )
        if padre is None:
            raise CostcenterError("parent_no_encontrado", "El centro padre no existe en la empresa")

    centro = CentroCoste(
        empresa_id=empresa_id,
        codigo=codigo.strip(),
        nombre=nombre.strip(),
        tipo=tipo_enum,
        parent_id=parent_id,
        subvencion_id=subvencion_id,
        estado=CentroEstado.activo,
        es_hoja=True,
    )
    if centro.id is None:
        centro.id = uuid.uuid4()
    db.add(centro)
    await db.flush()
    await _insertar_closure_nodo(db, empresa_id, centro.id, parent_id)
    if padre is not None:
        padre.es_hoja = False
        padre.updated_at = _ahora()
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREAR_CENTRO",
        entity="centro_coste",
        entity_id=str(centro.id),
        payload={"codigo": centro.codigo, "tipo": tipo_enum.value, "parent_id": str(parent_id) if parent_id else None},
    )
    return _centro_dto(centro)


async def _obtener(db: AsyncSession, empresa_id: int, centro_id: uuid.UUID) -> CentroCoste | None:
    return await db.scalar(
        select(CentroCoste).where(
            CentroCoste.empresa_id == empresa_id, CentroCoste.id == centro_id
        )
    )


async def obtener_centro(db: AsyncSession, *, empresa_id: int, centro_id: uuid.UUID) -> dict | None:
    centro = await _obtener(db, empresa_id, centro_id)
    if centro is None:
        return None
    dto = _centro_dto(centro)
    hijos = (
        await db.scalars(
            select(CentroCoste).where(
                CentroCoste.empresa_id == empresa_id, CentroCoste.parent_id == centro.id
            )
        )
    ).all()
    dto["hijos"] = [_centro_dto(h) for h in hijos]
    return dto


async def listar_centros(
    db: AsyncSession,
    *,
    empresa_id: int,
    estado: str | None = None,
    tipo: str | None = None,
    padre_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Listado paginado plano (con parent_id) + árbol si se pide."""
    filtros = [CentroCoste.empresa_id == empresa_id]
    if estado is not None:
        filtros.append(CentroCoste.estado == estado)
    if tipo is not None:
        try:
            filtros.append(CentroCoste.tipo == CentroTipo(tipo))
        except ValueError:
            raise CostcenterError("tipo_invalido", f"Tipo de centro desconocido: {tipo}")
    if padre_id is not None:
        filtros.append(CentroCoste.parent_id == padre_id)

    base = select(CentroCoste).where(*filtros)
    from sqlalchemy import func as _func

    total = await db.scalar(select(_func.count()).select_from(base.subquery()))
    centros = (
        await db.scalars(
            base.order_by(CentroCoste.codigo).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {
        "items": [_centro_dto(c) for c in centros],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


async def arbol_centros(db: AsyncSession, *, empresa_id: int) -> dict:
    """Árbol jerárquico completo resuelto con la closure (profundidad incluida)."""
    centros = (
        await db.scalars(
            select(CentroCoste).where(CentroCoste.empresa_id == empresa_id).order_by(CentroCoste.codigo)
        )
    ).all()
    pares = (
        await db.scalars(
            select(JerarquiaCentro).where(JerarquiaCentro.empresa_id == empresa_id)
        )
    ).all()
    hijos_por_padre: dict[uuid.UUID | None, list[CentroCoste]] = {}
    for c in centros:
        hijos_por_padre.setdefault(c.parent_id, []).append(c)
    profundidad: dict[uuid.UUID, int] = {}
    for p in pares:
        actual = profundidad.get(p.descendiente_id, 0)
        if p.profundidad > actual:
            profundidad[p.descendiente_id] = p.profundidad

    def _nodo(c: CentroCoste) -> dict:
        dto = _centro_dto(c)
        dto["profundidad"] = profundidad.get(c.id, 0)
        hijo_lista = hijos_por_padre.get(c.id, [])
        dto["hijos"] = [_nodo(h) for h in hijo_lista]
        dto["n_hijos"] = len(hijo_lista)
        return dto

    raices = [c for c in centros if c.parent_id is None]
    return {"items": [_nodo(r) for r in raices], "total": len(centros)}


async def editar_centro(
    db: AsyncSession,
    *,
    empresa_id: int,
    centro_id: uuid.UUID,
    nombre: str | None = None,
    tipo: str | None = None,
    parent_id: uuid.UUID | None = None,
    subvencion_id: uuid.UUID | None = None,
    actor: str | None = None,
) -> dict:
    """Edita metadatos; reparenting mantiene closure + es_hoja de ancestros."""
    centro = await _obtener(db, empresa_id, centro_id)
    if centro is None:
        raise CostcenterError("centro_no_encontrado", "El centro no existe en la empresa activa")

    if parent_id == centro.id:
        raise CostcenterError("ciclo", "Un centro no puede ser padre de sí mismo")

    if parent_id is not None and parent_id != centro.parent_id:
        # Rechazo de ciclos: parent_id no puede ser descendiente de centro_id
        subarbol = {d for d, _ in await _descendientes(db, empresa_id, centro_id)}
        if parent_id in subarbol:
            raise CostcenterError("ciclo", "El nuevo padre es descendiente del centro (ciclo)")
        nuevo_padre = await db.scalar(
            select(CentroCoste).where(
                CentroCoste.empresa_id == empresa_id, CentroCoste.id == parent_id
            )
        )
        if nuevo_padre is None:
            raise CostcenterError("parent_no_encontrado", "El centro padre no existe en la empresa")
        antiguo_padre = centro.parent_id
        centro.parent_id = parent_id
        await _reinsertar_closure_reasignado(db, empresa_id, centro.id, parent_id)
        await _recalcular_hojas(db, empresa_id, antiguo_padre) if antiguo_padre else None
        await _recalcular_hojas(db, empresa_id, parent_id)
    elif parent_id is None and centro.parent_id is not None:
        antiguo_padre = centro.parent_id
        centro.parent_id = None
        await _reinsertar_closure_reasignado(db, empresa_id, centro.id, None)
        await _recalcular_hojas(db, empresa_id, antiguo_padre) if antiguo_padre else None

    if nombre is not None and nombre.strip():
        centro.nombre = nombre.strip()
    if tipo is not None:
        try:
            centro.tipo = CentroTipo(tipo)
        except ValueError:
            raise CostcenterError("tipo_invalido", f"Tipo de centro desconocido: {tipo}")
    if subvencion_id is not None:
        centro.subvencion_id = subvencion_id

    centro.updated_at = _ahora()
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="EDITAR_CENTRO",
        entity="centro_coste",
        entity_id=str(centro.id),
        payload={"nombre": centro.nombre, "tipo": centro.tipo.value},
    )
    return _centro_dto(centro)


async def _cambiar_estado(
    db: AsyncSession,
    *,
    empresa_id: int,
    centro_id: uuid.UUID,
    a_estado: CentroEstado,
    action: str,
    actor: str | None,
) -> dict:
    centro = await _obtener(db, empresa_id, centro_id)
    if centro is None:
        raise CostcenterError("centro_no_encontrado", "El centro no existe en la empresa activa")
    if centro.estado == a_estado:
        raise CostcenterError("estado_duplicado", f"El centro ya está {a_estado.value}")
    centro.estado = a_estado
    centro.updated_at = _ahora()
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action=action,
        entity="centro_coste",
        entity_id=str(centro.id),
        payload={"estado": a_estado.value},
    )
    return _centro_dto(centro)


async def inactivar_centro(
    db: AsyncSession, *, empresa_id: int, centro_id: uuid.UUID, actor: str | None = None
) -> dict:
    """Inactiva el centro: bloquea nuevas imputaciones (no borrado físico)."""
    return await _cambiar_estado(
        db, empresa_id=empresa_id, centro_id=centro_id,
        a_estado=CentroEstado.inactivo, action="INACTIVAR_CENTRO", actor=actor,
    )


async def reactivar_centro(
    db: AsyncSession, *, empresa_id: int, centro_id: uuid.UUID, actor: str | None = None
) -> dict:
    return await _cambiar_estado(
        db, empresa_id=empresa_id, centro_id=centro_id,
        a_estado=CentroEstado.activo, action="REACTIVAR_CENTRO", actor=actor,
    )


__all__ = [
    "arbol_centros",
    "crear_centro",
    "editar_centro",
    "inactivar_centro",
    "listar_centros",
    "obtener_centro",
    "reactivar_centro",
]