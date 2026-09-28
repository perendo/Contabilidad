from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from base import Base
from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.fiscal.ajuste_extracontable import (
    AjusteExtracontable,
    TipoAjusteExtracontable,
)
from models.fiscal.calculo_is import CalculoIS, EstadoCalculoIS
from models.fiscal.configuracion_fiscal import ConfiguracionFiscal
from models.fiscal.modelo_200 import Modelo200
from models.iam.company import Company
from services.acct.seed import seed_default_pgc


async def _empresa(db: AsyncSession, empresa_id: int) -> None:
    db.add(
        Company(
            company_id=empresa_id,
            nif=f"T{empresa_id:08d}",
            razon_social=f"Empresa {empresa_id}",
        )
    )
    await db.flush()


def _calculo(
    empresa_id: int,
    ejercicio: int = 2025,
    *,
    provisional: bool = True,
    estado: EstadoCalculoIS = EstadoCalculoIS.calculado,
    tipo_impositivo: Decimal = Decimal("25.00"),
) -> CalculoIS:
    return CalculoIS(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        resultado_contable=Decimal("100000.0000"),
        ajustes_positivos=Decimal("12000.0000"),
        ajustes_negativos=Decimal("0.0000"),
        base_imponible=Decimal("112000.0000"),
        tipo_impositivo=tipo_impositivo,
        cuota_integra=Decimal("28000.0000"),
        deducciones=Decimal("8000.0000"),
        cuota_liquida=Decimal("20000.0000"),
        pagos_a_cuenta=Decimal("20000.0000"),
        cuota_diferencial=Decimal("0.0000"),
        provisional=provisional,
        estado=estado,
    )


def test_modelos_registrados_y_precision_decimal() -> None:
    assert {"calculo_is", "ajuste_extracontable", "modelo_200"} <= set(
        Base.metadata.tables
    )
    for tabla, columnas in {
        "calculo_is": (
            "resultado_contable",
            "ajustes_positivos",
            "ajustes_negativos",
            "base_imponible",
            "cuota_integra",
            "deducciones",
            "cuota_liquida",
            "pagos_a_cuenta",
            "cuota_diferencial",
        ),
        "ajuste_extracontable": ("importe",),
    }.items():
        for columna in columnas:
            assert str(Base.metadata.tables[tabla].columns[columna].type) in {
                "NUMERIC(18, 4)",
                "NUMERIC(18,4)",
            }
    assert str(Base.metadata.tables["calculo_is"].columns["tipo_impositivo"].type) in {
        "NUMERIC(5, 2)",
        "NUMERIC(5,2)",
    }


