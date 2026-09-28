from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.fiscal.retencion import TipoRetencion
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea


async def _crear_factura(
    session,
    api,
    *,
    numero: int,
    fecha: date,
    tercero: str,
    tipo_retencion: TipoRetencion,
    base: str,
    tasa: str,
    retencion: str,
    direccion_inmueble: str | None = None,
) -> Factura:
    asiento = JournalEntry(
        empresa_id=10,
        ejercicio=fecha.year,
        fecha=fecha,
        tipo=JournalEntryTipo.GENERAL,
        concepto="Factura quickstart IRPF",
        estado=JournalEntryEstado.DRAFT,
    )
    session.add(asiento)
    await session.flush()
    factura = Factura(
        empresa_id=10,
        serie_id=api.series[10],
        numero=numero,
        ejercicio=fecha.year,
        fecha=fecha,
        tipo=FacturaTipo.COMPRA,
        tercero_id=api.terceros[10][tercero],
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
            descripcion="Operación con retención",
            cantidad=Decimal("1.0000"),
            precio_unitario=Decimal(base),
            base=Decimal(base),
            tipo_irpf=Decimal(tasa),
            base_irpf=Decimal(base),
            cuota_irpf=Decimal(retencion),
            tipo_retencion=tipo_retencion,
            direccion_inmueble=direccion_inmueble,
        )
    )
    await session.flush()
    return factura


def test_scenario_1_acumula_retenciones_y_genera_modelo_111(
    retenciones_client,
) -> None:
    api = retenciones_client
    api.run(
        api.mutar(
            lambda session: _crear_factura(
                session,
                api,
                numero=1,
                fecha=date(2025, 8, 1),
                tercero="con_nif",
                tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
                base="1000.0000",
                tasa="15.00",
                retencion="150.0000",
            )
        )
    )

    liquidacion = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 3},
        headers=api.headers(10),
    )
    assert liquidacion.status_code == 201, liquidacion.text
    liquidacion_id = liquidacion.json()["id"]
    assert liquidacion.json()["total_retenciones"] == "150.0000"
    assert liquidacion.json()["estado"] == "pendiente"

    detalle = api.client.get(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}/retenciones",
        headers=api.headers(10),
    )
    assert detalle.status_code == 200
    assert detalle.json()[0]["nif"] == "12345678Z"

    modelo = api.client.post(
        "/api/v1/fiscal/retenciones/modelos-111",
        json={"liquidacion_id": liquidacion_id},
        headers=api.headers(10),
    )
    assert modelo.status_code == 201, modelo.text
    descarga = api.client.get(
        f"/api/v1/fiscal/retenciones/modelos-111/{modelo.json()['id']}",
        headers=api.headers(10),
    )
    assert descarga.status_code == 200
    assert descarga.content.startswith(b"\xef\xbb\xbf")


def test_scenario_2_liquida_con_asiento_4751_contra_572(retenciones_client) -> None:
    api = retenciones_client
    api.run(
        api.mutar(
            lambda session: _crear_factura(
                session,
                api,
                numero=1,
                fecha=date(2025, 8, 1),
                tercero="con_nif",
                tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
                base="1000.0000",
                tasa="15.00",
                retencion="150.0000",
            )
        )
    )
    liquidacion = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 3},
        headers=api.headers(10),
    )
    assert liquidacion.status_code == 201
    liquidacion_id = liquidacion.json()["id"]

    contabilizacion = api.client.post(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}/contabilizar",
        json={"fecha_asiento": "2025-09-30", "cuenta_banco": "5720"},
        headers=api.headers(10),
    )
    assert contabilizacion.status_code == 200, contabilizacion.text
    assert contabilizacion.json()["estado"] == "liquidado"
    assert contabilizacion.json()["total_retenciones"] == "150.0000"

    async def _asiento(session):
        asiento_id = uuid.UUID(contabilizacion.json()["asiento_id"])
        return await session.get(JournalEntry, asiento_id)

    asiento = api.run(api.consultar(_asiento))
    assert isinstance(asiento, JournalEntry)
    assert asiento.estado == JournalEntryEstado.POSTED

    async def _totales(session):
        lineas = (
            await session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.empresa_id == 10,
                    JournalEntryLine.journal_entry_id == asiento.id,
                )
            )
        ).all()
        return (
            sum((linea.debe for linea in lineas), Decimal("0.0000")),
            sum((linea.haber for linea in lineas), Decimal("0.0000")),
        )

    debe, haber = api.run(api.consultar(_totales))
    assert debe == haber == Decimal("150.0000")


