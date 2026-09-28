from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from services.fiscal.retenciones import acumular_retenciones


async def _crear_factura(
    session,
    api,
    *,
    numero: int,
    base: str,
    retencion: str,
    tipo: FacturaTipo,
    factura_original_id=None,
) -> Factura:
    asiento = JournalEntry(
        empresa_id=10,
        ejercicio=2025,
        fecha=date(2025, 8, numero),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Factura IRPF",
        estado=JournalEntryEstado.DRAFT,
    )
    session.add(asiento)
    await session.flush()
    factura = Factura(
        empresa_id=10,
        serie_id=api.series[10],
        numero=numero,
        ejercicio=2025,
        fecha=date(2025, 8, numero),
        tipo=tipo,
        tercero_id=api.terceros[10]["con_nif"],
        factura_original_id=factura_original_id,
        importe_base=Decimal(base),
        importe_irpf=Decimal(retencion),
        importe_total=Decimal(base),
        estado=FacturaEstado.emitida,
        asiento_id=asiento.id,
    )
    session.add(factura)
    await session.flush()
    session.add(
        FacturaLinea(
            empresa_id=10,
            factura_id=factura.id,
            line_no=1,
            descripcion="Retención IRPF",
            cantidad=Decimal("1.0000"),
            precio_unitario=Decimal(base),
            base=Decimal(base),
            tipo_irpf=Decimal("15.00"),
            base_irpf=Decimal(base),
            cuota_irpf=Decimal(retencion),
            tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
        )
    )
    await session.flush()
    return factura


def test_rectificativa_irpf_se_resta_y_no_duplica_la_acumulacion(
    retenciones_client,
) -> None:
    api = retenciones_client

    async def _crear(session) -> None:
        original = await _crear_factura(
            session,
            api,
            numero=1,
            base="1000.0000",
            retencion="150.0000",
            tipo=FacturaTipo.COMPRA,
        )
        await _crear_factura(
            session,
            api,
            numero=2,
            base="400.0000",
            retencion="60.0000",
            tipo=FacturaTipo.RECTIFICATIVA,
            factura_original_id=original.id,
        )

    api.run(api.mutar(_crear))
    liquidacion = api.run(
        api.mutar(
            lambda session: acumular_retenciones(
                session, empresa_id=10, ejercicio=2025, trimestre=3
            )
        )
    )

    assert liquidacion.total_base_retenciones == Decimal("600.0000")
    assert liquidacion.total_retenciones == Decimal("90.0000")
    assert liquidacion.n_perceptores == 1

    async def _detalle(session):
        return (
            await session.scalars(
                select(RetencionPeriodo).where(
                    RetencionPeriodo.empresa_id == 10,
                    RetencionPeriodo.liquidacion_retenciones_id == liquidacion.id,
                )
            )
        ).all()

    detalle = api.run(api.consultar(_detalle))
    assert len(detalle) == 1
    assert len(detalle[0].facturas) == 2
    assert {factura["signo"] for factura in detalle[0].facturas} == {1, -1}
    assert len({factura["factura_id"] for factura in detalle[0].facturas}) == 2
