"""SPEC-018 foundational model and service coverage."""

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.templates.errores import TemplateError
from services.templates.generacion import generar_asiento
from services.templates.plantillas import crear_plantilla, detalle_plantilla


async def _prepare(db, empresa_id: int) -> dict[str, int]:
    db.add(Company(company_id=empresa_id, nif=f"T{empresa_id:08d}", razon_social=f"Empresa {empresa_id}"))
    await db.flush()
    await seed_default_pgc(db, empresa_id)
    cuentas = {}
    for code in ("6000", "5720"):
        account = await db.scalar(select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == code))
        assert account is not None
        cuentas[code] = account.id
    return cuentas


@pytest.mark.asyncio
async def test_template_fixed_and_variable_and_version(db_session):
    accounts = await _prepare(db_session, 10)
    variable_id = UUID("00000000-0000-0000-0000-000000000001")
    template = await crear_plantilla(
        db_session,
        empresa_id=10,
        nombre="Pago",
        descripcion=None,
        categoria="tesoreria",
        variables=[{"id": variable_id, "nombre": "importe", "es_requerida": True}],
        lineas=[
            {"orden": 1, "cuenta_id": accounts["6000"], "posicion": "debe", "importe_fijo": "100.0000"},
            {"orden": 2, "cuenta_id": accounts["5720"], "posicion": "haber", "variable_id": variable_id},
        ],
        actor="test",
    )
    detail = await detalle_plantilla(db_session, empresa_id=10, plantilla_id=template.id)
    assert detail["version_actual"] == 1
    assert len(detail["lineas"]) == 2


@pytest.mark.asyncio
async def test_template_rejects_fixed_and_variable(db_session):
    accounts = await _prepare(db_session, 10)
    with pytest.raises(TemplateError) as error:
        await crear_plantilla(
            db_session,
            empresa_id=10,
            nombre="Invalida",
            descripcion=None,
            categoria=None,
            variables=[{"nombre": "importe"}],
            lineas=[
                {"orden": 1, "cuenta_id": accounts["6000"], "posicion": "debe", "importe_fijo": "10", "variable_id": "00000000-0000-0000-0000-000000000001"},
                {"orden": 2, "cuenta_id": accounts["5720"], "posicion": "haber", "importe_fijo": "10"},
            ],
        )
    assert error.value.code == "fijo_variable_excluyentes"


@pytest.mark.asyncio
async def test_generation_is_balanced_and_tenant_scoped(db_session):
    accounts = await _prepare(db_session, 10)
    template = await crear_plantilla(
        db_session,
        empresa_id=10,
        nombre="Cobro",
        descripcion=None,
        categoria=None,
        variables=[{"id": UUID("00000000-0000-0000-0000-000000000001"), "nombre": "importe"}],
        lineas=[
            {"orden": 1, "cuenta_id": accounts["6000"], "posicion": "debe", "variable_id": "00000000-0000-0000-0000-000000000001"},
            {"orden": 2, "cuenta_id": accounts["5720"], "posicion": "haber", "variable_id": "00000000-0000-0000-0000-000000000001"},
        ],
    )
    generated = await generar_asiento(db_session, empresa_id=10, plantilla_id=template.id, fecha=date(2026, 1, 15), variables={"importe": "250.0000"}, actor="test")
    assert generated["asiento"]["total_debe"] == "250.0000"
    assert generated["asiento"]["total_haber"] == "250.0000"
    with pytest.raises(TemplateError) as error:
        await detalle_plantilla(db_session, empresa_id=20, plantilla_id=template.id)
    assert error.value.code == "plantilla_no_encontrada"
