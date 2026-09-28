"""Validación de asientos importados (SPEC-005 US1)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from services.importexport.parseador import FilaCruda, ParseError, parsear_fecha

CUATRO = Decimal("0.0000")


def _error(
    fila: int, grupo: str, cuenta: str | None, tipo: str, mensaje: str
) -> dict:
    return {
        "fila": fila,
        "grupo_asiento": grupo,
        "cuenta": cuenta,
        "tipo_error": tipo,
        "mensaje": mensaje,
    }


async def validar_asiento(
    db: AsyncSession,
    empresa_id: int,
    grupo: str,
    filas: list[FilaCruda],
) -> tuple[list[dict], dict[str, AccountPlan]]:
    """Return (errores, cuentas_por_codigo) for one asiento group."""
    errores: list[dict] = []
    cuentas: dict[str, AccountPlan] = {}

    if len(filas) < 2:
        errores.append(
            _error(filas[0].fila, grupo, None, "lado_vacio", "El asiento necesita al menos 2 líneas")
        )
        return errores, cuentas

    try:
        fecha = parsear_fecha(filas[0].fecha)
    except ParseError as exc:
        errores.append(_error(filas[0].fila, grupo, None, "fecha_invalida", str(exc)))
        return errores, cuentas

    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == fecha.year
        )
    )
    if fy is not None and fy.is_closed:
        errores.append(
            _error(
                filas[0].fila, grupo, None, "ejercicio_cerrado",
                f"El ejercicio {fecha.year} está cerrado",
            )
        )
        return errores, cuentas

    total_debe = Decimal(0)
    total_haber = Decimal(0)
    hay_debe = hay_haber = False
    for fila in filas:
        total_debe += fila.debe
        total_haber += fila.haber
        if fila.debe > 0 and fila.haber > 0:
            errores.append(
                _error(fila.fila, grupo, fila.cuenta, "lado_vacio",
                       "Cada línea debe tener solo Debe o solo Haber")
            )
            continue
        if fila.debe > 0:
            hay_debe = True
        if fila.haber > 0:
            hay_haber = True
        if fila.cuenta not in cuentas:
            cuenta = await db.scalar(
                select(AccountPlan).where(
                    AccountPlan.tenant_id == empresa_id, AccountPlan.code == fila.cuenta
                )
            )
            if cuenta is None:
                errores.append(
                    _error(fila.fila, grupo, fila.cuenta, "cuenta_no_encontrada",
                           f"Cuenta {fila.cuenta} inexistente en la empresa activa")
                )
                continue
            if not (cuenta.is_selectable and cuenta.is_active):
                errores.append(
                    _error(fila.fila, grupo, fila.cuenta, "cuenta_no_apuntable",
                           f"Cuenta {fila.cuenta} no es apuntable o está inactiva")
                )
                continue
            cuentas[fila.cuenta] = cuenta

    if not hay_debe or not hay_haber:
        errores.append(
            _error(filas[0].fila, grupo, None, "lado_vacio",
                   "El asiento necesita al menos una línea al Debe y una al Haber")
        )
    if total_debe != total_haber:
        errores.append(
            _error(filas[0].fila, grupo, None, "desbalanceo",
                   f"Debe {total_debe} != Haber {total_haber}")
        )
    return errores, cuentas
