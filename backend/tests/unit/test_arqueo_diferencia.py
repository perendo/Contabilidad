"""Arqueos de caja y ajustes de diferencia (SPEC-019 US3).

Un arqueo que cuadra se aprueba automáticamente; si hay diferencia queda
pendiente y exige un asiento de ajuste POSTED cuyo efecto sobre la 570 cuadre el
efectivo contado; también se puede archivar. Las decisiones son irreversibles.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from services.ngo.arqueo import (
    aprobar_arqueo,
    archivar_arqueo,
    listar_arqueos,
    realizar_arqueo,
)
from services.ngo.caja import crear_caja, registrar_movimiento
from services.ngo.errores import NgoError


def _cuenta_id(ns, empresa_id, code):
    from sqlalchemy import select

    from models.acct.account_plan import AccountPlan

    async def _op(session):
        return await session.scalar(
            select(AccountPlan.id).where(
                AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
            )
        )

    return ns.run(ns.consultar(_op))


def _setup(ns):
    cuenta_570_id = ns.subcuenta_570(10)
    caja = ns.run(
        ns.mutar(
            lambda s: crear_caja(
                s, empresa_id=10, nombre="Caja", cuenta_570_id=cuenta_570_id, tipo="caja"
            )
        )
    )
    sid = uuid.UUID(caja["id"])
    capital = _cuenta_id(ns, 10, "1110")
    ns.run(
        ns.mutar(
            lambda s: registrar_movimiento(
                s,
                empresa_id=10,
                caja_id=sid,
                tipo="entrada",
                importe=Decimal("1000.0000"),
                fecha=date(2026, 8, 1),
                concepto="Aportación",
                contrapartida_cuenta_id=capital,
            )
        )
    )
    return sid


def _arqueo(ns, caja_id, efectivo, fecha="2026-08-31"):
    return ns.run(
        ns.mutar(
            lambda s: realizar_arqueo(
                s,
                empresa_id=10,
                caja_id=caja_id,
                fecha=date.fromisoformat(fecha),
                efectivo_contado=Decimal(efectivo),
            )
        )
    )


def test_arqueo_que_cuadra_se_aprueba(ngo_client):
    ns = ngo_client
    sid = _setup(ns)
    arqueo = _arqueo(ns, sid, "1000.0000")
    assert arqueo["estado"] == "cuadra"
    assert arqueo["decision"] == "aprobada"
    assert arqueo["diferencia"] == "0.0000"


def test_diferencia_exige_ajuste_que_cuadre(ngo_client):
    ns = ngo_client
    sid = _setup(ns)
    arqueo = _arqueo(ns, sid, "900.0000")
    assert arqueo["estado"] == "con_diferencia"
    assert arqueo["decision"] == "pendiente"
    assert arqueo["diferencia"] == "-100.0000"

    with pytest.raises(NgoError) as exc:
        ns.run(ns.mutar(lambda s: aprobar_arqueo(s, empresa_id=10, arqueo_id=uuid.UUID(arqueo["id"]))))
    assert exc.value.code == "falta_asiento_ajuste"

    ajuste = ns.asiento(
        10,
        [
            {"cuenta": "5720", "debe": Decimal("100.0000"), "haber": Decimal(0), "detalle": "ajuste"},
            {"cuenta": "5700", "debe": Decimal(0), "haber": Decimal("100.0000"), "detalle": "ajuste"},
        ],
        date(2026, 8, 31),
        "Ajuste de caja",
    )
    ns.run(
        ns.mutar(
            lambda s: aprobar_arqueo(
                s, empresa_id=10, arqueo_id=uuid.UUID(arqueo["id"]), asiento_ajuste_id=ajuste.id
            )
        )
    )

    listado = ns.run(ns.mutar(lambda s: listar_arqueos(s, empresa_id=10, caja_id=sid)))
    aprobado = next(a for a in listado["items"] if a["id"] == arqueo["id"])
    assert aprobado["decision"] == "aprobada"
    assert aprobado["asiento_ajuste_id"] == str(ajuste.id)


def test_ajuste_que_no_cuadra_rechazado(ngo_client):
    ns = ngo_client
    sid = _setup(ns)
    arqueo = _arqueo(ns, sid, "900.0000")
    ajuste = ns.asiento(
        10,
        [
            {"cuenta": "5720", "debe": Decimal("50.0000"), "haber": Decimal(0), "detalle": "ajuste"},
            {"cuenta": "5700", "debe": Decimal(0), "haber": Decimal("50.0000"), "detalle": "ajuste"},
        ],
        date(2026, 8, 31),
        "Ajuste incorrecto",
    )
    with pytest.raises(NgoError) as exc:
        ns.run(
            ns.mutar(
                lambda s: aprobar_arqueo(
                    s, empresa_id=10, arqueo_id=uuid.UUID(arqueo["id"]), asiento_ajuste_id=ajuste.id
                )
            )
        )
    assert exc.value.code == "ajuste_no_cuadra"


def test_archivar_y_decision_irreversible(ngo_client):
    ns = ngo_client
    sid = _setup(ns)
    arqueo = _arqueo(ns, sid, "950.0000")
    archivado = ns.run(
        ns.mutar(
            lambda s: archivar_arqueo(s, empresa_id=10, arqueo_id=uuid.UUID(arqueo["id"]))
        )
    )
    assert archivado["decision"] == "archivada"
    assert archivado["archivado"] is True

    with pytest.raises(NgoError) as exc:
        ns.run(
            ns.mutar(
                lambda s: archivar_arqueo(s, empresa_id=10, arqueo_id=uuid.UUID(arqueo["id"]))
            )
        )
    assert exc.value.code == "arqueo_ya_decidido"

    listado = ns.run(ns.mutar(lambda s: listar_arqueos(s, empresa_id=10, caja_id=sid)))
    assert listado["total"] == 1
    assert listado["items"][0]["archivado"] is True