"""Generador de asientos de factura (SPEC-007 T023).

Consume el motor multilínea de SPEC-006/002 (partida doble validada en el
punto más cercano a la persistencia + correlatividad de asientos):

- Venta:  Debe 430 (subcuenta del tercero) [+ Debe 475 IRPF]
          | Haber 700 (base) + 477 (IVA) + 477 (recargo FR-010).
- Compra: Debe 600 (base) + 472 (IVA) + 472 (recargo)
          | Haber 410 (subcuenta del tercero) + 475 (IRPF retenido).

El IRPF de venta se contabiliza al Debe (retención soportada, cuenta 475) y el
de compra al Haber (la empresa actúa como pagador de la retención).

Las cuentas fiscales (7000/4770/4772/4751/6000/4720/4722) son la configuración
por defecto consumida de SPEC-001; deben existir y ser apuntables en el plan
de la empresa (error 422 `cuenta_no_configurada` en caso contrario). La cuenta
de cliente/proveedor se toma de las subcuentas 430/410 del maestro SPEC-008.

`crear_asiento_reversal_factura` genera el asiento de anulación (REVERSAL) de
una rectificativa sin tocar el asiento original (constitución II).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.ar.tercero_subcuenta import TerceroSubcuenta, TipoSubcuenta
from models.invoice.factura import Factura, FacturaTipo
from services.audit.writer import audit_escribir
from services.invoicing.errores import error
from services.journal.motor import crear_asiento_multilinea
from services.journal.sequence import next_numero as next_numero_asiento
from services.journal.validador_multilinea import validar_asiento_multilinea

CUENTA_VENTAS = "7000"
CUENTA_COMPRAS = "6000"
CUENTA_IVA_REPERCUTIDO = "4770"
CUENTA_RECARGO_REPERCUTIDO = "4772"
CUENTA_IVA_SOPORTADO = "4720"
CUENTA_RECARGO_SOPORTADO = "4722"
CUENTA_IRPF = "4751"


async def subcuenta_tercero(
    db: AsyncSession,
    *,
    empresa_id: int,
    tercero_id: uuid.UUID,
    tipo: FacturaTipo,
) -> str:
    """Cuenta 430/410 del tercero (SPEC-008) para el asiento de la factura."""
    rol = TipoSubcuenta.CLIENTE if tipo == FacturaTipo.VENTA else TipoSubcuenta.PROVEEDOR
    sc = await db.scalar(
        select(TerceroSubcuenta).where(
            TerceroSubcuenta.empresa_id == empresa_id,
            TerceroSubcuenta.tercero_id == tercero_id,
            TerceroSubcuenta.tipo == rol,
        )
    )
    if sc is None:
        raise error(
            "subcuenta_tercero_faltante",
            f"El tercero no tiene subcuenta {rol.value} configurada",
        )
    await _cuenta_existe(db, empresa_id, sc.cuenta_codigo, "subcuenta_tercero_no_apuntable")
    return sc.cuenta_codigo


async def _cuenta_existe(
    db: AsyncSession, empresa_id: int, codigo: str, code_err: str
) -> str:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.code == codigo,
            AccountPlan.is_selectable.is_(True),
            AccountPlan.is_active.is_(True),
        )
    )
    if cuenta is None:
        raise error(code_err, f"Cuenta {codigo} no configurada o no apuntable")
    return codigo


async def _cuentas_fiscales(db: AsyncSession, empresa_id: int, tipo: FacturaTipo) -> dict[str, str]:
    if tipo == FacturaTipo.VENTA:
        codigos = {
            "resultado": CUENTA_VENTAS,
            "iva": CUENTA_IVA_REPERCUTIDO,
            "recargo": CUENTA_RECARGO_REPERCUTIDO,
        }
    else:
        codigos = {
            "resultado": CUENTA_COMPRAS,
            "iva": CUENTA_IVA_SOPORTADO,
            "recargo": CUENTA_RECARGO_SOPORTADO,
        }
    for rol in codigos:
        await _cuenta_existe(db, empresa_id, codigos[rol], "cuenta_no_configurada")
    await _cuenta_existe(db, empresa_id, CUENTA_IRPF, "cuenta_no_configurada")
    return codigos


def construir_lineas(
    *,
    tipo: FacturaTipo,
    cuenta_tercero: str,
    cuentas: dict[str, str],
    descripcion: str,
    base: Decimal,
    iva: Decimal,
    recargo: Decimal,
    irpf: Decimal,
) -> list[dict[str, str]]:
    """Líneas del asiento de facturación (Debe/Haber) en formato motor SPEC-006."""
    if tipo == FacturaTipo.VENTA:
        total = base + iva + recargo - irpf
        lineas: list[dict[str, str]] = [
            {"cuenta": cuenta_tercero, "debe": f"{total:0.4f}", "haber": "0", "detalle": descripcion},
            {"cuenta": cuentas["resultado"], "debe": "0", "haber": f"{base:0.4f}", "detalle": "base"},
        ]
        if iva > 0:
            lineas.append(
                {"cuenta": cuentas["iva"], "debe": "0", "haber": f"{iva:0.4f}", "detalle": "IVA"}
            )
        if recargo > 0:
            lineas.append(
                {"cuenta": cuentas["recargo"], "debe": "0", "haber": f"{recargo:0.4f}", "detalle": "recargo"}
            )
        if irpf > 0:
            lineas.append(
                {"cuenta": CUENTA_IRPF, "debe": f"{irpf:0.4f}", "haber": "0", "detalle": "IRPF retenido"}
            )
        return lineas

    total = base + iva + recargo - irpf
    lineas = [
        {"cuenta": cuentas["resultado"], "debe": f"{base:0.4f}", "haber": "0", "detalle": "base"},
    ]
    if iva > 0:
        lineas.append(
            {"cuenta": cuentas["iva"], "debe": f"{iva:0.4f}", "haber": "0", "detalle": "IVA"}
        )
    lineas.append(
        {"cuenta": cuenta_tercero, "debe": "0", "haber": f"{total:0.4f}", "detalle": descripcion}
    )
    if recargo > 0:
        lineas.append(
            {"cuenta": cuentas["recargo"], "debe": f"{recargo:0.4f}", "haber": "0", "detalle": "recargo"}
        )
    if irpf > 0:
        lineas.append(
            {"cuenta": CUENTA_IRPF, "debe": "0", "haber": f"{irpf:0.4f}", "detalle": "IRPF retenido"}
        )
    return lineas


async def crear_asiento_factura(
    db: AsyncSession,
    *,
    empresa_id: int,
    factura: Factura,
    actor: str | None = None,
) -> JournalEntry:
    """Genera y asienta el asiento vinculado a la factura (misma transacción)."""
    cuenta_tercero = await subcuenta_tercero(
        db, empresa_id=empresa_id, tercero_id=factura.tercero_id, tipo=factura.tipo
    )
    cuentas = await _cuentas_fiscales(db, empresa_id, factura.tipo)
    concepto = factura.concepto_global or f"Factura {factura.tipo.value}"
    lineas = construir_lineas(
        tipo=factura.tipo,
        cuenta_tercero=cuenta_tercero,
        cuentas=cuentas,
        descripcion=concepto,
        base=factura.importe_base,
        iva=factura.importe_iva,
        recargo=factura.importe_recargo,
        irpf=factura.importe_irpf,
    )
    asiento = await crear_asiento_multilinea(
        db,
        empresa_id=empresa_id,
        fecha=factura.fecha,
        concepto=concepto,
        lineas=lineas,
        actor=actor or "system",
    )
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="ASIENTO_FACTURA",
        entity="journal_entry",
        entity_id=str(asiento.id),
        payload={"factura_id": str(factura.id), "tipo": factura.tipo.value},
    )
    await db.flush()
    return asiento


def _invertir(lineas: list[dict]) -> list[dict]:
    return [
        {
            "cuenta": linea["cuenta"],
            "debe": linea["haber"],
            "haber": linea["debe"],
            "detalle": linea["detalle"],
        }
        for linea in lineas
    ]


async def _persistir_reversal(
    db: AsyncSession,
    *,
    empresa_id: int,
    lineas: list[dict],
    fecha: date,
    concepto: str,
    original_id: uuid.UUID,
    actor: str | None,
) -> JournalEntry:
    lineas_norm, _ = await validar_asiento_multilinea(
        db, empresa_id=empresa_id, lineas=lineas
    )
    numero = await next_numero_asiento(db, empresa_id, fecha.year)
    reversal = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=fecha.year,
        fecha=fecha,
        tipo=JournalEntryTipo.REVERSAL,
        concepto=concepto,
        estado=JournalEntryEstado.POSTED,
        numero_asiento=numero,
        original_id=original_id,
        created_by=actor,
    )
    if reversal.id is None:
        reversal.id = uuid.uuid4()
    db.add(reversal)
    await db.flush()

    for i, linea in enumerate(lineas_norm, start=1):
        db.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=reversal.id,
                account_id=linea["account_id"],
                line_no=i,
                cuenta=linea["cuenta"],
                debe=linea["debit"],
                haber=linea["credit"],
                descripcion=linea["detail"],
            )
        )
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="REVERSAL_FACTURA",
        entity="journal_entry",
        entity_id=str(reversal.id),
        payload={"original_id": str(original_id), "numero": numero},
    )
    await db.flush()
    return reversal


async def crear_asiento_reversal_factura(
    db: AsyncSession,
    *,
    empresa_id: int,
    asiento_original_id: uuid.UUID,
    fecha: date,
    concepto: str,
    actor: str | None = None,
) -> JournalEntry:
    """Rectificación total: invierte las líneas del asiento original real."""
    lineas_raw = (
        await db.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == asiento_original_id,
            )
        )
    ).all()
    if not lineas_raw:
        raise error("lineas_insuficientes", "El asiento original no tiene líneas")
    invertidas = [
        {
            "cuenta": linea.cuenta,
            "debe": f"{linea.haber:0.4f}",
            "haber": f"{linea.debe:0.4f}",
            "detalle": linea.descripcion,
        }
        for linea in lineas_raw
    ]
    return await _persistir_reversal(
        db,
        empresa_id=empresa_id,
        lineas=invertidas,
        fecha=fecha,
        concepto=concepto,
        original_id=asiento_original_id,
        actor=actor,
    )


async def crear_asiento_rectificativa(
    db: AsyncSession,
    *,
    empresa_id: int,
    factura: Factura,
    tipo_naturaleza: FacturaTipo,
    fecha: date,
    concepto: str,
    original_asiento_id: uuid.UUID,
    actor: str | None = None,
) -> JournalEntry:
    """Rectificación parcial: invierte solo las líneas del abono emitido."""
    cuenta_tercero = await subcuenta_tercero(
        db, empresa_id=empresa_id, tercero_id=factura.tercero_id, tipo=tipo_naturaleza
    )
    cuentas = await _cuentas_fiscales(db, empresa_id, tipo_naturaleza)
    lineas = construir_lineas(
        tipo=tipo_naturaleza,
        cuenta_tercero=cuenta_tercero,
        cuentas=cuentas,
        descripcion=concepto,
        base=factura.importe_base,
        iva=factura.importe_iva,
        recargo=factura.importe_recargo,
        irpf=factura.importe_irpf,
    )
    return await _persistir_reversal(
        db,
        empresa_id=empresa_id,
        lineas=_invertir(lineas),
        fecha=fecha,
        concepto=concepto,
        original_id=original_asiento_id,
        actor=actor,
    )


__all__ = [
    "CUENTA_IRPF",
    "construir_lineas",
    "crear_asiento_factura",
    "crear_asiento_rectificativa",
    "crear_asiento_reversal_factura",
    "subcuenta_tercero",
]