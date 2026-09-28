"""SPEC-018 T037: cumplimiento de la constitucion en el flujo de plantillas."""

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from base import Base
from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from models.templates.asiento_generado import AsientoGenerado
from services.acct.seed import seed_default_pgc
from services.templates.generacion import generar_asiento
from services.templates.plantillas import crear_plantilla


async def _prepare(db, empresa_id: int = 10) -> dict[str, int]:
    db.add(Company(company_id=empresa_id, nif=f"T{empresa_id:08d}", razon_social=f"Empresa {empresa_id}"))
    await db.flush()
    await seed_default_pgc(db, empresa_id)
    cuentas: dict[str, int] = {}
    for code in ("6000", "5720", "4300"):
        account = await db.scalar(select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.code == code))
        assert account is not None
        cuentas[code] = account.id
    return cuentas


async def _plantilla(db, cuentas):
    return await crear_plantilla(
        db,
        empresa_id=10,
        nombre="Constitucion",
        descripcion=None,
        categoria=None,
        variables=[],
        lineas=[
            {"orden": 1, "cuenta_id": cuentas["6000"], "posicion": "debe", "importe_fijo": "12.3456"},
            {"orden": 2, "cuenta_id": cuentas["5720"], "posicion": "haber", "importe_fijo": "12.3456"},
        ],
    )


def test_todas_las_tablas_de_plantillas_son_multi_tenant():
    for tabla in ("plantilla_asiento", "variable_plantilla", "linea_plantilla", "asiento_generado"):
        table = Base.metadata.tables[tabla]
        assert "empresa_id" in table.c, f"{tabla} sin empresa_id"
    pk_asiento_generado = {col.name for col in AsientoGenerado.__table__.primary_key.columns}
    assert "empresa_id" in pk_asiento_generado


async def test_asiento_generado_siempre_balanceado(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla(db_session, cuentas)
    for dia in (1, 2, 3):
        resultado = await generar_asiento(
            db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 7, dia), variables={}
        )
        assert resultado["asiento"]["total_debe"] == resultado["asiento"]["total_haber"]


async def test_asiento_generado_es_inmutable(db_session):
    cuentas = await _prepare(db_session)
    plantilla = await _plantilla(db_session, cuentas)
    resultado = await generar_asiento(
        db_session, empresa_id=10, plantilla_id=plantilla.id, fecha=date(2026, 7, 1), variables={}
    )
    asiento_id = UUID(resultado["asiento"]["id"])

    with pytest.raises(IntegrityError):
        await db_session.execute(
            update(AsientoGenerado)
            .where(AsientoGenerado.asiento_id == asiento_id)
            .values(version_plantilla=99)
        )
        await db_session.flush()
    await db_session.rollback()
