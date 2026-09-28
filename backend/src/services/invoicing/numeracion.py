"""Numeración correlativa de facturas y CRUD de series (SPEC-007 T021/T044).

El número se asigna **dentro de la transacción ACID del emisor**: se bloquea la
fila de la serie con ``SELECT ... FOR UPDATE`` (secuencia bloqueada, const. IV)
y el correlativo se deriva por ``(empresa_id, serie_id, ejercicio)`` como
``MAX(numero) + 1`` entre las facturas de ese ejercicio. Cada ejercicio y cada
serie son secuencias independientes; los números anulados quedan reservados
(no se reutilizan). ``SerieFactura.siguiente_numero`` se mantiene como
contador global (high-water) de la serie. El número se formatea como
``{prefijo}{correlativo}{sufijo}``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.invoice.factura import Factura
from models.invoice.serie_factura import SerieFactura, SerieFacturaEstado
from services.audit.writer import audit_escribir
from services.invoicing.errores import error


async def next_numero_factura(
    db: AsyncSession,
    *,
    empresa_id: int,
    serie_id: uuid.UUID,
    ejercicio: int,
) -> int:
    """Siguiente número correlativo por (empresa_id, serie_id, ejercicio)."""
    serie = await db.scalar(
        select(SerieFactura)
        .where(
            SerieFactura.empresa_id == empresa_id,
            SerieFactura.id == serie_id,
        )
        .with_for_update()
    )
    if serie is None:
        raise error("serie_no_encontrada", "Serie inexistente en la empresa activa")
    if serie.estado != SerieFacturaEstado.activa:
        raise error("serie_inactiva", "La serie está inactiva")

    ultimo = await db.scalar(
        select(func.max(Factura.numero)).where(
            Factura.empresa_id == empresa_id,
            Factura.serie_id == serie_id,
            Factura.ejercicio == ejercicio,
        )
    )
    numero = int(ultimo) + 1 if ultimo is not None else 1
    if numero > int(serie.siguiente_numero):
        serie.siguiente_numero = numero
        await db.flush()
    return numero


def numero_formateado(serie: SerieFactura, numero: int | None) -> str | None:
    """Formatea el número como ``{prefijo}{correlativo}{sufijo}``."""
    if numero is None:
        return None
    return f"{serie.prefijo}{numero}{serie.sufijo}"


async def crear_serie(
    db: AsyncSession,
    *,
    empresa_id: int,
    codigo: str,
    nombre: str,
    prefijo: str,
    sufijo: str = "",
    actor: str | None = None,
) -> SerieFactura:
    codigo = codigo.strip().upper()
    prefijo = prefijo.strip()
    sufijo = sufijo.strip()
    if not codigo:
        raise error("codigo_requerido", "El código de la serie es obligatorio")
    existe = await db.scalar(
        select(SerieFactura.id).where(
            SerieFactura.empresa_id == empresa_id,
            SerieFactura.codigo == codigo,
        )
    )
    if existe is not None:
        raise error("serie_duplicada", f"La serie {codigo} ya existe")
    serie = SerieFactura(
        empresa_id=empresa_id,
        codigo=codigo,
        nombre=nombre.strip() or codigo,
        prefijo=prefijo or codigo,
        sufijo=sufijo,
        siguiente_numero=0,
        estado=SerieFacturaEstado.activa,
    )
    db.add(serie)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREAR_SERIE",
        entity="serie_factura",
        entity_id=str(serie.id),
        payload={"codigo": codigo, "prefijo": prefijo, "sufijo": sufijo},
    )
    await db.flush()
    return serie


async def listar_series(db: AsyncSession, *, empresa_id: int) -> list[SerieFactura]:
    return list(
        (
            await db.scalars(
                select(SerieFactura)
                .where(SerieFactura.empresa_id == empresa_id)
                .order_by(SerieFactura.codigo)
            )
        ).all()
    )


async def obtener_serie(
    db: AsyncSession, *, empresa_id: int, serie_id: uuid.UUID
) -> SerieFactura | None:
    return await db.scalar(
        select(SerieFactura).where(
            SerieFactura.empresa_id == empresa_id,
            SerieFactura.id == serie_id,
        )
    )


async def cambiar_estado_serie(
    db: AsyncSession,
    *,
    empresa_id: int,
    serie_id: uuid.UUID,
    activa: bool,
    actor: str | None = None,
) -> SerieFactura:
    serie = await obtener_serie(db, empresa_id=empresa_id, serie_id=serie_id)
    if serie is None:
        raise error("serie_no_encontrada", "Serie inexistente en la empresa activa")
    serie.estado = SerieFacturaEstado.activa if activa else SerieFacturaEstado.inactiva
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="ESTADO_SERIE",
        entity="serie_factura",
        entity_id=str(serie.id),
        payload={"estado": serie.estado.value},
    )
    await db.flush()
    return serie