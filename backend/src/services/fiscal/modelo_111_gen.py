"""Generación y descarga del soporte del modelo 111 de retenciones."""

from __future__ import annotations

import csv
import hashlib
import io
import json
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
from models.fiscal.modelo_111 import Modelo111
from models.iam.company import Company
from services.audit import registrar_auditoria
from services.fiscal.errores import error
from services.fiscal.retenciones import (
    CERO,
    d2,
    d4,
    listar_retenciones_periodo,
)


def json_canonico(contenido: dict[str, Any]) -> str:
    """Serializa contenido de forma estable para calcular su hash."""
    return json.dumps(
        contenido,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _detalle_retenciones(retenciones: list[Any]) -> list[dict[str, str]]:
    detalle: list[dict[str, str]] = []
    for retencion in retenciones:
        if not (retencion.nif or "").strip():
            raise error("perceptor_sin_nif", "Todos los perceptores deben tener NIF")
        detalle.append(
            {
                "nif_perceptor": retencion.nif or "",
                "nombre_perceptor": retencion.nombre,
                "tipo_renta": retencion.tipo_retencion.value,
                "clave_retencion": d2(retencion.tipo_porcentaje),
                "base_imponible": d4(retencion.base_imponible),
                "tipo_retencion": d2(retencion.tipo_porcentaje),
                "retencion_practicada": d4(retencion.retencion_practicada),
            }
        )
    return detalle


async def construir_contenido_modelo_111(
    db: AsyncSession,
    *,
    empresa_id: int,
    liquidacion: LiquidacionRetenciones,
) -> dict[str, Any]:
    """Construye los bloques y totales del modelo desde la liquidación."""
    company = await db.get(Company, empresa_id)
    if company is None:
        raise error("empresa_no_encontrada", "La empresa no existe")
    retenciones = await listar_retenciones_periodo(
        db, empresa_id=empresa_id, liquidacion_id=liquidacion.id
    )
    detalle = _detalle_retenciones(retenciones)
    if retenciones:
        total_base = sum(
            (Decimal(str(retencion.base_imponible)) for retencion in retenciones), CERO
        )
        total_retenciones = sum(
            (Decimal(str(retencion.retencion_practicada)) for retencion in retenciones),
            CERO,
        )
        if d4(total_base) != d4(liquidacion.total_base_retenciones):
            raise error(
                "inconsistencia_modelo_111",
                "La base del modelo 111 no coincide con la liquidación",
            )
        if d4(total_retenciones) != d4(liquidacion.total_retenciones):
            raise error(
                "inconsistencia_modelo_111",
                "Las retenciones del modelo 111 no coinciden con la liquidación",
            )
    else:
        total_base = Decimal(str(liquidacion.total_base_retenciones))
        total_retenciones = Decimal(str(liquidacion.total_retenciones))
    return {
        "datos_declarante": {
            "nif": company.nif,
            "razon_social": company.razon_social,
            "ejercicio": liquidacion.ejercicio,
            "trimestre": liquidacion.trimestre,
            "periodo": liquidacion.periodo,
        },
        "datos_periodo": {
            "total_perceptores": liquidacion.n_perceptores,
            "total_base_retenciones": d4(total_base),
            "total_retenciones_practicadas": d4(total_retenciones),
        },
        "detalle_perceptores": detalle,
        "totales": {
            "total_retenciones": d4(total_retenciones),
            "resultado": d4(max(CERO, total_retenciones)),
        },
    }


async def generar_modelo_111(
    db: AsyncSession,
    *,
    empresa_id: int,
    liquidacion_id: uuid.UUID,
    actor: str | None = None,
    ip: str | None = None,
) -> Modelo111:
    """Genera y vincula un modelo 111 append-only de una liquidación."""
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
        select(Modelo111).where(
            Modelo111.empresa_id == empresa_id,
            Modelo111.liquidacion_retenciones_id == liquidacion_id,
        )
    )
    if existente is not None or liquidacion.modelo_111_id is not None:
        raise error("modelo_ya_generado", "El modelo 111 ya fue generado")
    contenido = await construir_contenido_modelo_111(
        db, empresa_id=empresa_id, liquidacion=liquidacion
    )
    hash_contenido = hashlib.sha256(
        json_canonico(contenido).encode("utf-8")
    ).hexdigest()
    modelo = Modelo111(
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
        raise error("modelo_ya_generado", "El modelo 111 ya fue generado") from exc
    if liquidacion.estado == EstadoLiquidacionRetenciones.pendiente:
        liquidacion.modelo_111_id = modelo.id
        await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="GENERAR_MODELO_111",
        entidad="modelo_111",
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


def contenido_csv(modelo: Modelo111) -> str:
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, delimiter=";", lineterminator="\n")
    escritor.writerow(("bloque", "campo", "valor"))
    for fila in _csv_filas(dict(modelo.contenido)):
        escritor.writerow(fila)
    return "\ufeff" + salida.getvalue()


def contenido_descarga(modelo: Modelo111) -> tuple[str, str, str]:
    return (
        contenido_csv(modelo),
        "text/csv; charset=utf-8",
        f"modelo-111-{modelo.id}.csv",
    )


async def descargar_modelo_111(
    db: AsyncSession,
    *,
    empresa_id: int,
    modelo_111_id: uuid.UUID,
) -> tuple[str, str, str]:
    """Obtiene el CSV autenticable de un modelo 111 de la empresa activa."""
    modelo = await db.scalar(
        select(Modelo111).where(
            Modelo111.empresa_id == empresa_id,
            Modelo111.id == modelo_111_id,
        )
    )
    if modelo is None:
        raise error("modelo_no_encontrado", "El modelo 111 no existe")
    return contenido_descarga(modelo)


async def listar_modelos_111(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    trimestre: int | None = None,
    pagina: int = 1,
    tamano: int = 50,
) -> tuple[list[Modelo111], int]:
    """Lista modelos 111 filtrados por empresa y trimestre."""
    if pagina < 1 or tamano < 1 or tamano > 200:
        raise error("paginacion_invalida", "La paginación no es válida")
    filtros = [Modelo111.empresa_id == empresa_id]
    if ejercicio is not None:
        filtros.append(Modelo111.ejercicio == ejercicio)
    if trimestre is not None:
        filtros.append(Modelo111.trimestre == trimestre)
    total = int(
        await db.scalar(select(func.count()).select_from(Modelo111).where(*filtros))
        or 0
    )
    filas = (
        await db.scalars(
            select(Modelo111)
            .where(*filtros)
            .order_by(Modelo111.fecha_generacion.desc(), Modelo111.id.desc())
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    return list(filas), total


def payload_modelo_111(modelo: Modelo111) -> dict[str, Any]:
    return {
        "id": str(modelo.id),
        "liquidacion_retenciones_id": str(modelo.liquidacion_retenciones_id),
        "ejercicio": modelo.ejercicio,
        "trimestre": modelo.trimestre,
        "fecha_generacion": modelo.fecha_generacion.isoformat(),
        "hash_contenido": modelo.hash_contenido,
    }


__all__ = [
    "construir_contenido_modelo_111",
    "contenido_csv",
    "contenido_descarga",
    "descargar_modelo_111",
    "generar_modelo_111",
    "json_canonico",
    "listar_modelos_111",
    "payload_modelo_111",
]
