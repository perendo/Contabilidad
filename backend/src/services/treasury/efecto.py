"""Cartera de efectos (SPEC-021 US1): cheques, pagarés y letras.

Un efecto se registra como ``emitido``; al vencimiento se liquida con un
asiento balanceado (constitución I):

- cobro   -> COBRO  Debe 572 | Haber 431, estado ``cobrado``.
- impago  -> REVERSAL Debe 431 (+ 626 gastos) | Haber 572,
             estado ``impagado`` y reapertura de los vencimientos del
             tercero (SPEC-011/FR-005).

Los estados ``cobrado``/``impagado`` son finales: no admiten UPDATE/DELETE
(constitucion II, reforzado a nivel DB por triggers) y las transiciones
entre ellos se rechazan con 409. La empresa activa se pasa explícitamente
(constitucion III) y nunca proviene del cliente.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.efecto import Efecto, EstadoEfecto, TipoEfecto
from services.accounting import verificar_balance
from services.audit import registrar_auditoria
from services.treasury.common import (
    CUENTA_BANCO,
    CUENTA_COMISION,
    CUENTA_EFECTOS,
    TesoreriaError,
    ejercicio_abierto,
)


class EfectoError(TesoreriaError):
    pass


def _cuantizar(valor: Decimal | str) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.0000"))


async def registrar_efecto(
    db: AsyncSession,
    *,
    empresa_id: int,
    tercero_id: uuid.UUID,
    tipo_efecto: TipoEfecto,
    numero_documento: str,
    fecha_emision: date,
    fecha_vencimiento: date,
    importe: str,
    moneda: str = "EUR",
    notas: str | None = None,
    actor: str | None = None,
) -> Efecto:
    importe_d = _cuantizar(importe)
    if importe_d <= 0:
        raise EfectoError("importe_invalido", 422, "El importe debe ser > 0")
    if fecha_vencimiento < fecha_emision:
        raise EfectoError(
            "fecha_invalida", 422, "La fecha de vencimiento no puede ser anterior a la emisión"
        )
    await ejercicio_abierto(db, empresa_id, fecha_emision, EfectoError)

    tercero = await db.scalar(
        select(Tercero).where(
            Tercero.empresa_id == empresa_id, Tercero.id == tercero_id
        )
    )
    if tercero is None:
        raise EfectoError("tercero_no_encontrado", 404, "Tercero inexistente para la empresa")

    duplicado = await db.scalar(
        select(Efecto).where(
            Efecto.empresa_id == empresa_id,
            Efecto.tercero_id == tercero_id,
            Efecto.tipo_efecto == tipo_efecto,
            Efecto.numero_documento == numero_documento,
        )
    )
    if duplicado is not None:
        raise EfectoError(
            "documento_duplicado", 409, "Ya existe un efecto con ese documento para el tercero"
        )

    efecto = Efecto(
        empresa_id=empresa_id,
        tercero_id=tercero_id,
        tipo_efecto=tipo_efecto,
        numero_documento=numero_documento,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento,
        importe=importe_d,
        moneda=moneda,
        estado=EstadoEfecto.emitido,
        notas=notas,
        created_by=actor,
    )
    db.add(efecto)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        operacion="REGISTRAR_EFECTO",
        entidad="efecto",
        entidad_id=efecto.id,
        payload={
            "tercero_id": str(tercero_id),
            "tipo_efecto": tipo_efecto.value,
            "numero_documento": numero_documento,
            "importe": f"{importe_d:0.4f}",
        },
    )
    await db.flush()
    return efecto


def _asiento_liquidacion(
    *,
    empresa_id: int,
    ejercicio: int,
    fecha: date,
    concepto: str,
    banco_debe: Decimal,
    gastos_debe: Decimal,
    haber: Decimal,
    cuenta_banco: str,
) -> tuple[JournalEntry, list[JournalEntryLine]]:
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=JournalEntryTipo.COBRO,
        concepto=concepto,
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    lineas = [
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=cuenta_banco,
            debe=banco_debe,
            haber=Decimal(0),
        ),
    ]
    if gastos_debe > 0:
        lineas.append(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=asiento.id,
                cuenta=CUENTA_COMISION,
                debe=gastos_debe,
                haber=Decimal(0),
            )
        )
    lineas.append(
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=CUENTA_EFECTOS,
            debe=Decimal(0),
            haber=haber,
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


async def cobrar_efecto(
    db: AsyncSession,
    *,
    empresa_id: int,
    efecto_id: uuid.UUID,
    fecha_cobro: date,
    cuenta_banco: str = CUENTA_BANCO,
    actor: str | None = None,
) -> Efecto:
    efecto = await db.scalar(
        select(Efecto).where(
            Efecto.empresa_id == empresa_id, Efecto.id == efecto_id
        )
    )
    if efecto is None:
        raise EfectoError("efecto_no_encontrado", 404, "Efecto inexistente")
    if efecto.estado != EstadoEfecto.emitido:
        raise EfectoError(
            "efecto_estado_no_valido",
            409,
            f"El efecto está en estado {efecto.estado.value}; solo se cobra un efecto emitido",
        )
    await ejercicio_abierto(db, empresa_id, fecha_cobro, EfectoError)

    asiento, lineas = _asiento_liquidacion(
        empresa_id=empresa_id,
        ejercicio=fecha_cobro.year,
        fecha=fecha_cobro,
        concepto=f"Cobro efecto {efecto.numero_documento}",
        banco_debe=efecto.importe,
        gastos_debe=Decimal(0),
        haber=efecto.importe,
        cuenta_banco=cuenta_banco,
    )
    await _persistir_asiento(db, asiento, lineas)

    efecto.asiento_cobro_id = asiento.id
    efecto.estado = EstadoEfecto.cobrado
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        operacion="COBRAR_EFECTO",
        entidad="efecto",
        entidad_id=efecto.id,
        payload={
            "fecha_cobro": fecha_cobro.isoformat(),
            "cuenta_banco": cuenta_banco,
            "asiento_cobro_id": str(asiento.id),
            "importe": f"{efecto.importe:0.4f}",
        },
    )
    await db.flush()
    return efecto


async def _reabrir_vencimientos_tercero(
    db: AsyncSession,
    *,
    empresa_id: int,
    tercero_id: uuid.UUID,
) -> None:
    """Best-effort SPEC-011/FR-005: reopen vencimientos del tercero afectados."""
    vencimientos = (
        await db.scalars(
            select(Vencimiento).where(
                Vencimiento.empresa_id == empresa_id,
                Vencimiento.tercero_id == tercero_id,
                Vencimiento.estado.in_(
                    (
                        EstadoVencimiento.cobrado,
                        EstadoVencimiento.parcial,
                        EstadoVencimiento.devuelto,
                    )
                ),
            )
        )
    ).all()
    for v in vencimientos:
        v.acumulado = Decimal(0)
        v.estado = EstadoVencimiento.pendiente


async def impagar_efecto(
    db: AsyncSession,
    *,
    empresa_id: int,
    efecto_id: uuid.UUID,
    fecha_impago: date,
    motivo: str | None = None,
    gastos_devolucion: str = "0",
    cuenta_banco: str = CUENTA_BANCO,
    actor: str | None = None,
) -> Efecto:
    efecto = await db.scalar(
        select(Efecto).where(
            Efecto.empresa_id == empresa_id, Efecto.id == efecto_id
        )
    )
    if efecto is None:
        raise EfectoError("efecto_no_encontrado", 404, "Efecto inexistente")
    if efecto.estado != EstadoEfecto.emitido:
        raise EfectoError(
            "efecto_estado_no_valido",
            409,
            f"El efecto está en estado {efecto.estado.value}; solo se imputa un impago a un efecto emitido",
        )
    await ejercicio_abierto(db, empresa_id, fecha_impago, EfectoError)

    gastos_d = _cuantizar(gastos_devolucion)
    if gastos_d < 0:
        raise EfectoError("importe_invalido", 422, "Los gastos de devolución no pueden ser negativos")

    total = efecto.importe + gastos_d
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=fecha_impago.year,
        fecha=fecha_impago,
        tipo=JournalEntryTipo.REVERSAL,
        concepto=f"Impago efecto {efecto.numero_documento}",
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    lineas = [
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=CUENTA_EFECTOS,
            debe=efecto.importe,
            haber=Decimal(0),
        ),
    ]
    if gastos_d > 0:
        lineas.append(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=asiento.id,
                cuenta=CUENTA_COMISION,
                debe=gastos_d,
                haber=Decimal(0),
            )
        )
    lineas.append(
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=cuenta_banco,
            debe=Decimal(0),
            haber=total,
        )
    )
    verificar_balance(lineas)
    await _persistir_asiento(db, asiento, lineas)

    efecto.asiento_impago_id = asiento.id
    efecto.estado = EstadoEfecto.impagado
    if motivo:
        efecto.notas = "\n".join(
            part for part in (efecto.notas, f"Impago: {motivo}") if part
        )
    await db.flush()

    await _reabrir_vencimientos_tercero(
        db, empresa_id=empresa_id, tercero_id=efecto.tercero_id
    )
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        operacion="IMPAGAR_EFECTO",
        entidad="efecto",
        entidad_id=efecto.id,
        payload={
            "fecha_impago": fecha_impago.isoformat(),
            "gastos_devolucion": f"{gastos_d:0.4f}",
            "asiento_impago_id": str(asiento.id),
        },
    )
    await db.flush()
    return efecto