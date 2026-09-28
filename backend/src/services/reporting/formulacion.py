"""Informe de Balance de Situacion y formulacion oficial (SPEC-010 T012/T034).

- `generar_balance`: agrega las masas patrimoniales (grupos 1-5) y verifica el
  cuadre `Activo == Pasivo + Patrimonio` con `Decimal` exacto; el resultado de
  gestion (grupos 6-7) se incorpora al patrimonio (FR-001).
- `formular`/`anular_formulacion`/`listar_formulaciones`: documento inmutable
  (snapshot + sha256) de un ejercicio cerrado, correlativo y trazable (FR-004/5).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.reporting.configuracion import InformeTipo
from models.reporting.formulacion import (
    FormulacionCuentasAnuales,
    FormulacionEstado,
)
from services.audit.writer import audit_escribir
from services.reporting.agrupacion import cargar_reglas, resolver_masa
from services.reporting.efe import generar_efe
from services.reporting.pyg import generar_pyg
from services.reporting.saldos import (
    error,
    fiscal_year,
    netos_por_cuenta,
    resultado_de_gestion,
)
from services.reports.common import cuantizar, fmt

GRUPOS_BALANCE = ("1", "2", "3", "4", "5")
GRUPOS_RESULTADO = ("6", "7")


def _acumular(bucket: dict[str, dict], codigo: str, nombre: str, importe: Decimal) -> None:
    masa = bucket.setdefault(
        codigo,
        {"codigo": codigo, "nombre": nombre, "importe": Decimal(0), "cuentas": []},
    )
    masa["importe"] += importe
    masa["cuentas"].append(codigo)


def _masas_payload(bucket: dict[str, dict]) -> list[dict]:
    return [
        {
            "codigo": masa["codigo"],
            "nombre": masa["nombre"],
            "importe": fmt(masa["importe"]),
            "partidas": [
                {
                    "nombre": masa["nombre"],
                    "importe": fmt(masa["importe"]),
                    "cuentas": sorted(masa["cuentas"]),
                }
            ],
        }
        for masa in sorted(bucket.values(), key=lambda m: m["codigo"])
    ]


async def generar_balance(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    modo: str = "provisional",
    comparativo: bool = False,
) -> dict:
    if modo not in ("provisional", "oficial"):
        raise error("modo_invalido", "modo debe ser provisional u oficial")
    fy = await fiscal_year(db, empresa_id, ejercicio)
    if modo == "oficial" and (fy is None or not fy.is_closed):
        raise error("ejercicio_no_cerrado", f"El ejercicio {ejercicio} no esta cerrado")

    netos = await netos_por_cuenta(
        db, empresa_id=empresa_id, ejercicio=ejercicio, excluir_cierre=True
    )
    reglas = await cargar_reglas(
        db, empresa_id=empresa_id, ejercicio=ejercicio, informe_tipo=InformeTipo.BALANCE
    )

    activo: dict[str, dict] = {}
    pasivo: dict[str, dict] = {}
    patrimonio: dict[str, dict] = {}
    total_activo = Decimal(0)
    total_pasivo = Decimal(0)
    total_patrimonio = Decimal(0)
    hay_otros = False

    for codigo, neto in netos.items():
        if codigo[:1] in GRUPOS_RESULTADO:
            continue
        masa_codigo, masa_nombre, clasificada = resolver_masa(codigo, reglas)
        if not clasificada:
            hay_otros = True
        if codigo[:1] == "1":
            importe = -neto
            total_patrimonio += importe
            _acumular(patrimonio, masa_codigo, masa_nombre, importe)
        elif codigo[:1] in ("2", "3") or neto > 0:
            total_activo += neto
            _acumular(activo, masa_codigo, masa_nombre, neto)
        else:
            importe = -neto
            total_pasivo += importe
            _acumular(pasivo, masa_codigo, masa_nombre, importe)

    resultado = resultado_de_gestion(netos)
    if resultado != 0:
        total_patrimonio += resultado
        _acumular(patrimonio, "RESULTADO", "Resultado del ejercicio", resultado)

    cuadre = cuantizar(total_activo) == cuantizar(total_pasivo + total_patrimonio)
    if not cuadre:
        raise error(
            "balance_descuadrado",
            f"Activo {fmt(total_activo)} != Pasivo+Patrimonio "
            f"{fmt(total_pasivo + total_patrimonio)}",
        )

    comparativo_anterior = None
    if comparativo:
        from services.reporting.comparativo import resumen_balance

        comparativo_anterior = await resumen_balance(
            db, empresa_id=empresa_id, ejercicio=ejercicio - 1
        )

    return {
        "ejercicio": ejercicio,
        "modo": modo,
        "cuadre": cuadre,
        "total_activo": fmt(total_activo),
        "total_pasivo": fmt(total_pasivo),
        "total_patrimonio": fmt(total_patrimonio),
        "resultado_ejercicio": fmt(resultado),
        "hay_cuentas_sin_agrupar": hay_otros,
        "activo": _masas_payload(activo),
        "pasivo": _masas_payload(pasivo),
        "patrimonio": _masas_payload(patrimonio),
        "comparativo_anterior": comparativo_anterior,
    }


def _hash_snapshot(snapshot: dict) -> str:
    crudo = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(crudo).hexdigest()


async def _siguiente_numero_formulacion(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> int:
    ultimo = await db.scalar(
        select(func.max(FormulacionCuentasAnuales.numero_formulacion))
        .where(
            FormulacionCuentasAnuales.empresa_id == empresa_id,
            FormulacionCuentasAnuales.ejercicio == ejercicio,
        )
        .with_for_update()
    )
    return int(ultimo) + 1 if ultimo is not None else 1


async def formular(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    usuario_id: str | None = None,
    observaciones: str | None = None,
) -> dict:
    fy = await fiscal_year(db, empresa_id, ejercicio)
    if fy is None or not fy.is_closed:
        raise error("ejercicio_no_cerrado", f"El ejercicio {ejercicio} no esta cerrado")

    vigente = await db.scalar(
        select(FormulacionCuentasAnuales.id).where(
            FormulacionCuentasAnuales.empresa_id == empresa_id,
            FormulacionCuentasAnuales.ejercicio == ejercicio,
            FormulacionCuentasAnuales.estado == FormulacionEstado.formulada,
        )
    )
    if vigente is not None:
        raise error("ya_formulada", "Ya existe una formulacion vigente del ejercicio")

    balance = await generar_balance(
        db, empresa_id=empresa_id, ejercicio=ejercicio, modo="oficial"
    )
    pyg = await generar_pyg(db, empresa_id=empresa_id, ejercicio=ejercicio, modo="oficial")
    efe = await generar_efe(db, empresa_id=empresa_id, ejercicio=ejercicio, modo="oficial")

    snapshot = {"balance": balance, "pyg": pyg, "efe": efe}
    contenido_hash = _hash_snapshot(snapshot)
    numero = await _siguiente_numero_formulacion(db, empresa_id, ejercicio)

    formulacion = FormulacionCuentasAnuales(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        numero_formulacion=numero,
        fecha_formulacion=datetime.now(timezone.utc),
        usuario_id=usuario_id,
        contenido_hash=contenido_hash,
        estado=FormulacionEstado.formulada,
        snapshot=snapshot,
        observaciones=(observaciones or "")[:255] or None,
    )
    db.add(formulacion)
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=usuario_id or "system",
        action="FORMULAR_CUENTAS_ANUALES",
        entity="formulacion_cuentas_anuales",
        entity_id=str(formulacion.id),
        payload={
            "ejercicio": ejercicio,
            "numero_formulacion": numero,
            "contenido_hash": contenido_hash,
        },
    )
    await db.flush()
    return _formulacion_payload(formulacion)


async def anular_formulacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    motivo: str,
    usuario_id: str | None = None,
) -> dict:
    formulacion = await db.scalar(
        select(FormulacionCuentasAnuales).where(
            FormulacionCuentasAnuales.empresa_id == empresa_id,
            FormulacionCuentasAnuales.ejercicio == ejercicio,
            FormulacionCuentasAnuales.estado == FormulacionEstado.formulada,
        )
    )
    if formulacion is None:
        raise error("sin_formulacion", "No hay formulacion vigente que anular")
    if not (motivo or "").strip():
        raise error("motivo_requerido", "La anulacion requiere un motivo")
    formulacion.estado = FormulacionEstado.anulada
    formulacion.motivo_anulacion = motivo[:255]
    formulacion.anulada_por = usuario_id
    formulacion.anulada_en = datetime.now(timezone.utc)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=usuario_id or "system",
        action="ANULAR_FORMULACION_CUENTAS_ANUALES",
        entity="formulacion_cuentas_anuales",
        entity_id=str(formulacion.id),
        payload={"ejercicio": ejercicio, "motivo": motivo[:255]},
    )
    await db.flush()
    return _formulacion_payload(formulacion)


async def listar_formulaciones(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> dict:
    filas = (
        await db.scalars(
            select(FormulacionCuentasAnuales)
            .where(
                FormulacionCuentasAnuales.empresa_id == empresa_id,
                FormulacionCuentasAnuales.ejercicio == ejercicio,
            )
            .order_by(FormulacionCuentasAnuales.numero_formulacion)
        )
    ).all()
    return {"items": [_formulacion_payload(f) for f in filas]}


def _formulacion_payload(formulacion: FormulacionCuentasAnuales) -> dict:
    return {
        "formulacion_id": str(formulacion.id),
        "ejercicio": formulacion.ejercicio,
        "numero_formulacion": formulacion.numero_formulacion,
        "fecha_formulacion": formulacion.fecha_formulacion.isoformat(),
        "usuario": formulacion.usuario_id,
        "estado": formulacion.estado.value,
        "contenido_hash": formulacion.contenido_hash,
        "motivo_anulacion": formulacion.motivo_anulacion,
    }