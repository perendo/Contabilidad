"""Bloque de datos SII para la AEAT (SPEC-029 T042/T043, research D8).

La **presentacion telematica queda fuera de alcance**: este modulo normaliza las
facturas emitidas y recibidas de la empresa activa al conjunto de campos que
exige el SII (`contracts/export-layout.md` 4) para que el usuario suba el fichero
manualmente al portal de la AEAT.

Se exportan solo facturas `emitida` (las que tienen asiento contabilizado): un
borrador no es una operacion declarada. Una rectificativa se clasifica por la
naturaleza de su factura **raiz** (`factura_original_id`), no por su propio
tipo, que es el criterio que ya usa SPEC-007. La empresa debe tener
`ConfigSii.obligado_sii = true`; si solo tiene la configuracion tecnica de
SPEC-012 (`ConfiguracionSII.obligatorio`), esa se usa como respaldo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from models.export.config_sii import ConfigSii
from models.fiscal.configuracion_sii import ConfiguracionSII
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from models.invoice.serie_factura import SerieFactura
from services.export.errores import error
from services.export.serializacion import cuatro_decimales, volcar_json

__all__ = [
    "BLOQUE_SII",
    "EMITIDAS",
    "RECIBIDAS",
    "ConfigEfectiva",
    "config_efectiva",
    "cuadra",
    "entradas_sii",
    "generar_bloque_sii",
    "leer_bloque_sii",
    "ruta_sii",
]

#: Nombre del bloque en el catalogo y prefijo de sus rutas dentro del ZIP.
BLOQUE_SII = "datos_sii"
EMITIDAS = "facturas_emitidas"
RECIBIDAS = "facturas_recibidas"

#: Mapa tipo de factura PGC -> tipo de factura del SII.
TIPOS_SII: dict[FacturaTipo, str] = {
    FacturaTipo.VENTA: "F1",
    FacturaTipo.COMPRA: "F2",
    FacturaTipo.RECTIFICATIVA: "R1",
}

CUADRADO = "CUADRADO"
DESCUADRADO = "DESCUADRADO"


def ruta_sii(nombre: str) -> str:
    """Ruta dentro del ZIP de uno de los dos ficheros SII."""
    return f"bloques/{BLOQUE_SII}/{nombre}.json"


@dataclass(frozen=True)
class ConfigEfectiva:
    """Configuracion SII resuelta de la empresa activa."""

    obligado_sii: bool
    sin_anexo: bool
    clave_regimen: str
    entidad_representante_id: str | None = None
    fecha_alta: str | None = None

    def contrato(self) -> dict[str, Any]:
        """Configuracion serializada para la respuesta de la API."""
        return {
            "obligado_sii": self.obligado_sii,
            "sin_anexo": self.sin_anexo,
            "clave_regimen": self.clave_regimen,
            "entidad_representante_id": self.entidad_representante_id,
            "fecha_alta": self.fecha_alta,
        }


async def config_efectiva(db: AsyncSession, empresa_id: int) -> ConfigEfectiva:
    """ConfigSii de la empresa, con `ConfiguracionSII` de SPEC-012 como respaldo."""
    fila = await db.scalar(select(ConfigSii).where(ConfigSii.empresa_id == empresa_id))
    if fila is not None:
        return ConfigEfectiva(
            obligado_sii=bool(fila.obligado_sii),
            sin_anexo=bool(fila.sin_anexo),
            clave_regimen=str(fila.clave_regimen or "01"),
            entidad_representante_id=(
                str(fila.entidad_representante_id) if fila.entidad_representante_id else None
            ),
            fecha_alta=fila.fecha_alta.isoformat() if fila.fecha_alta else None,
        )
    respaldo = await db.get(ConfiguracionSII, empresa_id)
    if respaldo is not None:
        return ConfigEfectiva(
            obligado_sii=bool(respaldo.obligatorio),
            sin_anexo=False,
            clave_regimen="01",
        )
    return ConfigEfectiva(obligado_sii=False, sin_anexo=False, clave_regimen="01")


def cuadra(base: Decimal, iva: Decimal, recargo: Decimal, irpf: Decimal, total: Decimal) -> bool:
    """`EstadoCuadre` de la factura: base + IVA + recargo - IRPF == total."""
    return cuatro_decimales(base + iva + recargo - irpf) == cuatro_decimales(total)


def _dec(valor: Any) -> Decimal:
    return cuatro_decimales(Decimal(str(valor or 0)))


def _tipo_impositivo(lineas: list[FacturaLinea]) -> str:
    """Tipo de IVA de la primera linea con tipo, con dos decimales (`"21.00"`)."""
    for linea in lineas:
        if linea.tipo_iva is not None:
            return f"{_dec(linea.tipo_iva):.2f}"
    return "0.00"


def _numero_factura(serie: SerieFactura | None, numero: int | None) -> str:
    if numero is None:
        return ""
    if serie is None:
        return str(numero)
    return f"{serie.prefijo or ''}{numero}{serie.sufijo or ''}"


async def _emitidas(
    db: AsyncSession, empresa_id: int
) -> list[Factura]:
    facturas = list(
        (
            await db.scalars(
                select(Factura)
                .where(
                    Factura.empresa_id == empresa_id,
                    Factura.estado == FacturaEstado.emitida,
                )
                .order_by(Factura.ejercicio, Factura.numero)
            )
        ).all()
    )
    return facturas


def _naturaleza(
    factura: Factura, por_id: dict[str, Factura]
) -> FacturaTipo:
    """Naturaleza de la factura raiz, para clasificar la rectificativa."""
    actual = factura
    vistos: set[str] = set()
    while actual.factura_original_id is not None:
        clave = str(actual.factura_original_id)
        if clave in vistos:
            break
        vistos.add(clave)
        padre = por_id.get(clave)
        if padre is None:
            break
        actual = padre
    if actual.tipo == FacturaTipo.RECTIFICATIVA:
        return FacturaTipo.VENTA
    return actual.tipo


async def _registros(
    db: AsyncSession,
    empresa_id: int,
    facturas: list[Factura],
    *,
    clave_regimen: str,
    naturaleza: FacturaTipo,
) -> list[dict[str, Any]]:
    if not facturas:
        return []
    terceros = {
        str(t.id): t
        for t in (await db.scalars(select(Tercero).where(Tercero.empresa_id == empresa_id))).all()
    }
    series = {
        str(s.id): s
        for s in (
            await db.scalars(
                select(SerieFactura).where(SerieFactura.empresa_id == empresa_id)
            )
        ).all()
    }
    lineas: dict[str, list[FacturaLinea]] = {}
    for linea in (
        await db.scalars(
            select(FacturaLinea)
            .where(
                FacturaLinea.empresa_id == empresa_id,
                FacturaLinea.factura_id.in_([f.id for f in facturas]),
            )
            .order_by(FacturaLinea.factura_id, FacturaLinea.line_no)
        )
    ).all():
        lineas.setdefault(str(linea.factura_id), []).append(linea)

    registros: list[dict[str, Any]] = []
    for factura in facturas:
        tercero = terceros.get(str(factura.tercero_id))
        serie = series.get(str(factura.serie_id))
        propias = lineas.get(str(factura.id), [])
        base = _dec(factura.importe_base)
        iva = _dec(factura.importe_iva)
        recargo = _dec(factura.importe_recargo)
        irpf = _dec(factura.importe_irpf)
        total = _dec(factura.importe_total)
        registros.append(
            {
                "IdFactura": str(factura.id),
                "NIF": str(getattr(tercero, "nif", "") or ""),
                "NombreRazon": str(getattr(tercero, "nombre", "") or ""),
                "TipoFactura": TIPOS_SII.get(factura.tipo, "F1"),
                "Naturaleza": naturaleza.value,
                "FechaOperacion": factura.fecha.isoformat(),
                "FechaExpedicion": factura.fecha.isoformat(),
                "NumeroFactura": _numero_factura(serie, factura.numero),
                "Ejercicio": factura.ejercicio,
                "ClaveRegimen": clave_regimen,
                "BaseImponible": f"{base:0.4f}",
                "TipoImpositivo": _tipo_impositivo(propias),
                "CuotaRepercutida": f"{iva:0.4f}",
                "ImporteTotal": f"{total:0.4f}",
                "EstadoCuadre": CUADRADO
                if cuadra(base, iva, recargo, irpf, total)
                else DESCUADRADO,
            }
        )
    return registros


async def generar_bloque_sii(
    db: AsyncSession,
    empresa_id: int,
    *,
    clave_regimen: str,
    ejercicio_desde: int | None = None,
    ejercicio_hasta: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Registros AEAT de facturas emitidas y recibidas, por nombre de bloque."""
    todas = await _emitidas(db, empresa_id)
    por_id = {str(f.id): f for f in todas}
    if ejercicio_desde is not None and ejercicio_hasta is not None:
        todas = [
            f for f in todas if ejercicio_desde <= f.ejercicio <= ejercicio_hasta
        ]
    emitidas = [f for f in todas if _naturaleza(f, por_id) == FacturaTipo.VENTA]
    recibidas = [f for f in todas if _naturaleza(f, por_id) == FacturaTipo.COMPRA]
    return {
        EMITIDAS: await _registros(
            db, empresa_id, emitidas, clave_regimen=clave_regimen, naturaleza=FacturaTipo.VENTA
        ),
        RECIBIDAS: await _registros(
            db, empresa_id, recibidas, clave_regimen=clave_regimen, naturaleza=FacturaTipo.COMPRA
        ),
    }


