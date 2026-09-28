"""Foundational model tests (T012, T012a).

Covers the constitution-critical constraints at the metadata level and through
real inserts:
- (empresa_id, ejercicio, numero_remesa) uniqueness on Remesa.
- Single active CondicionProntoPago per tercero.
- Composite empresa_id foreign keys on ReciboRemesa / DevolucionRecibo.
- Tenant-scoped unique keys and indexes on every treasury table.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from base import Base
from models.treasury import (
    CondicionProntoPago,
    FormatoRemesa,
    ReciboEstado,
    ReciboRemesa,
    Remesa,
    RemesaEstado,
    TipoAdeudo,
)

TERCERO_A = uuid.uuid4()
TERCERO_B = uuid.uuid4()
VENCIMIENTO = uuid.uuid4()


async def _crear_remesa(session: AsyncSession, empresa_id: int, numero: int = 1) -> Remesa:
    remesa = Remesa(
        empresa_id=empresa_id,
        ejercicio=2026,
        numero_remesa=numero,
        formato=FormatoRemesa.SEPA_DD,
        tipo_adeudo=TipoAdeudo.CORE,
        importe_total=Decimal("150.0000"),
        estado=RemesaEstado.borrador,
    )
    session.add(remesa)
    await session.flush()
    return remesa


# ---------------------------------------------------------------------------
# T012 — constraint (empresa_id, ejercicio, numero_remesa)
# ---------------------------------------------------------------------------


async def test_remesa_unique_numero_per_empresa_and_ejercicio(db_session):
    await _crear_remesa(db_session, empresa_id=1)
    with pytest.raises(IntegrityError):
        await _crear_remesa(db_session, empresa_id=1)
    await db_session.rollback()


async def test_remesa_same_numero_allowed_in_different_empresa(db_session):
    await _crear_remesa(db_session, empresa_id=1)
    await _crear_remesa(db_session, empresa_id=2)
    await db_session.commit()


async def test_remesa_same_numero_allowed_in_different_ejercicio(db_session):
    await _crear_remesa(db_session, empresa_id=1)
    otra = Remesa(
        empresa_id=1,
        ejercicio=2025,
        numero_remesa=1,
        formato=FormatoRemesa.SEPA_DD,
        tipo_adeudo=TipoAdeudo.CORE,
        importe_total=Decimal("50.0000"),
        estado=RemesaEstado.borrador,
    )
    db_session.add(otra)
    await db_session.flush()


# ---------------------------------------------------------------------------
# T012 — único registro vigente por tercero
# ---------------------------------------------------------------------------


async def test_condicion_vigente_unica_por_tercero(db_session):
    db_session.add(
        CondicionProntoPago(
            empresa_id=1,
            tercero_id=TERCERO_A,
            plazo_dias=10,
            porcentaje=Decimal("2.00"),
            vigente=True,
        )
    )
    await db_session.flush()
    db_session.add(
        CondicionProntoPago(
            empresa_id=1,
            tercero_id=TERCERO_A,
            plazo_dias=5,
            porcentaje=Decimal("3.00"),
            vigente=True,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_multiple_condiciones_inactivas_permitidas(db_session):
    for _ in range(2):
        db_session.add(
            CondicionProntoPago(
                empresa_id=1,
                tercero_id=TERCERO_B,
                plazo_dias=10,
                porcentaje=Decimal("2.00"),
                vigente=False,
            )
        )
    await db_session.flush()


async def test_condicion_vigente_misma_para_otra_empresa(db_session):
    for empresa in (1, 2):
        db_session.add(
            CondicionProntoPago(
                empresa_id=empresa,
                tercero_id=TERCERO_B,
                plazo_dias=10,
                porcentaje=Decimal("2.00"),
                vigente=True,
            )
        )
    await db_session.flush()


# ---------------------------------------------------------------------------
# T012 — FK compuesta con empresa_id
# ---------------------------------------------------------------------------


async def test_recibo_remesa_fk_compuesta_empresa(db_session):
    remesa_a = await _crear_remesa(db_session, empresa_id=1)
    await db_session.commit()
    db_session.add(
        ReciboRemesa(
            empresa_id=2,
            remesa_id=remesa_a.id,
            vencimiento_id=VENCIMIENTO,
            recibo_num="R-0001",
            tercero_id=TERCERO_A,
            iban="ES9121000418450200051332",
            importe=Decimal("150.0000"),
            fecha_cargo=date(2026, 10, 10),
            estado=ReciboEstado.pendiente,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_recibo_remesa_fk_compuesta_ok(db_session):
    remesa_a = await _crear_remesa(db_session, empresa_id=1)
    await db_session.commit()
    db_session.add(
        ReciboRemesa(
            empresa_id=1,
            remesa_id=remesa_a.id,
            vencimiento_id=VENCIMIENTO,
            recibo_num="R-0001",
            tercero_id=TERCERO_A,
            iban="ES9121000418450200051332",
            importe=Decimal("150.0000"),
            fecha_cargo=date(2026, 10, 10),
            estado=ReciboEstado.pendiente,
        )
    )
    await db_session.flush()


# ---------------------------------------------------------------------------
# T012a — claves tenant en todos los modelos
# ---------------------------------------------------------------------------

TABLAS_CON_UNIQUE = (
    "remesa",
    "recibo_remesa",
    "devolucion_recibo",
    "reclamacion",
    "condicion_pronto_pago",
    "mandato_sepa",
    "blob_fichero",
)


def test_todas_las_tablas_tienen_indice_por_empresa_id():
    for table_name in TABLAS_CON_UNIQUE:
        table = Base.metadata.tables[table_name]
        column_names = {col.name for col in table.columns}
        assert "empresa_id" in column_names, f"{table_name} sin empresa_id"
        assert any(
            index_columns and index_columns[0] == "empresa_id"
            for index_columns in (
                [c.name for c in idx.columns] for idx in table.indexes
            )
        ), f"{table_name} sin índice por empresa_id"


def test_indices_unicos_empiezan_por_empresa_id():
    table = Base.metadata.tables["remesa"]
    unique_columns = {
        tuple(c.name for c in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("empresa_id", "ejercicio", "numero_remesa") in unique_columns


def test_recibo_remesa_indice_unico_vencimiento_por_empresa():
    table = Base.metadata.tables["recibo_remesa"]
    index = next(i for i in table.indexes if i.name == "uq_recibo_remesa_empresa_vencimiento")
    assert index.unique
    assert [c.name for c in index.columns] == ["empresa_id", "vencimiento_id"]


def test_devolucion_identificador_unic_por_empresa():
    table = Base.metadata.tables["devolucion_recibo"]
    unique_columns = {
        tuple(c.name for c in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("empresa_id", "identificador_externo") in unique_columns


def test_condicion_indice_parcial_vigente_por_empresa():
    table = Base.metadata.tables["condicion_pronto_pago"]
    index = next(i for i in table.indexes if i.name == "uq_condicion_pronto_pago_vigente")
    assert index.unique
    assert [c.name for c in index.columns] == ["empresa_id", "tercero_id"]


def test_mandato_referencia_unica_por_empresa_y_tercero():
    table = Base.metadata.tables["mandato_sepa"]
    unique_columns = {
        tuple(c.name for c in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("empresa_id", "tercero_id", "mandato_ref") in unique_columns


def test_fk_compuestas_incluyen_empresa_id():
    recibo = Base.metadata.tables["recibo_remesa"]
    recibo_fk = next(
        fk for fk in recibo.foreign_key_constraints
        if "remesa" in fk.referred_table.name
    )
    assert [c.name for c in recibo_fk.columns] == ["empresa_id", "remesa_id"]
    assert recibo_fk.elements[0].column.table is Base.metadata.tables["remesa"]

    devolucion = Base.metadata.tables["devolucion_recibo"]
    devolucion_fk = next(
        fk for fk in devolucion.foreign_key_constraints
        if "recibo_remesa" in fk.referred_table.name
    )
    assert [c.name for c in devolucion_fk.columns] == ["empresa_id", "recibo_remesa_id"]


def test_importes_usam_numeric_18_4():
    importe_columns = {
        ("remesa", "importe_total"),
        ("recibo_remesa", "importe"),
        ("devolucion_recibo", "importe"),
        ("devolucion_recibo", "importe_gastos"),
    }
    for table_name, column_name in importe_columns:
        column = Base.metadata.tables[table_name].columns[column_name]
        assert str(column.type) in (
            "NUMERIC(18, 4)",
            "NUMERIC(18,4)",
        ), f"{table_name}.{column_name} → {column.type}"