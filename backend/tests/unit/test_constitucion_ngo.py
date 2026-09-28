"""Constitución aplicada a Gestión ONG (SPEC-019).

II (inmutabilidad): las trazas gasto_imputado / libro_oficial / movimiento_caja
y la legalización son append-only a nivel DB. III (aislamiento): la empresa
activa SIEMPRE filtra los datos del tenant. Auditoría escrita en la misma
transacción (WORM).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func as _func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.audit.audit_log import AuditLog
from services.ngo.caja import crear_caja, registrar_movimiento
from services.ngo.legalizacion import emitir_legalizacion
from services.ngo.subvenciones import obtener_subvencion


def _linea_debe(ns, empresa_id, entrada):
    from models.acct.journal import JournalEntryLine

    async def _op(session):
        filas = (
            await session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.empresa_id == empresa_id,
                    JournalEntryLine.journal_entry_id == entrada.id,
                )
            )
        ).all()
        return str(next(l for l in filas if l.debe > 0).id)

    return ns.run(ns.consultar(_op))


def _gasto(ns, empresa_id=10):
    return ns.asiento(
        empresa_id,
        [
            {"cuenta": "6400", "debe": Decimal("300.0000"), "haber": Decimal(0), "detalle": "gasto"},
            {"cuenta": "5720", "debe": Decimal(0), "haber": Decimal("300.0000"), "detalle": "banco"},
        ],
        date(2026, 6, 1),
        "Gasto ONG",
    )


def test_aislamiento_multitenant(ngo_client):
    ns = ngo_client
    sub10 = ns.crear_subvencion(empresa_id=10, importe="900.0000", referencia="ISO1")
    entrada10 = _gasto(ns, 10)
    linea10 = _linea_debe(ns, 10, entrada10)

    from services.ngo.errores import NgoError
    from services.ngo.justificacion import imputar_gasto as _imputar

    with pytest.raises(NgoError) as exc:
        ns.run(
            ns.mutar(
                lambda s: _imputar(
                    s,
                    empresa_id=20,
                    subvencion_id=uuid.UUID(sub10["id"]),
                    asiento_id=entrada10.id,
                    linea_id=uuid.UUID(linea10),
                    importe_asignado=Decimal("1.0000"),
                )
            )
        )
    assert exc.value.code == "subvencion_no_encontrada"

    visto20 = ns.run(ns.consultar(lambda s: obtener_subvencion(s, empresa_id=20, subvencion_id=uuid.UUID(sub10["id"]))))
    assert visto20 is None


def test_trazas_append_only(ngo_client):
    ns = ngo_client
    cuenta_570_id = ns.subcuenta_570(10)
    contrapartida_id = _cuenta_1110(ns, 10)
    caja = ns.run(
        ns.mutar(
            lambda s: crear_caja(
                s, empresa_id=10, nombre="Caja APP", cuenta_570_id=cuenta_570_id, tipo="caja"
            )
        )
    )
    ns.run(
        ns.mutar(
            lambda s: registrar_movimiento(
                s,
                empresa_id=10,
                caja_id=uuid.UUID(caja["id"]),
                tipo="entrada",
                importe=Decimal("50.0000"),
                fecha=date(2026, 6, 1),
                concepto="Fondo",
                contrapartida_cuenta_id=contrapartida_id,
            )
        )
    )

    from models.ngo.arqueo import MovimientoCaja

    async def _mov_id(session):
        return await session.scalar(
            select(MovimientoCaja.id).where(MovimientoCaja.empresa_id == 10)
        )

    mov_id = ns.run(ns.consultar(_mov_id))
    assert mov_id is not None

    async def _update(session):
        m = await session.get(MovimientoCaja, mov_id)
        assert m is not None
        m.importe = Decimal("999.0000")
        await session.flush()

    with pytest.raises(IntegrityError):
        ns.run(ns.mutar(_update))

    async def _delete(session):
        m = await session.get(MovimientoCaja, mov_id)
        assert m is not None
        await session.delete(m)
        await session.flush()

    with pytest.raises(IntegrityError):
        ns.run(ns.mutar(_delete))


def test_libro_oficial_append_only(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    from services.ngo.libros_pdf import generar_libros

    ns.run(ns.mutar(lambda s: generar_libros(s, empresa_id=10, ejercicio=2025, tipos=["diario"])))

    from models.ngo.libros import LibroOficial

    async def _libro_id(session):
        return await session.scalar(
            select(LibroOficial.id).where(
                LibroOficial.empresa_id == 10, LibroOficial.ejercicio == 2025
            )
        )

    libro_id = ns.run(ns.consultar(_libro_id))
    assert libro_id is not None

    async def _delete(session):
        l = await session.get(LibroOficial, libro_id)
        assert l is not None
        await session.delete(l)
        await session.flush()

    with pytest.raises(IntegrityError):
        ns.run(ns.mutar(_delete))

    async def _xxx(session):
        l = await session.get(LibroOficial, libro_id)
        assert l is not None
        l.sha256 = "0" * 64
        await session.flush()

    with pytest.raises(IntegrityError):
        ns.run(ns.mutar(_xxx))


def test_legalizacion_no_se_borra(ngo_client):
    ns = ngo_client
    ns.cerrar(10, 2025)
    ns.run(ns.mutar(lambda s: emitir_legalizacion(s, empresa_id=10, ejercicio=2025)))

    from models.ngo.libros import Legalizacion

    async def _delete(session):
        leg = await session.scalar(
            select(Legalizacion).where(Legalizacion.empresa_id == 10, Legalizacion.ejercicio == 2025)
        )
        assert leg is not None
        await session.delete(leg)
        await session.flush()

    with pytest.raises(IntegrityError):
        ns.run(ns.mutar(_delete))


def test_auditoria_escribe_en_la_misma_transaccion(ngo_client):
    ns = ngo_client
    ns.crear_subvencion(10, importe="900.0000", referencia="AUD")
    cuenta_570_id = ns.subcuenta_570(10)
    contrapartida_id = _cuenta_1110(ns, 10)
    caja = ns.run(
        ns.mutar(
            lambda s: crear_caja(
                s, empresa_id=10, nombre="Caja AUD", cuenta_570_id=cuenta_570_id, tipo="caja"
            )
        )
    )
    ns.run(
        ns.mutar(
            lambda s: registrar_movimiento(
                s,
                empresa_id=10,
                caja_id=uuid.UUID(caja["id"]),
                tipo="entrada",
                importe=Decimal("50.0000"),
                fecha=date(2026, 6, 1),
                concepto="Fondo",
                contrapartida_cuenta_id=contrapartida_id,
            )
        )
    )

    async def _conteo(session):
        return await session.scalar(
            select(_func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.empresa_id == 10,
                AuditLog.operacion.in_(["CREAR_SUBVENCION", "CREAR_CAJA", "REGISTRAR_MOVIMIENTO"]),
            )
        )

    total = ns.run(ns.consultar(_conteo))
    assert total == 3


def _cuenta_1110(ns, empresa_id):
    from models.acct.account_plan import AccountPlan

    async def _op(session):
        return await session.scalar(
            select(AccountPlan.id).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == "1110")
        )

    return ns.run(ns.consultar(_op))