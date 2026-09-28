"""Cross-cutting constitution V tests (T051).

Valida para todos los flujos de tesorería: (a) todo asiento (COBRO,
PRONTO_PAGO, REVERSAL) tiene Debe==Haber exacto; (b) ningún JournalEntry
POSTED se actualiza ni elimina; (c) toda tabla treasury/scaffold aísla por
empresa_id (constitución III).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

import models.acct.journal
import models.ar.vencimiento
import models.audit.audit_log
import models.treasury  # noqa: F401
from base import Base
from models.acct.journal import JournalEntry, JournalEntryLine
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.condicion_pronto_pago import CondicionProntoPago
from models.treasury.recibo_remesa import ReciboRemesa
from services.discount import liquidar_con_descuento
from services.remittance.emision import confirmar_cobro, crear_remesa, emitir_remesa
from services.remittance.refund_r19 import procesar_devolucion
from services.remittance.seleccion import Emisor

EMISOR = Emisor(nombre="ACME SL", nif="B12345678", iban="ES9121000418450200051332")


async def _vencimiento(db_session, empresa_id: int, recibo_num: str) -> Vencimiento:
    hoy = datetime.now(timezone.utc).date()
    vencimiento = Vencimiento(
        empresa_id=empresa_id,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num=recibo_num,
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=hoy + timedelta(days=10),
        importe=Decimal("100.0000"),
        estado=EstadoVencimiento.pendiente,
    )
    db_session.add(vencimiento)
    await db_session.flush()
    return vencimiento


async def _escenario_completo(db_session, empresa_id: int):
    """Cobro + pronto pago + devolución; devuelve el asiento de cobro."""
    hoy = datetime.now(timezone.utc).date()

    v1 = await _vencimiento(db_session, empresa_id, f"R-{empresa_id}-C")
    remesa1 = await crear_remesa(
        db_session,
        empresa_id,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[v1.id],
    )
    _, _, _ = await emitir_remesa(db_session, empresa_id, remesa1.id, emisor=EMISOR)
    recibo1 = await db_session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id,
            ReciboRemesa.remesa_id == remesa1.id,
        )
    )
    await confirmar_cobro(
        db_session, empresa_id, remesa1.id, recibo1.id, fecha_cobro=hoy
    )
    asiento_cobro_id = recibo1.asiento_cobro_id

    v2 = await _vencimiento(db_session, empresa_id, f"R-{empresa_id}-D")
    tercero2 = v2.tercero_id
    remesa2 = await crear_remesa(
        db_session,
        empresa_id,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[v2.id],
    )
    recibo2 = await db_session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id,
            ReciboRemesa.remesa_id == remesa2.id,
        )
    )
    db_session.add(
        CondicionProntoPago(
            empresa_id=empresa_id,
            tercero_id=tercero2,
            plazo_dias=10,
            porcentaje=Decimal("2.0000"),
            vigente=True,
            override_factura_id=None,
        )
    )
    await db_session.flush()
    await liquidar_con_descuento(
        db_session, empresa_id, recibo2.id, fecha_pago=hoy + timedelta(days=1)
    )

    await procesar_devolucion(
        db_session,
        empresa_id,
        recibo_id=recibo1.id,
        codigo="MD06",
        motivo="mandato rechazado",
        importe=Decimal("100.0000"),
        importe_gastos=Decimal("5.0000"),
        fecha_registro=hoy + timedelta(days=2),
        identificador_externo=f"R19:MD06:R-{empresa_id}-C:{hoy}:10000:500",
    )
    await db_session.flush()
    return asiento_cobro_id


async def test_todo_asiento_generado_esta_balanceado(db_session):
    await _escenario_completo(db_session, 12)

    asientos = list(
        (
            await db_session.scalars(
                select(JournalEntry).where(JournalEntry.empresa_id == 12)
            )
        ).all()
    )
    tipos = {asiento.tipo for asiento in asientos}
    assert {t.value for t in tipos} == {"COBRO", "PRONTO_PAGO", "REVERSAL"}
    assert len(asientos) >= 3
    for asiento in asientos:
        lineas = list(
            (
                await db_session.scalars(
                    select(JournalEntryLine).where(
                        JournalEntryLine.journal_entry_id == asiento.id
                    )
                )
            ).all()
        )
        debe = sum((l.debe for l in lineas), Decimal(0))
        haber = sum((l.haber for l in lineas), Decimal(0))
        assert debe == haber, f"asiento {asiento.id} desbalanceado"
        assert asiento.estado.value == "POSTED"


async def _snapshot_asientos(db_session, empresa_id: int):
    filas = (
        await db_session.execute(
            select(
                JournalEntry.id,
                JournalEntry.empresa_id,
                JournalEntry.ejercicio,
                JournalEntry.fecha,
                JournalEntry.tipo,
                JournalEntry.concepto,
                JournalEntry.numero_asiento,
                JournalEntry.original_id,
            ).where(JournalEntry.empresa_id == empresa_id)
        )
    ).all()
    return sorted((tuple(fila) for fila in filas), key=lambda f: str(f[0]))


async def test_asientos_posted_no_se_actualizan_ni_borran(db_session):
    asiento_cobro_id = await _escenario_completo(db_session, 13)
    antes = await _snapshot_asientos(db_session, 13)

    datetime.now(timezone.utc).date()
    recibo = await db_session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == 13,
            ReciboRemesa.asiento_cobro_id == asiento_cobro_id,
        )
    )
    vencimiento = await db_session.scalar(
        select(Vencimiento).where(
            Vencimiento.empresa_id == 13, Vencimiento.id == recibo.vencimiento_id
        )
    )
    vencimiento.estado = EstadoVencimiento.pendiente
    await db_session.flush()

    remesa_nueva = await crear_remesa(
        db_session,
        13,
        formato="SEPA_DD",
        tipo_adeudo="CORE",
        vencimiento_ids=[vencimiento.id],
    )
    await db_session.flush()

    despues = await _snapshot_asientos(db_session, 13)
    assert set(antes) & set(despues) == set(antes)
    assert len(set(despues) - set(antes)) == 0

    asiento_original = await db_session.scalar(
        select(JournalEntry).where(JournalEntry.id == asiento_cobro_id)
    )
    assert asiento_original is not None
    assert asiento_original.estado.value == "POSTED"
    assert remesa_nueva.estado.value == "borrador"


async def test_empresa_id_aisla_todas_las_tablas(db_session):
    await _escenario_completo(db_session, 21)

    tablas_tenant = [
        t
        for t in Base.metadata.sorted_tables
        if "empresa_id" in t.c
        and t.name
        in {
            "journal_entry",
            "journal_entry_line",
            "vencimiento",
            "recibo_remesa",
            "remesa",
            "blob_fichero",
            "secuencia_remesa",
            "cobro_conciliado",
            "condicion_pronto_pago",
            "mandato_sepa",
            "devolucion_recibo",
            "reclamacion",
            "audit_log",
            "tercero",
        }
    ]
    tablas_con_filas = {
        "journal_entry",
        "journal_entry_line",
        "vencimiento",
        "recibo_remesa",
        "remesa",
        "blob_fichero",
        "secuencia_remesa",
        "devolucion_recibo",
        "audit_log",
    }
    assert {"recibo_remesa", "devolucion_recibo", "journal_entry"} <= {
        t.name for t in tablas_tenant
    }

    for tabla in tablas_tenant:
        empresa_col = tabla.c.empresa_id
        con_otra = (
            await db_session.execute(
                select(empresa_col).where(empresa_col == 22).select_from(tabla)
            )
        ).all()
        assert len(con_otra) == 0, f"{tabla.name} tiene filas de otra empresa"
        con_activa = (
            await db_session.execute(
                select(empresa_col).where(empresa_col == 21).select_from(tabla)
            )
        ).all()
        if tabla.name in tablas_con_filas:
            assert len(con_activa) > 0, f"{tabla.name} sin filas de la empresa activa"