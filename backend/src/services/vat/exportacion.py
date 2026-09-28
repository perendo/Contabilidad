"""Exportacion de modelos fiscales (SPEC-012 T034/T035).

Genera el fichero (CSV/XML/JSON) con identificacion de empresa y periodo, hash
sha256 y numeracion correlativa por (empresa, ejercicio, modelo). Regenerar un
periodo ya exportado crea un nuevo registro con estado ``regenerado`` y
advertencia, sin borrar el historico (constitucion II).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal.exportacion_modelo import (
    EstadoExportacion,
    ExportacionModelo,
    ModeloFiscal,
)
from models.fiscal.periodo_fiscal import TipoPeriodo
from models.iam.company import Company
from services.audit.writer import audit_escribir
from services.vat.errores import error
from services.vat.modelos import calcular_303, preparar_347, preparar_349
from services.vat.periodo import etiqueta_periodo

DOS_DEC = Decimal("0.01")


def _dos(valor: str | Decimal) -> str:
    return f"{Decimal(str(valor)).quantize(DOS_DEC, rounding=ROUND_HALF_UP):0.2f}"


def generar_fichero(
    modelo: ModeloFiscal | str, datos: dict, formato: str, *, nif: str, etiqueta: str
) -> tuple[str, str]:
    modelo_norm = ModeloFiscal(modelo)
    formato_norm = formato.lower()
    if formato_norm == "json":
        return (
            json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True),
            "application/json",
        )
    if modelo_norm == ModeloFiscal.m303:
        lineas = ["nif;ejercicio;periodo;tipo_casilla;base;cuota"]
        for tipo, valores in datos.get("devengado", {}).items():
            lineas.append(
                f"{nif};{datos['ejercicio']};{etiqueta};{tipo};{_dos(valores['base'])};{_dos(valores['cuota'])}"
            )
        for tipo, valores in datos.get("deducible", {}).items():
            lineas.append(
                f"{nif};{datos['ejercicio']};{etiqueta};D{tipo};{_dos(valores['base'])};{_dos(valores['cuota'])}"
            )
        lineas.append(
            f"{nif};{datos['ejercicio']};{etiqueta};RE;0.00;{_dos(datos['recargo_equivalencia']['cuota'])}"
        )
        if formato_norm == "xml":
            contenido = (
                "<?xml version='1.0' encoding='UTF-8'?>\n"
                f"<Modelo303><NIF>{nif}</NIF><Ejercicio>{datos['ejercicio']}</Ejercicio>"
                f"<Periodo>{etiqueta}</Periodo>"
                f"<Resultado>{_dos(datos['resultado']['a_ingresar'])}</Resultado></Modelo303>\n"
            )
            return contenido, "application/xml"
        return "\n".join(lineas) + "\n", "text/csv"

    if modelo_norm == ModeloFiscal.m349:
        registros = "".join(
            f"  <Registro><NIF>{op['nif_tercero']}</NIF>"
            f"<ClaveOperacion>{op['clave_operacion']}</ClaveOperacion>"
            f"<Importe>{_dos(op['importe'])}</Importe></Registro>\n"
            for op in datos.get("operaciones", [])
        )
        contenido = (
            "<?xml version='1.0' encoding='UTF-8'?>\n"
            f"<Modelo349><Identificador><NIF>{nif}</NIF>"
            f"<Ejercicio>{datos['ejercicio']}</Ejercicio><Periodo>{etiqueta}</Periodo>"
            f"</Identificador>\n{registros}</Modelo349>\n"
        )
        return contenido, "application/xml"

    return (
        json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True),
        "application/json",
    )


def _sha256(contenido: str) -> str:
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


async def registrar_exportacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    modelo: str,
    ejercicio: int,
    formato: str,
    periodo: int | None = None,
    tipo_periodo: TipoPeriodo | str = TipoPeriodo.TRIMESTRE,
    usuario_id: str | None = None,
) -> dict:
    modelo_norm = ModeloFiscal(modelo)
    formato_norm = formato.lower()
    if formato_norm not in ("csv", "xml", "json"):
        raise error("formato_invalido", "Formato debe ser csv, xml o json")

    if modelo_norm == ModeloFiscal.m303:
        if periodo is None:
            raise error("periodo_requerido", "El 303 requiere periodo")
        datos = await calcular_303(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            tipo_periodo=tipo_periodo,
            periodo=periodo,
        )
        if not datos["cuadre_libros"]:
            raise error("descuadre_libros", "El 303 no cuadra con los libros")
        etiqueta = etiqueta_periodo(tipo_periodo, periodo)
    elif modelo_norm == ModeloFiscal.m349:
        if periodo is None:
            raise error("periodo_requerido", "El 349 requiere periodo")
        datos = await preparar_349(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            tipo_periodo=tipo_periodo,
            periodo=periodo,
        )
        etiqueta = etiqueta_periodo(tipo_periodo, periodo)
    else:
        datos = await preparar_347(db, empresa_id=empresa_id, ejercicio=ejercicio)
        etiqueta = "ANUAL"

    company = await db.get(Company, empresa_id)
    nif = company.nif if company is not None else ""

    contenido, content_type = generar_fichero(
        modelo_norm, datos, formato_norm, nif=nif, etiqueta=etiqueta
    )
    hash_contenido = _sha256(contenido)

    previas = await db.scalar(
        select(func.count())
        .select_from(ExportacionModelo)
        .where(
            ExportacionModelo.empresa_id == empresa_id,
            ExportacionModelo.ejercicio == ejercicio,
            ExportacionModelo.modelo == modelo_norm,
        )
    )
    estado = (
        EstadoExportacion.regenerado
        if (previas or 0) > 0
        else EstadoExportacion.generado
    )
    numero = await _siguiente_numero(db, empresa_id, ejercicio, modelo_norm)

    exportacion = ExportacionModelo(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        modelo=modelo_norm,
        numero_exportacion=numero,
        periodo_id=None,
        formato=formato_norm,
        fecha_exportacion=datetime.now(timezone.utc),
        usuario_id=usuario_id,
        contenido_hash=hash_contenido,
        fichero_json={
            "contenido": contenido,
            "content_type": content_type,
            "datos": datos,
            "etiqueta_periodo": etiqueta,
        },
        estado=estado,
    )
    db.add(exportacion)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=usuario_id or "system",
        action="EXPORTAR_MODELO",
        entity="exportacion_modelo",
        entity_id=str(exportacion.id),
        payload={
            "modelo": modelo_norm.value,
            "numero_exportacion": numero,
            "contenido_hash": hash_contenido,
        },
    )
    await db.flush()
    return _payload(exportacion)


async def _siguiente_numero(
    db: AsyncSession, empresa_id: int, ejercicio: int, modelo: ModeloFiscal
) -> int:
    ultimo = await db.scalar(
        select(func.max(ExportacionModelo.numero_exportacion))
        .where(
            ExportacionModelo.empresa_id == empresa_id,
            ExportacionModelo.ejercicio == ejercicio,
            ExportacionModelo.modelo == modelo,
        )
        .with_for_update()
    )
    return int(ultimo) + 1 if ultimo is not None else 1


async def obtener_exportacion(
    db: AsyncSession, *, empresa_id: int, exportacion_id: uuid.UUID
) -> ExportacionModelo | None:
    return await db.scalar(
        select(ExportacionModelo).where(
            ExportacionModelo.empresa_id == empresa_id,
            ExportacionModelo.id == exportacion_id,
        )
    )


async def listar_exportaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    modelo: str | None = None,
    ejercicio: int | None = None,
) -> dict:
    filtros = [ExportacionModelo.empresa_id == empresa_id]
    if modelo is not None:
        filtros.append(ExportacionModelo.modelo == ModeloFiscal(modelo))
    if ejercicio is not None:
        filtros.append(ExportacionModelo.ejercicio == ejercicio)
    filas = (
        await db.scalars(
            select(ExportacionModelo)
            .where(*filtros)
            .order_by(
                ExportacionModelo.ejercicio,
                ExportacionModelo.modelo,
                ExportacionModelo.numero_exportacion,
            )
        )
    ).all()
    return {"items": [_payload(f) for f in filas], "total": len(filas)}


def contenido_descarga(exportacion: ExportacionModelo) -> tuple[str, str, str]:
    contenido = str(exportacion.fichero_json.get("contenido", ""))
    content_type = str(
        exportacion.fichero_json.get("content_type", "application/octet-stream")
    )
    etiqueta = exportacion.fichero_json.get("etiqueta_periodo", "")
    nombre = f"{exportacion.modelo.value}-{exportacion.ejercicio}-{etiqueta}.{exportacion.formato}"
    return contenido, content_type, nombre


def _payload(exportacion: ExportacionModelo) -> dict:
    _, _, nombre = contenido_descarga(exportacion)
    return {
        "exportacion_id": str(exportacion.id),
        "numero_exportacion": exportacion.numero_exportacion,
        "modelo": exportacion.modelo.value,
        "ejercicio": exportacion.ejercicio,
        "periodo": exportacion.fichero_json.get("etiqueta_periodo"),
        "fecha": exportacion.fecha_exportacion.isoformat(),
        "usuario": exportacion.usuario_id,
        "sha256": exportacion.contenido_hash,
        "estado": exportacion.estado.value,
        "fichero": {"nombre": nombre, "sha256": exportacion.contenido_hash},
        "advertencia": (
            "re-exportado"
            if exportacion.estado == EstadoExportacion.regenerado
            else None
        ),
    }