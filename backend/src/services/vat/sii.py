"""Interfaz SII (SPEC-012 T048/T049): configuracion y XML, sin envio.

Declara el enlace SII opcional por empresa y genera el XML pendiente de envio a
partir del libro del periodo (``SuministroLrFacturasEmitidas/Recibidas``). El
envio real se integra con SPEC-029; aqui nunca se ejecuta.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal.configuracion_sii import ConfiguracionSII
from models.fiscal.periodo_fiscal import TipoPeriodo
from models.iam.company import Company
from services.vat.errores import error
from services.vat.libros_iva import construir_libro_emitidas, construir_libro_recibidas
from services.vat.periodo import etiqueta_periodo, rango_periodo


async def obtener_configuracion_sii(
    db: AsyncSession, empresa_id: int
) -> ConfiguracionSII:
    config = await db.get(ConfiguracionSII, empresa_id)
    if config is None:
        config = ConfiguracionSII(
            empresa_id=empresa_id,
            habilitado=False,
            obligatorio=False,
            identificador_emisor=None,
        )
        db.add(config)
        await db.flush()
    return config


async def configurar_sii(
    db: AsyncSession,
    *,
    empresa_id: int,
    habilitado: bool,
    identificador_emisor: str | None = None,
    obligatorio: bool | None = None,
) -> dict:
    if habilitado and identificador_emisor:
        nif = identificador_emisor.strip().upper()
        if len(nif) < 9:
            raise error("identificador_invalido", "El identificador del emisor no es valido")
    config = await obtener_configuracion_sii(db, empresa_id)
    config.habilitado = habilitado
    if identificador_emisor is not None:
        config.identificador_emisor = identificador_emisor.strip().upper()
    if obligatorio is not None:
        config.obligatorio = obligatorio
    config.updated_at = datetime.now(timezone.utc)
    await db.flush()
    advertencia = "periodicidad_ajustada_a_mensual" if habilitado else None
    return {
        "habilitado": config.habilitado,
        "obligatorio": config.obligatorio,
        "identificador_emisor": config.identificador_emisor,
        "periodicidad_303": "MES" if config.habilitado else "TRIMESTRE",
        "advertencia": advertencia,
    }


async def generar_xml_sii(
    db: AsyncSession,
    *,
    empresa_id: int,
    tipo: str,
    ejercicio: int,
    periodo: int,
    tipo_periodo: TipoPeriodo | str = TipoPeriodo.TRIMESTRE,
) -> dict:
    config = await obtener_configuracion_sii(db, empresa_id)
    if not config.habilitado:
        raise error("sii_no_habilitado", "El SII no esta habilitado para la empresa")
    if tipo not in ("emitidas", "recibidas"):
        raise error("tipo_sii_invalido", "Tipo debe ser emitidas o recibidas")

    inicio, fin = rango_periodo(ejercicio, tipo_periodo, periodo)
    etiqueta = etiqueta_periodo(tipo_periodo, periodo)
    company = await db.get(Company, empresa_id)
    nif = (config.identificador_emisor or (company.nif if company else "") or "")

    if tipo == "emitidas":
        libro = await construir_libro_emitidas(
            db, empresa_id=empresa_id, ejercicio=ejercicio, inicio=inicio, fin=fin
        )
        registros = "".join(
            "  <RegistroLrFE><IDFactura>"
            f"<NumSerieFacturaEmisor>{op['num_factura'] or op['factura_id']}</NumSerieFacturaEmisor>"
            f"<FechaExpedicionFacturaEmisor>{op['fecha_expedicion']}</FechaExpedicionFacturaEmisor>"
            "</IDFactura><FacturaExpedida><Contraparte>"
            f"<NIF>{op['nif_tercero']}</NIF>"
            "</Contraparte><DesgloseIVA>"
            f"<TipoImpositivo>{op['tipo_iva']}</TipoImpositivo>"
            f"<BaseImponible>{op['base']}</BaseImponible>"
            f"<CuotaRepercutida>{op['cuota']}</CuotaRepercutida>"
            "</DesgloseIVA></FacturaExpedida></RegistroLrFE>\n"
            for op in libro["operaciones"]
        )
        raiz = "SuministroLF"
        raiz_registro = "RegistroLrFE"
    else:
        libro = await construir_libro_recibidas(
            db, empresa_id=empresa_id, ejercicio=ejercicio, inicio=inicio, fin=fin
        )
        registros = "".join(
            "  <RegistroLrFR><IDFactura>"
            f"<NumSerieFacturaEmisor>{op['num_factura'] or op['factura_id']}</NumSerieFacturaEmisor>"
            "</IDFactura><FacturaRecibida><Contraparte>"
            f"<NIF>{op['nif_tercero']}</NIF>"
            "</Contraparte><DesgloseIVA>"
            f"<TipoImpositivo>{op['tipo_iva']}</TipoImpositivo>"
            f"<BaseImponible>{op['base']}</BaseImponible>"
            f"<CuotaSoportada>{op['cuota']}</CuotaSoportada>"
            "</DesgloseIVA></FacturaRecibida></RegistroLrFR>\n"
            for op in libro["operaciones"]
        )
        raiz = "SuministroLR"
        raiz_registro = "RegistroLrFR"

    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        f"<{raiz}><Cabecera><IDVersionSii>1.2</IDVersionSii>"
        f"<Titular><NIF>{nif}</NIF></Titular>"
        f"<Ejercicio>{ejercicio}</Ejercicio><Periodo>{etiqueta}</Periodo></Cabecera>\n"
        f"{registros}</{raiz}>\n"
    )
    return {
        "xml": xml,
        "sha256": hashlib.sha256(xml.encode("utf-8")).hexdigest(),
        "n_operaciones": len(libro["operaciones"]),
        "tipo": tipo,
        "raiz_registro": raiz_registro,
    }


async def listar_configuraciones(db: AsyncSession) -> list[ConfiguracionSII]:
    return list((await db.scalars(select(ConfiguracionSII))).all())