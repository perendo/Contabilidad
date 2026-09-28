from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from services.fiscal.retenciones import acumular_retenciones


async def _factura(
    session,
    api,
    *,
    empresa_id: int,
    fecha: date,
    numero: int,
    tercero_id,
    base: str,
    tasa: str,
    cuota: str,
    categoria: TipoRetencion | None,
    tipo: FacturaTipo = FacturaTipo.COMPRA,
    estado: FacturaEstado = FacturaEstado.emitida,
    factura_original_id=None,
) -> Factura:
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=fecha.year,
        fecha=fecha,
        tipo=JournalEntryTipo.GENERAL,
        concepto="Factura retencion",
        estado=JournalEntryEstado.DRAFT,
    )
    session.add(asiento)
    await session.flush()
    factura = Factura(
        empresa_id=empresa_id,
        serie_id=api.series[empresa_id],
        numero=numero,
        ejercicio=fecha.year,
        fecha=fecha,
        tipo=tipo,
        tercero_id=tercero_id,
        factura_original_id=factura_original_id,
        importe_base=Decimal(base),
        importe_irpf=Decimal(cuota),
        importe_total=Decimal(base),
        estado=estado,
        asiento_id=asiento.id,
    )
    session.add(factura)
    await session.flush()
    session.add(
        FacturaLinea(
            empresa_id=empresa_id,
            factura_id=factura.id,
            line_no=1,
            descripcion="Retencion",
            cantidad=Decimal(1),
            precio_unitario=Decimal(base),
            base=Decimal(base),
            tipo_irpf=Decimal(tasa),
            base_irpf=Decimal(base),
            cuota_irpf=Decimal(cuota),
            tipo_retencion=categoria,
        )
    )
    await session.flush()
    return factura


def test_acumula_facturas_q3_por_tercero_y_categoria(retenciones_client) -> None:
    api = retenciones_client

    async def _crear(session) -> None:
        await _factura(
            session,
            api,
            empresa_id=10,
            fecha=date(2025, 8, 1),
            numero=1,
            tercero_id=api.terceros[10]["con_nif"],
            base="1000.0000",
            tasa="15",
            cuota="150.0000",
            categoria=TipoRetencion.IRPF_PROFESIONALES,
        )
        await _factura(
            session,
            api,
            empresa_id=10,
            fecha=date(2025, 9, 30),
            numero=2,
            tercero_id=api.terceros[10]["sin_nif"],
            base="2000.0000",
            tasa="19",
            cuota="380.0000",
            categoria=TipoRetencion.IRPF_ARRENDAMIENTOS,
        )

    api.run(api.mutar(_crear))
    liquidacion = api.run(
        api.mutar(
            lambda session: acumular_retenciones(
                session, empresa_id=10, ejercicio=2025, trimestre=3
            )
        )
    )
    assert liquidacion.total_base_retenciones == Decimal("3000.0000")
    assert liquidacion.total_retenciones == Decimal("530.0000")
    assert liquidacion.n_perceptores == 2

    async def _detalles(session):
        return (
            await session.scalars(
                select(RetencionPeriodo).where(
                    RetencionPeriodo.liquidacion_retenciones_id == liquidacion.id
                )
            )
        ).all()

    detalles = api.run(api.consultar(_detalles))
    assert len(detalles) == 2
    assert {d.tipo_retencion for d in detalles} == {
        TipoRetencion.IRPF_PROFESIONALES,
        TipoRetencion.IRPF_ARRENDAMIENTOS,
    }
    assert all(len(d.facturas) == 1 for d in detalles)


def test_legacy_sin_categoria_clasifica_por_tasa(retenciones_client) -> None:
    api = retenciones_client

    async def _crear(session) -> None:
        await _factura(
            session,
            api,
            empresa_id=10,
            fecha=date(2025, 8, 15),
            numero=1,
            tercero_id=api.terceros[10]["con_nif"],
            base="1000.0000",
            tasa="19",
            cuota="190.0000",
            categoria=None,
        )

    api.run(api.mutar(_crear))
    liquidacion = api.run(
        api.mutar(
            lambda session: acumular_retenciones(
                session, empresa_id=10, ejercicio=2025, trimestre=3
            )
        )
    )
    async def _detalles(session):
        return (
            await session.scalars(
                select(RetencionPeriodo).where(
                    RetencionPeriodo.liquidacion_retenciones_id == liquidacion.id
                )
            )
        ).all()

    detalles = api.run(api.consultar(_detalles))
    assert len(detalles) == 1
    assert detalles[0].tipo_retencion == TipoRetencion.IRPF_ARRENDAMIENTOS
    assert liquidacion.total_retenciones == Decimal("190.0000")


def test_rectificativa_cancela_el_grupo_y_la_anulada_se_incluye(retenciones_client) -> None:
    api = retenciones_client

    async def _crear(session) -> None:
        original = await _factura(
            session,
            api,
            empresa_id=10,
            fecha=date(2025, 8, 1),
            numero=1,
            tercero_id=api.terceros[10]["con_nif"],
            base="1000.0000",
            tasa="15",
            cuota="150.0000",
            categoria=TipoRetencion.IRPF_PROFESIONALES,
        )
        original.estado = FacturaEstado.anulada
        await session.flush()
        await _factura(
            session,
            api,
            empresa_id=10,
            fecha=date(2025, 8, 15),
            numero=2,
            tercero_id=api.terceros[10]["con_nif"],
            base="1000.0000",
            tasa="15",
            cuota="150.0000",
            categoria=TipoRetencion.IRPF_PROFESIONALES,
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
    assert liquidacion.total_base_retenciones == Decimal("0.0000")
    assert liquidacion.total_retenciones == Decimal("0.0000")

    async def _detalles(session):
        return (
            await session.scalars(
                select(RetencionPeriodo).where(
                    RetencionPeriodo.liquidacion_retenciones_id == liquidacion.id
                )
            )
        ).all()

    assert api.run(api.consultar(_detalles)) == []
