"""Imputación única por línea del diario (SPEC-019 US1).

Una línea POSTED se imputa a una única subvención de forma íntegra (duplicado
total bloqueado); la desimputación libera la línea y restaura el disponible.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from services.ngo.errores import NgoError
from services.ngo.justificacion import desimputar_gasto, imputar_gasto


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


def _gasto(ns, empresa_id=10, importe="1000.0000"):
    return ns.asiento(
        empresa_id,
        [
            {"cuenta": "6400", "debe": Decimal(importe), "haber": Decimal(0), "detalle": "gasto"},
            {"cuenta": "5720", "debe": Decimal(0), "haber": Decimal(importe), "detalle": "banco"},
        ],
        date(2026, 4, 2),
        "Gasto repartible",
    )


def _imputar(ns, empresa_id, subvencion_id, asiento_id, linea_id, importe):
    return ns.run(
        ns.mutar(
            lambda s: imputar_gasto(
                s,
                empresa_id=empresa_id,
                subvencion_id=subvencion_id,
                asiento_id=asiento_id,
                linea_id=linea_id,
                importe_asignado=Decimal(importe),
            )
        )
    )


def test_linea_solo_se_imputa_a_una_subvencion(ngo_client):
    ns = ngo_client
    sub_a = ns.crear_subvencion(10, importe="1000.0000", referencia="A")
    sub_b = ns.crear_subvencion(10, importe="2000.0000", referencia="B")
    entrada = _gasto(ns)
    linea = uuid.UUID(_linea_debe(ns, 10, entrada))

    ra = _imputar(ns, 10, uuid.UUID(sub_a["id"]), entrada.id, linea, "400.0000")
    assert ra["gastado"] == "400.0000"

    with pytest.raises(NgoError) as exc:
        _imputar(ns, 10, uuid.UUID(sub_b["id"]), entrada.id, linea, "100.0000")
    assert exc.value.code == "gasto_ya_imputado"


def test_desimputar_libera_linea_y_restaura_disponible(ngo_client):
    ns = ngo_client
    sub = ns.crear_subvencion(10, importe="1000.0000")
    sid = uuid.UUID(sub["id"])
    entrada = _gasto(ns)
    linea = uuid.UUID(_linea_debe(ns, 10, entrada))

    r = _imputar(ns, 10, sid, entrada.id, linea, "400.0000")
    ns.run(
        ns.mutar(
            lambda s: desimputar_gasto(
                s, empresa_id=10, subvencion_id=sid, gasto_id=uuid.UUID(r["id"])
            )
        )
    )
    r2 = _imputar(ns, 10, sid, entrada.id, linea, "900.0000")
    assert r2["gastado"] == "900.0000"

    with pytest.raises(NgoError) as exc:
        ns.run(
            ns.mutar(
                lambda s: desimputar_gasto(
                    s, empresa_id=10, subvencion_id=sid, gasto_id=uuid.uuid4()
                )
            )
        )
    assert exc.value.code == "gasto_no_encontrado"