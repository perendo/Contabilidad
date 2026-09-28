"""Justificación de gastos (SPEC-019 US1): imputación línea a línea del diario.

La imputación ancla un `GastoImputado` a una línea POSTED de un asiento del
motor (SPEC-002): la suma imputada por línea no puede exceder el importe de la
línea, y la suma por subvención no puede exceder `importe_concedido`. Hasta que
la subvención no está justificada, la imputación puede deshacerse. Todo dentro
del boundary ACID del llamante (`get_db`).
"""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
)
from models.ngo.gasto_imputado import GastoImputado
from models.ngo.subvencion import Subvencion, SubvencionEstado
from services.audit.writer import audit_escribir
from services.ngo.errores import NgoError


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


async def _imputado_en_linea(db: AsyncSession, empresa_id: int, linea_id: uuid.UUID) -> Decimal:
    return Decimal(
        await db.scalar(
            select(func.coalesce(func.sum(GastoImputado.importe_asignado), 0)).where(
                GastoImputado.empresa_id == empresa_id,
                GastoImputado.linea_id == linea_id,
            )
        )
        or 0
    )


async def imputar_gasto(
    db: AsyncSession,
    *,
    empresa_id: int,
    subvencion_id: uuid.UUID,
    asiento_id: uuid.UUID,
    linea_id: uuid.UUID,
    importe_asignado: Decimal,
    partida: str | None = None,
    actor: str | None = None,
) -> dict:
    if importe_asignado <= 0:
        raise NgoError("importe_invalido", "El importe asignado debe ser positivo")

    sub = await db.scalar(
        select(Subvencion)
        .where(
            Subvencion.empresa_id == empresa_id,
            Subvencion.id == subvencion_id,
        )
        .with_for_update()
    )
    if sub is None:
        raise NgoError("subvencion_no_encontrada", "La subvención no existe en la empresa activa")
    if sub.estado in (SubvencionEstado.justificada, SubvencionEstado.reintegrada):
        raise NgoError("subvencion_cerrada", "La subvención ya está justificada o reintegrada")

    asiento = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.id == asiento_id,
        )
    )
    if asiento is None:
        raise NgoError("asiento_no_encontrado", "El asiento no existe en la empresa activa")
    if asiento.estado != JournalEntryEstado.POSTED:
        raise NgoError("asiento_no_asentado", "Solo se imputan gastos de asientos POSTED")

    linea = await db.scalar(
        select(JournalEntryLine).where(
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntryLine.id == linea_id,
        )
    )
    if linea is None:
        raise NgoError("linea_no_encontrada", "La línea no existe en la empresa activa")
    if linea.journal_entry_id != asiento.id:
        raise NgoError("linea_no_pertenece_asiento", "La línea no pertenece al asiento indicado")
    if linea.debe <= 0:
        raise NgoError("linea_no_es_gasto", "Solo se imputan líneas de gasto (Debe)")

    duplicado = await db.scalar(
        select(GastoImputado).where(
            GastoImputado.empresa_id == empresa_id,
            GastoImputado.asiento_id == asiento_id,
            GastoImputado.linea_id == linea_id,
        )
    )
    if duplicado is not None:
        raise NgoError("gasto_ya_imputado", "Esa línea ya está imputada a una subvención")

    imputado_linea = await _imputado_en_linea(db, empresa_id, linea_id)
    if imputado_linea + importe_asignado > linea.debe:
        raise NgoError(
            "excede_importe_linea",
            f"El importe {_cuatro(importe_asignado)} excede el resto de la línea "
            f"({_cuatro(linea.debe - imputado_linea)})",
        )

    gastado = await _gastado(db, empresa_id, sub.id)
    if gastado + importe_asignado > sub.importe_concedido:
        raise NgoError(
            "excede_disponible",
            f"El importe {_cuatro(importe_asignado)} excede el disponible de la subvención "
            f"({_cuatro(sub.importe_concedido - gastado)})",
        )

    gasto = GastoImputado(
        empresa_id=empresa_id,
        subvencion_id=sub.id,
        asiento_id=asiento.id,
        linea_id=linea.id,
        importe_asignado=importe_asignado,
        partida=partida.strip() if partida else None,
    )
    if gasto.id is None:
        gasto.id = uuid.uuid4()
    db.add(gasto)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="IMPUTAR_GASTO",
        entity="gasto_imputado",
        entity_id=str(gasto.id),
        payload={
            "subvencion_id": str(sub.id),
            "asiento_id": str(asiento.id),
            "importe": str(gasto.importe_asignado),
        },
    )
    await db.flush()
    nuevo_gastado = gastado + importe_asignado
    return {
        "id": str(gasto.id),
        "subvencion_id": str(sub.id),
        "asiento_id": str(asiento.id),
        "linea_id": str(linea.id),
        "importe_asignado": _cuatro(gasto.importe_asignado),
        "partida": gasto.partida,
        "gastado": _cuatro(nuevo_gastado),
        "pendiente": _cuatro(sub.importe_concedido - nuevo_gastado),
    }


