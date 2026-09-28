from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.fiscal.modelo_115 import Modelo115
from models.fiscal.retencion import TipoRetencion
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from services.fiscal.modelo_115_gen import generar_modelo_115
from services.fiscal.retenciones import acumular_retenciones


async def _crear_factura(session, api) -> None:
    asiento = JournalEntry(
        empresa_id=10,
        ejercicio=2025,
        fecha=date(2025, 8, 1),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Factura",
        estado=JournalEntryEstado.DRAFT,
    )
    session.add(asiento)
    await session.flush()
    tercero_id = api.terceros[10]["con_nif"]
    factura = Factura(
        empresa_id=10,
        serie_id=api.series[10],
        numero=1,
        ejercicio=2025,
        fecha=date(2025, 8, 1),
        tipo=FacturaTipo.COMPRA,
        tercero_id=tercero_id,
        importe_base=Decimal("3000.0000"),
        importe_irpf=Decimal("720.0000"),
        importe_total=Decimal("2280.0000"),
        estado=FacturaEstado.emitida,
        asiento_id=asiento.id,
    )
    session.add(factura)
    await session.flush()
    session.add_all(
        [
            FacturaLinea(
                empresa_id=10,
                factura_id=factura.id,
                line_no=1,
                descripcion="Profesional",
                cantidad=Decimal(1),
                precio_unitario=Decimal("1000.0000"),
                base=Decimal("1000.0000"),
                tipo_irpf=Decimal(15),
                base_irpf=Decimal("1000.0000"),
                cuota_irpf=Decimal("150.0000"),
                tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
            ),
            FacturaLinea(
                empresa_id=10,
                factura_id=factura.id,
                line_no=2,
                descripcion="Alquiler",
                cantidad=Decimal(1),
                precio_unitario=Decimal("2000.0000"),
                base=Decimal("2000.0000"),
                tipo_irpf=Decimal(19),
                base_irpf=Decimal("2000.0000"),
                cuota_irpf=Decimal("380.0000"),
                tipo_retencion=TipoRetencion.IRPF_ARRENDAMIENTOS,
                direccion_inmueble="Calle Mayor 1",
            ),
        ]
    )
    await session.flush()


def test_modelo_115_filtra_solo_arrendamientos(retenciones_client) -> None:
    api = retenciones_client
    api.run(api.mutar(lambda session: _crear_factura(session, api)))
    liquidacion = api.run(
        api.mutar(
            lambda session: acumular_retenciones(
                session, empresa_id=10, ejercicio=2025, trimestre=3
            )
        )
    )
    modelo = api.run(
        api.mutar(
            lambda session: generar_modelo_115(
                session, empresa_id=10, liquidacion_id=liquidacion.id
            )
        )
    )

    async def _consultar(session):
        return await session.scalar(
            select(Modelo115).where(Modelo115.id == modelo.id)
        )

    guardada = api.run(api.consultar(_consultar))
    assert guardada is not None
    assert set(guardada.contenido) == {
        "datos_declarante",
        "datos_periodo",
        "detalle_arrendadores",
        "totales",
    }
    assert len(guardada.contenido["detalle_arrendadores"]) == 1
    assert guardada.contenido["detalle_arrendadores"][0]["direccion_inmueble"] == "Calle Mayor 1"
    assert guardada.contenido["datos_periodo"]["total_retenciones"] == "380.0000"
    assert guardada.contenido["totales"]["total_retenciones"] == "380.0000"
