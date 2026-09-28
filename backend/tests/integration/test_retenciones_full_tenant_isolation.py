from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from services.fiscal.retenciones import listar_retenciones_periodo


async def _crear_facturas(session, api) -> None:
    asiento = JournalEntry(
        empresa_id=10,
        ejercicio=2025,
        fecha=date(2025, 8, 1),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Facturas con IRPF",
        estado=JournalEntryEstado.DRAFT,
    )
    session.add(asiento)
    await session.flush()
    factura = Factura(
        empresa_id=10,
        serie_id=api.series[10],
        numero=1,
        ejercicio=2025,
        fecha=date(2025, 8, 1),
        tipo=FacturaTipo.COMPRA,
        tercero_id=api.terceros[10]["con_nif"],
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
                cantidad=Decimal("1.0000"),
                precio_unitario=Decimal("1000.0000"),
                base=Decimal("1000.0000"),
                tipo_irpf=Decimal("15.00"),
                base_irpf=Decimal("1000.0000"),
                cuota_irpf=Decimal("150.0000"),
                tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
            ),
            FacturaLinea(
                empresa_id=10,
                factura_id=factura.id,
                line_no=2,
                descripcion="Arrendamiento",
                cantidad=Decimal("1.0000"),
                precio_unitario=Decimal("2000.0000"),
                base=Decimal("2000.0000"),
                tipo_irpf=Decimal("19.00"),
                base_irpf=Decimal("2000.0000"),
                cuota_irpf=Decimal("380.0000"),
                tipo_retencion=TipoRetencion.IRPF_ARRENDAMIENTOS,
                direccion_inmueble="Calle Mayor 1",
            ),
        ]
    )
    await session.flush()


def test_flujo_completo_y_cross_tenant_no_duplicate_la_liquidacion(
    retenciones_client,
) -> None:
    api = retenciones_client
    api.run(api.mutar(lambda session: _crear_facturas(session, api)))

    liquidacion_response = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 3},
        headers=api.headers(10),
    )
    assert liquidacion_response.status_code == 201, liquidacion_response.text
    liquidacion = liquidacion_response.json()
    liquidacion_id = liquidacion["id"]

    retenciones_response = api.client.get(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}/retenciones",
        headers=api.headers(10),
    )
    assert retenciones_response.status_code == 200
    assert len(retenciones_response.json()) == 2

    modelo_111_response = api.client.post(
        "/api/v1/fiscal/retenciones/modelos-111",
        json={"liquidacion_id": liquidacion_id},
        headers=api.headers(10),
    )
    modelo_115_response = api.client.post(
        "/api/v1/fiscal/retenciones/modelos-115",
        json={"liquidacion_id": liquidacion_id},
        headers=api.headers(10),
    )
    modelo_190_response = api.client.post(
        "/api/v1/fiscal/retenciones/modelo-190",
        json={"ejercicio": 2025},
        headers=api.headers(10),
    )
    assert modelo_111_response.status_code == 201, modelo_111_response.text
    assert modelo_115_response.status_code == 201, modelo_115_response.text
    assert modelo_190_response.status_code == 201, modelo_190_response.text

    contabilizacion = api.client.post(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}/contabilizar",
        json={"fecha_asiento": "2025-09-30", "cuenta_banco": "5720"},
        headers=api.headers(10),
    )
    assert contabilizacion.status_code == 200, contabilizacion.text
    asiento_id = contabilizacion.json()["asiento_id"]

    segunda = api.client.post(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}/contabilizar",
        json={"fecha_asiento": "2025-10-01", "cuenta_banco": "5720"},
        headers=api.headers(10),
    )
    assert segunda.status_code == 409
    assert segunda.json()["detail"]["code"] == "liquidacion_ya_contabilizada"

    cross_contabilizacion = api.client.post(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}/contabilizar",
        json={"fecha_asiento": "2025-10-01", "cuenta_banco": "5720"},
        headers=api.headers(20),
    )
    assert cross_contabilizacion.status_code == 404

    for ruta in (
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}",
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}/retenciones",
    ):
        response = api.client.get(ruta, headers=api.headers(20))
        assert response.status_code == 404

    for ruta, modelo_id in (
        ("modelos-111", modelo_111_response.json()["id"]),
        ("modelos-115", modelo_115_response.json()["id"]),
        ("modelo-190", modelo_190_response.json()["id"]),
    ):
        response = api.client.get(
            f"/api/v1/fiscal/retenciones/{ruta}/{modelo_id}",
            headers=api.headers(20),
        )
        assert response.status_code == 404

    for ruta in (
        "/api/v1/fiscal/retenciones/liquidaciones",
        "/api/v1/fiscal/retenciones/modelos-111",
        "/api/v1/fiscal/retenciones/modelos-115",
        "/api/v1/fiscal/retenciones/modelo-190",
    ):
        response = api.client.get(ruta, headers=api.headers(20))
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 0

    async def _retenciones_b(session):
        return await listar_retenciones_periodo(
            session,
            empresa_id=20,
            liquidacion_id=uuid.UUID(liquidacion_id),
        )

    assert api.run(api.consultar(_retenciones_b)) == []

    async def _listar_retenciones_b(session):
        return list(
            (
                await session.scalars(
                    select(RetencionPeriodo).where(RetencionPeriodo.empresa_id == 20)
                )
            ).all()
        )

    assert api.run(api.consultar(_listar_retenciones_b)) == []

    async def _asientos_a(session):
        return len(
            (
                await session.scalars(
                    select(JournalEntry).where(
                        JournalEntry.empresa_id == 10,
                        JournalEntry.id == uuid.UUID(asiento_id),
                    )
                )
            ).all()
        )

    assert api.run(api.consultar(_asientos_a)) == 1