def test_scenario_3_modelo_115_filtra_arrendamientos_y_rechaza_sin_datos(
    retenciones_client,
) -> None:
    api = retenciones_client

    async def _crear(session):
        await _crear_factura(
            session,
            api,
            numero=1,
            fecha=date(2025, 2, 1),
            tercero="con_nif",
            tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
            base="1000.0000",
            tasa="15.00",
            retencion="150.0000",
        )
        await _crear_factura(
            session,
            api,
            numero=2,
            fecha=date(2025, 5, 1),
            tercero="con_nif",
            tipo_retencion=TipoRetencion.IRPF_ARRENDAMIENTOS,
            base="2000.0000",
            tasa="19.00",
            retencion="380.0000",
            direccion_inmueble="Calle Mayor 1",
        )

    api.run(api.mutar(_crear))
    q1 = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 1},
        headers=api.headers(10),
    )
    q2 = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 2},
        headers=api.headers(10),
    )
    assert q1.status_code == 201
    assert q2.status_code == 201

    sin_arrendamiento = api.client.post(
        "/api/v1/fiscal/retenciones/modelos-115",
        json={"liquidacion_id": q1.json()["id"]},
        headers=api.headers(10),
    )
    assert sin_arrendamiento.status_code == 409
    assert sin_arrendamiento.json()["detail"]["code"] == "sin_retenciones_arrendamiento"

    modelo = api.client.post(
        "/api/v1/fiscal/retenciones/modelos-115",
        json={"liquidacion_id": q2.json()["id"]},
        headers=api.headers(10),
    )
    assert modelo.status_code == 201, modelo.text
    assert len(modelo.json()["hash_contenido"]) == 64


def test_scenario_4_genera_modelo_190_anual(retenciones_client) -> None:
    api = retenciones_client
    api.run(
        api.mutar(
            lambda session: _crear_factura(
                session,
                api,
                numero=1,
                fecha=date(2025, 2, 1),
                tercero="con_nif",
                tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
                base="1000.0000",
                tasa="15.00",
                retencion="150.0000",
            )
        )
    )
    liquidacion = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 1},
        headers=api.headers(10),
    )
    assert liquidacion.status_code == 201

    validacion = api.client.get(
        "/api/v1/fiscal/retenciones/modelo-190/validar",
        params={"ejercicio": 2025},
        headers=api.headers(10),
    )
    assert validacion.status_code == 200
    assert validacion.json() == {"valido": True, "perceptores_sin_nif": []}

    modelo = api.client.post(
        "/api/v1/fiscal/retenciones/modelo-190",
        json={"ejercicio": 2025},
        headers=api.headers(10),
    )
    assert modelo.status_code == 201, modelo.text
    assert modelo.json()["n_perceptores"] == 1

    descarga = api.client.get(
        f"/api/v1/fiscal/retenciones/modelo-190/{modelo.json()['id']}",
        headers=api.headers(10),
    )
    assert descarga.status_code == 200
    assert descarga.content.startswith(b"\xef\xbb\xbf")


def test_scenario_5_rechaza_modelo_190_sin_nif(retenciones_client) -> None:
    api = retenciones_client
    api.run(
        api.mutar(
            lambda session: _crear_factura(
                session,
                api,
                numero=1,
                fecha=date(2025, 2, 1),
                tercero="sin_nif",
                tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
                base="1000.0000",
                tasa="15.00",
                retencion="150.0000",
            )
        )
    )
    liquidacion = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 1},
        headers=api.headers(10),
    )
    assert liquidacion.status_code == 201

    validacion = api.client.get(
        "/api/v1/fiscal/retenciones/modelo-190/validar",
        params={"ejercicio": 2025},
        headers=api.headers(10),
    )
    assert validacion.status_code == 200
    assert validacion.json()["valido"] is False

    modelo = api.client.post(
        "/api/v1/fiscal/retenciones/modelo-190",
        json={"ejercicio": 2025},
        headers=api.headers(10),
    )
    assert modelo.status_code == 422
    assert modelo.json()["detail"]["code"] == "perceptores_sin_nif"
    assert modelo.json()["detail"]["perceptores_sin_nif"]


def test_scenario_6_empresa_b_no_ve_liquidacion_de_empresa_a(
    retenciones_client,
) -> None:
    api = retenciones_client
    api.run(
        api.mutar(
            lambda session: _crear_factura(
                session,
                api,
                numero=1,
                fecha=date(2025, 2, 1),
                tercero="con_nif",
                tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
                base="1000.0000",
                tasa="15.00",
                retencion="150.0000",
            )
        )
    )
    liquidacion = api.client.post(
        "/api/v1/fiscal/retenciones/liquidaciones",
        json={"ejercicio": 2025, "trimestre": 1},
        headers=api.headers(10),
    )
    assert liquidacion.status_code == 201
    liquidacion_id = liquidacion.json()["id"]

    cross = api.client.get(
        f"/api/v1/fiscal/retenciones/liquidaciones/{liquidacion_id}",
        headers=api.headers(20),
    )
    assert cross.status_code == 404
    assert cross.json()["detail"]["code"] == "liquidacion_no_encontrada"

    listado = api.client.get(
        "/api/v1/fiscal/retenciones/liquidaciones",
        headers=api.headers(20),
    )
    assert listado.status_code == 200
    assert listado.json()["total"] == 0
