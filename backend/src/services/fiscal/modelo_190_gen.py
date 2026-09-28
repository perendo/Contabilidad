"""Generación, validación y descarga del modelo 190 anual."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from models.fiscal.modelo_190 import Modelo190
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from models.iam.company import Company
from services.audit import registrar_auditoria
from services.fiscal.errores import FiscalISError
from services.fiscal.modelo_200_gen import json_canonico
from services.thirdparty.validacion_nif import normalizar_nif, validar_nif

Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")
CERO = Decimal("0.0000")


class Modelo190Error(FiscalISError):
    """Error de validación o descarga del modelo 190."""

    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        detalle: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code, message)
        self.status_code = status_code
        self.detalle = detalle or {}
        self.perceptores_sin_nif: list[dict[str, str]] = []
        self.errores: list[dict[str, str]] = []
        valor = self.detalle.get("perceptores_sin_nif")
        if isinstance(valor, list):
            self.perceptores_sin_nif = [
                item for item in valor if isinstance(item, dict)
            ]
            self.errores = self.perceptores_sin_nif


@dataclass
class _FilaRetencion:
    tercero_id: uuid.UUID
    nombre_retencion: str
    tipo_retencion: TipoRetencion
    tipo_porcentaje: Decimal
    base_imponible: Decimal
    retencion_practicada: Decimal
    nif_tercero: str | None
    nombre_tercero: str | None


@dataclass
class _GrupoPerceptor:
    tercero_id: uuid.UUID
    nif: str
    nombre: str
    tipo_retencion: TipoRetencion
    tipo_porcentaje: Decimal
    base_imponible: Decimal = CERO
    retencion_practicada: Decimal = CERO


def _d4(valor: Decimal | str | int) -> str:
    return f"{Decimal(str(valor)).quantize(Q4, rounding=ROUND_HALF_EVEN):0.4f}"


def _d2(valor: Decimal | str | int) -> str:
    return f"{Decimal(str(valor)).quantize(Q2, rounding=ROUND_HALF_EVEN):0.2f}"


def _normalizar_tipo(valor: TipoRetencion | str) -> TipoRetencion:
    if isinstance(valor, TipoRetencion):
        return valor
    return TipoRetencion(valor)


async def _filas_retenciones(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> list[_FilaRetencion]:
    filas = (
        await db.execute(
            select(
                RetencionPeriodo.tercero_id,
                RetencionPeriodo.nombre.label("nombre_retencion"),
                RetencionPeriodo.tipo_retencion,
                RetencionPeriodo.tipo_porcentaje,
                RetencionPeriodo.base_imponible,
                RetencionPeriodo.retencion_practicada,
                Tercero.nif.label("nif_tercero"),
                Tercero.nombre.label("nombre_tercero"),
            )
            .select_from(RetencionPeriodo)
            .join(
                LiquidacionRetenciones,
                and_(
                    LiquidacionRetenciones.empresa_id == RetencionPeriodo.empresa_id,
                    LiquidacionRetenciones.id
                    == RetencionPeriodo.liquidacion_retenciones_id,
                ),
            )
            .outerjoin(
                Tercero,
                and_(
                    Tercero.empresa_id == RetencionPeriodo.empresa_id,
                    Tercero.id == RetencionPeriodo.tercero_id,
                ),
            )
            .where(
                RetencionPeriodo.empresa_id == empresa_id,
                LiquidacionRetenciones.empresa_id == empresa_id,
                LiquidacionRetenciones.ejercicio == ejercicio,
            )
            .order_by(
                LiquidacionRetenciones.trimestre,
                RetencionPeriodo.tercero_id,
                RetencionPeriodo.id,
            )
        )
    ).all()
    return [
        _FilaRetencion(
            tercero_id=fila.tercero_id,
            nombre_retencion=fila.nombre_retencion,
            tipo_retencion=_normalizar_tipo(fila.tipo_retencion),
            tipo_porcentaje=Decimal(str(fila.tipo_porcentaje)),
            base_imponible=Decimal(str(fila.base_imponible)),
            retencion_practicada=Decimal(str(fila.retencion_practicada)),
            nif_tercero=fila.nif_tercero,
            nombre_tercero=fila.nombre_tercero,
        )
        for fila in filas
    ]


def _sin_nif(filas: list[_FilaRetencion]) -> list[dict[str, str]]:
    vistos: set[uuid.UUID] = set()
    faltantes: list[dict[str, str]] = []
    for fila in filas:
        if fila.tercero_id in vistos:
            continue
        vistos.add(fila.tercero_id)
        nif = normalizar_nif(fila.nif_tercero or "")
        if not validar_nif(nif):
            nombre = fila.nombre_tercero or fila.nombre_retencion or str(fila.tercero_id)
            faltantes.append(
                {"tercero_id": str(fila.tercero_id), "nombre": nombre}
            )
    return sorted(faltantes, key=lambda item: (item["nombre"].casefold(), item["tercero_id"]))


async def validar_nif_perceptores(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> dict[str, object]:
    """Comprueba los NIF actuales de los perceptores del ejercicio."""
    filas = await _filas_retenciones(
        db, empresa_id=empresa_id, ejercicio=ejercicio
    )
    faltantes = _sin_nif(filas)
    return {"valido": not faltantes, "perceptores_sin_nif": faltantes}


def _agrupar(filas: list[_FilaRetencion]) -> list[_GrupoPerceptor]:
    grupos: dict[tuple[uuid.UUID, TipoRetencion, Decimal], _GrupoPerceptor] = {}
    for fila in filas:
        tasa = fila.tipo_porcentaje.quantize(Q2, rounding=ROUND_HALF_EVEN)
        clave = (fila.tercero_id, fila.tipo_retencion, tasa)
        grupo = grupos.get(clave)
        if grupo is None:
            grupo = _GrupoPerceptor(
                tercero_id=fila.tercero_id,
                nif=normalizar_nif(fila.nif_tercero or ""),
                nombre=fila.nombre_tercero or fila.nombre_retencion,
                tipo_retencion=fila.tipo_retencion,
                tipo_porcentaje=tasa,
            )
            grupos[clave] = grupo
        grupo.base_imponible += fila.base_imponible
        grupo.retencion_practicada += fila.retencion_practicada
    return sorted(
        grupos.values(),
        key=lambda grupo: (
            grupo.nombre.casefold(),
            str(grupo.tercero_id),
            grupo.tipo_retencion.value,
            grupo.tipo_porcentaje,
        ),
    )


def _detalle_grupo(grupo: _GrupoPerceptor) -> dict[str, object]:
    return {
        "nif_perceptor": grupo.nif,
        "nombre_perceptor": grupo.nombre,
        "codigo_postal": None,
        "municipio": None,
        "provincia": None,
        "clave_retencion": _d2(grupo.tipo_porcentaje),
        "concepto_renta": grupo.tipo_retencion.value,
        "base_imponible_anual": _d4(grupo.base_imponible),
        "tipo_retencion": _d2(grupo.tipo_porcentaje),
        "retencion_anual": _d4(grupo.retencion_practicada),
        "ejercicios_anteriores": _d4(CERO),
    }


def _contenido_modelo_190(
    *, empresa: Company, ejercicio: int, grupos: list[_GrupoPerceptor]
) -> dict[str, Any]:
    total_base = sum((grupo.base_imponible for grupo in grupos), CERO)
    total_retenciones = sum(
        (grupo.retencion_practicada for grupo in grupos), CERO
    )
    return {
        "datos_declarante": {
            "nif": empresa.nif,
            "razon_social": empresa.razon_social,
            "ejercicio": ejercicio,
            "domicilio_social": None,
            "codigo_postal": None,
            "municipio": None,
            "provincia": None,
        },
        "totales_ejercicio": {
            "total_perceptores": len({grupo.tercero_id for grupo in grupos}),
            "total_base_retenciones": _d4(total_base),
            "total_retenciones": _d4(total_retenciones),
        },
        "detalle_perceptores": [_detalle_grupo(grupo) for grupo in grupos],
        "totales": {"total_retenciones_anual": _d4(total_retenciones)},
    }


async def construir_contenido_modelo_190(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
) -> dict[str, Any]:
    """Agrega las liquidaciones del ejercicio por perceptor y tipo."""
    empresa = await db.get(Company, empresa_id)
    if empresa is None:
        raise Modelo190Error(
            "empresa_no_encontrada", 404, "La empresa no existe"
        )
    filas = await _filas_retenciones(
        db, empresa_id=empresa_id, ejercicio=ejercicio
    )
    if not filas:
        raise Modelo190Error(
            "sin_retenciones", 422, "No hay retenciones para el ejercicio"
        )
    faltantes = _sin_nif(filas)
    if faltantes:
        raise Modelo190Error(
            "perceptores_sin_nif",
            422,
            "Hay perceptores sin NIF valido",
            detalle={"perceptores_sin_nif": faltantes},
        )
    return _contenido_modelo_190(
        empresa=empresa, ejercicio=ejercicio, grupos=_agrupar(filas)
    )


async def generar_modelo_190(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    actor: str | None = None,
    ip: str | None = None,
) -> Modelo190:
    """Genera y persiste un modelo 190 append-only del ejercicio."""
    existente = await db.scalar(
        select(Modelo190)
        .where(Modelo190.empresa_id == empresa_id, Modelo190.ejercicio == ejercicio)
        .with_for_update()
    )
    if existente is not None:
        raise Modelo190Error(
            "modelo_ya_generado", 409, "El modelo 190 ya fue generado"
        )
    contenido = await construir_contenido_modelo_190(
        db, empresa_id=empresa_id, ejercicio=ejercicio
    )
    canonico = json_canonico(contenido)
    hash_contenido = hashlib.sha256(canonico.encode("utf-8")).hexdigest()
    total_retenciones = contenido["totales"]["total_retenciones_anual"]
    n_perceptores = contenido["totales_ejercicio"]["total_perceptores"]
    modelo = Modelo190(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha_generacion=datetime.now(timezone.utc),
        contenido=contenido,
        hash_contenido=hash_contenido,
        n_perceptores=n_perceptores,
        created_by=actor,
    )
    db.add(modelo)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise Modelo190Error(
            "modelo_ya_generado", 409, "El modelo 190 ya fue generado"
        ) from exc
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="GENERAR_MODELO_190",
        entidad="modelo_190",
        entidad_id=modelo.id,
        payload={
            "ejercicio": str(ejercicio),
            "n_perceptores": n_perceptores,
            "hash_contenido": hash_contenido,
            "total_retenciones_anual": total_retenciones,
        },
        ip=ip,
    )
    return modelo


def _valor_csv(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (dict, list)):
        return json.dumps(
            valor, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    return str(valor)


def _filas_csv(
    contenido: dict[str, Any], prefijo: str = ""
) -> list[tuple[str, str, str]]:
    filas: list[tuple[str, str, str]] = []
    for clave, valor in contenido.items():
        ruta = f"{prefijo}.{clave}" if prefijo else clave
        if isinstance(valor, dict):
            filas.extend(_filas_csv(valor, ruta))
        elif isinstance(valor, list):
            for indice, elemento in enumerate(valor, start=1):
                elemento_ruta = f"{ruta}[{indice}]"
                if isinstance(elemento, dict):
                    filas.extend(_filas_csv(elemento, elemento_ruta))
                else:
                    filas.append(
                        (prefijo or "modelo", elemento_ruta, _valor_csv(elemento))
                    )
        else:
            filas.append((prefijo or "modelo", ruta, _valor_csv(valor)))
    return filas


def contenido_csv(modelo: Modelo190) -> str:
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, delimiter=";", lineterminator="\n")
    escritor.writerow(("bloque", "campo", "valor"))
    for fila in _filas_csv(dict(modelo.contenido)):
        escritor.writerow(fila)
    return "\ufeff" + salida.getvalue()


def contenido_descarga(modelo: Modelo190) -> tuple[str, str, str]:
    return (
        contenido_csv(modelo),
        "text/csv; charset=utf-8",
        f"modelo-190-{modelo.id}.csv",
    )


async def descargar_modelo_190(
    db: AsyncSession,
    *,
    empresa_id: int,
    modelo_190_id: uuid.UUID,
) -> tuple[str, str, str]:
    """Obtiene el CSV autenticable de un modelo 190 de la empresa activa."""
    modelo = await db.scalar(
        select(Modelo190).where(
            Modelo190.empresa_id == empresa_id,
            Modelo190.id == modelo_190_id,
        )
    )
    if modelo is None:
        raise Modelo190Error(
            "modelo_no_encontrado", 404, "El modelo 190 no existe"
        )
    return contenido_descarga(modelo)


async def listar_modelos_190(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    pagina: int = 1,
    tamano: int = 50,
) -> tuple[list[Modelo190], int]:
    """Lista modelos 190 filtrados por empresa y ejercicio."""
    if pagina < 1 or tamano < 1 or tamano > 200:
        raise Modelo190Error(
            "paginacion_invalida", 422, "La paginación no es válida"
        )
    filtros = [Modelo190.empresa_id == empresa_id]
    if ejercicio is not None:
        filtros.append(Modelo190.ejercicio == ejercicio)
    total = int(
        await db.scalar(select(func.count()).select_from(Modelo190).where(*filtros))
        or 0
    )
    filas = (
        await db.scalars(
            select(Modelo190)
            .where(*filtros)
            .order_by(
                Modelo190.ejercicio.desc(),
                Modelo190.fecha_generacion.desc(),
                Modelo190.id.desc(),
            )
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    return list(filas), total


def payload_modelo_190(modelo: Modelo190) -> dict[str, Any]:
    return {
        "id": str(modelo.id),
        "ejercicio": modelo.ejercicio,
        "fecha_generacion": modelo.fecha_generacion.isoformat(),
        "hash_contenido": modelo.hash_contenido,
        "n_perceptores": modelo.n_perceptores,
    }


__all__ = [
    "Modelo190Error",
    "construir_contenido_modelo_190",
    "contenido_csv",
    "contenido_descarga",
    "descargar_modelo_190",
    "generar_modelo_190",
    "json_canonico",
    "listar_modelos_190",
    "payload_modelo_190",
    "validar_nif_perceptores",
]
