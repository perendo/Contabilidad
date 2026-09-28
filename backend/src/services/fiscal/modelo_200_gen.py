from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal.ajuste_extracontable import (
    AjusteExtracontable,
    TipoAjusteExtracontable,
)
from models.fiscal.calculo_is import CalculoIS, EstadoCalculoIS
from models.fiscal.modelo_200 import Modelo200
from models.iam.company import Company
from services.audit import registrar_auditoria
from services.fiscal.errores import error
from services.fiscal.impuesto_sociedades import cuantizar_4dp

Q2 = Decimal("0.01")
CERO = Decimal("0.0000")


def _d4(valor: Decimal | str | int) -> str:
    return f"{cuantizar_4dp(valor):0.4f}"


def _d2(valor: Decimal | str | int) -> str:
    return cuantizar_4dp(Decimal(str(valor))).quantize(
        Q2, rounding=ROUND_HALF_EVEN
    ).__format__(".2f")


def _inconsistente(campo: str) -> None:
    raise error(
        "inconsistencia_modelo_200",
        f"El bloque del modelo 200 es inconsistente: {campo}",
    )


def validar_consistencia_modelo_200(
    calculo: CalculoIS,
    *,
    deducciones: Decimal,
    bonificaciones: Decimal,
) -> None:
    resultado = cuantizar_4dp(calculo.resultado_contable)
    ajustes_positivos = cuantizar_4dp(calculo.ajustes_positivos)
    ajustes_negativos = cuantizar_4dp(calculo.ajustes_negativos)
    base = cuantizar_4dp(calculo.base_imponible)
    tipo = cuantizar_4dp(calculo.tipo_impositivo)
    cuota_integra = cuantizar_4dp(calculo.cuota_integra)
    reduccion_deducciones = cuantizar_4dp(deducciones)
    reduccion_bonificaciones = cuantizar_4dp(bonificaciones)
    cuota_liquida = cuantizar_4dp(calculo.cuota_liquida)
    pagos = cuantizar_4dp(calculo.pagos_a_cuenta)
    diferencial = cuantizar_4dp(calculo.cuota_diferencial)
    if any(
        valor < 0
        for valor in (
            ajustes_positivos,
            ajustes_negativos,
            reduccion_deducciones,
            reduccion_bonificaciones,
            pagos,
        )
    ):
        _inconsistente("importes_no_negativos")
    if tipo <= 0 or tipo > 100:
        _inconsistente("tipo_impositivo")
    if base != cuantizar_4dp(resultado + ajustes_positivos - ajustes_negativos):
        _inconsistente("base_imponible")
    if cuota_integra != cuantizar_4dp(base * tipo / Decimal(100)):
        _inconsistente("cuota_integra")
    if cuantizar_4dp(calculo.deducciones) != cuantizar_4dp(
        reduccion_deducciones + reduccion_bonificaciones
    ):
        _inconsistente("deducciones")
    if cuota_liquida != cuantizar_4dp(
        cuota_integra - reduccion_deducciones - reduccion_bonificaciones
    ):
        _inconsistente("cuota_liquida")
    if diferencial != cuantizar_4dp(cuota_liquida - pagos):
        _inconsistente("cuota_diferencial")


def _resultado_cuota_diferencial(valor: Decimal) -> str:
    if valor > 0:
        return "a_pagar"
    if valor < 0:
        return "a_devolver"
    return "cero"


