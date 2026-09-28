"""Modelo de efectos, cobros por medio y comisiones (SPEC-021 T009).

Restricciones de la constitución verificadas a nivel metadata y con inserts
reales:
- unicidad del documento por (empresa, tercero, tipo).
- revisión de fechas e importe (CHECK safety_next).
- importe_neto/importe_comision coherentes en cobro_medio.
- FK compuesta con empresa_id en comision_bancaria → cobro_medio.
- índices con empresa_id a la cabeza en todas las tablas nuevas.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from base import Base
from models.treasury.cobro_medio import CobroMedio, MedioCobro
from models.treasury.comision import ComisionBancaria
from models.treasury.efecto import Efecto, EstadoEfecto, TipoEfecto

TERCERO_A = uuid.uuid4()
TERCERO_B = uuid.uuid4()
VENCIMIENTO = uuid.uuid4()


def _efecto(
    *,
    empresa_id: int,
    tercero_id: uuid.UUID = TERCERO_A,
    numero: str = "CH-0001",
    tipo: TipoEfecto = TipoEfecto.CHEQUE,
    emision: date = date(2026, 5, 1),
    vencimiento: date = date(2026, 7, 1),
    importe: Decimal = Decimal("1000.0000"),
) -> Efecto:
    return Efecto(
        empresa_id=empresa_id,
        tercero_id=tercero_id,
        tipo_efecto=tipo,
        numero_documento=numero,
        fecha_emision=emision,
        fecha_vencimiento=vencimiento,
        importe=importe,
        moneda="EUR",
        estado=EstadoEfecto.emitido,
    )


async def test_efecto_ok_tercero_sin_fk(db_session):
    db_session.add(_efecto(empresa_id=1))
    await db_session.flush()


async def test_efecto_documento_duplicado_misma_empresa_y_tercero(db_session):
    db_session.add(_efecto(empresa_id=1))
    await db_session.flush()
    db_session.add(_efecto(empresa_id=1))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_efecto_documento_duplicado_distinto_tercero(db_session):
    db_session.add(_efecto(empresa_id=1))
    await db_session.flush()
    db_session.add(_efecto(empresa_id=1, tercero_id=TERCERO_B))
    await db_session.flush()


async def test_efecto_documento_duplicado_distinta_empresa(db_session):
    db_session.add(_efecto(empresa_id=1))
    await db_session.flush()
    db_session.add(_efecto(empresa_id=2))
    await db_session.flush()


async def test_efecto_mismo_documento_distinto_tipo_permitido(db_session):
    db_session.add(_efecto(empresa_id=1))
    await db_session.flush()
    db_session.add(_efecto(empresa_id=1, tipo=TipoEfecto.PAGARE))
    await db_session.flush()


async def test_efecto_fechas_invalidas_rechazadas(db_session):
    db_session.add(
        _efecto(empresa_id=1, emision=date(2026, 7, 1), vencimiento=date(2026, 5, 1))
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_efecto_importe_no_positivo_rechazado(db_session):
    db_session.add(_efecto(empresa_id=1, importe=Decimal("0.0000")))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


def _cobro_medio(**kw) -> CobroMedio:
    base = {
        "empresa_id": 1,
        "vencimiento_id": VENCIMIENTO,
        "medio_cobro": MedioCobro.TRANSFERENCIA,
        "fecha_cobro": date(2026, 7, 1),
        "importe_total": Decimal("1000.0000"),
        "importe_comision": Decimal("15.0000"),
        "importe_neto": Decimal("985.0000"),
        "cuenta_banco": "572",
    }
    base.update(kw)
    return CobroMedio(**base)


async def test_cobro_medio_ok(db_session):
    db_session.add(_cobro_medio())
    await db_session.flush()


async def test_cobro_medio_comision_mayor_que_total_rechazada(db_session):
    db_session.add(
        _cobro_medio(
            importe_comision=Decimal("1200.0000"), importe_neto=Decimal("-200.0000")
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_cobro_medio_neto_negativo_rechazado(db_session):
    db_session.add(
        _cobro_medio(
            importe_comision=Decimal("800.0000"), importe_neto=Decimal("-5.0000")
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_comision_fk_compuesta_ok(db_session):
    cobro = _cobro_medio()
    db_session.add(cobro)
    await db_session.flush()
    db_session.add(
        ComisionBancaria(
            empresa_id=1,
            cobro_medio_id=cobro.id,
            banco_codigo="0001",
            tipo_comision="COMISION",
            importe=Decimal("15.0000"),
            porcentaje=Decimal("1.50"),
            cuenta_contable="626",
        )
    )
    await db_session.flush()


async def test_comision_fk_empresa_equivocada_rechazada(db_session):
    cobro = _cobro_medio()
    db_session.add(cobro)
    await db_session.flush()
    db_session.add(
        ComisionBancaria(
            empresa_id=2,
            cobro_medio_id=cobro.id,
            importe=Decimal("15.0000"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_comision_importe_negativo_rechazada(db_session):
    cobro = _cobro_medio()
    db_session.add(cobro)
    await db_session.flush()
    db_session.add(
        ComisionBancaria(empresa_id=1, cobro_medio_id=cobro.id, importe=Decimal("-1.0000"))
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


TABLAS_SPEC021 = ("efecto", "cobro_medio", "comision_bancaria")


def test_tablas_espec021_tienen_indice_por_empresa_id():
    for table_name in TABLAS_SPEC021:
        table = Base.metadata.tables[table_name]
        column_names = {col.name for col in table.columns}
        assert "empresa_id" in column_names, f"{table_name} sin empresa_id"
        assert any(
            index_columns and index_columns[0] == "empresa_id"
            for index_columns in (
                [c.name for c in idx.columns] for idx in table.indexes
            )
        ), f"{table_name} sin índice por empresa_id"


def test_efecto_unicos_incluyen_empresa_id():
    table = Base.metadata.tables["efecto"]
    unicos = {
        tuple(c.name for c in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("empresa_id", "id") in unicos
    assert ("empresa_id", "tercero_id", "tipo_efecto", "numero_documento") in unicos


def test_efecto_importe_numeric_18_4():
    column = Base.metadata.tables["efecto"].columns["importe"]
    assert str(column.type) in ("NUMERIC(18, 4)", "NUMERIC(18,4)")


def test_comision_fk_compuesta_incluye_empresa_id():
    comision = Base.metadata.tables["comision_bancaria"]
    fk = next(
        c for c in comision.foreign_key_constraints
        if "cobro_medio" in c.referred_table.name
    )
    assert [c.name for c in fk.columns] == ["empresa_id", "cobro_medio_id"]
    assert fk.elements[0].column.table is Base.metadata.tables["cobro_medio"]