"""T035: Subtotales por jerarquía en el informe de costes (SPEC-017 US3).

La closure materializa ancestros: el subtotal de un centro padre incluye los
importes directos de sus descendientes inmediatos y de todo el subárbol.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from services.costcenters.centros import crear_centro
from services.costcenters.informes import informe_costes
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc


def _uid(s: str) -> uuid.UUID:
    return uuid.UUID(s)


async def _cuenta(db_session, empresa_id, code: str) -> AccountPlan:
    cuenta = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
        )
    )
    assert cuenta is not None
    return cuenta


async def _gasto(db_session, empresa_id, centro_id, importe: str):
    c6000 = await _cuenta(db_session, empresa_id, "6000")
    c572 = await _cuenta(db_session, empresa_id, "5720")
    await crear_asiento_multilinea(
        db_session,
        empresa_id=empresa_id,
        fecha=date(2026, 6, 1),
        concepto="Gasto",
        lineas=[
            {"cuenta": c6000.code, "debe": importe, "haber": "0", "centro_coste_id": str(centro_id)},
            {"cuenta": c572.code, "debe": "0", "haber": importe},
        ],
    )


async def test_subtotal_padre_incluye_descendientes(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    padre = await crear_centro(db_session, empresa_id=10, codigo="PAD", nombre="Padre", tipo="departamento")
    hijo = await crear_centro(db_session, empresa_id=10, codigo="HIJ", nombre="Hijo", tipo="proyecto", parent_id=_uid(padre["id"]))
    nieto = await crear_centro(db_session, empresa_id=10, codigo="NIE", nombre="Nieto", tipo="proyecto", parent_id=_uid(hijo["id"]))

    await _gasto(db_session, 10, hijo["id"], "100.0000")   # línea en hijo
    await _gasto(db_session, 10, nieto["id"], "40.0000")   # línea en nieto

    informe = await informe_costes(db_session, empresa_id=10, ejercicio=2026, centro_id=_uid(padre["id"]))
    por_codigo = {f["codigo"]: f for f in informe["filas"]}
    assert set(por_codigo) == {"PAD", "HIJ", "NIE"}

    # Hijos del padre (HIJ+NIE) suman 140 -> subtotal padre
    assert por_codigo["PAD"]["directo_debe"] == "0.0000"
    assert por_codigo["PAD"]["hijos_debe"] == "140.0000"
    assert por_codigo["PAD"]["subtotal_debe"] == "140.0000"

    # Hijo: directo 100 + nieto 40
    assert por_codigo["HIJ"]["directo_debe"] == "100.0000"
    assert por_codigo["HIJ"]["subtotal_debe"] == "140.0000"

    # Nieto: solo sus 40
    assert por_codigo["NIE"]["directo_debe"] == "40.0000"
    assert por_codigo["NIE"]["subtotal_debe"] == "40.0000"

    assert informe["totales"]["coste"] == "140.0000"


async def test_scope_por_centro_incluye_subarbol(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    padre = await crear_centro(db_session, empresa_id=10, codigo="PA2", nombre="Padre", tipo="departamento")
    hijo = await crear_centro(db_session, empresa_id=10, codigo="HI2", nombre="Hijo", tipo="proyecto", parent_id=_uid(padre["id"]))
    otro = await crear_centro(db_session, empresa_id=10, codigo="OTR", nombre="Otro", tipo="proyecto")

    await _gasto(db_session, 10, hijo["id"], "75.0000")
    await _gasto(db_session, 10, otro["id"], "999.0000")

    informe = await informe_costes(db_session, empresa_id=10, ejercicio=2026, centro_id=_uid(padre["id"]))
    por_codigo = {f["codigo"]: f for f in informe["filas"]}
    assert set(por_codigo) == {"PA2", "HI2"}
    assert "OTR" not in por_codigo
    assert informe["totales"]["coste"] == "75.0000"