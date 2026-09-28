"""Early-payment discount calculation tests (T031).

FR-005: dentro del plazo aplica el %, neto >= 0; fuera del plazo no aplica;
edge neto=0; precisión de 4 decimales; override por factura.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from services.discount import (
    DescuentoInvalidoError,
    aplicar_pronto_pago,
    calcular_descuento,
    en_plazo,
)
from services.tercero_amend import crear_condicion


def _vencimiento(
    *,
    tercero_id: uuid.UUID,
    factura_id: uuid.UUID | None = None,
    fecha_factura: date | None = None,
    importe: str = "100.0000",
) -> Vencimiento:
    return Vencimiento(
        empresa_id=12,
        tercero_id=tercero_id,
        factura_id=factura_id,
        fecha_factura=fecha_factura,
        recibo_num="R-PP",
        iban="ES9121000418450200051332",
        ejercicio=2026,
        fecha_vencimiento=date(2026, 12, 31),
        importe=Decimal(importe),
        estado=EstadoVencimiento.pendiente,
    )


def test_neto_precision_4_decimales():
    resultado = calcular_descuento(Decimal("100.1234"), Decimal("2.00"))
    assert resultado.neto == Decimal("98.1209")
    assert resultado.descuento == Decimal("2.0025")
    assert resultado.neto + resultado.descuento == Decimal("100.1234")
    assert resultado.neto.as_tuple().exponent == -4


def test_neto_nunca_negativo_edge_cero():
    resultado = calcular_descuento(Decimal("50.0000"), Decimal("100.00"))
    assert resultado.neto == Decimal("0.0000")
    assert resultado.descuento == Decimal("50.0000")
    assert resultado.neto >= Decimal(0)


def test_porcentaje_sobre_100_rechazado():
    with pytest.raises(DescuentoInvalidoError):
        calcular_descuento(Decimal("100.0000"), Decimal("250.00"))


async def test_dentro_de_plazo_aplica_y_fuera_no(db_session):
    tercero = uuid.uuid4()
    condicion = await crear_condicion(
        db_session, 12, tercero, plazo_dias=10, porcentaje=Decimal("2.00")
    )
    fecha_factura = date(2026, 10, 1)
    vencimiento = _vencimiento(tercero_id=tercero, fecha_factura=fecha_factura)

    dentro = await aplicar_pronto_pago(
        db_session, 12, vencimiento, fecha_factura + timedelta(days=5)
    )
    assert dentro is not None
    cond, resultado = dentro
    assert cond.id == condicion.id
    assert resultado.neto == Decimal("98.0000")
    assert resultado.descuento == Decimal("2.0000")

    justo_en_limite = await aplicar_pronto_pago(
        db_session, 12, vencimiento, fecha_factura + timedelta(days=10)
    )
    assert justo_en_limite is not None

    fuera = await aplicar_pronto_pago(
        db_session, 12, vencimiento, fecha_factura + timedelta(days=11)
    )
    assert fuera is None


async def test_sin_condicion_vigente_no_aplica(db_session):
    vencimiento = _vencimiento(tercero_id=uuid.uuid4())
    assert await aplicar_pronto_pago(db_session, 12, vencimiento, date(2026, 10, 5)) is None


async def test_override_por_factura(db_session):
    tercero = uuid.uuid4()
    factura = uuid.uuid4()
    general = await crear_condicion(
        db_session, 12, tercero, plazo_dias=10, porcentaje=Decimal("1.00")
    )

    con_factura = _vencimiento(tercero_id=tercero, factura_id=None, fecha_factura=date(2026, 10, 1))
    generico = await aplicar_pronto_pago(db_session, 12, con_factura, date(2026, 10, 5))
    assert generico is not None
    assert generico[0].id == general.id
    assert generico[1].neto == Decimal("99.0000")

    condicion_factura = await crear_condicion(
        db_session,
        12,
        tercero,
        plazo_dias=30,
        porcentaje=Decimal("5.00"),
        override_factura_id=factura,
    )
    assert condicion_factura.id != general.id

    vencimiento_factura = _vencimiento(
        tercero_id=tercero, factura_id=factura, fecha_factura=date(2026, 10, 1)
    )
    aplicado = await aplicar_pronto_pago(db_session, 12, vencimiento_factura, date(2026, 10, 20))
    assert aplicado is not None
    assert aplicado[0].id == condicion_factura.id
    assert aplicado[1].neto == Decimal("95.0000")

    sin_la_factura = _vencimiento(
        tercero_id=tercero, factura_id=None, fecha_factura=date(2026, 10, 1)
    )
    no_aplica = await aplicar_pronto_pago(db_session, 12, sin_la_factura, date(2026, 10, 20))
    assert no_aplica is None


async def test_fecha_referencia_falla_a_fecha_vencimiento(db_session):
    tercero = uuid.uuid4()
    condicion = await crear_condicion(
        db_session, 12, tercero, plazo_dias=7, porcentaje=Decimal("2.00")
    )
    vencimiento = _vencimiento(
        tercero_id=tercero,
        fecha_factura=None,
    )
    assert en_plazo(condicion, vencimiento, vencimiento.fecha_vencimiento)
    assert not en_plazo(
        condicion, vencimiento, vencimiento.fecha_vencimiento + timedelta(days=8)
    )