def test_modelos_globales_uuid_y_tenant_unique() -> None:
    for nombre in ("calculo_is", "ajuste_extracontable", "modelo_200"):
        tabla = Base.metadata.tables[nombre]
        assert [columna.name for columna in tabla.primary_key.columns] == ["id"]
        unicos = {
            tuple(columna.name for columna in constraint.columns)
            for constraint in tabla.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert ("empresa_id", "id") in unicos


def test_indice_definitivo_es_parcial_y_por_empresa() -> None:
    tabla = Base.metadata.tables["calculo_is"]
    indice = next(
        item
        for item in tabla.indexes
        if item.name == "uq_calculo_is_definitivo"
    )
    assert indice.unique is True
    assert [columna.name for columna in indice.columns] == ["empresa_id", "ejercicio"]
    assert indice.dialect_options["sqlite"]["where"] is not None
    assert indice.dialect_options["postgresql"]["where"] is not None


def test_modelo_200_unicamente_uno_por_calculo() -> None:
    tabla = Base.metadata.tables["modelo_200"]
    unicos = {
        tuple(columna.name for columna in constraint.columns)
        for constraint in tabla.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("empresa_id", "calculo_is_id") in unicos


def test_configuracion_fiscal_tiene_tipo_y_vigencia() -> None:
    tabla = Base.metadata.tables["configuracion_fiscal"]
    assert str(tabla.columns["tipo_is"].type) in {"NUMERIC(5, 2)", "NUMERIC(5,2)"}
    assert tabla.columns["tipo_is"].nullable is False
    assert tabla.columns["fecha_vigencia_desde"].nullable is False
    assert tabla.columns["fecha_vigencia_hasta"].nullable is True
    assert tabla.columns["updated_at"].type.timezone is True
    checks = {
        str(constraint.sqltext)
        for constraint in tabla.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert any("tipo_is > 0" in check for check in checks)
    assert any("fecha_vigencia_hasta" in check for check in checks)


async def test_tipo_impositivo_debe_ser_positivo(db_session: AsyncSession) -> None:
    await _empresa(db_session, 1)
    db_session.add(_calculo(1, tipo_impositivo=Decimal("0.00")))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_importe_ajuste_debe_ser_positivo(db_session: AsyncSession) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1)
    db_session.add(calculo)
    await db_session.flush()
    db_session.add(
        AjusteExtracontable(
            empresa_id=1,
            calculo_is_id=calculo.id,
            tipo=TipoAjusteExtracontable.AJUSTE_POSITIVO,
            descripcion="Ajuste inválido",
            importe=Decimal("0.0000"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_provisionales_repetidos_y_definitivo_unico(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 1)
    primero = _calculo(1)
    segundo = _calculo(1)
    db_session.add_all([primero, segundo])
    await db_session.flush()
    segundo.provisional = False
    await db_session.flush()
    db_session.add(_calculo(1, provisional=False))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_fk_empresa_calculo_rechaza_hijos_cross_tenant(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 1)
    await _empresa(db_session, 2)
    calculo = _calculo(1)
    db_session.add(calculo)
    await db_session.flush()
    db_session.add(
        AjusteExtracontable(
            empresa_id=2,
            calculo_is_id=calculo.id,
            tipo=TipoAjusteExtracontable.DEDUCCION,
            descripcion="Cross tenant",
            importe=Decimal("100.0000"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_calculado_permite_editar_financial(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1)
    db_session.add(calculo)
    await db_session.flush()
    calculo.resultado_contable = Decimal("110000.0000")
    await db_session.flush()
    persisted = await db_session.get(CalculoIS, calculo.id)
    assert persisted is not None
    assert persisted.resultado_contable == Decimal("110000.0000")


async def test_calculo_contabilizado_bloquea_update(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1, estado=EstadoCalculoIS.contabilizado)
    db_session.add(calculo)
    await db_session.flush()
    calculo.notas = "No mutable"
    with pytest.raises(IntegrityError, match="contabilizado"):
        await db_session.flush()
    await db_session.rollback()


async def test_calculo_contabilizado_bloquea_delete(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1, estado=EstadoCalculoIS.contabilizado)
    db_session.add(calculo)
    await db_session.flush()
    await db_session.delete(calculo)
    with pytest.raises(IntegrityError, match="contabilizado"):
        await db_session.flush()
    await db_session.rollback()


async def test_ajustes_bloqueados_con_calculo_contabilizado(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1, estado=EstadoCalculoIS.contabilizado)
    db_session.add(calculo)
    await db_session.flush()
    ajuste = AjusteExtracontable(
        empresa_id=1,
        calculo_is_id=calculo.id,
        tipo=TipoAjusteExtracontable.BONIFICACION,
        descripcion="Bloqueado",
        importe=Decimal("100.0000"),
    )
    db_session.add(ajuste)
    with pytest.raises(IntegrityError, match="contabilizado"):
        await db_session.flush()
    await db_session.rollback()


async def test_modelo_200_es_append_only(db_session: AsyncSession) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1, estado=EstadoCalculoIS.contabilizado)
    db_session.add(calculo)
    await db_session.flush()
    modelo = Modelo200(
        empresa_id=1,
        calculo_is_id=calculo.id,
        contenido={"bloque": {"resultado": "100000.0000"}},
        hash_contenido="a" * 64,
    )
    db_session.add(modelo)
    await db_session.flush()
    modelo.hash_contenido = "b" * 64
    with pytest.raises(IntegrityError, match="append-only"):
        await db_session.flush()
    await db_session.rollback()


async def test_configuracion_fiscal_default_y_rango(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 1)
    config = ConfiguracionFiscal(empresa_id=1)
    db_session.add(config)
    await db_session.flush()
    assert config.tipo_is == Decimal("25.00")
    assert config.fecha_vigencia_desde is not None
    config.tipo_is = Decimal("100.01")
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_seed_pgc_incluye_cuentas_is(db_session: AsyncSession) -> None:
    await _empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)
    codigos = set(
        (
            await db_session.scalars(
                select(AccountPlan.code).where(AccountPlan.tenant_id == 1)
            )
        ).all()
    )
    assert {"63", "630", "6300", "473", "4730", "475", "4751", "4752", "4709"} <= codigos
    detalle = await db_session.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == 1, AccountPlan.code == "6300"
        )
    )
    assert detalle is not None
    assert detalle.is_selectable is True


def test_configuracion_fiscal_fk_empresa() -> None:
    tabla = Base.metadata.tables["configuracion_fiscal"]
    assert any(
        columna.name == "empresa_id" and constraint.referred_table.name == "companies"
        for constraint in tabla.foreign_key_constraints
        for columna in constraint.columns
    )


async def test_asiento_cross_tenant_rechazado(db_session: AsyncSession) -> None:
    await _empresa(db_session, 1)
    await _empresa(db_session, 2)
    asiento = JournalEntry(
        empresa_id=1,
        ejercicio=2025,
        fecha=date(2025, 12, 31),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Empresa A",
        estado=JournalEntryEstado.DRAFT,
    )
    db_session.add(asiento)
    await db_session.flush()
    calculo = _calculo(2)
    calculo.asiento_id = asiento.id
    db_session.add(calculo)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_ajuste_update_bloqueado_con_padre_contabilizado(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1)
    db_session.add(calculo)
    await db_session.flush()
    ajuste = AjusteExtracontable(
        empresa_id=1,
        calculo_is_id=calculo.id,
        tipo=TipoAjusteExtracontable.AJUSTE_POSITIVO,
        descripcion="Original",
        importe=Decimal("100.0000"),
    )
    db_session.add(ajuste)
    await db_session.flush()
    calculo.estado = EstadoCalculoIS.contabilizado
    await db_session.flush()
    ajuste.importe = Decimal("200.0000")
    with pytest.raises(IntegrityError, match="contabilizado"):
        await db_session.flush()
    await db_session.rollback()


async def test_ajuste_delete_bloqueado_con_padre_contabilizado(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1)
    db_session.add(calculo)
    await db_session.flush()
    ajuste = AjusteExtracontable(
        empresa_id=1,
        calculo_is_id=calculo.id,
        tipo=TipoAjusteExtracontable.AJUSTE_POSITIVO,
        descripcion="Original",
        importe=Decimal("100.0000"),
    )
    db_session.add(ajuste)
    await db_session.flush()
    calculo.estado = EstadoCalculoIS.contabilizado
    await db_session.flush()
    await db_session.delete(ajuste)
    with pytest.raises(IntegrityError, match="contabilizado"):
        await db_session.flush()
    await db_session.rollback()


async def test_modelo_200_delete_bloqueado(db_session: AsyncSession) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1, estado=EstadoCalculoIS.contabilizado)
    db_session.add(calculo)
    await db_session.flush()
    modelo = Modelo200(
        empresa_id=1,
        calculo_is_id=calculo.id,
        contenido={"bloque": "inmutable"},
        hash_contenido="a" * 64,
    )
    db_session.add(modelo)
    await db_session.flush()
    await db_session.delete(modelo)
    with pytest.raises(IntegrityError, match="append-only"):
        await db_session.flush()
    await db_session.rollback()


async def test_un_solo_modelo_200_por_calculo(db_session: AsyncSession) -> None:
    await _empresa(db_session, 1)
    calculo = _calculo(1)
    db_session.add(calculo)
    await db_session.flush()
    db_session.add_all(
        [
            Modelo200(
                empresa_id=1,
                calculo_is_id=calculo.id,
                contenido={"numero": 1},
                hash_contenido="a" * 64,
            ),
            Modelo200(
                empresa_id=1,
                calculo_is_id=calculo.id,
                contenido={"numero": 2},
                hash_contenido="b" * 64,
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
