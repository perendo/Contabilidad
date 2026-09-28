"""SPEC-018 T010: aislamiento multi-tenant de las tablas de plantillas."""


import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from models.templates.linea import LineaPlantilla
from services.acct.seed import seed_default_pgc
from services.templates.errores import TemplateError
from services.templates.plantillas import (
    crear_plantilla,
    detalle_plantilla,
    listar_plantillas,
)


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


async def _plantilla(db, empresa_id: int, nombre: str):
    cuentas = await _prepare(db, empresa_id)
    return await crear_plantilla(
        db,
        empresa_id=empresa_id,
        nombre=nombre,
        descripcion=None,
        categoria=None,
        variables=[],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": "10.0000"},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "importe_fijo": "10.0000"},
        ],
    )


async def test_plantilla_de_a_no_es_visible_desde_b(db_session):
    plantilla = await _plantilla(db_session, 10, "Solo A")
    with pytest.raises(TemplateError) as exc:
        await detalle_plantilla(db_session, empresa_id=20, plantilla_id=plantilla.id)
    assert exc.value.code == "plantilla_no_encontrada"

    listado = await listar_plantillas(db_session, empresa_id=20)
    assert listado["total"] == 0


async def test_fk_compuesta_impide_cross_tenant(db_session):
    plantilla = await _plantilla(db_session, 10, "Base A")
    cuentas_b = await _prepare(db_session, 20)
    db_session.add(
        LineaPlantilla(
            empresa_id=20,
            plantilla_id=plantilla.id,
            orden=1,
            cuenta_id=cuentas_b["6000"],
            posicion="debe",
            importe_fijo="5.0000",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_plantilla_sin_variables_queda_version_uno(db_session):
    plantilla = await _plantilla(db_session, 10, "Estable")
    assert plantilla.version_actual == 1
