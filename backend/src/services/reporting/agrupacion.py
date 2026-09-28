"""Agrupacion de cuentas por masa/partida (SPEC-010 T006).

Resuelve para cada cuenta su agrupacion segun la configuracion por empresa
(``ConfiguracionInforme``). Sin configuracion, la cuenta se clasifica en
"Otros" con aviso (research D1). La comparacion de rangos es lexicografica
sobre el codigo (prefijos del PGC), robusta para longitudes variables.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.reporting.configuracion import ConfiguracionInforme, InformeTipo

MASA_OTROS_CODIGO = "OTROS"
MASA_OTROS_NOMBRE = "Otros"


def rango_matchea(codigo: str, cuenta_ini: str, cuenta_fin: str | None) -> bool:
    if cuenta_fin is None:
        return codigo.startswith(cuenta_ini)
    return cuenta_ini <= codigo <= cuenta_fin


def resolver_masa(
    codigo: str, reglas: list[ConfiguracionInforme]
) -> tuple[str, str, bool]:
    """Devuelve ``(agrupacion_codigo, agrupacion_nombre, clasificada)``."""
    for regla in reglas:
        if rango_matchea(codigo, regla.cuenta_ini, regla.cuenta_fin):
            return regla.agrupacion_codigo, regla.agrupacion_nombre, True
    return MASA_OTROS_CODIGO, MASA_OTROS_NOMBRE, False


async def cargar_reglas(
    db: AsyncSession, *, empresa_id: int, ejercicio: int, informe_tipo: InformeTipo
) -> list[ConfiguracionInforme]:
    return list(
        (
            await db.scalars(
                select(ConfiguracionInforme)
                .where(
                    ConfiguracionInforme.empresa_id == empresa_id,
                    ConfiguracionInforme.ejercicio == ejercicio,
                    ConfiguracionInforme.informe_tipo == informe_tipo,
                )
                .order_by(ConfiguracionInforme.orden, ConfiguracionInforme.cuenta_ini)
            )
        ).all()
    )


def agrupar(
    netos: dict[str, Decimal],
    reglas: list[ConfiguracionInforme],
    *,
    prefijos: tuple[str, ...] | None = None,
) -> tuple[dict[str, dict], bool]:
    """Agrupa los netos por agrupacion resuelta.

    Devuelve ``(masas, hay_otros)``; ``masas`` es
    ``{codigo: {"codigo", "nombre", "importe"}}``.
    """
    masas: dict[str, dict] = {}
    hay_otros = False
    for codigo, neto in netos.items():
        if prefijos is not None and codigo[:1] not in prefijos:
            continue
        masa_codigo, masa_nombre, clasificada = resolver_masa(codigo, reglas)
        if not clasificada:
            hay_otros = True
        masa = masas.setdefault(
            masa_codigo,
            {"codigo": masa_codigo, "nombre": masa_nombre, "importe": Decimal(0)},
        )
        masa["importe"] += neto
    return masas, hay_otros