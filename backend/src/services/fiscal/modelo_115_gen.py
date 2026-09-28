"""Generación y descarga del soporte del modelo 115 de arrendamientos."""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal.liquidacion_retenciones import (
    EstadoLiquidacionRetenciones,
    LiquidacionRetenciones,
)
from models.fiscal.modelo_115 import Modelo115
from models.fiscal.retencion import TipoRetencion
from models.iam.company import Company
from services.audit import registrar_auditoria
from services.fiscal.errores import error
from services.fiscal.modelo_111_gen import json_canonico
from services.fiscal.retenciones import (
    CERO,
    d2,
    d4,
    listar_retenciones_periodo,
)


def _detalle_arrendadores(retenciones: list[Any]) -> list[dict[str, str | None]]:
    detalle: list[dict[str, str | None]] = []
    for retencion in retenciones:
        if not (retencion.nif or "").strip():
            raise error("perceptor_sin_nif", "Todos los arrendadores deben tener NIF")
        direccion = retencion.notas
        if not direccion:
            for factura in retencion.facturas or []:
                if isinstance(factura, dict) and factura.get("direccion_inmueble"):
                    direccion = str(factura["direccion_inmueble"])
                    break
        detalle.append(
            {
                "nif_arrendador": retencion.nif or "",
                "nombre_arrendador": retencion.nombre,
                "direccion_inmueble": direccion,
                "clave_retencion": d2(retencion.tipo_porcentaje),
                "base_imponible": d4(retencion.base_imponible),
                "tipo_retencion": d2(retencion.tipo_porcentaje),
                "retencion_practicada": d4(retencion.retencion_practicada),
            }
        )
    return detalle


async def construir_contenido_modelo_115(
    db: AsyncSession,
    *,
    empresa_id: int,
    liquidacion: LiquidacionRetenciones,
) -> dict[str, Any]:
    """Construye el soporte 115 usando solo retenciones de arrendamiento."""
    company = await db.get(Company, empresa_id)
    if company is None:
        raise error("empresa_no_encontrada", "La empresa no existe")
    retenciones = [
        retencion
        for retencion in await listar_retenciones_periodo(
            db, empresa_id=empresa_id, liquidacion_id=liquidacion.id
        )
        if retencion.tipo_retencion == TipoRetencion.IRPF_ARRENDAMIENTOS
    ]
    if not retenciones:
        raise error(
            "sin_retenciones_arrendamiento",
            "La liquidación no contiene retenciones de arrendamiento",
        )
    detalle = _detalle_arrendadores(retenciones)
    total_rendimientos = sum(
        (Decimal(str(retencion.base_imponible)) for retencion in retenciones), CERO
    )
    total_retenciones = sum(
        (Decimal(str(retencion.retencion_practicada)) for retencion in retenciones),
        CERO,
    )
    return {
        "datos_declarante": {
            "nif": company.nif,
            "razon_social": company.razon_social,
            "ejercicio": liquidacion.ejercicio,
            "trimestre": liquidacion.trimestre,
            "periodo": liquidacion.periodo,
        },
        "datos_periodo": {
            "total_arrendadores": len(
                {retencion.tercero_id for retencion in retenciones}
            ),
            "total_rendimientos": d4(total_rendimientos),
            "total_retenciones": d4(total_retenciones),
        },
        "detalle_arrendadores": detalle,
        "totales": {
            "total_retenciones": d4(total_retenciones),
            "resultado": d4(max(CERO, total_retenciones)),
        },
    }


async def generar_modelo_115(
    db: AsyncSession,
    *,
    empresa_id: int,
    liquidacion_id: uuid.UUID,
    actor: str | None = None,
    ip: str | None = None,
) -> Modelo115:
    """Genera y vincula un modelo 115 append-only de una liquidación."""
    liquidacion = await db.scalar(
        select(LiquidacionRetenciones)
        .where(
            LiquidacionRetenciones.empresa_id == empresa_id,
            LiquidacionRetenciones.id == liquidacion_id,
        )
        .with_for_update()
    )
    if liquidacion is None:
        raise error("liquidacion_no_encontrada", "La liquidación no existe")
    existente = await db.scalar(
        select(Modelo115).where(
            Modelo115.empresa_id == empresa_id,
            Modelo115.liquidacion_retenciones_id == liquidacion_id,
        )
    )
    if existente is not None or liquidacion.modelo_115_id is not None:
        raise error("modelo_ya_generado", "El modelo 115 ya fue generado")
    contenido = await construir_contenido_modelo_115(
        db, empresa_id=empresa_id, liquidacion=liquidacion
    )
    hash_contenido = hashlib.sha256(
        json_canonico(contenido).encode("utf-8")
    ).hexdigest()
    modelo = Modelo115(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        liquidacion_retenciones_id=liquidacion.id,
        ejercicio=liquidacion.ejercicio,
        trimestre=liquidacion.trimestre,
        fecha_generacion=datetime.now(timezone.utc),
        contenido=contenido,
        hash_contenido=hash_contenido,
        created_by=actor,
    )
    db.add(modelo)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise error("modelo_ya_generado", "El modelo 115 ya fue generado") from exc
    if liquidacion.estado == EstadoLiquidacionRetenciones.pendiente:
        liquidacion.modelo_115_id = modelo.id
        await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="GENERAR_MODELO_115",
        entidad="modelo_115",
        entidad_id=modelo.id,
        payload={
            "liquidacion_id": str(liquidacion.id),
            "hash_contenido": hash_contenido,
            "periodo": liquidacion.periodo,
        },
        ip=ip,
    )
    return modelo


