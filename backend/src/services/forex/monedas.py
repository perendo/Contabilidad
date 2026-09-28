"""Moneda funcional y divisas de trabajo (SPEC-016 US1).

Cada empresa tiene exactamente una moneda funcional (se crea en EUR de forma
perezosa e idempotente) y N divisas de trabajo activas/inactivas. La empresa
activa SIEMPRE se deriva de la sesión (`get_empresa_id`), nunca del cliente
(constitución III).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.monedas.moneda import Moneda
from services.audit.writer import audit_escribir
from services.forex.errores import ForexError

_CODIGO_DEFECTO = "EUR"
_ISO_RE = re.compile(r"^[A-Z]{3}$")


def normalizar_iso(codigo_iso: str) -> str:
    return codigo_iso.strip().upper()


async def moneda_funcional(db: AsyncSession, empresa_id: int) -> Moneda:
    """Devuelve la moneda funcional de la empresa, creándola (EUR) si no existe."""
    funcional = await db.scalar(
        select(Moneda).where(
            Moneda.empresa_id == empresa_id,
            Moneda.es_funcional.is_(True),
        )
    )
    if funcional is not None:
        return funcional
    funcional = Moneda(
        empresa_id=empresa_id,
        codigo_iso=_CODIGO_DEFECTO,
        es_funcional=True,
        activa=True,
    )
    if funcional.id is None:
        funcional.id = uuid.uuid4()
    db.add(funcional)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor="system",
        action="CREAR_MONEDA_FUNCIONAL",
        entity="moneda",
        entity_id=str(funcional.id),
        payload={"codigo_iso": _CODIGO_DEFECTO},
    )
    await db.flush()
    return funcional


async def divisa_de_empresa(
    db: AsyncSession,
    empresa_id: int,
    divisa_id: uuid.UUID,
    *,
    activa: bool = True,
) -> Moneda | None:
    """Divisa de trabajo (no funcional) de la empresa; ``None`` si no existe."""
    return await db.scalar(
        select(Moneda).where(
            Moneda.empresa_id == empresa_id,
            Moneda.id == divisa_id,
            Moneda.es_funcional.is_(False),
            Moneda.activa.is_(activa),
        )
    )


async def listar_divisas(db: AsyncSession, empresa_id: int) -> dict:
    """Contrato GET /api/v1/divisas: moneda funcional + divisas de trabajo."""
    funcional = await moneda_funcional(db, empresa_id)
    divisas = (
        await db.scalars(
            select(Moneda)
            .where(Moneda.empresa_id == empresa_id, Moneda.es_funcional.is_(False))
            .order_by(Moneda.codigo_iso)
        )
    ).all()
    return {
        "funcional": funcional.codigo_iso,
        "items": [
            {
                "id": str(d.id),
                "codigo_iso": d.codigo_iso,
                "es_funcional": False,
                "activa": d.activa,
            }
            for d in divisas
        ],
    }


async def registrar_divisa(
    db: AsyncSession,
    *,
    empresa_id: int,
    codigo_iso: str,
    activa: bool = True,
    actor: str | None = None,
) -> dict:
    """Alta de una divisa de trabajo (POST /api/v1/divisas)."""
    codigo = normalizar_iso(codigo_iso)
    if _ISO_RE.match(codigo) is None:
        raise ForexError(
            "codigo_iso_invalido",
            "El código de divisa debe ser ISO 4217 de 3 letras",
        )
    funcional = await moneda_funcional(db, empresa_id)
    if codigo == funcional.codigo_iso:
        raise ForexError(
            "divisa_funcional",
            "La moneda funcional ya existe con ese código de divisa",
        )
    duplicada = await db.scalar(
        select(Moneda.id).where(
            Moneda.empresa_id == empresa_id,
            Moneda.codigo_iso == codigo,
            Moneda.es_funcional.is_(False),
        )
    )
    if duplicada is not None:
        raise ForexError(
            "divisa_ya_existe",
            f"Ya existe una divisa {codigo} en la empresa activa",
        )
    divisa = Moneda(
        empresa_id=empresa_id,
        codigo_iso=codigo,
        es_funcional=False,
        activa=activa,
    )
    if divisa.id is None:
        divisa.id = uuid.uuid4()
    db.add(divisa)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREAR_DIVISA",
        entity="moneda",
        entity_id=str(divisa.id),
        payload={"codigo_iso": codigo, "activa": activa},
    )
    await db.flush()
    return {
        "id": str(divisa.id),
        "codigo_iso": divisa.codigo_iso,
        "es_funcional": False,
        "activa": divisa.activa,
    }