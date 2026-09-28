"""Fichero de legalización de libros oficiales (SPEC-019 US2 / FR-006, FR-007).

Emisión restringida a ejercicios cerrados (SPEC-004). La huella SHA-256 se
calcula sobre el contenido canónico del diario (igual que el libro `diario`,
contracts/legalizacion.md §2). Re-emisión solo con huella idéntica; si difiere
se rechaza sin tocar la vigente (el ejercicio está cerrado e inmutable). Una
legalización vigente refuerza el bloqueo de SPEC-004 (FR-007) también a nivel
de motor.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from models.ngo.libros import Legalizacion
from services.audit.writer import audit_escribir
from services.ngo.errores import NgoError
from services.ngo.libros_pdf import (
    _ejercicio_cerrado,
    _entradas_ejercicio,
    _rango,
    canon_diario,
)

FORMATO = "LEGALIZACION V1"


def _fichero_bytes(
    razon_social: str,
    nif: str,
    ejercicio: int,
    desde: int,
    hasta: int,
    total: int,
    fecha_emision: datetime,
    fecha_legalizacion: date | None,
    huella: str,
) -> bytes:
    lineas = [
        FORMATO,
        f"EMPRESA:{razon_social}",
        f"NIF:{nif}",
        f"EJERCICIO:{ejercicio}",
        f"RANGO_ASIENTOS_DESDE:{desde}",
        f"RANGO_ASIENTOS_HASTA:{hasta}",
        f"TOTAL_ASIENTOS:{total}",
        f"FECHA_EMISION:{fecha_emision.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"FECHA_LEGALIZACION:{fecha_legalizacion.isoformat() if fecha_legalizacion else ''}",
        f"HUELLA:{huella}",
        "HUELLA_ALGORITMO:SHA-256",
    ]
    return ("\n".join(lineas) + "\n").encode("utf-8")


async def emitir_legalizacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    fecha_legalizacion: date | None = None,
    actor: str | None = None,
) -> dict:
    await _ejercicio_cerrado(db, empresa_id, ejercicio)
    comp = await db.get(Company, empresa_id)
    razon_social = comp.razon_social if comp else ""
    nif = comp.nif if comp else ""

    entradas = await _entradas_ejercicio(db, empresa_id, ejercicio)
    desde, hasta = _rango(entradas)
    total = int(hasta - desde + 1) if hasta >= desde else 0
    canon = canon_diario(empresa_id, ejercicio, entradas)
    huella = hashlib.sha256(canon.encode("utf-8")).hexdigest()

    existente = await db.scalar(
        select(Legalizacion).where(
            Legalizacion.empresa_id == empresa_id,
            Legalizacion.ejercicio == ejercicio,
        )
    )

    if existente is not None and existente.huella != huella:
        raise NgoError(
            "huella_no_coincide",
            "La huella difiere de la legalización vigente: el contenido del ejercicio cambió",
        )

    ahora = datetime.now(UTC)
    fichero = _fichero_bytes(
        razon_social,
        nif,
        ejercicio,
        desde,
        hasta,
        total,
        ahora,
        fecha_legalizacion,
        huella,
    )

    if existente is None:
        existente = Legalizacion(
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            rango_asientos_desde=desde,
            rango_asientos_hasta=hasta,
            total_asientos=total,
            huella=huella,
            fichero=fichero,
            fecha_emision=ahora,
            fecha_legalizacion=fecha_legalizacion,
            valido=True,
        )
        db.add(existente)
    else:
        existente.rango_asientos_desde = desde
        existente.rango_asientos_hasta = hasta
        existente.total_asientos = total
        existente.huella = huella
        existente.fichero = fichero
        existente.fecha_emision = ahora
        existente.fecha_legalizacion = fecha_legalizacion
        existente.valido = True
        existente.motivo_reemision = "Re-emisión con huella idéntica"
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="EMITIR_LEGALIZACION",
        entity="legalizacion",
        entity_id=str(existente.id),
        payload={
            "ejercicio": ejercicio,
            "rango_desde": desde,
            "rango_hasta": hasta,
            "huella": huella,
        },
    )
    await db.flush()
    return {
        "id": str(existente.id),
        "razon_social": razon_social,
        "nif": nif,
        "ejercicio": ejercicio,
        "rango_asientos_desde": desde,
        "rango_asientos_hasta": hasta,
        "total_asientos": total,
        "huella": huella,
        "fecha_emision": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fecha_legalizacion": fecha_legalizacion.isoformat() if fecha_legalizacion else None,
        "valido": existente.valido,
        "motivo_reemision": existente.motivo_reemision,
        "url": f"/api/v1/legalizaciones/{existente.id}/descarga",
    }


async def listar_legalizaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    total = await db.scalar(
        select(func.count()).select_from(Legalizacion).where(Legalizacion.empresa_id == empresa_id)
    )
    items = (
        await db.scalars(
            select(Legalizacion)
            .where(Legalizacion.empresa_id == empresa_id)
            .order_by(Legalizacion.ejercicio.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(l.id),
                "ejercicio": l.ejercicio,
                "rango_asientos_desde": l.rango_asientos_desde,
                "rango_asientos_hasta": l.rango_asientos_hasta,
                "total_asientos": l.total_asientos,
                "huella": l.huella,
                "fecha_emision": l.fecha_emision.isoformat() if l.fecha_emision else None,
                "fecha_legalizacion": l.fecha_legalizacion.isoformat() if l.fecha_legalizacion else None,
                "valido": l.valido,
                "motivo_reemision": l.motivo_reemision,
                "url": f"/api/v1/legalizaciones/{l.id}/descarga",
            }
            for l in items
        ],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


async def obtener_legalizacion(db: AsyncSession, *, empresa_id: int, legalizacion_id) -> Legalizacion | None:
    return await db.scalar(
        select(Legalizacion).where(
            Legalizacion.empresa_id == empresa_id,
            Legalizacion.id == legalizacion_id,
        )
    )