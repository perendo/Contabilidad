"""Journal entry service (SPEC-002 US1): draft creation and posting.

Partida doble estricta is validated here (closest point to persistence) with
Decimal arithmetic; PG triggers (003_journal.sql) are defense-in-depth.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.ngo.libros import Legalizacion
from services.audit.writer import audit_escribir
from services.journal.money import as_decimal, tiene_mas_de_4_decimales
from services.journal.sequence import next_numero

AÑO_MIN, AÑO_MAX = 2000, 2100


class AsientoError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def error(code: str, mensaje: str) -> AsientoError:
    return AsientoError(code, mensaje)


async def _cuenta_apuntable(db: AsyncSession, empresa_id: int, account_id: int) -> AccountPlan | None:
    return await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.id == account_id,
            AccountPlan.is_selectable.is_(True),
            AccountPlan.is_active.is_(True),
        )
    )


async def _ejercicio_cerrado(db: AsyncSession, empresa_id: int, anio: int) -> bool:
    """True if a closed fiscal_year exists for (empresa_id, year).

    SPEC-002 data-model mandates HTTP 400 when the exercise is closed or
    missing; SPEC-004 owns the open/close lifecycle and its rows are optional
    in this phase, so a missing ``fiscal_year`` is treated as an open exercise
    (guarda referenciada). The strict "must exist" rule is deferred to SPEC-004.
    """
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id,
            FiscalYear.year == anio,
        )
    )
    return fy is not None and fy.is_closed


async def _ejercicio_legalizado(db: AsyncSession, empresa_id: int, anio: int) -> bool:
    """True if a valid legalización exists for (empresa_id, year) (FR-007).

    SPEC-019: una legalización vigente (`valido = true`) refuerza el bloqueo de
    SPEC-004: no se admiten asientos posteriores con fecha dentro del ejercicio.
    """
    leg = await db.scalar(
        select(Legalizacion).where(
            Legalizacion.empresa_id == empresa_id,
            Legalizacion.ejercicio == anio,
            Legalizacion.valido.is_(True),
        )
    )
    return leg is not None


async def _validar_ejercicio(db: AsyncSession, empresa_id: int, fecha: date) -> int:
    if not (AÑO_MIN <= fecha.year <= AÑO_MAX):
        raise error("ejercicio_invalido", "La fecha no corresponde a un ejercicio abierto")
    if await _ejercicio_cerrado(db, empresa_id, fecha.year):
        raise error(
            "ejercicio_cerrado",
            f"El ejercicio {fecha.year} está cerrado para la empresa",
        )
    if await _ejercicio_legalizado(db, empresa_id, fecha.year):
        raise error(
            "ejercicio_legalizado",
            f"El ejercicio {fecha.year} está legalizado: no admite nuevos asientos",
        )
    return fecha.year


async def _validar_periodo(
    db: AsyncSession, empresa_id: int, fecha: date, tipo: JournalEntryTipo
) -> None:
    """SPEC-028 T020: 409 `periodo_cerrado` si la fecha cae en un mes/trimestre
    cerrado de la empresa (research D9, doble proteccion con el trigger
    `chk_journal_entry_fecha_abierta`).

    Los asientos del propio paquete de cierre (`REGULARIZACION`, `CIERRE`,
    `OPENING`) quedan exentos: el cierre anual se fecha el ultimo dia del
    ejercicio, que pertenece al ultimo mes cerrado por definicion.
    """
    from services.closing.reglas_cierre import validar_periodo_abierto_motor

    await validar_periodo_abierto_motor(db, empresa_id, fecha, tipo)


def _normalizar_linea(linea: dict[str, Any], idx: int) -> dict[str, Any]:
    try:
        account_id = int(linea["account_id"])
    except (KeyError, TypeError, ValueError):
        raise error("linea_invalida", f"Línea {idx}: account_id inválido")
    if account_id <= 0:
        raise error("linea_invalida", f"Línea {idx}: account_id inválido")

    debit_str = str(linea.get("debit", "0"))
    credit_str = str(linea.get("credit", "0"))
    if tiene_mas_de_4_decimales(debit_str) or tiene_mas_de_4_decimales(credit_str):
        raise error("precision_invalida", f"Línea {idx}: más de 4 decimales")
    debit = as_decimal(debit_str)
    credit = as_decimal(credit_str)
    if debit < 0 or credit < 0:
        raise error("importe_negativo", f"Línea {idx}: importes negativos no permitidos")
    if (debit > 0) == (credit > 0):
        raise error("linea_invalida", f"Línea {idx}: cada línea debe tener solo Debe o solo Haber")
    detail = linea.get("detail")
    centro_raw = linea.get("centro_coste_id")
    centro_id: uuid.UUID | None = None
    if centro_raw not in (None, "", "0"):
        try:
            centro_id = centro_raw if isinstance(centro_raw, uuid.UUID) else uuid.UUID(str(centro_raw))
        except (ValueError, TypeError):
            raise error("centro_invalido", f"Línea {idx}: centro_coste_id inválido")
    return {
        "account_id": account_id,
        "debit": debit,
        "credit": credit,
        "detail": str(detail) if detail is not None else None,
        "centro_coste_id": centro_id,
    }


async def _validar_lineas(
    db: AsyncSession,
    empresa_id: int,
    lineas_raw: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, AccountPlan]]:
    if len(lineas_raw) < 2:
        raise error("lineas_insuficientes", "Un asiento requiere al menos dos líneas")

    lineas = [_normalizar_linea(l, i) for i, l in enumerate(lineas_raw)]

    cuentas: dict[int, AccountPlan] = {}
    for linea in lineas:
        cuenta = await _cuenta_apuntable(db, empresa_id, linea["account_id"])
        if cuenta is None:
            global_cuenta = await db.get(AccountPlan, linea["account_id"])
            if global_cuenta is not None and global_cuenta.tenant_id != empresa_id:
                raise error(
                    "cuenta_otra_empresa",
                    f"La cuenta {linea['account_id']} pertenece a otra empresa",
                )
            raise error(
                "cuenta_no_apuntable",
                f"La cuenta {linea['account_id']} no es apuntable o no pertenece a la empresa",
            )
        cuentas[linea["account_id"]] = cuenta

    desde = sum((l["debit"] for l in lineas), Decimal(0))
    hasta = sum((l["credit"] for l in lineas), Decimal(0))
    if desde <= 0 or hasta <= 0:
        raise error("desbalanceado", "El asiento necesita Debe y Haber positivos")
    if desde != hasta:
        raise error("desbalanceado", f"Asiento desbalanceado: Debe {desde} != Haber {hasta}")
    return lineas, cuentas


async def _persist_entrada(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha: date,
    concepto: str,
    tipo: JournalEntryTipo,
    estado: JournalEntryEstado,
    lineas: list[dict[str, Any]],
    cuentas: dict[int, AccountPlan],
    actor: str | None,
    numero: int | None = None,
    original_id: uuid.UUID | None = None,
) -> JournalEntry:
    ejercicio = await _validar_ejercicio(db, empresa_id, fecha)
    await _validar_periodo(db, empresa_id, fecha, tipo)
    entrada = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=tipo,
        concepto=concepto,
        estado=estado,
        numero_asiento=numero,
        original_id=original_id,
        created_by=actor,
    )
    if entrada.id is None:
        entrada.id = uuid.uuid4()
    db.add(entrada)
    await db.flush()

    for numero_linea, linea in enumerate(lineas, start=1):
        cuenta = cuentas[linea["account_id"]]
        db.add(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=entrada.id,
                account_id=cuenta.id,
                line_no=numero_linea,
                cuenta=cuenta.code,
                debe=linea["debit"],
                haber=linea["credit"],
                descripcion=linea["detail"],
                centro_coste_id=linea.get("centro_coste_id"),
            )
        )
    await db.flush()
    return entrada


async def crear_borrador(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha: date,
    concepto: str,
    lineas: list[dict[str, Any]],
    actor: str | None = None,
    tipo: JournalEntryTipo = JournalEntryTipo.GENERAL,
    original_id: uuid.UUID | None = None,
) -> JournalEntry:
    """Crea un borrador; `original_id` enlaza la correccion con el asiento que
    corrige (research D7 de SPEC-028).

    El enlace se fija **en la creacion**: un asiento POSTED es inmutable
    (constitucion II), de modo que `original_id` no puede asignarse despues.
    """
    await _validar_ejercicio(db, empresa_id, fecha)
    if not concepto or not concepto.strip():
        raise error("concepto_vacio", "El concepto es obligatorio")
    lineas_norm, cuentas = await _validar_lineas(db, empresa_id, lineas)
    entrada = await _persist_entrada(
        db,
        empresa_id=empresa_id,
        fecha=fecha,
        concepto=concepto,
        tipo=tipo,
        estado=JournalEntryEstado.DRAFT,
        lineas=lineas_norm,
        cuentas=cuentas,
        actor=actor,
        original_id=original_id,
    )
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREATE",
        entity="journal_entry",
        entity_id=str(entrada.id),
        payload={
            "ejercicio": entrada.ejercicio,
            "fecha": fecha.isoformat(),
            "lineas": len(lineas_norm),
        },
    )
    await db.flush()
    return entrada


async def asentar(
    db: AsyncSession,
    *,
    empresa_id: int,
    entry_id: uuid.UUID,
    actor: str | None = None,
) -> JournalEntry:
    entrada = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.empresa_id == empresa_id, JournalEntry.id == entry_id
        )
    )
    if entrada is None:
        raise error("asiento_no_encontrado", "Asiento inexistente en la empresa activa")
    if entrada.estado != JournalEntryEstado.DRAFT:
        raise error("estado_invalido", "El asiento ya está asentado o anulado")
    await _validar_ejercicio(db, empresa_id, entrada.fecha)
    await _validar_periodo(db, empresa_id, entrada.fecha, entrada.tipo)

    lineas_raw = (
        await db.scalars(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == entrada.id,
                JournalEntryLine.empresa_id == empresa_id,
            )
        )
    ).all()
    await _validar_lineas(
        db,
        empresa_id,
        [
            {
                "account_id": l.account_id if l.account_id is not None else l.cuenta,
                "debit": l.debe,
                "credit": l.haber,
                "detail": l.descripcion,
            }
            for l in lineas_raw
        ],
    )

    numero = await next_numero(db, empresa_id, entrada.ejercicio)
    entrada.estado = JournalEntryEstado.POSTED
    entrada.numero_asiento = numero
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="POSTED",
        entity="journal_entry",
        entity_id=str(entrada.id),
        payload={"numero": numero, "ejercicio": entrada.ejercicio},
    )
    await db.flush()
    return entrada