def _csv_filas(
    contenido: dict[str, Any], prefijo: str = ""
) -> list[tuple[str, str, str]]:
    filas: list[tuple[str, str, str]] = []
    for clave, valor in contenido.items():
        ruta = f"{prefijo}.{clave}" if prefijo else clave
        if isinstance(valor, dict):
            filas.extend(_csv_filas(valor, ruta))
        elif isinstance(valor, list):
            for indice, elemento in enumerate(valor, start=1):
                elemento_ruta = f"{ruta}[{indice}]"
                if isinstance(elemento, dict):
                    filas.extend(_csv_filas(elemento, elemento_ruta))
                else:
                    filas.append((prefijo or "modelo", elemento_ruta, str(elemento)))
        else:
            filas.append((prefijo or "modelo", ruta, "" if valor is None else str(valor)))
    return filas


def contenido_csv(modelo: Modelo115) -> str:
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, delimiter=";", lineterminator="\n")
    escritor.writerow(("bloque", "campo", "valor"))
    for fila in _csv_filas(dict(modelo.contenido)):
        escritor.writerow(fila)
    return "\ufeff" + salida.getvalue()


def contenido_descarga(modelo: Modelo115) -> tuple[str, str, str]:
    return (
        contenido_csv(modelo),
        "text/csv; charset=utf-8",
        f"modelo-115-{modelo.id}.csv",
    )


async def descargar_modelo_115(
    db: AsyncSession,
    *,
    empresa_id: int,
    modelo_115_id: uuid.UUID,
) -> tuple[str, str, str]:
    """Obtiene el CSV autenticable de un modelo 115 de la empresa activa."""
    modelo = await db.scalar(
        select(Modelo115).where(
            Modelo115.empresa_id == empresa_id,
            Modelo115.id == modelo_115_id,
        )
    )
    if modelo is None:
        raise error("modelo_no_encontrado", "El modelo 115 no existe")
    return contenido_descarga(modelo)


async def listar_modelos_115(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    trimestre: int | None = None,
    pagina: int = 1,
    tamano: int = 50,
) -> tuple[list[Modelo115], int]:
    """Lista modelos 115 filtrados por empresa y trimestre."""
    if pagina < 1 or tamano < 1 or tamano > 200:
        raise error("paginacion_invalida", "La paginación no es válida")
    filtros = [Modelo115.empresa_id == empresa_id]
    if ejercicio is not None:
        filtros.append(Modelo115.ejercicio == ejercicio)
    if trimestre is not None:
        filtros.append(Modelo115.trimestre == trimestre)
    total = int(
        await db.scalar(select(func.count()).select_from(Modelo115).where(*filtros))
        or 0
    )
    filas = (
        await db.scalars(
            select(Modelo115)
            .where(*filtros)
            .order_by(Modelo115.fecha_generacion.desc(), Modelo115.id.desc())
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    return list(filas), total


def payload_modelo_115(modelo: Modelo115) -> dict[str, Any]:
    return {
        "id": str(modelo.id),
        "liquidacion_retenciones_id": str(modelo.liquidacion_retenciones_id),
        "ejercicio": modelo.ejercicio,
        "trimestre": modelo.trimestre,
        "fecha_generacion": modelo.fecha_generacion.isoformat(),
        "hash_contenido": modelo.hash_contenido,
    }


__all__ = [
    "construir_contenido_modelo_115",
    "contenido_csv",
    "contenido_descarga",
    "descargar_modelo_115",
    "generar_modelo_115",
    "listar_modelos_115",
    "payload_modelo_115",
]
