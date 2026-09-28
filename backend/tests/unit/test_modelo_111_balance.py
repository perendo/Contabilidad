from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from models.fiscal.modelo_111 import Modelo111
from models.fiscal.retencion import TipoRetencion
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from services.fiscal.modelo_111_gen import generar_modelo_111, json_canonico
from services.fiscal.retenciones import acumular_retenciones


async def _crear_factura(session, api) -> None:
    asiento = JournalEntry(
        empresa_id=10,
        ejercicio=2025,
        fecha=date(2025, 7, 15),
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
        fecha=date(2025, 7, 15),
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
            descripcion="Profesional",
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


def test_modelo_111_tiene_cuatro_bloques_y_hash(retenciones_client) -> None:
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
            lambda session: generar_modelo_111(
                session, empresa_id=10, liquidacion_id=liquidacion.id
            )
        )
    )

    async def _consultar(session):
        return await session.scalar(
            select(Modelo111).where(Modelo111.id == modelo.id)
        )

    guardada = api.run(api.consultar(_consultar))
    assert guardada is not None
    assert set(guardada.contenido) == {
        "datos_declarante",
        "datos_periodo",
        "detalle_perceptores",
        "totales",
    }
    assert guardada.contenido["datos_declarante"]["nif"] == "A00000010"
    assert guardada.contenido["datos_declarante"]["razon_social"] == "Retenciones Diez SL"
    assert guardada.contenido["totales"]["total_retenciones"] == "150.0000"
    assert guardada.contenido["totales"]["resultado"] == "150.0000"
    canonico = json_canonico(guardada.contenido)
    assert hashlib.sha256(canonico.encode("utf-8")).hexdigest() == guardada.hash_contenido

    async def _parent(session):
        parent = await session.get(LiquidacionRetenciones, liquidacion.id)
        assert parent is not None
        return parent.modelo_111_id

    assert api.run(api.consultar(_parent)) == modelo.id