def json_canonico(contenido: dict[str, Any]) -> str:
    return json.dumps(
        contenido,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


async def _desglose_reducciones(
    db: AsyncSession, *, empresa_id: int, calculo_is_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    filas = (
        await db.scalars(
            select(AjusteExtracontable).where(
                AjusteExtracontable.empresa_id == empresa_id,
                AjusteExtracontable.calculo_is_id == calculo_is_id,
            )
        )
    ).all()
    deducciones = CERO
    bonificaciones = CERO
    for ajuste in filas:
        if ajuste.tipo == TipoAjusteExtracontable.DEDUCCION:
            deducciones += cuantizar_4dp(ajuste.importe)
        elif ajuste.tipo == TipoAjusteExtracontable.BONIFICACION:
            bonificaciones += cuantizar_4dp(ajuste.importe)
    return cuantizar_4dp(deducciones), cuantizar_4dp(bonificaciones)


async def construir_contenido_modelo_200(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo: CalculoIS,
) -> dict[str, dict[str, Any]]:
    company = await db.get(Company, empresa_id)
    if company is None:
        raise error("empresa_no_encontrada", "La empresa no existe")
    deducciones, bonificaciones = await _desglose_reducciones(
        db, empresa_id=empresa_id, calculo_is_id=calculo.id
    )
    validar_consistencia_modelo_200(
        calculo,
        deducciones=deducciones,
        bonificaciones=bonificaciones,
    )
    return {
        "datos_declarante": {
            "nif": company.nif,
            "razon_social": company.razon_social,
            "ejercicio": calculo.ejercicio,
            "tipo_entidad": "sociedad",
            "domicilio_social": None,
            "codigo_postal": None,
            "municipio": None,
            "provincia": None,
            "comunidad_autonoma": None,
        },
        "resultado_contable": {
            "resultado_neto": _d4(calculo.resultado_contable),
            "ajustes_positivos": _d4(calculo.ajustes_positivos),
            "ajustes_negativos": _d4(calculo.ajustes_negativos),
            "resultado_ajustado": _d4(calculo.base_imponible),
        },
        "base_imponible_y_cuota": {
            "base_imponible": _d4(calculo.base_imponible),
            "tipo_impositivo": _d2(calculo.tipo_impositivo),
            "cuota_integra": _d4(calculo.cuota_integra),
            "bonificaciones": _d4(bonificaciones),
            "deducciones": _d4(deducciones),
            "cuota_liquida": _d4(calculo.cuota_liquida),
        },
        "pagos_a_cuenta_y_cuota_diferencial": {
            "pagos_a_cuenta": _d4(calculo.pagos_a_cuenta),
            "cuota_diferencial": _d4(calculo.cuota_diferencial),
            "resultado": _resultado_cuota_diferencial(
                cuantizar_4dp(calculo.cuota_diferencial)
            ),
        },
        "datos_liquidacion": {
            "fecha_primera_mutex": None,
            "cuota_liquidacion_anterior": None,
            "complementaria": False,
        },
    }


async def generar_modelo_200(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo_is_id: uuid.UUID,
    actor: str | None = None,
    ip: str | None = None,
) -> Modelo200:
    calculo = await db.scalar(
        select(CalculoIS)
        .where(
            CalculoIS.empresa_id == empresa_id,
            CalculoIS.id == calculo_is_id,
        )
        .with_for_update()
    )
    if calculo is None:
        raise error("calculo_no_encontrado", "El cálculo no existe")
    if calculo.estado != EstadoCalculoIS.contabilizado:
        raise error(
            "calculo_no_contabilizado",
            "El cálculo debe estar contabilizado",
        )
    existente = await db.scalar(
        select(Modelo200).where(
            Modelo200.empresa_id == empresa_id,
            Modelo200.calculo_is_id == calculo_is_id,
        )
    )
    if existente is not None:
        raise error("modelo_ya_generado", "El modelo 200 ya fue generado")
    contenido = await construir_contenido_modelo_200(
        db, empresa_id=empresa_id, calculo=calculo
    )
    canonico = json_canonico(contenido)
    hash_contenido = hashlib.sha256(canonico.encode("utf-8")).hexdigest()
    modelo = Modelo200(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        calculo_is_id=calculo_is_id,
        fecha_generacion=datetime.now(timezone.utc),
        contenido=contenido,
        hash_contenido=hash_contenido,
        created_by=actor,
    )
    db.add(modelo)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise error("modelo_ya_generado", "El modelo 200 ya fue generado") from exc
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="GENERAR_MODELO_200",
        entidad="modelo_200",
        entidad_id=modelo.id,
        payload={
            "calculo_is_id": str(calculo.id),
            "hash_contenido": hash_contenido,
            "bloques": str(len(contenido)),
        },
        ip=ip,
    )
    return modelo


def _valor_csv(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor)


def _filas_csv(
    contenido: dict[str, Any], prefijo: str = ""
) -> list[tuple[str, str, str]]:
    filas: list[tuple[str, str, str]] = []
    for clave, valor in contenido.items():
        ruta = f"{prefijo}.{clave}" if prefijo else clave
        if isinstance(valor, dict):
            filas.extend(_filas_csv(valor, ruta))
        else:
            filas.append((prefijo or "modelo", ruta, _valor_csv(valor)))
    return filas


def contenido_csv(modelo: Modelo200) -> str:
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, delimiter=";", lineterminator="\n")
    escritor.writerow(("bloque", "campo", "valor"))
    for bloque, campo, valor in _filas_csv(dict(modelo.contenido)):
        escritor.writerow((bloque, campo, valor))
    return salida.getvalue()


def contenido_descarga(modelo: Modelo200) -> tuple[str, str, str]:
    return (
        contenido_csv(modelo),
        "text/csv; charset=utf-8",
        f"modelo-200-{modelo.id}.csv",
    )


async def descargar_modelo_200(
    db: AsyncSession,
    *,
    empresa_id: int,
    modelo_200_id: uuid.UUID,
) -> tuple[str, str, str]:
    modelo = await db.scalar(
        select(Modelo200).where(
            Modelo200.empresa_id == empresa_id,
            Modelo200.id == modelo_200_id,
        )
    )
    if modelo is None:
        raise error("modelo_no_encontrado", "El modelo 200 no existe")
    return contenido_descarga(modelo)


async def listar_modelos_200(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    pagina: int = 1,
    tamano: int = 20,
) -> tuple[list[Modelo200], int]:
    filtros = [Modelo200.empresa_id == empresa_id]
    if ejercicio is not None:
        filtros.append(Modelo200.calculo_is_id.in_(
            select(CalculoIS.id).where(
                CalculoIS.empresa_id == empresa_id,
                CalculoIS.ejercicio == ejercicio,
            )
        ))
    total = int(
        await db.scalar(select(func.count()).select_from(Modelo200).where(*filtros))
        or 0
    )
    filas = (
        await db.scalars(
            select(Modelo200)
            .where(*filtros)
            .order_by(Modelo200.fecha_generacion.desc(), Modelo200.id.desc())
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    return list(filas), total


def payload_modelo_200(modelo: Modelo200) -> dict[str, Any]:
    return {
        "id": str(modelo.id),
        "calculo_is_id": str(modelo.calculo_is_id),
        "fecha_generacion": modelo.fecha_generacion.isoformat(),
        "hash_contenido": modelo.hash_contenido,
    }
