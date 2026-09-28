"""SPEC-018 US1: alta de plantillas con importes fijos y variables."""

from uuid import UUID

from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from models.templates.linea import LineaPlantilla
from models.templates.variable import VariablePlantilla
from services.acct.seed import seed_default_pgc
from services.templates.plantillas import crear_plantilla


async def _prepare(db, empresa_id: int) -> dict[str, int]:
    db.add(Company(company_id=empresa_id, nif=f"T{empresa_id:08d}", razon_social=f"Empresa {empresa_id}"))
    await db.flush()
    await seed_default_pgc(db, empresa_id)
    cuentas: dict[str, int] = {}
    for code in ("6000", "5720"):
        account = await db.scalar(select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == code))
        assert account is not None
        cuentas[code] = account.id
    return cuentas


async def test_alta_persiste_fijos_variables_y_version_uno(db_session):
    cuentas = await _prepare(db_session, 10)
    variable_id = UUID("00000000-0000-0000-0000-0000000000a1")
    plantilla = await crear_plantilla(
        db_session,
        empresa_id=10,
        nombre="Pago proveedor",
        descripcion="Pago recurrente",
        categoria="tesoreria",
        variables=[{"id": variable_id, "nombre": "importe", "es_requerida": True}],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": "100.0000"},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "variable_id": variable_id},
        ],
        actor="test",
    )
    assert plantilla.version_actual == 1
    variables = (await db_session.scalars(select(VariablePlantilla).where(VariablePlantilla.plantilla_id == plantilla.id))).all()
    lineas = (await db_session.scalars(select(LineaPlantilla).where(LineaPlantilla.plantilla_id == plantilla.id).order_by(LineaPlantilla.orden))).all()
    assert len(variables) == 1
    assert variables[0].nombre == "importe"
    assert len(lineas) == 2
    assert lineas[0].importe_fijo is not None
    assert lineas[1].variable_id == variable_id


async def test_alta_sin_variables_solo_fijos(db_session):
    cuentas = await _prepare(db_session, 10)
    plantilla = await crear_plantilla(
        db_session,
        empresa_id=10,
        nombre="Traspaso caja",
        descripcion=None,
        categoria=None,
        variables=[],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": "10.0000"},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "importe_fijo": "10.0000"},
        ],
    )
    lineas = (await db_session.scalars(select(LineaPlantilla).where(LineaPlantilla.plantilla_id == plantilla.id))).all()
    assert all(linea.variable_id is None for linea in lineas)
    assert plantilla.version_actual == 1
