"""Configuracion fiscal de cuentas de IVA y regimenes (SPEC-012 T009).

Las cuentas 472/477 y las de recargo (4772/4722) proceden de la configuracion
de SPEC-001; esta capa expone los codigos por defecto y permite override por
empresa (``ConfiguracionFiscal``) para la cuenta de recargo y los regimenes
especiales.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal.configuracion_fiscal import ConfiguracionFiscal

CUENTAS_DEFECTO = {
    "iva_repercutido": "4770",
    "iva_soportado": "4720",
    "recargo_repercutido": "4772",
    "recargo_soportado": "4722",
}
CUENTA_RECARGO_DEFECTO = "4772"


async def obtener_configuracion_fiscal(
    db: AsyncSession, empresa_id: int
) -> ConfiguracionFiscal:
    config = await db.get(ConfiguracionFiscal, empresa_id)
    if config is None:
        config = ConfiguracionFiscal(
            empresa_id=empresa_id,
            recargo_equivalencia_habilitado=False,
            cuenta_recargo=None,
            criterio_caja_habilitado=False,
        )
        db.add(config)
        await db.flush()
    return config


async def cuentas_iva(db: AsyncSession, empresa_id: int) -> dict[str, str]:
    config = await obtener_configuracion_fiscal(db, empresa_id)
    cuentas = dict(CUENTAS_DEFECTO)
    if config.cuenta_recargo:
        cuentas["cuenta_recargo"] = config.cuenta_recargo
    else:
        cuentas["cuenta_recargo"] = CUENTA_RECARGO_DEFECTO
    return cuentas


async def cuenta_recargo(db: AsyncSession, empresa_id: int) -> str:
    return (await cuentas_iva(db, empresa_id))["cuenta_recargo"]


async def habilitar_recargo(
    db: AsyncSession, empresa_id: int, habilitado: bool, cuenta: str | None = None
) -> ConfiguracionFiscal:
    config = await obtener_configuracion_fiscal(db, empresa_id)
    config.recargo_equivalencia_habilitado = habilitado
    if cuenta:
        config.cuenta_recargo = cuenta
    await db.flush()
    return config


async def habilitar_criterio_caja(
    db: AsyncSession, empresa_id: int, habilitado: bool
) -> ConfiguracionFiscal:
    config = await obtener_configuracion_fiscal(db, empresa_id)
    config.criterio_caja_habilitado = habilitado
    await db.flush()
    return config