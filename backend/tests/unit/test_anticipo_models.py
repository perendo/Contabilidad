"""Modelos fundacionales de anticipos y cesiones (SPEC-022 T011).

Verifica las constraints del modelo en SQLite: ``saldo_pendiente >= 0``,
``importe_aplicado > 0``, unicidad cesión-vencimiento y que las FKs
compuestas preservan el multi-tenancy (constitución III).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.ar.tercero import Tercero
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.iam.company import Company
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.serie_factura import SerieFactura, SerieFacturaEstado
from models.treasury.anticipo import (
    Anticipo,
    EstadoAnticipo,
    TipoAnticipo,
)
from models.treasury.cesion import (
    CesionCobro,
    CesionCobroDetalle,
    EstadoCesion,
    TipoComisionCesion,
)
from models.treasury.liquidacion_anticipo import LiquidacionAnticipo

CLIENTE_1 = uuid.uuid4()
CLIENTE_2 = uuid.uuid4()


async def _sembrar_base(
    db: AsyncSession, empresa_id: int, cliente_id: uuid.UUID
) -> uuid.UUID:
    db.add(
        Company(company_id=empresa_id, nif=f"T{empresa_id:08d}", razon_social=f"E{empresa_id}")
    )
    await db.flush()
    cliente = Tercero(
        empresa_id=empresa_id, id=cliente_id, nombre="Cliente", nif=f"B{empresa_id}000001",
        es_cliente=True, es_proveedor=False,
    )
    db.add(cliente)
    await db.flush()
    serie = SerieFactura(
        empresa_id=empresa_id, codigo="SERIE", nombre="Serie", prefijo="F",
        siguiente_numero=1, estado=SerieFacturaEstado.activa,
    )
    db.add(serie)
    await db.flush()
    factura = Factura(
        empresa_id=empresa_id, serie_id=serie.id, numero=1, ejercicio=2026,
        fecha=date(2026, 6, 1), tipo=FacturaTipo.VENTA, tercero_id=cliente_id,
        importe_total=Decimal("2000.0000"), estado=FacturaEstado.emitida,
    )
    db.add(factura)
    db.add(
        FiscalYear(
            empresa_id=empresa_id, year=2026,
            date_start=date(2026, 1, 1), date_end=date(2026, 12, 31), is_closed=False,
        )
    )
    await db.flush()
    return factura.id


@pytest.mark.parametrize("empresa_id", [1, 2])
async def test_anticipo_saldo_pendiente_no_negativo(db_session, empresa_id):
    await _sembrar_base(db_session, empresa_id, CLIENTE_1)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(
            Anticipo(
                empresa_id=empresa_id, tercero_id=CLIENTE_1, tipo=TipoAnticipo.CLIENTE,
                cuenta_contable="438", fecha=date(2026, 6, 10),
                importe=Decimal("100.0000"), concepto="A", estado=EstadoAnticipo.pendiente,
                saldo_pendiente=Decimal("-1.0000"),
            )
        )
        await db_session.flush()
    await db_session.rollback()


async def test_liquidacion_importe_aplicado_positivo(db_session):
    factura_id = await _sembrar_base(db_session, 1, CLIENTE_1)
    anticipo = Anticipo(
        empresa_id=1, tercero_id=CLIENTE_1, tipo=TipoAnticipo.CLIENTE,
        cuenta_contable="438", fecha=date(2026, 6, 10),
        importe=Decimal("1000.0000"), concepto="Anticipo", estado=EstadoAnticipo.pendiente,
        saldo_pendiente=Decimal("1000.0000"),
    )
    db_session.add(anticipo)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(
            LiquidacionAnticipo(
                empresa_id=1, anticipo_id=anticipo.id, factura_id=factura_id,
                fecha_aplicacion=date(2026, 7, 1), importe_aplicado=Decimal("0.0000"),
            )
        )
        await db_session.flush()
    await db_session.rollback()


async def test_cesion_vencimiento_unico(db_session):
    await _sembrar_base(db_session, 1, CLIENTE_1)
    v = Vencimiento(
        empresa_id=1, tercero_id=CLIENTE_1, recibo_num="V1", ejercicio=2026,
        iban="ES9121000418450200051332",
        tipo=TipoVencimiento.cobro, fecha_vencimiento=date(2026, 9, 30),
        importe=Decimal("1500.0000"), acumulado=Decimal("0.0000"),
        estado=EstadoVencimiento.pendiente,
    )
    db_session.add(v)
    await db_session.flush()
    cesion = CesionCobro(
        empresa_id=1, entidad_financiera="Banco", fecha_cesion=date(2026, 8, 1),
        comision=Decimal("0.0000"), tipo_comision=TipoComisionCesion.IMPORTE_FIJO,
        importe_total_cedido=Decimal("1500.0000"), importe_neto_recibido=Decimal("1500.0000"),
        estado=EstadoCesion.activa,
    )
    db_session.add(cesion)
    await db_session.flush()
    db_session.add(
        CesionCobroDetalle(
            empresa_id=1, cesion_id=cesion.id, vencimiento_id=v.id,
            importe=Decimal("1500.0000"),
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(
            CesionCobroDetalle(
                empresa_id=1, cesion_id=cesion.id, vencimiento_id=v.id,
                importe=Decimal("1500.0000"),
            )
        )
        await db_session.flush()
    await db_session.rollback()


async def test_anticipo_fk_compuesta_empresa(db_session):
    await _sembrar_base(db_session, 1, CLIENTE_1)
    await _sembrar_base(db_session, 2, CLIENTE_2)
    with pytest.raises(IntegrityError):
        db_session.add(
            Anticipo(
                empresa_id=2, tercero_id=CLIENTE_1, tipo=TipoAnticipo.CLIENTE,
                cuenta_contable="438", fecha=date(2026, 6, 10),
                importe=Decimal("100.0000"), concepto="A", estado=EstadoAnticipo.pendiente,
                saldo_pendiente=Decimal("100.0000"),
            )
        )
        await db_session.flush()
    await db_session.rollback()