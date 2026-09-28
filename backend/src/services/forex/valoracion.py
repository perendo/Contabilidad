"""Valoración de saldos en divisa a cierre (SPEC-016 US2).

Calcula los saldos vivos por (cuenta, divisa) en asientos POSTED hasta la fecha
de valoración y compara el saldo funcional previo (la suma de los equivalentes
convertidos al postearse) con la valoración al tipo de la fecha de cierre. La
diferencia de cambio de cada cuenta se convierte en un asiento balanceado
(constitución I): pérdida (6680) / cuenta, o cuenta / ganancia (7690), con tipo
ADJUSTMENT y numeración correlativa. Enlazado al cierre: ejercicio con estado
cerrado -> 409.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.monedas.asiento_divisa import AsientoDivisa
from models.monedas.diferencia_cambio import (
    DiferenciaCambio,
    DiferenciaCambioEstado,
)
from models.monedas.linea_divisa import LineaDivisa
from models.monedas.moneda import Moneda
from models.monedas.tipo_cambio import TipoCambio
from services.audit.writer import audit_escribir
from services.forex.conversion import convertir
from services.forex.cuentas import cuenta_diferencia_cambio
from services.forex.errores import ForexError
from services.forex.tipos import _cuatro, _ocho, obtener_tipo
from services.journal.entry_service import AsientoError, asentar, crear_borrador

PAGINA_MIN, PAGINA_MAX = 1, 100


async def _ejercicio_cerrado(db: AsyncSession, empresa_id: int, anio: int) -> bool:
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id,
            FiscalYear.year == anio,
        )
    )
    return fy is not None and fy.is_closed


async def _saldos_vivos_divisa(
    db: AsyncSession,
    empresa_id: int,
    fecha_valoracion: date,
) -> list[tuple[int, uuid.UUID, Decimal, Decimal]]:
    stmt = (
        select(
            JournalEntryLine.account_id,
            AsientoDivisa.divisa_id,
            (JournalEntryLine.debe > 0).label("es_debe"),
            LineaDivisa.importe_divisa,
            LineaDivisa.importe_funcional,
        )
        .join(
            AsientoDivisa,
            and_(
                AsientoDivisa.id == LineaDivisa.asiento_divisa_id,
                AsientoDivisa.empresa_id == LineaDivisa.empresa_id,
            ),
        )
        .join(
            JournalEntryLine,
            and_(
                JournalEntryLine.id == LineaDivisa.linea_id,
                JournalEntryLine.empresa_id == LineaDivisa.empresa_id,
            ),
        )
        .join(
            JournalEntry,
            and_(
                JournalEntry.id == JournalEntryLine.journal_entry_id,
                JournalEntry.empresa_id == JournalEntryLine.empresa_id,
            ),
        )
        .where(
            AsientoDivisa.empresa_id == empresa_id,
            JournalEntry.estado == JournalEntryEstado.POSTED,
            JournalEntry.fecha <= fecha_valoracion,
        )
    )
    filas = (await db.execute(stmt)).all()
    acum: dict[tuple[int, uuid.UUID], list[Decimal]] = {}
    for account_id, divisa_id, es_debe, imp_div, imp_fun in filas:
        key = (int(account_id) if account_id is not None else 0, divisa_id)
        saldo = acum.setdefault(key, [Decimal(0), Decimal(0)])
        signo = Decimal(1) if es_debe else Decimal(-1)
        saldo[0] += signo * imp_div
        saldo[1] += signo * imp_fun
    return [
        (k[0], k[1], v[0], v[1])
        for k, v in acum.items()
        if v[0] != 0
    ]


async def iniciar_valoracion(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    fecha_valoracion: date,
    actor: str | None = None,
) -> dict:
    """Ejecuta y asienta la valoración de saldos en divisa a la fecha dada."""
    if fecha_valoracion.year != ejercicio:
        raise ForexError(
            "ejercicio_invalido",
            "La fecha de valoración debe pertenecer al ejercicio indicado",
        )
    if await _ejercicio_cerrado(db, empresa_id, ejercicio):
        raise ForexError(
            "ejercicio_cerrado",
            f"El ejercicio {ejercicio} está cerrado: no se puede valorar",
        )
    ya = await db.scalar(
        select(DiferenciaCambio.id)
        .where(
            DiferenciaCambio.empresa_id == empresa_id,
            DiferenciaCambio.ejercicio == ejercicio,
            DiferenciaCambio.fecha_valoracion == fecha_valoracion,
        )
        .limit(1)
    )
    if ya is not None:
        raise ForexError(
            "valoracion_ya_existente",
            "Ya existe una valoración para este ejercicio y fecha",
        )

    saldos = await _saldos_vivos_divisa(db, empresa_id, fecha_valoracion)

    valoraciones: list[dict] = []
    divisa_codes: dict[uuid.UUID, str] = {}
    for account_id, divisa_id, saldo_div, saldo_fun in saldos:
        tipo = await obtener_tipo(db, empresa_id, divisa_id, fecha_valoracion)
        if tipo is None:
            codigo = divisa_codes.get(divisa_id)
            if codigo is None:
                moneda = await db.get(Moneda, divisa_id)
                codigo = moneda.codigo_iso if moneda is not None else str(divisa_id)
                divisa_codes[divisa_id] = codigo
            raise ForexError(
                "sin_tipo_cierre",
                f"No hay tipo de cambio en {fecha_valoracion} para {codigo}",
            )
        valorado = convertir(saldo_div, tipo.ratio)
        diferencia = valorado - saldo_fun
        if diferencia == 0:
            continue
        valoraciones.append(
            {
                "id": str(uuid.uuid4()),
                "cuenta_id": account_id,
                "divisa_id": str(divisa_id),
                "tipo_cierre_id": str(tipo.id),
                "saldo_divisa": _cuatro(saldo_div),
                "saldo_funcional_previo": _cuatro(saldo_fun),
                "valoracion": _cuatro(valorado),
                "diferencia": _cuatro(diferencia if diferencia > 0 else -diferencia),
                "tipo": "ganancia" if diferencia > 0 else "perdida",
                "asiento_id": None,
            }
        )

    if not valoraciones:
        return {
            "asiento_id": None,
            "ejercicio": ejercicio,
            "fecha_valoracion": fecha_valoracion.isoformat(),
            "n": 0,
            "valoraciones": [],
        }

    cta_perdida = await cuenta_diferencia_cambio(db, empresa_id, "debe")
    cta_ganancia = await cuenta_diferencia_cambio(db, empresa_id, "haber")

    lineas: list[dict] = []
    for v in valoraciones:
        importe = Decimal(v["diferencia"])
        cuenta_existe = await db.scalar(
            select(AccountPlan.id).where(
                AccountPlan.tenant_id == empresa_id,
                AccountPlan.id == v["cuenta_id"],
            )
        )
        if cuenta_existe is None:
            raise ForexError(
                "cuenta_no_encontrada",
                f"La cuenta {v['cuenta_id']} no existe en la empresa activa",
            )
        if v["tipo"] == "ganancia":
            lineas.append(
                {
                    "account_id": v["cuenta_id"],
                    "debit": importe,
                    "credit": Decimal(0),
                    "detail": f"Dif. cambio {v['tipo']}",
                }
            )
            lineas.append(
                {
                    "account_id": cta_ganancia.id,
                    "debit": Decimal(0),
                    "credit": importe,
                    "detail": f"Dif. cambio {v['tipo']}",
                }
            )
        else:
            lineas.append(
                {
                    "account_id": cta_perdida.id,
                    "debit": importe,
                    "credit": Decimal(0),
                    "detail": f"Dif. cambio {v['tipo']}",
                }
            )
            lineas.append(
                {
                    "account_id": v["cuenta_id"],
                    "debit": Decimal(0),
                    "credit": importe,
                    "detail": f"Dif. cambio {v['tipo']}",
                }
            )

    try:
        borrador = await crear_borrador(
            db,
            empresa_id=empresa_id,
            fecha=fecha_valoracion,
            concepto=f"Diferencias de cambio ejercicio {ejercicio}",
            lineas=lineas,
            actor=actor,
            tipo=JournalEntryTipo.ADJUSTMENT,
        )
        entrada = await asentar(
            db,
            empresa_id=empresa_id,
            entry_id=borrador.id,
            actor=actor,
        )
    except AsientoError as exc:
        raise ForexError(exc.code, str(exc)) from exc

    for v in valoraciones:
        tipo_id = uuid.UUID(v["tipo_cierre_id"])
        v["asiento_id"] = str(entrada.id)
        db.add(
            DiferenciaCambio(
                id=uuid.UUID(v["id"]),
                empresa_id=empresa_id,
                ejercicio=ejercicio,
                fecha_valoracion=fecha_valoracion,
                cuenta_id=v["cuenta_id"],
                divisa_id=uuid.UUID(v["divisa_id"]),
                tipo_cierre_id=tipo_id,
                saldo_divisa=Decimal(v["saldo_divisa"]),
                saldo_funcional_previo=Decimal(v["saldo_funcional_previo"]),
                valoracion=Decimal(v["valoracion"]),
                diferencia=(
                    Decimal(v["diferencia"])
                    if v["tipo"] == "ganancia"
                    else -Decimal(v["diferencia"])
                ),
                estado=DiferenciaCambioEstado.asentada,
                asiento_id=entrada.id,
            )
        )

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="VALORACION_CAMBIO",
        entity="diferencia_cambio",
        entity_id=str(entrada.id),
        payload={
            "ejercicio": ejercicio,
            "fecha_valoracion": fecha_valoracion.isoformat(),
            "asiento_id": str(entrada.id),
            "n": len(valoraciones),
        },
    )
    await db.flush()
    return {
        "asiento_id": str(entrada.id),
        "ejercicio": ejercicio,
        "fecha_valoracion": fecha_valoracion.isoformat(),
        "n": len(valoraciones),
        "valoraciones": valoraciones,
    }


async def listar_diferencias(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    divisa_id: uuid.UUID | None = None,
    cuenta_id: int | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Listado de valoraciones de cambio (GET /api/v1/diferencias-cambio)."""
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise ForexError("page_size_invalido", "page_size debe estar entre 1 y 100")
    filtros = [DiferenciaCambio.empresa_id == empresa_id]
    if ejercicio is not None:
        filtros.append(DiferenciaCambio.ejercicio == ejercicio)
    if divisa_id is not None:
        filtros.append(DiferenciaCambio.divisa_id == divisa_id)
    if cuenta_id is not None:
        filtros.append(DiferenciaCambio.cuenta_id == cuenta_id)
    if estado is not None:
        if estado not in {e.value for e in DiferenciaCambioEstado}:
            raise ForexError("estado_invalido", f"Estado desconocido: {estado}")
        filtros.append(DiferenciaCambio.estado == estado)
    base = (
        select(
            DiferenciaCambio,
            AccountPlan.code,
            Moneda.codigo_iso,
            TipoCambio.ratio,
        )
        .join(
            AccountPlan,
            and_(
                AccountPlan.tenant_id == DiferenciaCambio.empresa_id,
                AccountPlan.id == DiferenciaCambio.cuenta_id,
            ),
        )
        .join(
            Moneda,
            and_(
                Moneda.empresa_id == DiferenciaCambio.empresa_id,
                Moneda.id == DiferenciaCambio.divisa_id,
            ),
        )
        .join(
            TipoCambio,
            and_(
                TipoCambio.empresa_id == DiferenciaCambio.empresa_id,
                TipoCambio.id == DiferenciaCambio.tipo_cierre_id,
            ),
        )
        .where(*filtros)
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    filas = (
        await db.execute(
            base.order_by(
                DiferenciaCambio.fecha_valoracion.desc(),
                Moneda.codigo_iso,
                AccountPlan.code,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = []
    for dc, codigo_cuenta, codigo_divisa, ratio in filas:
        items.append(
            {
                "id": str(dc.id),
                "ejercicio": dc.ejercicio,
                "fecha_valoracion": dc.fecha_valoracion.isoformat(),
                "cuenta_id": dc.cuenta_id,
                "cuenta": codigo_cuenta,
                "divisa_id": str(dc.divisa_id),
                "divisa": codigo_divisa,
                "tipo_cierre_id": str(dc.tipo_cierre_id),
                "ratio": _ocho(ratio),
                "saldo_divisa": _cuatro(dc.saldo_divisa),
                "saldo_funcional_previo": _cuatro(dc.saldo_funcional_previo),
                "valoracion": _cuatro(dc.valoracion),
                "diferencia": _cuatro(dc.diferencia if dc.diferencia > 0 else -dc.diferencia),
                "tipo": "ganancia" if dc.diferencia > 0 else "perdida",
                "estado": dc.estado.value,
                "asiento_id": str(dc.asiento_id) if dc.asiento_id is not None else None,
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}