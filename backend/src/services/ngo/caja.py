"""Cajas y movimientos de caja (SPEC-019 US3 / FR-008).

Cada caja cuelga de una subcuenta 570 real del plan (SPEC-001); los movimientos
(entradas/salidas) son asientos reales del motor (SPEC-002) de 2 líneas
(570 ↔ contrapartida) y la traza `movimiento_caja` se materializa en la misma
transacción (vista del diario, sin duplicar importes). El saldo es exactamente
la suma de las líneas 570 de la caja en asientos POSTED.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.ngo.arqueo import MovimientoCaja, MovimientoTipo
from models.ngo.caja import Caja, CajaEstado, CajaTipo
from services.audit.writer import audit_escribir
from services.journal.motor import crear_asiento_multilinea
from services.ngo.errores import NgoError

PAGINA_MIN, PAGINA_MAX = 1, 100


def _cuatro(value: Decimal) -> str:
    return f"{value:0.4f}"


async def _cuenta(db: AsyncSession, empresa_id: int, cuenta_id: int) -> AccountPlan | None:
    return await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.id == cuenta_id,
        )
    )


async def _validar_cuenta_570(db: AsyncSession, empresa_id: int, cuenta_id: int) -> AccountPlan:
    cuenta = await _cuenta(db, empresa_id, cuenta_id)
    if cuenta is None or not cuenta.code.startswith("570"):
        raise NgoError("cuenta_570_no_encontrada", "La cuenta 570 no existe en la empresa activa")
    if not cuenta.is_active:
        raise NgoError("cuenta_570_inactiva", "La subcuenta 570 está inactiva")
    if not cuenta.is_selectable:
        raise NgoError("cuenta_570_no_apuntable", "La subcuenta 570 no es apuntable")
    return cuenta


async def saldo_570(
    db: AsyncSession,
    *,
    empresa_id: int,
    account_id: int,
    hasta: date | None = None,
) -> Decimal:
    query = (
        select(
            func.coalesce(
                func.sum(JournalEntryLine.debe - JournalEntryLine.haber), 0
            )
        )
        .select_from(JournalEntryLine)
        .join(
            JournalEntry,
            and_(
                JournalEntry.empresa_id == JournalEntryLine.empresa_id,
                JournalEntry.id == JournalEntryLine.journal_entry_id,
            ),
        )
        .where(
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntryLine.account_id == account_id,
            JournalEntry.estado == JournalEntryEstado.POSTED,
        )
    )
    if hasta is not None:
        query = query.where(JournalEntry.fecha <= hasta)
    return Decimal(await db.scalar(query) or 0)


async def crear_caja(
    db: AsyncSession,
    *,
    empresa_id: int,
    nombre: str,
    cuenta_570_id: int,
    tipo: str,
    actor: str | None = None,
) -> dict:
    nombre = nombre.strip()
    if not (1 <= len(nombre) <= 80):
        raise NgoError("nombre_invalido", "El nombre debe tener entre 1 y 80 caracteres")

    duplicado = await db.scalar(
        select(Caja).where(
            Caja.empresa_id == empresa_id,
            Caja.nombre == nombre,
        )
    )
    if duplicado is not None:
        raise NgoError("nombre_duplicado", f"Ya existe una caja llamada {nombre!r}")

    asignada = await db.scalar(
        select(Caja).where(
            Caja.empresa_id == empresa_id,
            Caja.cuenta_570_id == cuenta_570_id,
        )
    )
    if asignada is not None:
        raise NgoError("cuenta_570_asignada", "La subcuenta 570 ya está asignada a otra caja")

    if tipo not in (t.value for t in CajaTipo):
        raise NgoError("tipo_invalido", f"Tipo de caja desconocido: {tipo}")
    if tipo == CajaTipo.caja_chica.value:
        # Revisión específica del diseño: la subcuenta 570 debe ser apuntable.
        await _validar_cuenta_570(db, empresa_id, cuenta_570_id)
    else:
        await _validar_cuenta_570(db, empresa_id, cuenta_570_id)

    caja = Caja(
        empresa_id=empresa_id,
        nombre=nombre,
        cuenta_570_id=cuenta_570_id,
        tipo=CajaTipo(tipo),
        estado=CajaEstado.activa,
    )
    if caja.id is None:
        caja.id = uuid.uuid4()
    db.add(caja)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CREAR_CAJA",
        entity="caja",
        entity_id=str(caja.id),
        payload={"nombre": nombre, "cuenta_570_id": cuenta_570_id},
    )
    await db.flush()
    return {
        "id": str(caja.id),
        "nombre": caja.nombre,
        "cuenta_570_id": caja.cuenta_570_id,
        "tipo": caja.tipo.value,
        "estado": caja.estado.value,
        "saldo": _cuatro(await saldo_570(db, empresa_id=empresa_id, account_id=cuenta_570_id)),
    }


async def listar_cajas(
    db: AsyncSession,
    *,
    empresa_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise NgoError("page_size_invalido", "page_size debe estar entre 1 y 100")
    total = await db.scalar(
        select(func.count()).select_from(Caja).where(Caja.empresa_id == empresa_id)
    )
    cajas = (
        await db.scalars(
            select(Caja)
            .where(Caja.empresa_id == empresa_id)
            .order_by(Caja.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = []
    for c in cajas:
        items.append(
            {
                "id": str(c.id),
                "nombre": c.nombre,
                "cuenta_570_id": c.cuenta_570_id,
                "tipo": c.tipo.value,
                "estado": c.estado.value,
                "saldo": _cuatro(await saldo_570(db, empresa_id=empresa_id, account_id=c.cuenta_570_id)),
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


async def obtener_caja(
    db: AsyncSession,
    *,
    empresa_id: int,
    caja_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> dict | None:
    caja = await db.scalar(
        select(Caja).where(
            Caja.empresa_id == empresa_id,
            Caja.id == caja_id,
        )
    )
    if caja is None:
        return None
    saldo = await saldo_570(db, empresa_id=empresa_id, account_id=caja.cuenta_570_id)
    movs = await listar_movimientos(
        db, empresa_id=empresa_id, caja_id=caja_id, page=page, page_size=page_size
    )
    return {
        "id": str(caja.id),
        "nombre": caja.nombre,
        "cuenta_570_id": caja.cuenta_570_id,
        "tipo": caja.tipo.value,
        "estado": caja.estado.value,
        "saldo": _cuatro(saldo),
        "movimientos": movs,
    }


async def inactivar_caja(
    db: AsyncSession,
    *,
    empresa_id: int,
    caja_id: uuid.UUID,
    actor: str | None = None,
) -> dict:
    caja = await db.scalar(
        select(Caja).where(
            Caja.empresa_id == empresa_id,
            Caja.id == caja_id,
        )
    )
    if caja is None:
        raise NgoError("caja_no_encontrada", "La caja no existe en la empresa activa")
    if caja.estado == CajaEstado.inactiva:
        raise NgoError("caja_inactiva", "La caja ya está inactiva")
    caja.estado = CajaEstado.inactiva
    caja.updated_at = datetime.now(UTC)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="INACTIVAR_CAJA",
        entity="caja",
        entity_id=str(caja.id),
        payload={},
    )
    await db.flush()
    return {
        "id": str(caja.id),
        "nombre": caja.nombre,
        "cuenta_570_id": caja.cuenta_570_id,
        "tipo": caja.tipo.value,
        "estado": caja.estado.value,
    }


def _movimiento_dto(m: MovimientoCaja) -> dict:
    return {
        "id": str(m.id),
        "caja_id": str(m.caja_id),
        "asiento_id": str(m.asiento_id),
        "linea_id": str(m.linea_id),
        "tipo": m.tipo.value,
        "importe": _cuatro(m.importe),
        "fecha": m.fecha.isoformat(),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def registrar_movimiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    caja_id: uuid.UUID,
    tipo: str,
    importe: Decimal,
    fecha: date,
    concepto: str,
    contrapartida_cuenta_id: int,
    actor: str | None = None,
) -> dict:
    caja = await db.scalar(
        select(Caja).where(
            Caja.empresa_id == empresa_id,
            Caja.id == caja_id,
        )
    )
    if caja is None:
        raise NgoError("caja_no_encontrada", "La caja no existe en la empresa activa")
    if caja.estado == CajaEstado.inactiva:
        raise NgoError("caja_inactiva", "No se pueden registrar movimientos en una caja inactiva")
    if tipo not in (t.value for t in MovimientoTipo):
        raise NgoError("tipo_invalido", f"Tipo de movimiento desconocido: {tipo}")
    if importe <= 0:
        raise NgoError("importe_invalido", "El importe debe ser positivo")
    if not concepto or not concepto.strip():
        raise NgoError("concepto_vacio", "El concepto es obligatorio")

    cuenta_570 = await _validar_cuenta_570(db, empresa_id, caja.cuenta_570_id)
    contrapartida = await _cuenta(db, empresa_id, contrapartida_cuenta_id)
    if contrapartida is None:
        raise NgoError("cuenta_no_encontrada", "La cuenta contrapartida no existe en la empresa activa")
    if not contrapartida.is_selectable or not contrapartida.is_active:
        raise NgoError("cuenta_no_apuntable", "La cuenta contrapartida no es apuntable")
    if contrapartida.id == caja.cuenta_570_id:
        raise NgoError("cuenta_contrapartida_invalida", "La contrapartida no puede ser la propia 570")

    if tipo == MovimientoTipo.entrada.value:
        lineas = [
            {"cuenta": cuenta_570.code, "debe": importe, "haber": Decimal(0), "detalle": concepto},
            {"cuenta": contrapartida.code, "debe": Decimal(0), "haber": importe, "detalle": concepto},
        ]
    else:
        lineas = [
            {"cuenta": contrapartida.code, "debe": importe, "haber": Decimal(0), "detalle": concepto},
            {"cuenta": cuenta_570.code, "debe": Decimal(0), "haber": importe, "detalle": concepto},
        ]

    entrada = await crear_asiento_multilinea(
        db,
        empresa_id=empresa_id,
        fecha=fecha,
        concepto=concepto,
        lineas=lineas,
        actor=actor,
    )

    linea_570 = await db.scalar(
        select(JournalEntryLine).where(
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntryLine.journal_entry_id == entrada.id,
            JournalEntryLine.account_id == caja.cuenta_570_id,
        )
    )
    if linea_570 is None:
        raise NgoError("linea_570_no_encontrada", "No se localizó la línea 570 del asiento")

    movimiento = MovimientoCaja(
        empresa_id=empresa_id,
        caja_id=caja.id,
        asiento_id=entrada.id,
        linea_id=linea_570.id,
        tipo=MovimientoTipo(tipo),
        importe=importe,
        fecha=fecha,
    )
    if movimiento.id is None:
        movimiento.id = uuid.uuid4()
    db.add(movimiento)
    await db.flush()
    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="REGISTRAR_MOVIMIENTO",
        entity="movimiento_caja",
        entity_id=str(movimiento.id),
        payload={
            "caja_id": str(caja.id),
            "asiento_id": str(entrada.id),
            "tipo": tipo,
            "importe": str(importe),
        },
    )
    await db.flush()
    return {**_movimiento_dto(movimiento), "saldo": _cuatro(await saldo_570(db, empresa_id=empresa_id, account_id=caja.cuenta_570_id))}


async def listar_movimientos(
    db: AsyncSession,
    *,
    empresa_id: int,
    caja_id: uuid.UUID,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise NgoError("page_size_invalido", "page_size debe estar entre 1 y 100")
    filtros = [
        MovimientoCaja.empresa_id == empresa_id,
        MovimientoCaja.caja_id == caja_id,
    ]
    if fecha_desde is not None:
        filtros.append(MovimientoCaja.fecha >= fecha_desde)
    if fecha_hasta is not None:
        filtros.append(MovimientoCaja.fecha <= fecha_hasta)
    base = select(MovimientoCaja).where(*filtros)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    movimientos = (
        await db.scalars(
            base.order_by(MovimientoCaja.fecha, MovimientoCaja.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [_movimiento_dto(m) for m in movimientos],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }