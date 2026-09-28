"""Asientos en divisa (SPEC-016 US1): cuadre doble divisa/funcional.

El cliente envía líneas con importes en la divisa (Debe/Haber exactamente uno
por línea); el servicio convierte línea a línea a moneda funcional (4
decimales, ROUND_HALF_EVEN) y si el contravalor funcional no cuadra imputa el
remanente a una línea de redondeo (6680/7690) para que Debe == Haber en la
moneda funcional (constitución I, nunca se desequilibra). El asiento se crea
con el motor de SPEC-002/006 (POSTED, numeración correlativa) y el TipoCambio
queda sellado en la misma transacción.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntryLine
from models.monedas.asiento_divisa import AsientoDivisa
from models.monedas.linea_divisa import LineaDivisa
from models.monedas.moneda import Moneda
from models.monedas.tipo_cambio import TipoCambio
from services.audit.writer import audit_escribir
from services.forex.conversion import convertir
from services.forex.cuentas import Lado, cuenta_diferencia_cambio
from services.forex.errores import ForexError
from services.forex.monedas import divisa_de_empresa
from services.forex.tipos import (
    _cuatro,
    _ocho,
    obtener_tipo_asiento,
    sellar_tipo,
)
from services.journal.entry_service import AsientoError
from services.journal.money import as_decimal
from services.journal.motor import crear_asiento_multilinea
from services.journal.validador_multilinea import MultilineaError


def _normalizar_linea(linea: dict, idx: int) -> dict:
    cuenta_id_raw = linea.get("cuenta_id")
    if cuenta_id_raw is None:
        raise ForexError("linea_invalida", f"Línea {idx}: cuenta_id inválido")
    try:
        cuenta_id = int(cuenta_id_raw)
    except (TypeError, ValueError):
        raise ForexError("linea_invalida", f"Línea {idx}: cuenta_id inválido")
    if cuenta_id <= 0:
        raise ForexError("linea_invalida", f"Línea {idx}: cuenta_id inválido")
    debe = as_decimal(str(linea.get("debe_divisa") or "0"))
    haber = as_decimal(str(linea.get("haber_divisa") or "0"))
    if (debe > 0) == (haber > 0):
        raise ForexError(
            "linea_invalida",
            f"Línea {idx}: cada línea debe llevar solo Debe o solo Haber en divisa",
        )
    return {"cuenta_id": cuenta_id, "debe": debe, "haber": haber}


async def _cuentas_de(
    db: AsyncSession,
    empresa_id: int,
    cuenta_ids: set[int],
) -> dict[int, AccountPlan]:
    if not cuenta_ids:
        return {}
    filas = (
        await db.scalars(
            select(AccountPlan).where(
                AccountPlan.tenant_id == empresa_id,
                AccountPlan.id.in_(cuenta_ids),
            )
        )
    ).all()
    return {c.id: c for c in filas}


async def registrar_asiento_divisa(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha: date,
    divisa_id: uuid.UUID,
    concepto: str,
    lineas: list[dict],
    tipo_cambio_id: uuid.UUID | None = None,
    ratio_explicito: str | int | Decimal | None = None,
    actor: str | None = None,
) -> dict:
    """Registra y asienta (POSTED) un asiento en divisa con cuadre funcional."""
    divisa = await divisa_de_empresa(db, empresa_id, divisa_id)
    if divisa is None:
        raise ForexError(
            "divisa_no_encontrada",
            "La divisa no pertenece a la empresa activa o no está activa",
        )
    if divisa.es_funcional:
        raise ForexError(
            "divisa_funcional",
            "El asiento en divisa requiere una divisa no funcional",
        )
    if not concepto or not concepto.strip():
        raise ForexError("concepto_vacio", "El concepto es obligatorio")

    lineas_norm = [_normalizar_linea(l, i) for i, l in enumerate(lineas)]
    if len(lineas_norm) < 2:
        raise ForexError("lineas_insuficientes", "Se requieren al menos dos líneas")

    debe_div = sum((l["debe"] for l in lineas_norm), Decimal(0))
    haber_div = sum((l["haber"] for l in lineas_norm), Decimal(0))
    if debe_div <= 0 or haber_div <= 0 or debe_div != haber_div:
        raise ForexError(
            "desbalance_divisa",
            "El asiento en divisa necesita Debe y Haber positivos e iguales",
        )

    tipo = await obtener_tipo_asiento(
        db,
        empresa_id=empresa_id,
        divisa_id=divisa_id,
        fecha=fecha,
        tipo_cambio_id=tipo_cambio_id,
        ratio_explicito=ratio_explicito,
    )
    ratio = tipo.ratio

    cuentas = await _cuentas_de(
        db, empresa_id, {l["cuenta_id"] for l in lineas_norm}
    )
    for l in lineas_norm:
        if l["cuenta_id"] not in cuentas:
            raise ForexError(
                "cuenta_no_encontrada",
                f"La cuenta {l['cuenta_id']} no existe en la empresa activa",
            )

    lineas_full: list[dict] = []
    func_debe = Decimal(0)
    func_haber = Decimal(0)
    for linea in lineas_norm:
        es_debe = linea["debe"] > 0
        importe = linea["debe"] if es_debe else linea["haber"]
        func = convertir(importe, ratio)
        if es_debe:
            func_debe += func
        else:
            func_haber += func
        lineas_full.append(
            {
                "cuenta": cuentas[linea["cuenta_id"]].code,
                "debe": func if es_debe else Decimal(0),
                "haber": Decimal(0) if es_debe else func,
                "detalle": f"{divisa.codigo_iso} {_cuatro(importe)}",
                "importe_divisa": importe,
                "es_redondeo": False,
            }
        )

    delta = func_debe - func_haber
    if delta != 0:
        lado_redondeo: Lado = "debe" if delta < 0 else "haber"
        importe_redondeo = abs(delta)
        cuenta_red = await cuenta_diferencia_cambio(db, empresa_id, lado_redondeo)
        if lado_redondeo == "debe":
            func_debe += importe_redondeo
        else:
            func_haber += importe_redondeo
        lineas_full.append(
            {
                "cuenta": cuenta_red.code,
                "debe": importe_redondeo if lado_redondeo == "debe" else Decimal(0),
                "haber": importe_redondeo if lado_redondeo == "haber" else Decimal(0),
                "detalle": f"Redondeo {divisa.codigo_iso}",
                "importe_divisa": Decimal(0),
                "es_redondeo": True,
            }
        )

    assert func_debe == func_haber, "el contravalor funcional debe cuadrar"

    lineas_motor = [
        {
            "cuenta": l["cuenta"],
            "debe": _cuatro(l["debe"]),
            "haber": _cuatro(l["haber"]),
            "detalle": l["detalle"],
        }
        for l in lineas_full
    ]
    try:
        entrada = await crear_asiento_multilinea(
            db,
            empresa_id=empresa_id,
            fecha=fecha,
            concepto=concepto,
            lineas=lineas_motor,
            actor=actor,
        )
    except (AsientoError, MultilineaError) as exc:
        raise ForexError(exc.code, str(exc)) from exc

    ad = AsientoDivisa(
        empresa_id=empresa_id,
        asiento_id=entrada.id,
        divisa_id=divisa_id,
        tipo_cambio_id=tipo.id,
        fecha=fecha,
        concepto=concepto,
        importe_total_divisa=debe_div,
        importe_total_funcional=func_debe,
    )
    if ad.id is None:
        ad.id = uuid.uuid4()
    db.add(ad)
    await db.flush()

    lineas_finales = (
        await db.scalars(
            select(JournalEntryLine)
            .where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == entrada.id,
            )
            .order_by(JournalEntryLine.line_no)
        )
    ).all()
    for jl, lf in zip(lineas_finales, lineas_full):
        db.add(
            LineaDivisa(
                empresa_id=empresa_id,
                asiento_divisa_id=ad.id,
                linea_id=jl.id,
                importe_divisa=lf["importe_divisa"],
                importe_funcional=(lf["debe"] or lf["haber"]),
                es_linea_redondeo=lf["es_redondeo"],
            )
        )

    await sellar_tipo(db, tipo)
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="ASIENTO_DIVISA",
        entity="asiento_divisa",
        entity_id=str(ad.id),
        payload={
            "asiento_id": str(entrada.id),
            "divisa_id": str(divisa_id),
            "fecha": fecha.isoformat(),
            "importe_total_divisa": _cuatro(ad.importe_total_divisa),
            "importe_total_funcional": _cuatro(ad.importe_total_funcional),
            "tipo_cambio_id": str(tipo.id),
            "ratio": _ocho(ratio),
            "n_lineas": len(lineas_finales),
        },
    )
    await db.flush()
    linea_redondeo = next(
        (l for l in lineas_full if l["es_redondeo"]), None
    )
    return {
        "id": str(ad.id),
        "asiento_id": str(entrada.id),
        "numero_asiento": entrada.numero_asiento,
        "fecha": fecha.isoformat(),
        "divisa_id": str(divisa_id),
        "divisa": divisa.codigo_iso,
        "concepto": concepto,
        "importe_total_divisa": _cuatro(ad.importe_total_divisa),
        "importe_total_funcional": _cuatro(ad.importe_total_funcional),
        "ratio": _ocho(ratio),
        "tipo_cambio_id": str(tipo.id),
        "sellado": tipo.sellado,
        "usos_posteados": tipo.usos_posteados,
        "n_lineas": len(lineas_finales),
        "linea_redondeo": (
            {
                "cuenta": linea_redondeo["cuenta"],
                "importe": (
                    _cuatro(linea_redondeo["debe"])
                    if linea_redondeo["debe"] > 0
                    else _cuatro(linea_redondeo["haber"])
                ),
            }
            if linea_redondeo is not None
            else None
        ),
    }


async def detalle_asiento_divisa(
    db: AsyncSession,
    empresa_id: int,
    asiento_id: uuid.UUID,
) -> dict | None:
    """Detalle de un asiento en divisa con sus líneas (contrato US1)."""
    ad = await db.scalar(
        select(AsientoDivisa).where(
            AsientoDivisa.empresa_id == empresa_id,
            AsientoDivisa.asiento_id == asiento_id,
        )
    )
    if ad is None:
        return None
    tipo = await db.scalar(
        select(TipoCambio).where(
            TipoCambio.empresa_id == empresa_id,
            TipoCambio.id == ad.tipo_cambio_id,
        )
    )
    divisa = await db.get(Moneda, ad.divisa_id)
    lineas = (
        await db.scalars(
            select(JournalEntryLine)
            .where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.journal_entry_id == ad.asiento_id,
            )
            .order_by(JournalEntryLine.line_no)
        )
    ).all()
    divs = {
        ld.linea_id: ld
        for ld in (
            await db.scalars(
                select(LineaDivisa).where(
                    LineaDivisa.empresa_id == empresa_id,
                    LineaDivisa.asiento_divisa_id == ad.id,
                )
            )
        ).all()
    }
    filas = []
    for jl in lineas:
        ld = divs.get(jl.id)
        if ld is None:
            continue
        es_debe = jl.debe > 0
        filas.append(
            {
                "linea_id": str(jl.id),
                "cuenta": jl.cuenta,
                "cuenta_id": jl.account_id if jl.account_id is not None else None,
                "debe": _cuatro(jl.debe),
                "haber": _cuatro(jl.haber),
                "debe_funcional": _cuatro(jl.debe),
                "haber_funcional": _cuatro(jl.haber),
                "debe_divisa": _cuatro(ld.importe_divisa) if es_debe else "0.0000",
                "haber_divisa": "0.0000" if es_debe else _cuatro(ld.importe_divisa),
                "importe_divisa": _cuatro(ld.importe_divisa),
                "importe_funcional": _cuatro(ld.importe_funcional),
                "es_linea_redondeo": ld.es_linea_redondeo,
            }
        )
    return {
        "id": str(ad.id),
        "asiento_id": str(ad.asiento_id),
        "fecha": ad.fecha.isoformat(),
        "divisa_id": str(ad.divisa_id),
        "divisa": divisa.codigo_iso if divisa is not None else str(ad.divisa_id),
        "concepto": ad.concepto,
        "importe_total_divisa": _cuatro(ad.importe_total_divisa),
        "importe_total_funcional": _cuatro(ad.importe_total_funcional),
        "total_divisa": _cuatro(ad.importe_total_divisa),
        "total_funcional": _cuatro(ad.importe_total_funcional),
        "ratio": _ocho(tipo.ratio) if tipo is not None else None,
        "tipo_cambio_id": str(ad.tipo_cambio_id),
        "sellado": tipo.sellado if tipo is not None else False,
        "usos_posteados": tipo.usos_posteados if tipo is not None else 0,
        "n_lineas": len(filas),
        "lineas": filas,
    }