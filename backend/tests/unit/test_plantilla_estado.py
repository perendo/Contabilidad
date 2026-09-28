"""SPEC-018 T031: activacion/desactivacion y proteccion de borrado."""

from datetime import date

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from models.templates.linea import LineaPlantilla
from models.templates.plantilla import EstadoPlantilla, PlantillaAsiento
from models.templates.variable import VariablePlantilla
from services.acct.seed import seed_default_pgc
from services.templates.errores import TemplateError
from services.templates.generacion import generar_asiento
from services.templates.plantillas import cambiar_estado, crear_plantilla


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


async def _plantilla(db, cuentas):
    return await crear_plantilla(
        db,
        empresa_id=10,
        nombre="Estado",
        descripcion=None,
        categoria=None,
        variables=[],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": "20.0000"},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "importe_fijo": "20.0000"},
        ],
    )


async def test_inactivar_bloquea_y_reactivar_permite(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla(db_session, cuentas)

    await cambiar_estado(db_session, empresa_id=10, plantilla_id=plantilla.id, estado=EstadoPlantilla.inactiva)
    with pytest.raises(TemplateError) as exc:
        await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 4, 1), variables={})
    assert exc.value.code == "plantilla_inactiva"
    assert exc.value.status_code == 409

    await cambiar_estado(db_session, empresa_id=10, plantilla_id=plantilla.id, estado=EstadoPlantilla.activa)
    resultado = await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 4, 1), variables={})
    assert resultado["asiento"]["estado"] == "POSTED"


async def test_estado_duplicado_es_conflicto(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla(db_session, cuentas)
    with pytest.raises(TemplateError) as exc:
        await cambiar_estado(db_session, empresa_id=10, plantilla_id=plantilla.id, estado=EstadoPlantilla.activa)
    assert exc.value.code == "estado_duplicado"


async def test_no_se_borra_plantilla_con_generados(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla(db_session, cuentas)
    await generar_asiento(db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 4, 1), variables={})

    with pytest.raises(IntegrityError):
        await db_session.execute(
            delete(PlantillaAsiento).where(PlantillaAsiento.empresa_id == 10, PlantillaAsiento.id == plantilla.id)
        )
        await db_session.flush()
    await db_session.rollback()


async def test_plantilla_sin_generados_se_puede_borrar(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla(db_session, cuentas)
    await db_session.execute(delete(LineaPlantilla).where(LineaPlantilla.plantilla_id == plantilla.id))
    await db_session.execute(delete(VariablePlantilla).where(VariablePlantilla.plantilla_id == plantilla.id))
    await db_session.execute(
        delete(PlantillaAsiento).where(PlantillaAsiento.empresa_id == 10, PlantillaAsiento.id == plantilla.id)
    )
    await db_session.flush()
    restante = await db_session.scalar(select(PlantillaAsiento).where(PlantillaAsiento.id == plantilla.id))
    assert restante is None
