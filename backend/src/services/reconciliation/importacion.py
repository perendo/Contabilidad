"""Importación de extractos bancarios (SPEC-013 US1)."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.treasury.extracto_bancario import ExtractoBancario
from models.treasury.movimiento_bancario import MovimientoBancario, SignoMovimiento
from services.audit.writer import audit_escribir
from services.reconciliation.parsers import ExtractoDTO, LayoutError, parse_extracto


class ImportacionError(Exception):
    def __init__(self, code: str, message: str, **extra: object) -> None:
        super().__init__(message)
        self.code = code
        self.extra = extra


async def _cuenta_572(
    db: AsyncSession, empresa_id: int, codigo: str
) -> AccountPlan:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.code == codigo,
        )
    )
    if cuenta is None or not cuenta.is_active:
        raise ImportacionError(
            "cuenta_no_encontrada",
            f"Cuenta {codigo} inexistente en la empresa activa",
        )
    return cuenta


async def importar_extracto(
    db: AsyncSession,
    *,
    empresa_id: int,
    file_bytes: bytes,
    nombre_fichero: str,
    layout: str = "norma_43_1919",
    cuenta_codigo: str | None = None,
    actor: str | None = None,
) -> ExtractoBancario:
    """Parse, dedupe and persist the extract + movements atomically (flush boundary)."""
    try:
        dto: ExtractoDTO = parse_extracto(file_bytes, layout)
    except (LayoutError, ValueError) as exc:
        raise ImportacionError(*_layout_args(exc))

    codigo = (cuenta_codigo or dto.cuenta or "").strip()
    if not codigo:
        raise ImportacionError("cuenta_requerida", "La cuenta es obligatoria")
    cuenta = await _cuenta_572(db, empresa_id, codigo)

    sha256 = hashlib.sha256(file_bytes).hexdigest()
    existente = await db.scalar(
        select(ExtractoBancario).where(
            ExtractoBancario.empresa_id == empresa_id,
            ExtractoBancario.sha256 == sha256,
        )
    )
    if existente is not None:
        raise ImportacionError(
            "extracto_duplicado",
            "El extracto ya fue importado",
            extracto_existente_id=str(existente.id),
        )
    solapado = await db.scalar(
        select(ExtractoBancario).where(
            ExtractoBancario.empresa_id == empresa_id,
            ExtractoBancario.cuenta_id == cuenta.id,
            ExtractoBancario.fecha_inicio == dto.fecha_inicio,
            ExtractoBancario.fecha_fin == dto.fecha_fin,
            ExtractoBancario.saldo_inicial == dto.saldo_inicial,
            ExtractoBancario.saldo_final == dto.saldo_final,
            ExtractoBancario.n_movimientos == len(dto.movimientos),
        )
    )
    if solapado is not None:
        raise ImportacionError(
            "extracto_duplicado",
            "Extracto solapado con uno ya importado",
            extracto_existente_id=str(solapado.id),
        )

    extracto = ExtractoBancario(
        empresa_id=empresa_id,
        cuenta_id=cuenta.id,
        fecha_inicio=dto.fecha_inicio,
        fecha_fin=dto.fecha_fin,
        saldo_inicial=dto.saldo_inicial,
        saldo_final=dto.saldo_final,
        nombre_fichero=nombre_fichero,
        sha256=sha256,
        n_movimientos=len(dto.movimientos),
        creado_por=actor,
    )
    db.add(extracto)
    await db.flush()
    for mov in dto.movimientos:
        db.add(
            MovimientoBancario(
                empresa_id=empresa_id,
                extracto_id=extracto.id,
                orden=mov.orden,
                fecha_operacion=mov.fecha_operacion,
                fecha_valor=mov.fecha_valor,
                concepto=mov.concepto,
                importe=mov.importe,
                signo=SignoMovimiento(mov.signo),
                referencia=mov.referencia,
            )
        )
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="IMPORT_EXTRACTO",
        entity="extracto_bancario",
        entity_id=str(extracto.id),
        payload={
            "cuenta": codigo,
            "n_movimientos": str(len(dto.movimientos)),
            "saldo_final": str(dto.saldo_final),
        },
    )
    await db.flush()
    return extracto


def _layout_args(exc: Exception) -> tuple[str, str]:
    code = getattr(exc, "code", "layout_invalido")
    return code, str(exc)
