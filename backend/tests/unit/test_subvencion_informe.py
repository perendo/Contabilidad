"""Informe de justificación y exportación CSV/JSON (SPEC-019 US1).

El informe suma el gasto imputado, calcula el pendiente y devuelve el detalle
ordenado por imputaciones; la huella del informe deriva del contenido canónico
de las líneas imputadas.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from services.ngo.justificacion import (
    exportar_informe,
    imputar_gasto,
    informe_justificacion,
)


def _linea_debe(ns, empresa_id, entrada):
    from sqlalchemy import select

    from models.acct.journal import JournalEntryLine

    async def _op(session):
        filas = (
            await session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.empresa_id == empresa_id,
                    JournalEntryLine.journal_entry_id == entrada.id,
                )
            )
        ).all()
        return str(next(l for l in filas if l.debe > 0).id)

    return ns.run(ns.consultar(_op))


def _gasto(ns, importe="400.0000", concepto="Gasto"):
    return ns.asiento(
        10,
        [
            {"cuenta": "6400", "debe": Decimal(importe), "haber": Decimal(0), "detalle": "sueldos"},
            {"cuenta": "5720", "debe": Decimal(0), "haber": Decimal(importe), "detalle": "banco"},
        ],
        date(2026, 5, 10),
        concepto,
    )


def test_informe_acumula_y_detalla(ngo_client):
    ns = ngo_client
    sub = ns.crear_subvencion(10, importe="1000.0000", referencia="INF")
    sid = uuid.UUID(sub["id"])
    gastos = []
    for importe, concepto in (("400.0000", "Gasto 1"), ("350.0000", "Gasto 2")):
        entrada = _gasto(ns, importe, concepto)
        linea = uuid.UUID(_linea_debe(ns, 10, entrada))
        gastos.append(
            ns.run(
                ns.mutar(
                    lambda s, e=entrada, l=linea, i=importe: imputar_gasto(
                        s,
                        empresa_id=10,
                        subvencion_id=sid,
                        asiento_id=e.id,
                        linea_id=l,
                        importe_asignado=Decimal(i),
                    )
                )
            )
        )

    informe = ns.run(ns.consultar(lambda s: informe_justificacion(s, empresa_id=10, subvencion_id=sid)))
    assert informe is not None
    assert informe["importe_concedido"] == "1000.0000"
    assert informe["gastado"] == "750.0000"
    assert informe["pendiente"] == "250.0000"
    assert len(informe["detalle"]) == 2
    assert len(informe["huella"]) == 64

    csv = ns.run(
        ns.mutar(
            lambda s: exportar_informe(
                s, empresa_id=10, subvencion_id=sid, formato="csv"
            )
        )
    )
    assert csv[0].startswith(b"\xef\xbb\xbfentidad;programa;referencia;")
    assert "text/csv" in csv[1]
    assert csv[2] == f"justificacion_{sid}.csv"

    js = ns.run(
        ns.mutar(
            lambda s: exportar_informe(
                s, empresa_id=10, subvencion_id=sid, formato="json"
            )
        )
    )
    assert js[0].startswith(b"{")
    assert "json" in js[1]