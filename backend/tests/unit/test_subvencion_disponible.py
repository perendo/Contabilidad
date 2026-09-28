"""Disponibilidad y límites de imputación de gastos (SPEC-019 US1).

Reglas: la suma imputada a una línea no excede el debe de la línea; la suma por
subvención no excede el importe concedido; una línea solo se imputa una vez por
subvención; solo líneas POSTED; solo líneas de gasto (Debe).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from services.journal.anulador import anular_asiento
from services.ngo.errores import NgoError
from services.ngo.justificacion import imputar_gasto
from services.ngo.subvenciones import cambiar_estado_subvencion


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


def _gasto(ns, empresa_id=10, importe="1000.0000", concepto="Gasto"):
    return ns.asiento(
        empresa_id,
        [
            {"cuenta": "6400", "debe": Decimal(importe), "haber": Decimal(0), "detalle": "sueldos"},
            {"cuenta": "5720", "debe": Decimal(0), "haber": Decimal(importe), "detalle": "bancos"},
        ],
        date(2026, 3, 15),
        concepto,
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


def test_limites_de_linea_y_disponible(ngo_client):
    ns = ngo_client
    sub = ns.crear_subvencion(10, importe="1000.0000")
    sid = uuid.UUID(sub["id"])
    entrada = _gasto(ns)
    linea = uuid.UUID(_linea_debe(ns, 10, entrada))

    r = _imputar(ns, 10, sid, entrada.id, linea, "400.0000")
    assert r["gastado"] == "400.0000" and r["pendiente"] == "600.0000"

    with pytest.raises(NgoError) as exc:
        _imputar(ns, 10, sid, entrada.id, linea, "100.0000")
    assert exc.value.code == "gasto_ya_imputado"

    sub2 = ns.crear_subvencion(10, importe="2000.0000", referencia="S2")
    entrada2 = _gasto(ns, concepto="Gasto 2")
    linea2 = uuid.UUID(_linea_debe(ns, 10, entrada2))
    with pytest.raises(NgoError) as exc2:
        _imputar(ns, 10, uuid.UUID(sub2["id"]), entrada2.id, linea2, "1500.0000")
    assert exc2.value.code == "excede_importe_linea"

    sub3 = ns.crear_subvencion(10, importe="300.0000", referencia="S3")
    entrada3 = _gasto(ns, concepto="Gasto 3")
    linea3 = uuid.UUID(_linea_debe(ns, 10, entrada3))
    with pytest.raises(NgoError) as exc3:
        _imputar(ns, 10, uuid.UUID(sub3["id"]), entrada3.id, linea3, "500.0000")
    assert exc3.value.code == "excede_disponible"


def test_solo_asientos_posteado_y_lineas_de_gasto(ngo_client):
    ns = ngo_client
    sub = ns.crear_subvencion(10, importe="5000.0000")
    sid = uuid.UUID(sub["id"])
    entrada = _gasto(ns)
    linea_debe = uuid.UUID(_linea_debe(ns, 10, entrada))

    ns.run(
        ns.mutar(lambda s: anular_asiento(s, empresa_id=10, entry_id=entrada.id))
    )
    with pytest.raises(NgoError) as exc:
        _imputar(ns, 10, sid, entrada.id, linea_debe, "100.0000")
    assert exc.value.code == "asiento_no_asentado"


def test_linea_haber_no_es_gasto(ngo_client):
    from sqlalchemy import select

    from models.acct.journal import JournalEntryLine

    ns = ngo_client
    sub = ns.crear_subvencion(10, importe="5000.0000")
    sid = uuid.UUID(sub["id"])
    entrada = _gasto(ns)

    async def _op(session):
        filas = (
            await session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.empresa_id == 10,
                    JournalEntryLine.journal_entry_id == entrada.id,
                )
            )
        ).all()
        return str(next(l for l in filas if l.haber > 0).id)

    linea_haber = uuid.UUID(ns.run(ns.consultar(_op)))
    with pytest.raises(NgoError) as exc:
        _imputar(ns, 10, sid, entrada.id, linea_haber, "100.0000")
    assert exc.value.code == "linea_no_es_gasto"


def test_subvencion_cerrada_bloquea_imputacion(ngo_client):
    ns = ngo_client
    sub = ns.crear_subvencion(10, importe="5000.0000")
    sid = uuid.UUID(sub["id"])
    for estado in ("en_curso", "justificada"):
        ns.run(
            ns.mutar(
                lambda s, e=estado: cambiar_estado_subvencion(
                    s, empresa_id=10, subvencion_id=sid, estado=e
                )
            )
        )
    entrada = _gasto(ns)
    linea = uuid.UUID(_linea_debe(ns, 10, entrada))
    with pytest.raises(NgoError) as exc:
        _imputar(ns, 10, sid, entrada.id, linea, "100.0000")
    assert exc.value.code == "subvencion_cerrada"