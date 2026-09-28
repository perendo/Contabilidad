"""Remittance emission service: crear, emitir, confirmar cobro, conciliar.

T020/T021 (crear remesa con exclusiones + correlatividad), T022 (soporte de
servicios), T023 (cobro manual con asiento balanceado), T023a (conciliación
idempotente FR-007). Todos los filtros usan empresa_id de sesión (constitución
III); numeración correlativa atómica (IV) y auditoría en la misma transacción (II).
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.blob_fichero import BlobFichero, TipoBlob
from models.treasury.cobro_conciliado import CobroConciliado
from models.treasury.mandato_sepa import MandatoEstado, MandatoSepa
from models.treasury.recibo_remesa import ReciboEstado, ReciboRemesa
from models.treasury.remesa import FormatoRemesa, Remesa, RemesaEstado, TipoAdeudo
from services import accounting
from services.audit import registrar_auditoria
from services.remittance import csb_1919, sepa_dd
from services.remittance.seleccion import (
    Emisor,
    siguiente_numero_remesa,
    validar_vencimientos,
)

CUENTA_BANCO_DEFECTO = "572"


def _hoy() -> date:
    return datetime.now(timezone.utc).date()


class RemesaError(Exception):
    status_code = 400
    code = "error"


class RemesaNotFoundError(RemesaError):
    status_code = 404
    code = "no_encontrada"


class ReciboNotFoundError(RemesaError):
    status_code = 404
    code = "recibo_no_encontrado"


class EmisionEstadoError(RemesaError):
    status_code = 409
    code = "estado_no_valido"


class PlazoPresentacionRemesaError(RemesaError):
    status_code = 422
    code = "plazo_presentacion"


class InelegibleError(RemesaError):
    """One or more receivables cannot enter the remesa; the operation is atomic."""

    status_code = 422
    code = "vencimientos_no_elegibles"

    def __init__(self, excluidos: list) -> None:
        self.excluidos = excluidos
        super().__init__(f"{len(excluidos)} vencimiento(s) no elegibles")


class MandatoB2BError(RemesaError):
    status_code = 422
    code = "sin_mandato_b2b"

    def __init__(self, tercero_id: uuid.UUID) -> None:
        self.tercero_id = tercero_id
        super().__init__(f"el tercero {tercero_id} no tiene mandato B2B firmado")


class CobroEstadoError(RemesaError):
    status_code = 409
    code = "cobro_estado_no_valido"


def emisor_por_defecto() -> Emisor:
    """Company master-data placeholder (SPEC-001 not implemented yet)."""
    return Emisor(
        nombre=os.getenv("EMPRESA_NOMBRE", "EMPRESA"),
        nif=os.getenv("EMPRESA_NIF", "000000000"),
        iban=os.getenv("EMPRESA_IBAN", "ES0000000000000000000000"),
        bic=os.getenv("EMPRESA_BIC") or None,
    )


async def crear_remesa(
    session: AsyncSession,
    empresa_id: int,
    *,
    formato: str,
    tipo_adeudo: str,
    vencimiento_ids: list[uuid.UUID],
    usuario: str | None = None,
) -> Remesa:
    """Create a draft remesa validating receivables and assigning next number."""
    tipo_adeudo_enum = TipoAdeudo(tipo_adeudo)
    ejercicio = _hoy().year
    elegibles, excluidos = await validar_vencimientos(
        session, empresa_id, vencimiento_ids
    )
    if excluidos:
        raise InelegibleError(excluidos)
    if not elegibles:
        raise InelegibleError([])

    numero = await siguiente_numero_remesa(session, empresa_id, ejercicio)
    fecha_cargo = (
        elegibles[0].fecha_vencimiento
        if len({v.fecha_vencimiento for v in elegibles}) == 1
        else None
    )
    importe_total = sum((v.importe for v in elegibles), Decimal(0))

    remesa = Remesa(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        numero_remesa=numero,
        fecha_emision=None,
        fecha_cargo=fecha_cargo,
        formato=FormatoRemesa(formato),
        tipo_adeudo=tipo_adeudo_enum,
        importe_total=importe_total,
        estado=RemesaEstado.borrador,
        fichero_id=None,
    )
    session.add(remesa)
    await session.flush()

    for vencimiento in elegibles:
        session.add(
            ReciboRemesa(
                empresa_id=empresa_id,
                remesa_id=remesa.id,
                vencimiento_id=vencimiento.id,
                recibo_num=vencimiento.recibo_num,
                tercero_id=vencimiento.tercero_id,
                iban=vencimiento.iban,
                importe=vencimiento.importe,
                fecha_cargo=vencimiento.fecha_vencimiento,
                descuento_id=None,
                estado=ReciboEstado.pendiente,
                asiento_cobro_id=None,
                fecha_cobro=None,
            )
        )

    await registrar_auditoria(
        session,
        empresa_id,
        "CREAR",
        "remesa",
        remesa.id,
        {
            "numero_remesa": numero,
            "formato": formato,
            "tipo_adeudo": tipo_adeudo,
            "n_recibos": len(elegibles),
            "importe_total": str(importe_total),
        },
        usuario=usuario,
    )
    await session.flush()
    return remesa


async def _firmados_por_tercero(
    session: AsyncSession, empresa_id: int, tercero_ids: set[uuid.UUID]
) -> dict[uuid.UUID, MandatoSepa]:
    firmados = (
        await session.scalars(
            select(MandatoSepa).where(
                MandatoSepa.empresa_id == empresa_id,
                MandatoSepa.tercero_id.in_(tercero_ids),
                MandatoSepa.estado == MandatoEstado.firmado,
            )
        )
    ).all()
    return {m.tercero_id: m for m in firmados}


async def emitir_remesa(
    session: AsyncSession,
    empresa_id: int,
    remesa_id: uuid.UUID,
    *,
    emisor: Emisor | None = None,
    usuario: str | None = None,
) -> tuple[Remesa, BlobFichero, bytes]:
    """Generate and persist the file for a draft remesa."""
    remesa = await session.scalar(
        select(Remesa).where(Remesa.empresa_id == empresa_id, Remesa.id == remesa_id)
    )
    if remesa is None:
        raise RemesaNotFoundError("remesa no encontrada")
    if remesa.estado != RemesaEstado.borrador:
        raise EmisionEstadoError(
            f"solo las remesas en borrador se pueden emitir (estado={remesa.estado.value})"
        )

    recibos = list(
        (
            await session.scalars(
                select(ReciboRemesa).where(
                    ReciboRemesa.empresa_id == empresa_id,
                    ReciboRemesa.remesa_id == remesa.id,
                )
            )
        ).all()
    )
    if not recibos:
        raise EmisionEstadoError("la remesa no contiene recibos")

    emisor = emisor or emisor_por_defecto()
    hoy = _hoy()

    if remesa.formato == FormatoRemesa.CSB_19_19 and remesa.tipo_adeudo == TipoAdeudo.B2B:
        raise EmisionEstadoError("CSB 19.19 solo admite adeudos CORE")

    tercero_ids = {recibo.tercero_id for recibo in recibos}
    mandatos = await _firmados_por_tercero(session, empresa_id, tercero_ids)
    if remesa.tipo_adeudo == TipoAdeudo.B2B:
        faltantes = tercero_ids - set(mandatos)
        if faltantes:
            raise MandatoB2BError(next(iter(faltantes)))

    fecha_grupos = sorted({recibo.fecha_cargo for recibo in recibos})
    if remesa.formato == FormatoRemesa.SEPA_DD:
        try:
            for fecha_cargo in fecha_grupos:
                sepa_dd.validar_plazo_presentacion(remesa.tipo_adeudo, fecha_cargo, hoy)
        except sepa_dd.PlazoPresentacionError as exc:
            raise PlazoPresentacionRemesaError(str(exc)) from exc

    if remesa.formato == FormatoRemesa.SEPA_DD:
        contenido = sepa_dd.generar_sepa(remesa, recibos, {}, mandatos, emisor, hoy)
        tipo_blob = TipoBlob.remesa_sepa
    else:
        contenido = csb_1919.generar_csb1919(remesa, recibos, {}, emisor)
        tipo_blob = TipoBlob.remesa_csb1919

    blob = BlobFichero(
        empresa_id=empresa_id,
        tipo=tipo_blob,
        contenido=contenido,
        sha256=sepa_dd.sha256_fichero(contenido),
    )
    session.add(blob)
    await session.flush()

    remesa.estado = RemesaEstado.emitida
    remesa.fecha_emision = hoy
    remesa.fichero_id = blob.id
    for recibo in recibos:
        recibo.estado = ReciboEstado.remesado
        session.add(recibo)

    await registrar_auditoria(
        session,
        empresa_id,
        "EMITIR",
        "remesa",
        remesa.id,
        {
            "numero_remesa": remesa.numero_remesa,
            "formato": remesa.formato.value,
            "sha256": blob.sha256,
            "n_recibos": len(recibos),
            "fecha_grupos": [str(d) for d in fecha_grupos],
        },
        usuario=usuario,
    )
    await session.flush()
    return remesa, blob, contenido


async def confirmar_cobro(
    session: AsyncSession,
    empresa_id: int,
    remesa_id: uuid.UUID,
    recibo_id: uuid.UUID,
    *,
    fecha_cobro: date | None = None,
    cuenta_banco: str = CUENTA_BANCO_DEFECTO,
    usuario: str | None = None,
) -> tuple[Remesa, ReciboRemesa]:
    """Manually mark a remesado recibo as collected with a balanced asiento."""
    remesa = await session.scalar(
        select(Remesa).where(Remesa.empresa_id == empresa_id, Remesa.id == remesa_id)
    )
    if remesa is None:
        raise RemesaNotFoundError("remesa no encontrada")
    recibo = await session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id,
            ReciboRemesa.remesa_id == remesa_id,
            ReciboRemesa.id == recibo_id,
        )
    )
    if recibo is None:
        raise ReciboNotFoundError("recibo no encontrado en la remesa")
    if recibo.estado != ReciboEstado.remesado:
        raise CobroEstadoError(
            f"el recibo no se puede cobrar en estado {recibo.estado.value}"
        )

    fecha_cobro = fecha_cobro or _hoy()
    asiento, lineas = accounting.construir_asiento_cobro(
        empresa_id=empresa_id,
        ejercicio=remesa.ejercicio,
        fecha=fecha_cobro,
        importe=recibo.importe,
        cuenta_banco=cuenta_banco,
        concepto=f"Cobro recibo {recibo.recibo_num} (remesa {remesa.numero_remesa})",
    )
    session.add(asiento)
    for linea in lineas:
        session.add(linea)

    recibo.estado = ReciboEstado.cobrado
    recibo.fecha_cobro = fecha_cobro
    recibo.asiento_cobro_id = asiento.id
    vencimiento = await session.scalar(
        select(Vencimiento).where(
            Vencimiento.empresa_id == empresa_id,
            Vencimiento.id == recibo.vencimiento_id,
        )
    )
    if vencimiento is not None:
        vencimiento.estado = EstadoVencimiento.cobrado
        session.add(vencimiento)

    await registrar_auditoria(
        session,
        empresa_id,
        "COBRO",
        "recibo_remesa",
        recibo.id,
        {
            "remesa_id": str(remesa.id),
            "asiento_id": str(asiento.id),
            "importe": str(recibo.importe),
            "fecha_cobro": fecha_cobro.isoformat(),
        },
        usuario=usuario,
    )
    await session.flush()
    return remesa, recibo


async def conciliar_cobro(
    session: AsyncSession,
    empresa_id: int,
    *,
    remesa_id: uuid.UUID,
    recibo_id: uuid.UUID,
    movimiento_id: uuid.UUID,
    fecha_cobro: date | None = None,
    cuenta_banco: str = CUENTA_BANCO_DEFECTO,
    usuario: str | None = None,
) -> tuple[ReciboRemesa, bool]:
    """Idempotent bank reconciliation collection (FR-007 / SPEC-013)."""
    existing = await session.scalar(
        select(CobroConciliado).where(
            CobroConciliado.empresa_id == empresa_id,
            CobroConciliado.movimiento_id == movimiento_id,
        )
    )
    if existing is not None:
        recibo = await session.scalar(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == empresa_id,
                ReciboRemesa.id == existing.recibo_remesa_id,
            )
        )
        if recibo is None:
            raise ReciboNotFoundError("recibo conciliado no encontrado")
        return recibo, True

    remesa = await session.scalar(
        select(Remesa).where(Remesa.empresa_id == empresa_id, Remesa.id == remesa_id)
    )
    if remesa is None:
        raise RemesaNotFoundError("remesa no encontrada")
    recibo = await session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id,
            ReciboRemesa.remesa_id == remesa_id,
            ReciboRemesa.id == recibo_id,
        )
    )
    if recibo is None:
        raise ReciboNotFoundError("recibo no encontrado en la remesa")
    if recibo.estado != ReciboEstado.remesado:
        raise CobroEstadoError(
            f"el recibo no se puede cobrar en estado {recibo.estado.value}"
        )

    fecha_cobro = fecha_cobro or _hoy()
    asiento, lineas = accounting.construir_asiento_cobro(
        empresa_id=empresa_id,
        ejercicio=remesa.ejercicio,
        fecha=fecha_cobro,
        importe=recibo.importe,
        cuenta_banco=cuenta_banco,
        concepto=f"Concil cobro {recibo.recibo_num} (remesa {remesa.numero_remesa})",
    )
    session.add(asiento)
    for linea in lineas:
        session.add(linea)
    session.add(
        CobroConciliado(
            empresa_id=empresa_id,
            movimiento_id=movimiento_id,
            recibo_remesa_id=recibo.id,
            journal_entry_id=asiento.id,
        )
    )

    recibo.estado = ReciboEstado.cobrado
    recibo.fecha_cobro = fecha_cobro
    recibo.asiento_cobro_id = asiento.id
    vencimiento = await session.scalar(
        select(Vencimiento).where(
            Vencimiento.empresa_id == empresa_id,
            Vencimiento.id == recibo.vencimiento_id,
        )
    )
    if vencimiento is not None:
        vencimiento.estado = EstadoVencimiento.cobrado
        session.add(vencimiento)

    await registrar_auditoria(
        session,
        empresa_id,
        "CONCILIAR",
        "recibo_remesa",
        recibo.id,
        {
            "remesa_id": str(remesa.id),
            "asiento_id": str(asiento.id),
            "movimiento_id": str(movimiento_id),
            "importe": str(recibo.importe),
        },
        usuario=usuario,
    )
    await session.flush()
    return recibo, False