"""Servicio de gestión de cuentas bancarias (tesorería multi-banco)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.treasury.cuenta_bancaria import CuentaBancaria
from services.audit.writer import audit_escribir


class CuentaBancariaError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def listar_cuentas_bancarias(
    db: AsyncSession,
    *,
    empresa_id: int,
    solo_activas: bool = True,
) -> list[CuentaBancaria]:
    """Lista las cuentas bancarias de la empresa activa."""
    query = select(CuentaBancaria).where(CuentaBancaria.empresa_id == empresa_id)
    if solo_activas:
        query = query.where(CuentaBancaria.activa.is_(True))
    query = query.order_by(CuentaBancaria.nombre)
    return list((await db.scalars(query)).all())


async def obtener_cuenta_bancaria(
    db: AsyncSession,
    *,
    empresa_id: int,
    cuenta_bancaria_id: uuid.UUID,
) -> CuentaBancaria | None:
    """Obtiene una cuenta bancaria asegurando el ámbito del tenant."""
    return await db.scalar(
        select(CuentaBancaria).where(
            CuentaBancaria.empresa_id == empresa_id,
            CuentaBancaria.id == cuenta_bancaria_id,
        )
    )


async def crear_cuenta_bancaria(
    db: AsyncSession,
    *,
    empresa_id: int,
    nombre: str,
    iban: str,
    banco: str | None = None,
    bic: str | None = None,
    cuenta_contable: str = "572",
    actor: str | None = None,
) -> CuentaBancaria:
    """Registra una nueva cuenta bancaria para la empresa activa."""
    iban_limpio = iban.replace(" ", "").upper()
    if not iban_limpio:
        raise CuentaBancariaError("iban_vacio", "El IBAN no puede estar vacío")

    # Verificar unicidad de IBAN en la empresa activa
    existente = await db.scalar(
        select(CuentaBancaria).where(
            CuentaBancaria.empresa_id == empresa_id,
            CuentaBancaria.iban == iban_limpio,
        )
    )
    if existente is not None:
        raise CuentaBancariaError("iban_duplicado", f"El IBAN {iban_limpio} ya existe para esta empresa")

    cuenta = CuentaBancaria(
        empresa_id=empresa_id,
        nombre=nombre.strip(),
        banco=banco.strip() if banco else None,
        iban=iban_limpio,
        bic=bic.strip().upper() if bic else None,
        cuenta_contable=cuenta_contable.strip() or "572",
        activa=True,
    )
    db.add(cuenta)
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREAR_CUENTA_BANCARIA",
        entity="cuentas_bancarias",
        entity_id=str(cuenta.id),
        payload={
            "nombre": cuenta.nombre,
            "iban": cuenta.iban,
            "cuenta_contable": cuenta.cuenta_contable,
        },
    )
    await db.flush()
    return cuenta
