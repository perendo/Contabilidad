from __future__ import annotations

from datetime import date
from decimal import Decimal

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.fiscal.retencion import TipoRetencion
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea


async def _crear_factura(session, api) -> None:
    asiento = JournalEntry(
        empresa_id=10,
        ejercicio=2025,
        fecha=date(2025, 7, 1),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Factura A",
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
        fecha=date(2025, 7, 1),
        tipo=FacturaTipo.COMPRA,
        tercero_id=tercero_id,
        importe_base=Decimal("1000.0000"),
        importe_irpf=Decimal("150.0000"),
        importe_total=Decimal("850.0000"),
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
            descripcion="Retencion A",
            cantidad=Decimal(1),
            precio_unitario=Decimal("1000.0000"),
            base=Decimal("1000.0000"),
            tipo_irpf=Decimal(15),
            base_irpf=Decimal("1000.0000"),
            cuota_irpf=Decimal("150.0000"),
            tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
        )
    )
    await session.flush()


def test_liquidacion_y_retenciones_estan_aisladas_por_empresa(retenciones_client) -> None:
    api = retenciones_client
    api.run(api.mutar(lambda session: _crear_factura(session, api)))
    created = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 3},
        headers=api.headers(10),
    )
    assert created.status_code == 201, created.text
    liquidacion_id = created.json()["id"]

    cross = api.client.get(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}",
        headers=api.headers(20),
    )
    assert cross.status_code == 404
    assert cross.json()["detail"]["code"] == "liquidacion_no_encontrada"

    listado_b = api.client.get(
        "/api/v1/fiscal/retenciones/liquidaciones",
        headers=api.headers(20),
    )
    assert listado_b.status_code == 200
    assert listado_b.json()["total"] == 0

    retenciones_b = api.client.get(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}/retenciones",
        headers=api.headers(20),
    )
    assert retenciones_b.status_code == 404
