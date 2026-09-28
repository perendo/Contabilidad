"""Validación de asientos multilínea (SPEC-006 Foundational T003).

Valida asientos con N partidas al Debe y M al Haber en formato de contrato:
``[{"cuenta", "debe", "haber", "detalle"}]`` (``cuenta`` es el código del PGC
de la empresa activa). Rechaza **antes de persistir**: lado vacío
(`lado_vacio`), desbalanceo (`desbalanceo`), línea con ambos o ningún importe
(`linea_invalida`), cuenta inexistente/no apuntable
(`cuenta_no_encontrada`/`cuenta_no_apuntable`), más de 4 decimales
(`precision_invalida`), importe negativo (`importe_negativo`) y límite de
líneas (`limite_lineas_excedido`, default 100).

Las sumas se acumulan en `Decimal` (prohibido `float`, constitución I).
Líneas repetidas de la misma cuenta son admisibles (FR-007).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.costcenters.centro_coste import CentroCoste, CentroEstado
from services.journal.money import as_decimal, tiene_mas_de_4_decimales

LIMITE_LINEAS_DEFAULT = 100


@dataclass
class ErrorValidacion:
    linea: int | None
    code: str
    message: str


class MultilineaError(Exception):
    """Primer error de validación (patrón de la casa: `code` + message)."""

    def __init__(self, code: str, message: str, errores: list[ErrorValidacion] | None = None):
        self.code = code
        self.errores = errores or []
        super().__init__(message)


def _error(linea: int | None, code: str, message: str) -> ErrorValidacion:
    return ErrorValidacion(linea=linea, code=code, message=message)


def _normalizar_linea(linea: dict[str, Any], idx: int) -> tuple[dict[str, Any], ErrorValidacion | None]:
    cuenta = str(linea.get("cuenta") or "").strip()
    if not cuenta:
        return {}, _error(idx, "linea_invalida", f"Línea {idx}: código de cuenta vacío")

    debe_str = str(linea.get("debe") or "0")
    haber_str = str(linea.get("haber") or "0")
    if tiene_mas_de_4_decimales(debe_str) or tiene_mas_de_4_decimales(haber_str):
        return {}, _error(idx, "precision_invalida", f"Línea {idx}: más de 4 decimales")
    debe = as_decimal(debe_str)
    haber = as_decimal(haber_str)
    if debe < 0 or haber < 0:
        return {}, _error(idx, "importe_negativo", f"Línea {idx}: importes negativos no permitidos")
    if (debe > 0) == (haber > 0):
        if debe == 0 and haber == 0:
            return {}, _error(idx, "linea_invalida", f"Línea {idx}: debe y haber ambos 0")
        return {}, _error(idx, "linea_invalida", f"Línea {idx}: debe y haber ambos > 0")
    detalle = linea.get("detalle")
    centro_raw = linea.get("centro_coste_id")
    centro_id: uuid.UUID | None = None
    if centro_raw not in (None, "", "0"):
        try:
            centro_id = centro_raw if isinstance(centro_raw, uuid.UUID) else uuid.UUID(str(centro_raw))
        except (ValueError, TypeError):
            return {}, _error(idx, "centro_invalido", f"Línea {idx}: centro_coste_id inválido")
    return {
        "account_id": None,
        "cuenta": cuenta,
        "debit": debe,
        "credit": haber,
        "detail": str(detalle) if detalle is not None else None,
        "centro_coste_id": centro_id,
    }, None


async def validar_asiento_multilinea(
    db: AsyncSession,
    *,
    empresa_id: int,
    lineas: list[dict[str, Any]],
    limite: int = LIMITE_LINEAS_DEFAULT,
) -> tuple[list[dict[str, Any]], dict[str, AccountPlan]]:
    """Valida un asiento N:M y devuelve (lineas_normalizadas, cuentas_por_codigo).

    Solo devuelve cuando todas las líneas son válidas y el balance cuadra; en
    caso contrario lanza `MultilineaError` con el primer `ErrorValidacion`.
    """
    if not lineas:
        raise MultilineaError("lineas_insuficientes", "El asiento requiere al menos dos líneas")
    if len(lineas) > limite:
        raise MultilineaError(
            "limite_lineas_excedido",
            f"Máximo {limite} líneas por asiento ({len(lineas)} recibidas)",
        )

    lineas_norm: list[dict[str, Any]] = []
    errores: list[ErrorValidacion] = []
    for i, linea in enumerate(lineas, start=1):
        normalizada, fallo = _normalizar_linea(linea, i)
        if fallo is not None:
            errores.append(fallo)
        else:
            lineas_norm.append(normalizada)
    if errores:
        primero = errores[0]
        raise MultilineaError(primero.code, primero.message, errores)

    total_debe = sum((l["debit"] for l in lineas_norm), Decimal(0))
    total_haber = sum((l["credit"] for l in lineas_norm), Decimal(0))
    if total_debe <= 0:
        raise MultilineaError("lado_vacio", "Faltan partidas en el lado DEBE")
    if total_haber <= 0:
        raise MultilineaError("lado_vacio", "Faltan partidas en el lado HABER")
    if total_debe != total_haber:
        raise MultilineaError(
            "desbalanceo",
            f"Suma Debe ({total_debe:0.4f}) != Suma Haber ({total_haber:0.4f})",
        )

    cuentas: dict[str, AccountPlan] = {}
    for linea in lineas_norm:
        code = linea["cuenta"]
        if code in cuentas:
            linea["account_id"] = cuentas[code].id
            continue
        cuenta = await db.scalar(
            select(AccountPlan).where(
                AccountPlan.tenant_id == empresa_id,
                AccountPlan.code == code,
                AccountPlan.is_selectable.is_(True),
                AccountPlan.is_active.is_(True),
            )
        )
        if cuenta is None:
            existe = await db.scalar(
                select(AccountPlan).where(
                    AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
                )
            )
            if existe is None:
                raise MultilineaError(
                    "cuenta_no_encontrada", f"Cuenta {code} no encontrada en el plan"
                )
            raise MultilineaError(
                "cuenta_no_apuntable", f"Cuenta {code} no es apuntable"
            )
        cuentas[code] = cuenta
        linea["account_id"] = cuenta.id

    for linea in lineas_norm:
        centro_id = linea["centro_coste_id"]
        if centro_id is None:
            continue
        centro = await db.scalar(
            select(CentroCoste).where(
                CentroCoste.empresa_id == empresa_id,
                CentroCoste.id == centro_id,
            )
        )
        if centro is None:
            raise MultilineaError(
                "centro_no_encontrado", "El centro de coste no existe en la empresa activa"
            )
        if centro.estado != CentroEstado.activo:
            raise MultilineaError(
                "centro_inactivo", "No se puede imputar a un centro de coste inactivo"
            )

    return lineas_norm, cuentas