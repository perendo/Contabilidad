"""SPEC-018 T021: resolucion de variables en la generacion."""

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


async def _plantilla_variable(db, cuentas, *, requerida: bool = True):
    variable_id = "00000000-0000-0000-0000-0000000000d1"
    plantilla = await crear_plantilla(
        db,
        empresa_id=10,
        nombre="Con variable",
        descripcion=None,
        categoria=None,
        variables=[{"id": variable_id, "nombre": "importe", "es_requerida": requerida}],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "variable_id": variable_id},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "variable_id": variable_id},
        ],
    )
    return plantilla, variable_id


async def test_variable_requerida_ausente_es_422(db_session):
    cuentas = await _prepare(db_session)
    plantilla, _ = await _plantilla_variable(db_session, cuentas)
    with pytest.raises(TemplateError) as exc:
        await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 2, 1), variables={})
    assert exc.value.code == "variables_faltantes"
    assert exc.value.status_code == 422


async def test_variable_no_numerica_es_422(db_session):
    cuentas = await _prepare(db_session)
    plantilla, _ = await _plantilla_variable(db_session, cuentas)
    with pytest.raises(TemplateError) as exc:
        await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 2, 1), variables={"importe": "abc"})
    assert exc.value.code == "variable_no_numerica"
    assert exc.value.status_code == 422


async def test_variable_por_nombre_resuelve_la_linea(db_session):
    cuentas = await _prepare(db_session)
    plantilla, _ = await _plantilla_variable(db_session, cuentas)
    resultado = await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 2, 1), variables={"importe": "77.0000"})
    assert resultado["asiento"]["total_debe"] == "77.0000"
    assert resultado["asiento"]["total_haber"] == "77.0000"


async def test_variable_opcional_vacia_omite_sus_lineas(db_session):
    cuentas = await _prepare(db_session)
    variable_id = "00000000-0000-0000-0000-0000000000d2"
    plantilla = await crear_plantilla(
        db_session,
        empresa_id=10,
        nombre="Opcionales",
        descripcion=None,
        categoria=None,
        variables=[{"id": variable_id, "nombre": "opcional", "es_requerida": False}],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": "100.0000"},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "importe_fijo": "100.0000"},
            {"orden": 3, "cuenta_id": cuentas["6000"], "posicion": "debe", "variable_id": variable_id},
            {"orden": 4, "cuenta_id": cuentas["5720"], "posicion": "haber", "variable_id": variable_id},
        ],
    )
    sin_opcional = await generar_asiento(
        db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 2, 1), variables={}
    )
    assert sin_opcional["asiento"]["n_lineas"] == 2

    con_opcional = await generar_asiento(
        db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 2, 2), variables={"opcional": "50.0000"}
    )
    assert con_opcional["asiento"]["n_lineas"] == 4
    assert con_opcional["asiento"]["total_debe"] == "150.0000"
    assert con_opcional["asiento"]["total_haber"] == "150.0000"
