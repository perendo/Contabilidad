"""Shared helpers for treasury services (SPEC-011/020/021).

Pequeños helpers compartidos entre los módulos de tesorería: códigos de
cuenta del PGC usados por todos los asientos de tesorería y la validación
de ejercicio abierto (el cierre/bloqueo de SPEC-004 bloquea nuevos
movimientos en ejercicios cerrados).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear

CUENTA_CLIENTES = "430"
CUENTA_EFECTOS = "431"
CUENTA_PROVEEDORES = "400"
CUENTA_EFECTOS_PAGAR = "401"
CUENTA_ACREEDORES_SERVICIOS = "410"
CUENTA_ANTICIPOS_CLIENTES = "438"
CUENTA_ANTICIPOS_PROVEEDORES = "407"
CUENTA_ACREEDORES_PENDIENTES_FACTURA = "408"
CUENTA_BANCO = "572"
CUENTA_CAJA = "570"
CUENTA_COMISION = "626"
CUENTA_INTERESES_DEUDAS = "662"


class TesoreriaError(Exception):
    """Base error for treasury services with HTTP-friendly mapping."""

    def __init__(self, code: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


async def ejercicio_abierto(
    db: AsyncSession,
    empresa_id: int,
    fecha: date,
    error_tipo: type[TesoreriaError],
) -> None:
    """Raise ``error_tipo('ejercicio_cerrado', 409, ...)`` on a closed year."""
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == fecha.year
        )
    )
    if fy is not None and fy.is_closed:
        raise error_tipo(
            "ejercicio_cerrado",
            409,
            f"El ejercicio {fecha.year} está cerrado",
        )