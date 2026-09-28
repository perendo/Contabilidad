"""Cobros por TPV/tarjeta/transferencia y comisiones (SPEC-021 US2).

Liquida un vencimiento pendiente (SPEC-011) por un medio concreto. Si hay
comisión, el asiento es balanceado de tres patas:

  Debe 572 (neto) + 626 (comisión) | Haber 430 (total)

y se persiste además el desglose ``ComisionBancaria`` (banco, tipo, importe,
porcentaje, cuenta contable de gasto). El vencimiento pasa a ``cobrado``
con su acumulado saldado.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.cobro_medio import CobroMedio, MedioCobro
from models.treasury.comision import ComisionBancaria, TipoComision
from services.accounting import verificar_balance
from services.audit import registrar_auditoria
from services.treasury.common import (
    CUENTA_BANCO,
    CUENTA_CLIENTES,
    CUENTA_COMISION,
    TesoreriaError,
    ejercicio_abierto,
)


class CobroMedioError(TesoreriaError):
    pass


def _cuantizar(valor: Decimal | str, precision: int = 4) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("1.0000") if precision == 4 else Decimal("0.01"))


def _out(cobro: CobroMedio, comisiones: list[ComisionBancaria] | None = None) -> dict:
    return {
        "id": str(cobro.id),
        "vencimiento_id": str(cobro.vencimiento_id),
        "medio_cobro": cobro.medio_cobro.value,
        "fecha_cobro": cobro.fecha_cobro.isoformat(),
        "importe_total": f"{cobro.importe_total:0.4f}",
        "importe_comision": f"{cobro.importe_comision:0.4f}",
        "importe_neto": f"{cobro.importe_neto:0.4f}",
        "cuenta_banco": cobro.cuenta_banco,
        "asiento_cobro_id": (
            str(cobro.asiento_cobro_id) if cobro.asiento_cobro_id else None
        ),
        "comisiones": [
            {
                "id": str(c.id),
                "banco_codigo": c.banco_codigo,
                "tipo_comision": c.tipo_comision,
                "importe": f"{c.importe:0.4f}",
                "porcentaje": f"{c.porcentaje:0.2f}" if c.porcentaje is not None else None,
                "cuenta_contable": c.cuenta_contable,
            }
            for c in (comisiones or [])
        ],
    }


async def registrar_cobro_medio(
    db: AsyncSession,
    *,
    empresa_id: int,
    vencimiento_id: uuid.UUID,
    medio_cobro: MedioCobro,
    fecha_cobro: date,
    cuenta_banco: str = CUENTA_BANCO,
    importe_comision: str = "0",
    tipo_comision: TipoComision | str = "OTRA",
    banco_codigo: str | None = None,
    porcentaje: str | None = None,
    actor: str | None = None,
) -> tuple[CobroMedio, list[ComisionBancaria]]:
    vencimiento = await db.scalar(
        select(Vencimiento).where(
            Vencimiento.empresa_id == empresa_id,
            Vencimiento.id == vencimiento_id,
        )
    )
    if vencimiento is None:
        raise CobroMedioError("vencimiento_no_encontrado", 404, "Vencimiento inexistente")
    if vencimiento.estado != EstadoVencimiento.pendiente:
        raise CobroMedioError(
            "vencimiento_estado_no_valido",
            409,
            f"El vencimiento está en estado {vencimiento.estado.value}; solo se cobra un vencimiento pendiente",
        )
    await ejercicio_abierto(db, empresa_id, fecha_cobro, CobroMedioError)

    comision_d = _cuantizar(importe_comision)
    if comision_d < 0 or comision_d > vencimiento.importe:
        raise CobroMedioError(
            "comision_no_valida",
            422,
            "La comisión debe estar entre 0 e importe total",
        )
    neto = vencimiento.importe - comision_d

    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=fecha_cobro.year,
        fecha=fecha_cobro,
        tipo=JournalEntryTipo.COBRO,
        concepto=f"Cobro {medio_cobro.value} {vencimiento.recibo_num}",
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    lineas = [
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=cuenta_banco,
            debe=neto,
            haber=Decimal(0),
        ),
    ]
    if comision_d > 0:
        lineas.append(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=asiento.id,
                cuenta=CUENTA_COMISION,
                debe=comision_d,
                haber=Decimal(0),
            )
        )
    lineas.append(
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=CUENTA_CLIENTES,
            debe=Decimal(0),
            haber=vencimiento.importe,
        )
    )
    verificar_balance(lineas)
    db.add(asiento)
    await db.flush()
    for linea in lineas:
        db.add(linea)
    await db.flush()

    vencimiento.acumulado = vencimiento.importe
    vencimiento.estado = EstadoVencimiento.cobrado

    cobro = CobroMedio(
        empresa_id=empresa_id,
        vencimiento_id=vencimiento.id,
        medio_cobro=medio_cobro,
        fecha_cobro=fecha_cobro,
        importe_total=vencimiento.importe,
        importe_comision=comision_d,
        importe_neto=neto,
        cuenta_banco=cuenta_banco,
        asiento_cobro_id=asiento.id,
        created_by=actor,
    )
    db.add(cobro)
    await db.flush()

    comisiones: list[ComisionBancaria] = []
    if comision_d > 0:
        comision = ComisionBancaria(
            empresa_id=empresa_id,
            cobro_medio_id=cobro.id,
            banco_codigo=banco_codigo,
            tipo_comision=(
                tipo_comision.value if isinstance(tipo_comision, TipoComision) else tipo_comision
            ),
            importe=comision_d,
            porcentaje=_cuantizar(porcentaje, 2) if porcentaje is not None else None,
            cuenta_contable=CUENTA_COMISION,
            created_by=actor,
        )
        db.add(comision)
        await db.flush()
        comisiones.append(comision)

    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        operacion="REGISTRAR_COBRO_MEDIO",
        entidad="cobro_medio",
        entidad_id=cobro.id,
        payload={
            "vencimiento_id": str(vencimiento.id),
            "medio_cobro": medio_cobro.value,
            "fecha_cobro": fecha_cobro.isoformat(),
            "importe_total": f"{cobro.importe_total:0.4f}",
            "importe_comision": f"{comision_d:0.4f}",
            "importe_neto": f"{neto:0.4f}",
            "asiento_cobro_id": str(asiento.id),
        },
    )
    await db.flush()
    return cobro, comisiones


async def listar_cobros_medio(
    db: AsyncSession,
    *,
    empresa_id: int,
    medio_cobro: MedioCobro | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    condiciones = [CobroMedio.empresa_id == empresa_id]
    if medio_cobro is not None:
        condiciones.append(CobroMedio.medio_cobro == medio_cobro)
    if fecha_desde is not None:
        condiciones.append(CobroMedio.fecha_cobro >= fecha_desde)
    if fecha_hasta is not None:
        condiciones.append(CobroMedio.fecha_cobro <= fecha_hasta)
    total = await db.scalar(select(func.count(CobroMedio.id)).where(*condiciones))
    filas = (
        await db.scalars(
            select(CobroMedio)
            .where(*condiciones)
            .order_by(CobroMedio.fecha_cobro.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [_out(c) for c in filas], total or 0


async def detalle_cobro_medio(
    db: AsyncSession,
    *,
    empresa_id: int,
    cobro_medio_id: uuid.UUID,
) -> dict | None:
    cobro = await db.scalar(
        select(CobroMedio).where(
            CobroMedio.empresa_id == empresa_id, CobroMedio.id == cobro_medio_id
        )
    )
    if cobro is None:
        return None
    comisiones = (
        await db.scalars(
            select(ComisionBancaria).where(
                ComisionBancaria.empresa_id == empresa_id,
                ComisionBancaria.cobro_medio_id == cobro_medio_id,
            )
        )
    ).all()
    datos = _out(cobro, list(comisiones))
    if cobro.asiento_cobro_id is not None:
        asiento = await db.scalar(
            select(JournalEntry).where(
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.id == cobro.asiento_cobro_id,
            )
        )
        if asiento is not None:
            datos["asiento"] = {
                "id": str(asiento.id),
                "fecha": asiento.fecha.isoformat(),
                "tipo": asiento.tipo.value,
                "concepto": asiento.concepto,
            }
    return datos