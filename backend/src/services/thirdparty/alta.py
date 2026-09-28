"""Tercero creation with NIF/IBAN validation and automatic subaccounts (SPEC-008 T019)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from services.audit.writer import audit_escribir
from services.thirdparty.bancos import normalizar_iban, validar_iban
from services.thirdparty.subcuentas import asignar_subcuentas
from services.thirdparty.validacion_nif import normalizar_nif, validar_nif


class TerceroError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def crear_tercero(
    db: AsyncSession,
    *,
    empresa_id: int,
    nif: str,
    razon_social: str,
    es_cliente: bool = False,
    es_proveedor: bool = False,
    direcciones: list | None = None,
    telefono: str | None = None,
    correo: str | None = None,
    iban: str | None = None,
    bic: str | None = None,
    banco: str | None = None,
    autofactura: bool = False,
    actor: str | None = None,
) -> Tercero:
    """Validate, persist the ficha and assign 430/410 subaccounts atomically."""
    if not es_cliente and not es_proveedor:
        raise TerceroError("rol_requerido", "Debe indicarse cliente y/o proveedor")
    if not razon_social or not razon_social.strip():
        raise TerceroError("razon_social_requerida", "La razón social es obligatoria")

    nif_norm = normalizar_nif(nif)
    if not validar_nif(nif_norm):
        raise TerceroError("nif_invalido", f"El NIF {nif_norm} no es válido")

    duplicado = await db.scalar(
        select(Tercero.id).where(
            Tercero.empresa_id == empresa_id, Tercero.nif == nif_norm
        )
    )
    if duplicado is not None:
        raise TerceroError("nif_duplicado", "Ya existe un tercero con ese NIF")

    iban_norm: str | None = None
    if iban:
        iban_norm = normalizar_iban(iban)
        if not validar_iban(iban_norm):
            raise TerceroError("iban_invalido", "El IBAN no es válido")

    tercero = Tercero(
        empresa_id=empresa_id,
        nif=nif_norm,
        nombre=razon_social.strip(),
        es_cliente=es_cliente,
        es_proveedor=es_proveedor,
        direcciones=direcciones,
        telefono=telefono,
        correo=correo,
        iban=iban_norm,
        bic=bic,
        banco=banco,
        autofactura=autofactura,
    )
    db.add(tercero)
    await db.flush()
    await asignar_subcuentas(
        db,
        empresa_id,
        tercero.id,
        es_cliente=es_cliente,
        es_proveedor=es_proveedor,
    )
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREATE_TERCERO",
        entity="tercero",
        entity_id=str(tercero.id),
        payload={"nif": nif_norm, "cliente": str(es_cliente), "proveedor": str(es_proveedor)},
    )
    await db.flush()
    return tercero
