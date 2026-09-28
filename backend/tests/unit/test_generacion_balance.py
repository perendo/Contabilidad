"""SPEC-018 T020: la generacion desde plantilla respeta el balance estricto."""

from datetime import date

import pytest
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.templates.errores import TemplateError
from services.templates.generacion import generar_asiento
from services.templates.plantillas import crear_plantilla


async def _prepare(db, empresa_id: int = 10) -> dict[str, int]:
    db.add(Company(company_id=empresa_id, nif=f"T{empresa_id:08d}", razon_social=f"Empresa {empresa_id}"))
    await db.flush()
    await seed_default_pgc(db, empresa_id)
    cuentas: dict[str, int] = {}
    for code in ("6000", "5720"):
        account = await db.scalar(select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == code))
        assert account is not None
        cuentas[code] = account.id
    return cuentas


async def test_generacion_balanceada_con_decimales(db_session):
    cuentas = await _prepare(db_session)
    variable_id = "00000000-0000-0000-0000-0000000000c1"
    plantilla = await crear_plantilla(
        db_session,
        empresa_id=10,
        nombre="Balanceada",
        descripcion=None,
        categoria=None,
        variables=[{"id": variable_id, "nombre": "importe"}],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "variable_id": variable_id},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "variable_id": variable_id},
        ],
    )
    resultado = await generar_asiento(
        db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 2, 1), variables={"importe": "123.4567"}
    )
    assert resultado["asiento"]["total_debe"] == "123.4567"
    assert resultado["asiento"]["total_haber"] == "123.4567"
    assert resultado["variables_aportadas"][variable_id] == "123.4567"
    assert resultado["version_plantilla"] == 1


async def test_plantilla_desbalanceada_es_rechazada(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await crear_plantilla(
        db_session,
        empresa_id=10,
        nombre="Descuadra",
        descripcion=None,
        categoria=None,
        variables=[],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": "100.0000"},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "importe_fijo": "50.0000"},
        ],
    )
    # El flujo no debe producir ninguna linea Posted
    with pytest.raises(TemplateError) as exc:
        await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 2, 1), variables={})
    assert exc.value.code == "desbalanceo"
    assert exc.value.status_code == 409
