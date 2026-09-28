"""SPEC-018 T022: validacion de cuentas y ejercicio en la generacion."""

from datetime import date

import pytest
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
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


async def _plantilla_fija(db, cuentas):
    return await crear_plantilla(
        db,
        empresa_id=10,
        nombre="Fija",
        descripcion=None,
        categoria=None,
        variables=[],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": "30.0000"},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "importe_fijo": "30.0000"},
        ],
    )


async def test_cuenta_inactivada_bloquea_la_generacion(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla_fija(db_session, cuentas)
    cuenta = await db_session.get(AccountPlan, cuentas["6000"])
    assert cuenta is not None
    cuenta.is_active = False
    await db_session.flush()

    with pytest.raises(TemplateError) as exc:
        await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 2, 1), variables={})
    assert exc.value.code == "cuenta_invalida"
    assert exc.value.status_code == 422


async def test_ejercicio_cerrado_bloquea_la_generacion(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla_fija(db_session, cuentas)
    db_session.add(
        FiscalYear(
            empresa_id=10,
            year=2026,
            date_start=date(2026, 1, 1),
            date_end=date(2026, 12, 31),
            is_closed=True,
        )
    )
    await db_session.flush()

    with pytest.raises(TemplateError) as exc:
        await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 2, 1), variables={})
    assert exc.value.code == "ejercicio_cerrado"
    assert exc.value.status_code == 409


async def test_fecha_fuera_de_rango_es_rechazada(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla_fija(db_session, cuentas)
    with pytest.raises(TemplateError) as exc:
        await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(1999, 1, 1), variables={})
    assert exc.value.code == "ejercicio_invalido"
    assert exc.value.status_code == 409
