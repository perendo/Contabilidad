"""T036: Filtros de período y tipo en el informe de costes (SPEC-017 US3).

`fecha_desde`/`fecha_hasta` recortan movimientos; `tipo` aísla coste o ingreso;
la validación de período y tipo responde códigos `periodo_invalido` /
`tipo_invalido`.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from services.costcenters.centros import crear_centro
from services.costcenters.errores import CostcenterError
from services.costcenters.informes import informe_costes
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc


async def _cuenta(db_session, empresa_id, code: str) -> AccountPlan:
    cuenta = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == code
        )
    )
    assert cuenta is not None
    return cuenta


async def _movimiento(db_session, empresa_id, fecha: date, centro_id, importe: str, lado: str):
    if lado == "coste":
        c1, c2 = await _cuenta(db_session, empresa_id, "6000"), await _cuenta(db_session, empresa_id, "5720")
        l1 = {"cuenta": c1.code, "debe": importe, "haber": "0", "centro_coste_id": str(centro_id)}
        l2 = {"cuenta": c2.code, "debe": "0", "haber": importe}
    else:
        c1, c2 = await _cuenta(db_session, empresa_id, "7000"), await _cuenta(db_session, empresa_id, "5720")
        l1 = {"cuenta": c1.code, "debe": "0", "haber": importe, "centro_coste_id": str(centro_id)}
        l2 = {"cuenta": c2.code, "debe": importe, "haber": "0"}
    await crear_asiento_multilinea(
        db_session, empresa_id=empresa_id, fecha=fecha, concepto=lado, lineas=[l1, l2]
    )


async def test_rango_de_fechas(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="RAN", nombre="Rango", tipo="proyecto")
    await _movimiento(db_session, 10, date(2026, 2, 1), centro["id"], "30.0000", "coste")
    await _movimiento(db_session, 10, date(2026, 8, 1), centro["id"], "70.0000", "coste")

    informe = await informe_costes(
        db_session, empresa_id=10, ejercicio=2026,
        fecha_desde=date(2026, 3, 1), fecha_hasta=date(2026, 9, 30),
    )
    assert informe["totales"]["coste"] == "70.0000"


async def test_tipo_aisla_costes_e_ingresos(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    centro = await crear_centro(db_session, empresa_id=10, codigo="TIP", nombre="Tipo", tipo="proyecto")
    await _movimiento(db_session, 10, date(2026, 4, 1), centro["id"], "120.0000", "coste")
    await _movimiento(db_session, 10, date(2026, 4, 1), centro["id"], "20.0000", "ingreso")

    solo_costes = await informe_costes(db_session, empresa_id=10, ejercicio=2026, tipo="coste")
    assert solo_costes["totales"]["coste"] == "120.0000"
    assert solo_costes["totales"]["ingreso"] == "0.0000"
    fila_costes = solo_costes["filas"][0]
    assert fila_costes["subtotal_haber"] == "0.0000"

    solo_ingresos = await informe_costes(db_session, empresa_id=10, ejercicio=2026, tipo="ingreso")
    assert solo_ingresos["totales"]["ingreso"] == "20.0000"
    assert solo_ingresos["totales"]["coste"] == "0.0000"


async def test_periodo_invalido(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    await crear_centro(db_session, empresa_id=10, codigo="PV", nombre="PV", tipo="proyecto")
    with pytest.raises(CostcenterError) as exc:
        await informe_costes(
            db_session, empresa_id=10, ejercicio=2026,
            fecha_desde=date(2026, 10, 1), fecha_hasta=date(2026, 1, 1),
        )
    assert exc.value.code == "periodo_invalido"


async def test_tipo_invalido(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    with pytest.raises(CostcenterError) as exc:
        await informe_costes(db_session, empresa_id=10, ejercicio=2026, tipo="desconocido")
    assert exc.value.code == "tipo_invalido"


async def test_centro_id_invalido_404(db_session):
    import uuid

    await sembrar_empresa_pgc(db_session, 10)
    with pytest.raises(CostcenterError) as exc:
        await informe_costes(db_session, empresa_id=10, ejercicio=2026, centro_id=uuid.uuid4())
    assert exc.value.code == "centro_no_encontrado"