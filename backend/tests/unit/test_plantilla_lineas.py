"""SPEC-018 US1: restricciones de lineas y variables de plantilla."""

from uuid import UUID

import pytest
from sqlalchemy import select

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.templates.errores import TemplateError
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


def _linea(cuenta_id: int, posicion: str = "debe", **extra) -> dict:
    return {"orden": extra.pop("orden", 1), "cuenta_id": cuenta_id, "posicion": posicion, **extra}


async def test_linea_con_fijo_y_variable_es_rechazada(db_session):
    cuentas = await _prepare(db_session)
    with pytest.raises(TemplateError) as exc:
        await crear_plantilla(
            db_session,
            empresa_id=10,
            nombre="Mixta",
            descripcion=None,
            categoria=None,
            variables=[{"nombre": "importe"}],
            lineas=[
                _linea(cuentas["6000"], orden=1, importe_fijo="10.0000", variable_id="00000000-0000-0000-0000-0000000000b1"),
                _linea(cuentas["5720"], orden=2, importe_fijo="10.0000", posicion="haber"),
            ],
        )
    assert exc.value.code == "fijo_variable_excluyentes"


async def test_variable_no_declarada_es_rechazada(db_session):
    cuentas = await _prepare(db_session)
    with pytest.raises(TemplateError) as exc:
        await crear_plantilla(
            db_session,
            empresa_id=10,
            nombre="Huerfana",
            descripcion=None,
            categoria=None,
            variables=[],
            lineas=[
                _linea(cuentas["6000"], orden=1, variable_id=UUID("00000000-0000-0000-0000-0000000000b2")),
                _linea(cuentas["5720"], orden=2, importe_fijo="10.0000", posicion="haber"),
            ],
        )
    assert exc.value.code == "variable_no_declarada"


async def test_cuenta_inexistente_es_rechazada(db_session):
    cuentas = await _prepare(db_session)
    with pytest.raises(TemplateError) as exc:
        await crear_plantilla(
            db_session,
            empresa_id=10,
            nombre="Cuenta mala",
            descripcion=None,
            categoria=None,
            variables=[],
            lineas=[
                _linea(999999, orden=1, importe_fijo="10.0000"),
                _linea(cuentas["5720"], orden=2, importe_fijo="10.0000", posicion="haber"),
            ],
        )
    assert exc.value.code == "cuenta_invalida"


async def test_linea_sin_importe_es_rechazada(db_session):
    cuentas = await _prepare(db_session)
    with pytest.raises(TemplateError) as exc:
        await crear_plantilla(
            db_session,
            empresa_id=10,
            nombre="Vacia",
            descripcion=None,
            categoria=None,
            variables=[],
            lineas=[
                _linea(cuentas["6000"], orden=1),
                _linea(cuentas["5720"], orden=2, importe_fijo="10.0000", posicion="haber"),
            ],
        )
    assert exc.value.code == "importe_requerido"


async def test_nombre_duplicado_es_conflicto(db_session):
    cuentas = await _prepare(db_session)
    lineas = [
        _linea(cuentas["6000"], orden=1, importe_fijo="10.0000"),
        _linea(cuentas["5720"], orden=2, importe_fijo="10.0000", posicion="haber"),
    ]
    await crear_plantilla(db_session, empresa_id=10, nombre="Unica", descripcion=None, categoria=None, variables=[], lineas=lineas)
    with pytest.raises(TemplateError) as exc:
        await crear_plantilla(db_session, empresa_id=10, nombre="Unica", descripcion=None, categoria=None, variables=[], lineas=lineas)
    assert exc.value.code == "nombre_duplicado"
    assert exc.value.status_code == 409
