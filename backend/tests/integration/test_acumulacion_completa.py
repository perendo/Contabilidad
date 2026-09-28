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
        fecha=date(2025, 9, 10),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Factura Q3",
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
        fecha=date(2025, 9, 10),
        tipo=FacturaTipo.COMPRA,
        tercero_id=tercero_id,
        importe_base=Decimal("3000.0000"),
        importe_irpf=Decimal("530.0000"),
        importe_total=Decimal("2470.0000"),
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
                direccion_inmueble="Avenida Central 2",
            ),
        ]
    )
    await session.flush()


def test_flujo_acumula_y_genera_modelos_111_y_115(retenciones_client) -> None:
    api = retenciones_client
    api.run(api.mutar(lambda session: _crear_factura(session, api)))
    created = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 3},
        headers=api.headers(),
    )
    assert created.status_code == 201, created.text
    liquidacion = created.json()
    assert liquidacion["total_retenciones"] == "530.0000"
    assert liquidacion["n_perceptores"] == 1

    detalle = api.client.get(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion['id']}",
        headers=api.headers(),
    )
    assert detalle.status_code == 200
    assert len(detalle.json()["retenciones"]) == 2

    modelo_111 = api.client.post(
        "/api/v1/fiscal/retenciones/modelos-111",
        json={"liquidacion_id": liquidacion["id"]},
        headers=api.headers(),
    )
    assert modelo_111.status_code == 201, modelo_111.text
    assert len(modelo_111.json()["hash_contenido"]) == 64

    modelo_115 = api.client.post(
        "/api/v1/fiscal/retenciones/modelos-115",
        json={"liquidacion_id": liquidacion["id"]},
        headers=api.headers(),
    )
    assert modelo_115.status_code == 201, modelo_115.text

    download_111 = api.client.get(
        f"/api/v1/fiscal/retenciones/modelos-111/{modelo_111.json()['id']}",
        headers=api.headers(),
    )
    download_115 = api.client.get(
        f"/api/v1/fiscal/retenciones/modelos-115/{modelo_115.json()['id']}",
        headers=api.headers(),
    )
    assert download_111.status_code == 200
    assert download_115.status_code == 200
    assert download_111.content.startswith(b"\xef\xbb\xbf")
    assert download_115.content.startswith(b"\xef\xbb\xbf")
