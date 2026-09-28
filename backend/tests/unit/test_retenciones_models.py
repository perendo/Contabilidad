from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from base import Base
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryTipo
from models.ar.tercero import Tercero
from models.fiscal.liquidacion_retenciones import (
    EstadoLiquidacionRetenciones,
    LiquidacionRetenciones,
)
from models.fiscal.modelo_111 import Modelo111
from models.fiscal.modelo_115 import Modelo115
from models.fiscal.modelo_190 import Modelo190
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from models.iam.company import Company

TABLAS = {
    "liquidacion_retenciones",
    "retencion_periodo",
    "modelo_111",
    "modelo_115",
    "modelo_190",
}


def _unicos(tabla_nombre: str) -> set[tuple[str, ...]]:
    tabla = Base.metadata.tables[tabla_nombre]
    return {
        tuple(columna.name for columna in constraint.columns)
        for constraint in tabla.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _checks(tabla_nombre: str) -> set[str]:
    tabla = Base.metadata.tables[tabla_nombre]
    return {
        str(constraint.sqltext)
        for constraint in tabla.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _fk_a(tabla_nombre: str, destino: str) -> list[tuple[str, ...]]:
    tabla = Base.metadata.tables[tabla_nombre]
    return [
        tuple(columna.name for columna in fk.columns)
        for fk in tabla.foreign_key_constraints
        if fk.elements and fk.elements[0].column.table.name == destino
    ]


async def _empresa(db: AsyncSession, empresa_id: int) -> None:
    db.add(
        Company(
            company_id=empresa_id,
            nif=f"T{empresa_id:08d}",
            razon_social=f"Empresa {empresa_id}",
        )
    )
    await db.flush()


async def _tercero(db: AsyncSession, empresa_id: int, nif: str | None) -> Tercero:
    tercero = Tercero(
        empresa_id=empresa_id,
        nombre=f"Perceptor {empresa_id}",
        nif=nif,
        es_cliente=False,
        es_proveedor=True,
    )
    db.add(tercero)
    await db.flush()
    return tercero


def _liquidacion(
    empresa_id: int,
    *,
    trimestre: int = 3,
    total_base: Decimal = Decimal("1000.0000"),
    total_retenciones: Decimal = Decimal("150.0000"),
) -> LiquidacionRetenciones:
    return LiquidacionRetenciones(
        empresa_id=empresa_id,
        ejercicio=2025,
        trimestre=trimestre,
        periodo=f"2025-Q{trimestre}",
        total_base_retenciones=total_base,
        total_retenciones=total_retenciones,
        n_perceptores=1,
    )


def test_modelos_registrados_con_uuid_y_tipos_decimales() -> None:
    assert TABLAS <= set(Base.metadata.tables)
    for tabla_nombre in TABLAS:
        tabla = Base.metadata.tables[tabla_nombre]
        assert [columna.name for columna in tabla.primary_key.columns] == ["id"]
        assert ("empresa_id", "id") in _unicos(tabla_nombre)

    assert str(Base.metadata.tables["liquidacion_retenciones"].columns["total_base_retenciones"].type) in {
        "NUMERIC(18, 4)",
        "NUMERIC(18,4)",
    }
    assert str(Base.metadata.tables["retencion_periodo"].columns["base_imponible"].type) in {
        "NUMERIC(18, 4)",
        "NUMERIC(18,4)",
    }
    assert str(Base.metadata.tables["retencion_periodo"].columns["tipo_porcentaje"].type) in {
        "NUMERIC(5, 2)",
        "NUMERIC(5,2)",
    }
    assert str(Base.metadata.tables["modelo_190"].columns["contenido"].type) in {
        "JSON",
        "JSONB",
    }


def test_unicidades_y_fks_compuestas_de_retenciones() -> None:
    assert ("empresa_id", "ejercicio", "trimestre") in _unicos(
        "liquidacion_retenciones"
    )
    assert ("empresa_id", "liquidacion_retenciones_id") in _unicos("modelo_111")
    assert ("empresa_id", "liquidacion_retenciones_id") in _unicos("modelo_115")
    assert ("empresa_id", "ejercicio") in _unicos("modelo_190")
    assert ("empresa_id", "liquidacion_retenciones_id") in _fk_a(
        "retencion_periodo", "liquidacion_retenciones"
    )
    assert ("empresa_id", "tercero_id") in _fk_a("retencion_periodo", "tercero")
    assert ("empresa_id", "modelo_111_id") in _fk_a(
        "liquidacion_retenciones", "modelo_111"
    )
    assert ("empresa_id", "modelo_115_id") in _fk_a(
        "liquidacion_retenciones", "modelo_115"
    )


def test_checks_de_trimestre_importes_y_formula() -> None:
    liquidacion_checks = _checks("liquidacion_retenciones")
    retencion_checks = _checks("retencion_periodo")
    assert any("trimestre BETWEEN 1 AND 4" in check for check in liquidacion_checks)
    assert any("total_base_retenciones >= 0" in check for check in liquidacion_checks)
    assert any("total_retenciones >= 0" in check for check in liquidacion_checks)
    assert any("base_imponible > 0" in check for check in retencion_checks)
    assert any("retencion_practicada > 0" in check for check in retencion_checks)
    assert any("tipo_porcentaje > 0" in check for check in retencion_checks)
    assert any("tipo_porcentaje <= 100" in check for check in retencion_checks)
    assert any("ABS(retencion_practicada" in check for check in retencion_checks)


async def test_liquidacion_unica_por_empresa_y_trimestre(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    db_session.add_all([_liquidacion(10), _liquidacion(20)])
    await db_session.flush()
    db_session.add(_liquidacion(10))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_liquidacion_rechaza_trimestre_invalido(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    db_session.add(_liquidacion(10, trimestre=5))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_retencion_admite_nif_vacio_y_valida_formula(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    tercero = await _tercero(db_session, 10, None)
    liquidacion = _liquidacion(10)
    db_session.add(liquidacion)
    await db_session.flush()
    db_session.add(
        RetencionPeriodo(
            empresa_id=10,
            liquidacion_retenciones_id=liquidacion.id,
            tercero_id=tercero.id,
            nif="",
            nombre=tercero.nombre,
            tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
            base_imponible=Decimal("1000.0000"),
            tipo_porcentaje=Decimal("15.00"),
            retencion_practicada=Decimal("150.0000"),
            facturas=[],
        )
    )
    await db_session.flush()

    db_session.add(
        RetencionPeriodo(
            empresa_id=10,
            liquidacion_retenciones_id=liquidacion.id,
            tercero_id=tercero.id,
            nif="12345678Z",
            nombre="Otro",
            tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
            base_imponible=Decimal("1000.0000"),
            tipo_porcentaje=Decimal("15.00"),
            retencion_practicada=Decimal("151.0000"),
            facturas=[],
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_fk_retencion_rechaza_tercero_de_otra_empresa(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    tercero_a = await _tercero(db_session, 10, "12345678Z")
    liquidacion_b = _liquidacion(20)
    db_session.add(liquidacion_b)
    await db_session.flush()
    db_session.add(
        RetencionPeriodo(
            empresa_id=20,
            liquidacion_retenciones_id=liquidacion_b.id,
            tercero_id=tercero_a.id,
            nif="12345678Z",
            nombre="Cross tenant",
            tipo_retencion=TipoRetencion.IRPF_OTROS,
            base_imponible=Decimal("100.0000"),
            tipo_porcentaje=Decimal("10.00"),
            retencion_practicada=Decimal("10.0000"),
            facturas=[],
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_modelos_unicos_por_liquidacion_y_190_por_ejercicio(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    liquidacion = _liquidacion(10)
    db_session.add(liquidacion)
    await db_session.flush()
    db_session.add(
        Modelo111(
            empresa_id=10,
            liquidacion_retenciones_id=liquidacion.id,
            ejercicio=2025,
            trimestre=3,
            contenido={"bloque": 1},
            hash_contenido="a" * 64,
        )
    )
    await db_session.flush()
    db_session.add(
        Modelo111(
            empresa_id=10,
            liquidacion_retenciones_id=liquidacion.id,
            ejercicio=2025,
            trimestre=3,
            contenido={"bloque": 1},
            hash_contenido="b" * 64,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_modelo_190_unico_por_empresa_y_ejercicio(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    db_session.add(
        Modelo190(
            empresa_id=10,
            ejercicio=2025,
            contenido={"bloque": 1},
            hash_contenido="a" * 64,
            n_perceptores=1,
        )
    )
    await db_session.flush()
    db_session.add(
        Modelo190(
            empresa_id=10,
            ejercicio=2025,
            contenido={"bloque": 1},
            hash_contenido="b" * 64,
            n_perceptores=1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_liquidacion_pendiente_admite_enlaces_y_liquidada_es_final(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    liquidacion = _liquidacion(10)
    db_session.add(liquidacion)
    await db_session.flush()
    modelo_111 = Modelo111(
        empresa_id=10,
        liquidacion_retenciones_id=liquidacion.id,
        ejercicio=2025,
        trimestre=3,
        contenido={"bloque": 1},
        hash_contenido="a" * 64,
    )
    db_session.add(modelo_111)
    await db_session.flush()
    liquidacion.modelo_111_id = modelo_111.id
    liquidacion.notas = "Pendiente"
    await db_session.flush()

    asiento = JournalEntry(
        empresa_id=10,
        ejercicio=2025,
        fecha=date(2025, 9, 30),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Liquidacion",
        estado=JournalEntryEstado.DRAFT,
    )
    db_session.add(asiento)
    await db_session.flush()
    liquidacion.asiento_id = asiento.id
    liquidacion.fecha_liquidacion = date(2025, 9, 30)
    liquidacion.estado = EstadoLiquidacionRetenciones.liquidado
    await db_session.flush()
    liquidacion.notas = "No mutable"
    with pytest.raises(IntegrityError, match="liquidado"):
        await db_session.flush()
    await db_session.rollback()


async def test_liquidacion_liquidada_bloquea_delete(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    liquidacion = _liquidacion(10)
    db_session.add(liquidacion)
    await db_session.flush()
    asiento = JournalEntry(
        empresa_id=10,
        ejercicio=2025,
        fecha=date(2025, 9, 30),
        tipo=JournalEntryTipo.GENERAL,
        concepto="Liquidacion",
        estado=JournalEntryEstado.DRAFT,
    )
    db_session.add(asiento)
    await db_session.flush()
    liquidacion.asiento_id = asiento.id
    liquidacion.fecha_liquidacion = date(2025, 9, 30)
    liquidacion.estado = EstadoLiquidacionRetenciones.liquidado
    await db_session.flush()
    await db_session.delete(liquidacion)
    with pytest.raises(IntegrityError, match="liquidado"):
        await db_session.flush()
    await db_session.rollback()


async def test_modelo_111_append_only(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    liquidacion = _liquidacion(10)
    db_session.add(liquidacion)
    await db_session.flush()
    modelo = Modelo111(
        empresa_id=10,
        liquidacion_retenciones_id=liquidacion.id,
        ejercicio=2025,
        trimestre=3,
        contenido={"bloque": 1},
        hash_contenido="a" * 64,
    )
    db_session.add(modelo)
    await db_session.flush()
    modelo.hash_contenido = "b" * 64
    with pytest.raises(IntegrityError, match="append-only"):
        await db_session.flush()
    await db_session.rollback()


async def test_modelo_115_append_only_delete(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    liquidacion = _liquidacion(10)
    db_session.add(liquidacion)
    await db_session.flush()
    modelo = Modelo115(
        empresa_id=10,
        liquidacion_retenciones_id=liquidacion.id,
        ejercicio=2025,
        trimestre=3,
        contenido={"bloque": 1},
        hash_contenido="a" * 64,
    )
    db_session.add(modelo)
    await db_session.flush()
    await db_session.delete(modelo)
    with pytest.raises(IntegrityError, match="append-only"):
        await db_session.flush()
    await db_session.rollback()


async def test_modelo_190_append_only_update(
    db_session: AsyncSession,
) -> None:
    await _empresa(db_session, 10)
    modelo = Modelo190(
        empresa_id=10,
        ejercicio=2025,
        contenido={"bloque": 1},
        hash_contenido="a" * 64,
        n_perceptores=1,
    )
    db_session.add(modelo)
    await db_session.flush()
    modelo.n_perceptores = 2
    with pytest.raises(IntegrityError, match="append-only"):
        await db_session.flush()
    await db_session.rollback()
