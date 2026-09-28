"""CRUD service for tercero amendments: CondicionProntoPago and MandatoSepa.

Business rules enforced here (never in the UI):
- At most one active (vigente=true) CondicionProntoPago per (empresa_id, tercero_id);
  creating/activating a new one deactivates the previous one.
- MandatoSepa is registered under the active company; a single reference per
  (empresa_id, tercero_id, mandato_ref).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import Enum

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.treasury.condicion_pronto_pago import CondicionProntoPago
from models.treasury.mandato_sepa import MandatoEstado, MandatoSepa
from models.treasury.remesa import TipoAdeudo


class TerceroAmendError(Exception):
    pass


class MandatoEstadoInput(str, Enum):
    firmado = "firmado"
    caducado = "caducado"
    revocado = "revocado"


async def crear_condicion(
    session: AsyncSession,
    empresa_id: int,
    tercero_id: uuid.UUID,
    plazo_dias: int,
    porcentaje: Decimal,
    vigente: bool = True,
    override_factura_id: uuid.UUID | None = None,
) -> CondicionProntoPago:
    if plazo_dias <= 0:
        raise TerceroAmendError("plazo_dias debe ser > 0")
    if not (Decimal(0) < porcentaje <= Decimal(100)):
        raise TerceroAmendError("porcentaje debe estar en (0, 100]")

    if vigente:
        await session.execute(
            update(CondicionProntoPago)
            .where(
                CondicionProntoPago.empresa_id == empresa_id,
                CondicionProntoPago.tercero_id == tercero_id,
                CondicionProntoPago.vigente.is_(True),
            )
            .values(vigente=False)
        )

    condicion = CondicionProntoPago(
        empresa_id=empresa_id,
        tercero_id=tercero_id,
        plazo_dias=plazo_dias,
        porcentaje=porcentaje,
        vigente=vigente,
        override_factura_id=override_factura_id,
    )
    session.add(condicion)
    await session.flush()
    return condicion


async def actualizar_condicion(
    session: AsyncSession,
    empresa_id: int,
    condicion_id: uuid.UUID,
    *,
    plazo_dias: int | None = None,
    porcentaje: Decimal | None = None,
    vigente: bool | None = None,
    override_factura_id: uuid.UUID | None = None,
) -> CondicionProntoPago:
    condicion = await session.get(
        CondicionProntoPago, condicion_id, with_for_update=True
    )
    if condicion is None or condicion.empresa_id != empresa_id:
        raise TerceroAmendError("condición no encontrada en la empresa activa")

    if plazo_dias is not None:
        if plazo_dias <= 0:
            raise TerceroAmendError("plazo_dias debe ser > 0")
        condicion.plazo_dias = plazo_dias
    if porcentaje is not None:
        if not (Decimal(0) < porcentaje <= Decimal(100)):
            raise TerceroAmendError("porcentaje debe estar en (0, 100]")
        condicion.porcentaje = porcentaje
    if override_factura_id is not None:
        condicion.override_factura_id = override_factura_id

    if vigente is True:
        await session.execute(
            update(CondicionProntoPago)
            .where(
                CondicionProntoPago.empresa_id == empresa_id,
                CondicionProntoPago.tercero_id == condicion.tercero_id,
                CondicionProntoPago.id != condicion.id,
                CondicionProntoPago.vigente.is_(True),
            )
            .values(vigente=False)
        )
        condicion.vigente = True
    elif vigente is False:
        condicion.vigente = False

    await session.flush()
    return condicion


async def crear_mandato(
    session: AsyncSession,
    empresa_id: int,
    tercero_id: uuid.UUID,
    mandato_ref: str,
    fecha_firma: date,
    tipo: TipoAdeudo,
    estado: MandatoEstado = MandatoEstado.firmado,
) -> MandatoSepa:
    if not mandato_ref.strip():
        raise TerceroAmendError("mandato_ref es obligatorio")
    if len(mandato_ref) > 35:
        raise TerceroAmendError("mandato_ref supera 35 caracteres")
    if tipo == TipoAdeudo.B2B and estado != MandatoEstado.firmado:
        raise TerceroAmendError("un mandato B2B debe registrarse como firmado")

    exists = await session.scalar(
        select(MandatoSepa.id).where(
            MandatoSepa.empresa_id == empresa_id,
            MandatoSepa.tercero_id == tercero_id,
            MandatoSepa.mandato_ref == mandato_ref,
        )
    )
    if exists is not None:
        raise TerceroAmendError("el mandato ya existe para ese tercero")

    mandato = MandatoSepa(
        empresa_id=empresa_id,
        tercero_id=tercero_id,
        mandato_ref=mandato_ref,
        fecha_firma=fecha_firma,
        tipo=tipo,
        estado=estado,
    )
    session.add(mandato)
    await session.flush()
    return mandato


async def actualizar_mandato(
    session: AsyncSession,
    empresa_id: int,
    mandato_id: uuid.UUID,
    *,
    estado: MandatoEstadoInput | None = None,
    fecha_firma: date | None = None,
) -> MandatoSepa:
    mandato = await session.get(MandatoSepa, mandato_id, with_for_update=True)
    if mandato is None or mandato.empresa_id != empresa_id:
        raise TerceroAmendError("mandato no encontrado en la empresa activa")

    if estado is not None:
        if mandato.tipo == TipoAdeudo.B2B and estado == MandatoEstadoInput.caducado:
            raise TerceroAmendError("no se puede caducar un mandato B2B")
        mandato.estado = MandatoEstado(estado.value)
    if fecha_firma is not None:
        mandato.fecha_firma = fecha_firma

    await session.flush()
    return mandato