async def desimputar_gasto(
    db: AsyncSession,
    *,
    empresa_id: int,
    subvencion_id: uuid.UUID,
    gasto_id: uuid.UUID,
    actor: str | None = None,
) -> None:
    sub = await db.scalar(
        select(Subvencion).where(
            Subvencion.empresa_id == empresa_id,
            Subvencion.id == subvencion_id,
        )
    )
    if sub is None:
        raise NgoError("subvencion_no_encontrada", "La subvención no existe en la empresa activa")

    gasto = await db.scalar(
        select(GastoImputado).where(
            GastoImputado.empresa_id == empresa_id,
            GastoImputado.subvencion_id == subvencion_id,
            GastoImputado.id == gasto_id,
        )
    )
    if gasto is None:
        raise NgoError("gasto_no_encontrado", "La imputación no existe en la empresa activa")
    if sub.estado in (SubvencionEstado.justificada, SubvencionEstado.reintegrada):
        raise NgoError("gasto_ya_usado", "No se puede desimputar un gasto de una subvención justificada")

    await db.delete(gasto)
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="DESIMPUTAR_GASTO",
        entity="gasto_imputado",
        entity_id=str(gasto_id),
        payload={"subvencion_id": str(subvencion_id)},
    )
    await db.flush()


def _canon_informe(
    empresa_id: int,
    sub: Subvencion,
    gastado: Decimal,
    lineas: list[JournalEntryLine],
) -> str:
    canon = (
        f"{empresa_id}|{sub.estado.value}|{sub.importe_concedido:.4f}|{gastado:.4f}|"
    )
    for linea in lineas:
        canon += (
            f"{linea.journal_entry_id!s}|{linea.cuenta}|"
            f"{linea.debe:.4f}|{linea.haber:.4f}|"
        )
    return canon


async def informe_justificacion(
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

    imputaciones = (
        await db.scalars(
            select(GastoImputado)
            .where(
                GastoImputado.empresa_id == empresa_id,
                GastoImputado.subvencion_id == sub.id,
            )
            .order_by(GastoImputado.created_at)
        )
    ).all()

    lineas_canon: list[JournalEntryLine] = []
    asientos = {
        a.id: a
        for a in (
            await db.scalars(
                select(JournalEntry).where(
                    JournalEntry.empresa_id == empresa_id,
                    JournalEntry.id.in_([g.asiento_id for g in imputaciones]),
                )
            )
        ).all()
    }
    detalle = []
    for g in imputaciones:
        linea = await db.scalar(
            select(JournalEntryLine).where(
                JournalEntryLine.empresa_id == empresa_id,
                JournalEntryLine.id == g.linea_id,
            )
        )
        asiento = asientos.get(g.asiento_id)
        if linea is not None:
            lineas_canon.append(linea)
        detalle.append(
            {
                "id": str(g.id),
                "asiento_id": str(g.asiento_id),
                "numero_asiento": asiento.numero_asiento if asiento else None,
                "fecha": asiento.fecha.isoformat() if asiento else None,
                "cuenta": linea.cuenta if linea else None,
                "importe": _cuatro(g.importe_asignado),
                "partida": g.partida,
            }
        )

    pendiente = sub.importe_concedido - gastado
    canon = _canon_informe(empresa_id, sub, gastado, lineas_canon)
    return {
        "id": str(sub.id),
        "entidad_concedente": sub.entidad_concedente,
        "programa": sub.programa,
        "referencia": sub.referencia,
        "importe_concedido": _cuatro(sub.importe_concedido),
        "gastado": _cuatro(gastado),
        "pendiente": _cuatro(pendiente),
        "estado": sub.estado.value,
        "partidas": sub.partidas,
        "detalle": detalle,
        "huella": hashlib.sha256(canon.encode("utf-8")).hexdigest(),
    }


async def exportar_informe(
    db: AsyncSession,
    *,
    empresa_id: int,
    subvencion_id: uuid.UUID,
    formato: str,
) -> tuple[bytes, str, str]:
    informe = await informe_justificacion(db, empresa_id=empresa_id, subvencion_id=subvencion_id)
    if informe is None:
        raise NgoError("subvencion_no_encontrada", "La subvención no existe en la empresa activa")

    filename = f"justificacion_{subvencion_id}.{formato}"
    if formato == "csv":
        renglones = [
            "entidad;programa;referencia;numero_asiento;fecha;cuenta;importe;partida"
        ]
        for d in informe["detalle"]:
            renglones.append(
                ";".join(
                    [
                        informe["entidad_concedente"],
                        informe["programa"],
                        informe["referencia"] or "",
                        str(d.get("numero_asiento") or ""),
                        d.get("fecha") or "",
                        d.get("cuenta") or "",
                        d.get("importe") or "",
                        d.get("partida") or "",
                    ]
                )
            )
        content = "\n".join(renglones)
        return (
            ("\ufeff" + content).encode("utf-8"),
            "text/csv; charset=utf-8",
            filename,
        )
    if formato == "json":
        payload: Any = informe
        return (
            __import__("json").dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            filename,
        )
    raise NgoError("formato_invalido", f"Formato desconocido: {formato}")