def leer_bloque_sii(
    contenido: bytes,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Lee el bloque SII **desde el ZIP almacenado** (research D9).

    Devuelve `(config, bloques)` con la forma que espera
    `contracts/api-contracts.md`. Leer el blob en vez de recalcularlo garantiza
    que la API muestra exactamente lo que se exporto, aunque el tenant haya
    cambiado despues. Lanza 422 `bloque_sii_ausente` si el ZIP no lo contiene.
    """
    import io
    import json
    import zipfile

    with zipfile.ZipFile(io.BytesIO(contenido), "r") as archivo:
        bloques: dict[str, list[dict[str, Any]]] = {}
        config: dict[str, Any] = {}
        for nombre in (EMITIDAS, RECIBIDAS):
            ruta = ruta_sii(nombre)
            try:
                payload = json.loads(archivo.read(ruta).decode("utf-8"))
            except KeyError as exc:
                raise error(
                    "bloque_sii_ausente",
                    f"La exportacion no contiene {ruta}",
                    422,
                ) from exc
            config = {
                "clave_regimen": payload.get("clave_regimen", "01"),
                "sin_anexo": bool(payload.get("sin_anexo", False)),
                "obligado_sii": True,
                # Configuracion completa serializada por `payload_sii`. Con
                # `.get` y no acceso directo: un ZIP generado antes de que se
                # anadieran estos dos campos se sigue leyendo, y devuelve `None`
                # —que es exactamente lo que se guardaba entonces— en vez de
                # reventar con un KeyError.
                "entidad_representante_id": payload.get("entidad_representante_id"),
                "fecha_alta": payload.get("fecha_alta"),
            }
            bloques[nombre] = list(payload.get("registros", []))
    return config, bloques


def payload_sii(
    nombre: str, registros: list[dict[str, Any]], config: ConfigEfectiva
) -> dict[str, Any]:
    """Payload de uno de los ficheros SII del bloque.

    Serializa la configuracion **completa** de la que la AEAT deriva la
    cabecera (ClaveRegimen, ModeloNSIF, SinAnexo y el alta en el censal):
    entidad_representante_id y echa_alta son parte de la declaracion, no
    adorno. Sin ellos, la lectura del bloque desde el ZIP (que es la unica via
    que respeta la inmutabilidad de la exportacion) devolvia una configuracion
    incompleta, distinta de la que expone la API, y el manifiesto historico no
    conservaba el alta en el censal del contribuyente.
    """
    return {
        "bloque": f"{BLOQUE_SII}.{nombre}",
        "clave_regimen": config.clave_regimen,
        "sin_anexo": config.sin_anexo,
        "entidad_representante_id": config.entidad_representante_id,
        "fecha_alta": config.fecha_alta,
        "conteo_registros": len(registros),
        "registros": registros,
    }


async def entradas_sii(
    db: AsyncSession,
    empresa_id: int,
    *,
    ejercicio_desde: int | None = None,
    ejercicio_hasta: int | None = None,
) -> tuple[dict[str, bytes], dict[str, list[dict[str, Any]]], ConfigEfectiva]:
    """Ficheros del bloque SII listos para el ZIP, registros y configuracion.

    Lanza 422 `sin_configuracion_sii` si la empresa no esta obligada.
    """
    config = await config_efectiva(db, empresa_id)
    if not config.obligado_sii:
        raise error(
            "sin_configuracion_sii",
            "La empresa no esta obligada al SII; configura ConfigSii para exportarlo",
            422,
        )
    bloques = await generar_bloque_sii(
        db,
        empresa_id,
        clave_regimen=config.clave_regimen,
        ejercicio_desde=ejercicio_desde,
        ejercicio_hasta=ejercicio_hasta,
    )
    entradas = {
        ruta_sii(nombre): volcar_json(payload_sii(nombre, registros, config))
        for nombre, registros in bloques.items()
    }
    return entradas, bloques, config
