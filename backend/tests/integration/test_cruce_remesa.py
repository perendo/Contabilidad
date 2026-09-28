"""Tests SPEC-013 US2 (T027): acoplamiento con SPEC-020 al confirmar el cruce."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry
from models.treasury.recibo_remesa import ReciboEstado, ReciboRemesa
from models.treasury.remesa import FormatoRemesa, Remesa, RemesaEstado, TipoAdeudo
from services.journal.entry_service import asentar, crear_borrador
from services.reconciliation.conciliacion import abrir_conciliacion
from services.reconciliation.cruce import confirmar_cruce
from services.reconciliation.importacion import importar_extracto
from services.reconciliation.matching import generar_propuestas
from tests.conftest import sembrar_empresa_pgc

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


async def test_confirmar_cruce_cobro_remesa(db_session: AsyncSession) -> None:
    await sembrar_empresa_pgc(db_session, 10)
    cuentas = {
        c.code: c.id
        for c in (
            await db_session.scalars(
                select(AccountPlan).where(
                    AccountPlan.tenant_id == 10,
                    AccountPlan.code.in_(["5720", "4300"]),
                )
            )
        ).all()
    }
    # Asiento de cobro 5720 haber 1805 / 4300 debe 1805
    borrador = await crear_borrador(
        db_session, empresa_id=10, fecha=date(2026, 9, 15), concepto="ABONO CLIENTE",
        lineas=[
            {"account_id": cuentas["4300"], "debit": "1805.0000", "credit": "0"},
            {"account_id": cuentas["5720"], "debit": "0", "credit": "1805.0000"},
        ],
        actor="t",
    )
    asiento = await asentar(db_session, empresa_id=10, entry_id=borrador.id, actor="t")

    remesa = Remesa(
        empresa_id=10, ejercicio=2026, numero_remesa=1,
        formato=FormatoRemesa.SEPA_DD, tipo_adeudo=TipoAdeudo.CORE,
        importe_total=Decimal("1805.0000"), estado=RemesaEstado.emitida,
    )
    db_session.add(remesa)
    await db_session.flush()
    recibo = ReciboRemesa(
        empresa_id=10, remesa_id=remesa.id, vencimiento_id=uuid.uuid4(), recibo_num="R-1",
        tercero_id=uuid.uuid4(), iban="ES9121000418450200051332",
        importe=Decimal("1805.0000"), fecha_cargo=date(2026, 9, 15),
        estado=ReciboEstado.remesado, asiento_cobro_id=asiento.id,
    )
    db_session.add(recibo)
    await db_session.flush()

    extracto = await importar_extracto(
        db_session, empresa_id=10,
        file_bytes=(FIXTURES / "extracto_43_19_valido.txt").read_bytes(),
        nombre_fichero="v.txt", actor="t",
    )
    conc = await abrir_conciliacion(
        db_session, empresa_id=10, cuenta_id=cuentas["5720"],
        fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30),
        extracto_id=extracto.id, actor="t",
    )
    n_asientos_antes = await db_session.scalar(select(func.count(JournalEntry.id)))

    propuestas = await generar_propuestas(db_session, empresa_id=10, conciliacion=conc)
    objetivo = next(
        p for p in propuestas
        if p.importe == Decimal("1805.0000") and p.signo == "H"
    )
    await confirmar_cruce(
        db_session, empresa_id=10, conciliacion=conc,
        movimiento_id=objetivo.movimiento_id, apunte_id=objetivo.apunte_id, actor="t",
    )
    await db_session.refresh(recibo)
    assert recibo.estado == ReciboEstado.cobrado
    assert recibo.fecha_cobro == date(2026, 9, 16)
    n_asientos_despues = await db_session.scalar(select(func.count(JournalEntry.id)))
    assert n_asientos_despues == n_asientos_antes  # no se crea segundo asiento
