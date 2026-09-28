"""Alta y carga masiva del presupuesto anual (SPEC-026 US1, FR-001/FR-005).

`guardar_presupuesto` valida en el punto mas cercano a la persistencia
(constitucion): cuenta apuntable de la empresa activa, centro de coste de la
misma empresa, coherencia del `tipo` con el grupo PGC y periodo de seguimiento
abierto. `importar_presupuesto` valida fila por fila y es atomica: si alguna
fila falla se aborta toda la importacion (contrato `POST /importar`).
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.budget.periodo_seguimiento import EstadoPeriodo
from models.budget.presupuesto import Presupuesto, TipoPresupuesto
from models.costcenters.centro_coste import CentroCoste
from services.audit import registrar_auditoria
from services.budget.errores import PresupuestoError, error
from services.budget.periodos import (
    asegurar_periodo,
    ejercicio_cerrado,
    periodo_bloqueante,
)
from services.budget.utils import (
    GRUPO_GASTO,
    GRUPO_INGRESO,
    c4,
    tiene_mas_de_4_decimales,
)

__all__ = [
    "LineaImportada",
    "fila_invalida",
    "guardar_presupuesto",
    "importar_presupuesto",
    "listar_presupuestos",
    "parsear_csv",
    "validar_cuenta",
]

MAX_FILAS_IMPORTACION = 10_000


class LineaImportada(BaseModel):
    """Fila del CSV/JSON de importacion (validacion Pydantic v2, T014)."""

    codigo_cuenta: str = Field(min_length=1, max_length=8)
    centro: str | None = Field(default=None, max_length=120)
    importe: str
    tipo: str | None = Field(default=None, max_length=20)


def fila_invalida(fila: int, motivo: str) -> dict[str, Any]:
    return {"fila": fila, "motivo": motivo}


def _decimal(valor: Any, campo: str) -> Decimal:
    texto = str(valor).strip()
    if tiene_mas_de_4_decimales(texto):
        raise error(
            "precision_invalida", f"{campo}: mas de 4 decimales ({texto})", 422
        )
    try:
        return c4(Decimal(texto))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise error("importe_invalido", f"{campo}: importe invalido ({texto})", 422) from exc


async def validar_cuenta(
    db: AsyncSession, empresa_id: int, cuenta_id: int
) -> AccountPlan:
    """Cuenta apuntable de la empresa activa o 422 (T012, constitucion III)."""
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.id == cuenta_id,
        )
    )
    if cuenta is None:
        raise error(
            "cuenta_no_encontrada",
            f"La cuenta {cuenta_id} no pertenece a la empresa activa",
            422,
        )
    if not cuenta.is_selectable or not cuenta.is_active:
        raise error(
            "cuenta_inapunteable",
            f"La cuenta {cuenta.code} no es apuntable: no admite presupuesto",
            422,
        )
    return cuenta


async def _validar_centro(
    db: AsyncSession, empresa_id: int, centro: uuid.UUID | None
) -> uuid.UUID | None:
    """Centro de coste de la misma empresa o 422 (FR-006, constitucion III)."""
    if centro is None:
        return None
    existe = await db.scalar(
        select(CentroCoste.id).where(
            CentroCoste.empresa_id == empresa_id, CentroCoste.id == centro
        )
    )
    if existe is None:
        raise error(
            "centro_no_encontrado",
            "El centro de coste no pertenece a la empresa activa",
            422,
        )
    return centro


def _tipo_para_cuenta(
    cuenta: AccountPlan, tipo: TipoPresupuesto | None
) -> TipoPresupuesto:
    """Coherencia `tipo` <-> grupo PGC (D2: 6 gasto / 7 ingreso).

    Solo las cuentas de gasto (grupo 6) e ingreso (grupo 7) admiten presupuesto:
    presupuestar una cuenta de balance haria que el informe sumase una
    contrapartida con signo opuesto y sus totales no quadrarian (spec.md SC-002).
    """
    grupo = int(cuenta.code[:1]) if cuenta.code[:1].isdigit() else 0
    if grupo == GRUPO_GASTO:
        esperado = TipoPresupuesto.gasto
    elif grupo == GRUPO_INGRESO:
        esperado = TipoPresupuesto.ingreso
    else:
        raise error(
            "cuenta_no_presupuestable",
            (
                f"La cuenta {cuenta.code} es del grupo {grupo}: solo se presupuestan "
                "cuentas de gasto (6) e ingreso (7)"
            ),
            422,
        )
    if tipo is not None and tipo is not esperado:
        raise error(
            "tipo_incoherente",
            f"La cuenta {cuenta.code} es {esperado.value}: el tipo no coincide",
            422,
        )
    return esperado


async def guardar_presupuesto(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    cuenta_id: int,
    importe: str | Decimal,
    centro_coste_id: uuid.UUID | str | None = None,
    tipo: str | None = None,
    actor: str = "sistema",
    observaciones: str | None = None,
    audit: bool = True,
    permitir_identico: bool = False,
) -> Presupuesto:
    """Crea o actualiza la linea de presupuesto de la combinacion (T013).

    Idempotente por combinacion (FR-005): repetir la misma combinacion con otro
    importe **actualiza** la linea; el rechazo por duplicado_identico se
    produce cuando el importe y el tipo son identicos a los ya almacenados
    (contrato: "rechazo de duplicado identico"). La importacion en lote pasa
    `permitir_identico=True` para que reimportar el mismo fichero sea un
    no-op y no un error.
    """
    if await ejercicio_cerrado(db, empresa_id, ejercicio):
        raise error(
            "ejercicio_cerrado",
            f"El ejercicio {ejercicio} esta cerrado: no admite presupuesto",
            409,
        )
    cuenta = await validar_cuenta(db, empresa_id, cuenta_id)
    centro = await _validar_centro(
        db, empresa_id, uuid.UUID(str(centro_coste_id)) if centro_coste_id else None
    )
    tipo_enum = _tipo_para_cuenta(
        cuenta, TipoPresupuesto(tipo) if tipo else None
    )
    valor = _decimal(importe, "importe")
    bloqueante = await periodo_bloqueante(db, empresa_id, ejercicio)
    if bloqueante is not None:
        raise error(
            "periodo_cerrado",
            (
                f"El ejercicio {ejercicio} tiene el periodo "
                f"{bloqueante.numero_periodo} cerrado: abre un periodo nuevo "
                "para modificar el presupuesto"
            ),
            409,
        )
    periodo = await asegurar_periodo(
        db, empresa_id=empresa_id, ejercicio=ejercicio, actor=actor
    )
    if periodo.estado is not EstadoPeriodo.abierto:  # pragma: no cover - defensivo
        raise error(
            "periodo_cerrado",
            f"El periodo {periodo.numero_periodo} esta cerrado",
            409,
        )

    existente = await db.scalar(
        select(Presupuesto).where(
            Presupuesto.empresa_id == empresa_id,
            Presupuesto.ejercicio == ejercicio,
            Presupuesto.cuenta_id == cuenta_id,
            Presupuesto.centro_coste_id.is_(None)
            if centro is None
            else Presupuesto.centro_coste_id == centro,
        )
    )
    if (
        not permitir_identico
        and existente is not None
        and c4(existente.importe) == valor
        and existente.tipo is tipo_enum
    ):
        raise error(
            "duplicado_identico",
            (
                f"Ya existe un presupuesto identico para la cuenta {cuenta.code} "
                f"en el ejercicio {ejercicio}"
            ),
            422,
        )
    if existente is None:
        presupuesto = Presupuesto(
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            cuenta_id=cuenta_id,
            centro_coste_id=centro,
            periodo_id=periodo.id,
            importe=valor,
            tipo=tipo_enum,
            observaciones=observaciones,
        )
        db.add(presupuesto)
        accion = "CREAR"
    else:
        presupuesto = existente
        presupuesto.importe = valor
        presupuesto.tipo = tipo_enum
        presupuesto.periodo_id = periodo.id
        if observaciones is not None:
            presupuesto.observaciones = observaciones
        accion = "ACTUALIZAR"
    try:
        await db.flush()
    except IntegrityError as exc:
        raise error(
            "duplicado_identico",
            "Ya existe un presupuesto para esa combinacion cuenta-centro-ejercicio",
            422,
        ) from exc
    if audit:
        await registrar_auditoria(
            db,
            empresa_id=empresa_id,
            operacion=f"PRESUPUESTO_{accion}",
            entidad="presupuesto",
            entidad_id=presupuesto.id,
            payload={
                "ejercicio": ejercicio,
                "cuenta_id": cuenta_id,
                "codigo_cuenta": cuenta.code,
                "centro_coste_id": str(centro) if centro else None,
                "importe": f"{valor:0.4f}",
                "tipo": tipo_enum.value,
                "periodo_id": str(periodo.id),
            },
            usuario=actor,
        )
    return presupuesto


def parsear_csv(texto: str) -> list[dict[str, Any]]:
    """CSV `codigo_cuenta,centro,importe,tipo` (encabezado opcional)."""
    filas: list[dict[str, Any]] = []
    lineas = [linea for linea in texto.replace("\r\n", "\n").split("\n") if linea.strip()]
    for indice, linea in enumerate(lineas, start=1):
        if indice == 1 and linea.lower().lstrip("﻿").startswith("codigo_cuenta"):
            continue
        partes = [p.strip() for p in linea.split(";")]
        if len(partes) == 1:
            partes = [p.strip() for p in linea.split(",")]
        if len(partes) < 3:
            raise error(
                "csv_invalido",
                f"Fila {indice}: se esperaban al menos codigo_cuenta,centro,importe",
                422,
            )
        filas.append(
            {
                "fila": indice,
                "codigo_cuenta": partes[0],
                "centro": partes[1] or None,
                "importe": partes[2],
                "tipo": partes[3] if len(partes) > 3 and partes[3] else None,
            }
        )
    return filas


async def importar_presupuesto(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    filas: list[dict[str, Any]],
    actor: str = "sistema",
) -> dict[str, Any]:
    """Importacion en lote validada fila por fila y atomica (T014).

    Si alguna fila falla, **toda** la importacion se aborta: se lanza
    `PresupuestoError` con el detalle de las filas invalidas y el llamante
    revierte la transaccion (boundary ACID de `get_db`).
    """
    if len(filas) > MAX_FILAS_IMPORTACION:
        raise error(
            "demasiadas_filas",
            f"El lote supera el maximo de {MAX_FILAS_IMPORTACION} filas",
            422,
        )
    if await ejercicio_cerrado(db, empresa_id, ejercicio):
        raise error(
            "ejercicio_cerrado",
            f"El ejercicio {ejercicio} esta cerrado: no admite presupuesto",
            409,
        )
    bloqueante = await periodo_bloqueante(db, empresa_id, ejercicio)
    if bloqueante is not None:
        raise error(
            "periodo_cerrado",
            f"El ejercicio {ejercicio} tiene el periodo {bloqueante.numero_periodo} cerrado",
            409,
        )

    por_codigo: dict[str, int] = {}
    centros: dict[str, uuid.UUID | None] = {}
    claves: set[tuple[int, uuid.UUID | None]] = set()
    errores: list[dict[str, Any]] = []
    validadas: list[tuple[int, int, Decimal, uuid.UUID | None, TipoPresupuesto]] = []

    for posicion, fila in enumerate(filas, start=1):
        numero = int(fila.get("fila") or posicion)
        try:
            if not isinstance(fila, dict):
                fila = dict(fila)
            codigo = str(fila.get("codigo_cuenta") or "").strip()
            if not codigo:
                raise error("fila_invalida", "Falta codigo_cuenta", 422)
            if codigo not in por_codigo:
                cuenta = await db.scalar(
                    select(AccountPlan).where(
                        AccountPlan.tenant_id == empresa_id, AccountPlan.code == codigo
                    )
                )
                if cuenta is None:
                    raise error(
                        "cuenta_no_encontrada",
                        f"La cuenta {codigo} no pertenece a la empresa activa",
                        422,
                    )
                por_codigo[codigo] = int(cuenta.id)
            cuenta = await db.get(AccountPlan, por_codigo[codigo])
            if cuenta is None:  # pragma: no cover - carrera
                raise error("cuenta_no_encontrada", f"La cuenta {codigo} no existe", 422)
            await validar_cuenta(db, empresa_id, por_codigo[codigo])
            nombre_centro = (fila.get("centro") or "").strip() or None
            if nombre_centro and nombre_centro not in centros:
                centro = await db.scalar(
                    select(CentroCoste).where(
                        CentroCoste.empresa_id == empresa_id,
                        or_(
                            CentroCoste.codigo == nombre_centro,
                            CentroCoste.nombre == nombre_centro,
                        ),
                    )
                )
                if centro is None:
                    raise error(
                        "centro_no_encontrado",
                        f"El centro '{nombre_centro}' no pertenece a la empresa activa",
                        422,
                    )
                centros[nombre_centro] = centro.id
            valor = _decimal(fila.get("importe"), "importe")
            tipo_texto = (fila.get("tipo") or "").strip().lower() or None
            if tipo_texto and tipo_texto not in {t.value for t in TipoPresupuesto}:
                raise error("tipo_invalido", f"Tipo '{tipo_texto}' desconocido", 422)
            tipo_enum = _tipo_para_cuenta(
                cuenta, TipoPresupuesto(tipo_texto) if tipo_texto else None
            )
            centro_id = centros.get(nombre_centro) if nombre_centro else None
            if (cuenta.id, centro_id) in claves:
                raise error(
                    "duplicado_lote",
                    f"La cuenta {codigo} aparece dos veces en el mismo lote",
                    422,
                )
            claves.add((cuenta.id, centro_id))
            validadas.append((numero, int(cuenta.id), valor, centro_id, tipo_enum))
        except Exception as exc:  # noqa: BLE001 - se reempaqueta como error de negocio
            codigo_error = getattr(exc, "code", "fila_invalida")
            mensaje = getattr(exc, "message", str(exc))
            errores.append(fila_invalida(numero, f"{codigo_error}: {mensaje}"))

    if errores:
        raise PresupuestoError(
            "importacion_invalida",
            f"{len(errores)} fila(s) invalida(s): la importacion se aborta",
            422,
            {"errores": errores, "importadas": 0},
        )

    importadas = 0
    for _, cuenta_id, valor, centro_id, tipo_enum in validadas:
        await guardar_presupuesto(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            cuenta_id=cuenta_id,
            centro_coste_id=centro_id,
            importe=valor,
            tipo=tipo_enum.value if tipo_enum else None,
            actor=actor,
            audit=False,
            permitir_identico=True,
        )
        importadas += 1
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion="IMPORTAR_PRESUPUESTO",
        entidad="presupuesto",
        payload={"ejercicio": ejercicio, "importadas": importadas},
        usuario=actor,
    )
    return {"ejercicio": ejercicio, "importadas": importadas, "errores": []}


async def listar_presupuestos(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    cuenta_id: int | None = None,
    centro_coste_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Listado paginado con codigo y nombre de centro resueltos (T015)."""
    consulta = select(Presupuesto).where(Presupuesto.empresa_id == empresa_id)
    if ejercicio is not None:
        consulta = consulta.where(Presupuesto.ejercicio == ejercicio)
    if cuenta_id is not None:
        consulta = consulta.where(Presupuesto.cuenta_id == cuenta_id)
    if centro_coste_id:
        consulta = consulta.where(
            Presupuesto.centro_coste_id == uuid.UUID(centro_coste_id)
        )
    total = int(
        await db.scalar(
            select(func.count()).select_from(consulta.subquery())
        )
        or 0
    )
    filas = (
        await db.scalars(
            consulta.order_by(Presupuesto.ejercicio, Presupuesto.cuenta_id)
            .offset((max(page, 1) - 1) * max(page_size, 1))
            .limit(min(max(page_size, 1), 500))
        )
    ).all()
    cuentas = {
        int(cuenta_id_): (code, nombre)
        for cuenta_id_, code, nombre in (
            await db.execute(
                select(
                    AccountPlan.id,
                    AccountPlan.code,
                    AccountPlan.name,
                ).where(AccountPlan.tenant_id == empresa_id)
            )
        ).all()
    }
    ids_centro = [f.centro_coste_id for f in filas if f.centro_coste_id is not None]
    nombres_centro: dict[str, str] = {}
    if ids_centro:
        for centro_id_, codigo_c, nombre_c in (
            await db.execute(
                select(CentroCoste.id, CentroCoste.codigo, CentroCoste.nombre).where(
                    CentroCoste.empresa_id == empresa_id,
                    CentroCoste.id.in_(ids_centro),
                )
            )
        ).all():
            nombres_centro[str(centro_id_)] = f"{codigo_c} · {nombre_c}"
    return {
        "items": [
            {
                "id": str(fila.id),
                "ejercicio": fila.ejercicio,
                "cuenta_id": fila.cuenta_id,
                "codigo_cuenta": cuentas.get(fila.cuenta_id, ("", ""))[0],
                "nombre_cuenta": cuentas.get(fila.cuenta_id, ("", ""))[1],
                "centro_coste_id": str(fila.centro_coste_id)
                if fila.centro_coste_id
                else None,
                "nombre_centro": nombres_centro.get(str(fila.centro_coste_id)),
                "importe": f"{c4(fila.importe):0.4f}",
                "tipo": fila.tipo.value,
                "periodo_id": str(fila.periodo_id) if fila.periodo_id else None,
            }
            for fila in filas
        ],
        "total": total,
    }
