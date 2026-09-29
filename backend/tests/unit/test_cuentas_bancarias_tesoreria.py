"""Tests para el maestro de cuentas bancarias y selección de cuenta de origen en asientos de tesorería."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntryLine
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.iam.company import Company
from models.treasury.cuenta_bancaria import CuentaBancaria
from services.treasury.cobros_pagos import registrar_cobro, registrar_pago
from services.treasury.cuentas_bancarias import (
    CuentaBancariaError,
    crear_cuenta_bancaria,
    listar_cuentas_bancarias,
)


async def _empresa(db: AsyncSession, cid: int = 20) -> None:
    db.add(Company(company_id=cid, nif=f"B{cid:08d}", razon_social=f"Empresa MultiBanco {cid} SL"))
    await db.flush()


async def _vencimiento(
    db: AsyncSession, cid: int = 20, importe: str = "500.0000", tipo: TipoVencimiento = TipoVencimiento.pago
) -> Vencimiento:
    v = Vencimiento(
        empresa_id=cid,
        tercero_id=uuid.uuid4(),
        factura_id=None,
        recibo_num="REC-B-1",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=date(2026, 7, 1),
        importe=Decimal(importe),
        tipo=tipo,
        estado=EstadoVencimiento.pendiente,
    )
    db.add(v)
    await db.flush()
    return v


async def test_crear_multiples_cuentas_bancarias(db_session: AsyncSession) -> None:
    await _empresa(db_session, 20)

    # Crear Banco A (Santander)
    cb_a = await crear_cuenta_bancaria(
        db_session,
        empresa_id=20,
        nombre="Santander Cuenta Principal",
        banco="Banco Santander",
        iban="ES0000000000000000000001",
        bic="BSCHESMMXXX",
        cuenta_contable="57200001",
    )
    assert cb_a.id is not None
    assert cb_a.cuenta_contable == "57200001"

    # Crear Banco B (BBVA)
    cb_b = await crear_cuenta_bancaria(
        db_session,
        empresa_id=20,
        nombre="BBVA Operativa Pagos",
        banco="BBVA",
        iban="ES0000000000000000000002",
        bic="BBVAESMMXXX",
        cuenta_contable="57200002",
    )
    assert cb_b.id is not None
    assert cb_b.cuenta_contable == "57200002"

    # Listar cuentas de la empresa
    lista = await listar_cuentas_bancarias(db_session, empresa_id=20)
    assert len(lista) == 2
    nombres = [c.nombre for c in lista]
    assert "BBVA Operativa Pagos" in nombres
    assert "Santander Cuenta Principal" in nombres

    # Rechazar IBAN duplicado en la misma empresa
    with pytest.raises(CuentaBancariaError) as exc:
        await crear_cuenta_bancaria(
            db_session,
            empresa_id=20,
            nombre="Santander Repetido",
            iban="ES0000000000000000000001",
        )
    assert exc.value.code == "iban_duplicado"


async def test_asiento_tesoreria_con_cuenta_bancaria_origen(db_session: AsyncSession) -> None:
    await _empresa(db_session, 20)

    # Crear cuenta bancaria específica
    cb = await crear_cuenta_bancaria(
        db_session,
        empresa_id=20,
        nombre="CaixaBank Nóminas",
        iban="ES0000000000000000000003",
        cuenta_contable="57200003",
    )

    v = await _vencimiento(db_session, cid=20, importe="250.0000", tipo=TipoVencimiento.pago)

    # Registrar pago seleccionando la cuenta bancaria de origen
    op = await registrar_pago(
        db_session,
        empresa_id=20,
        vencimiento_id=v.id,
        fecha=date(2026, 7, 5),
        importe="250.0000",
        cuenta_bancaria_id=cb.id,
    )

    # Verificar que las líneas del asiento usan la subcuenta contable del banco seleccionado (57200003)
    lineas = (
        await db_session.scalars(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == op.journal_entry_id)
        )
    ).all()
    assert len(lineas) == 2
    cuentas = {l.cuenta: (l.debe, l.haber) for l in lineas}
    assert "400" in cuentas
    assert "57200003" in cuentas
    # En el pago, se carga a proveedores (400) y se abona en la cuenta bancaria (57200003)
    assert cuentas["400"][0] == Decimal("250.0000")
    assert cuentas["57200003"][1] == Decimal("250.0000")
