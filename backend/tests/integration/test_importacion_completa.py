"""Tests SPEC-013 US1 (T016/T023/T024): importación de extractos y aislamiento."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.treasury.extracto_bancario import ExtractoBancario
from models.treasury.movimiento_bancario import MovimientoBancario
from services.reconciliation.importacion import ImportacionError, importar_extracto
from tests.conftest import sembrar_empresa_pgc

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _leer(nombre: str) -> bytes:
    return (FIXTURES / nombre).read_bytes()


async def test_importar_valido_persiste_extracto_y_movimientos(db_session: AsyncSession) -> None:
    await sembrar_empresa_pgc(db_session, 10)
    extracto = await importar_extracto(
        db_session, empresa_id=10, file_bytes=_leer("extracto_43_19_valido.txt"),
        nombre_fichero="valido.txt", layout="norma_43_1919", actor="t",
    )
    assert extracto.n_movimientos == 3
    assert extracto.saldo_final == extracto.saldo_final
    n = await db_session.scalar(
        select(func.count(MovimientoBancario.id)).where(MovimientoBancario.extracto_id == extracto.id)
    )
    assert n == 3


async def test_reimportar_mismo_fichero_409(db_session: AsyncSession) -> None:
    await sembrar_empresa_pgc(db_session, 10)
    datos = _leer("extracto_43_19_valido.txt")
    await importar_extracto(
        db_session, empresa_id=10, file_bytes=datos, nombre_fichero="a.txt", actor="t"
    )
    with pytest.raises(ImportacionError) as exc:
        await importar_extracto(
            db_session, empresa_id=10, file_bytes=datos, nombre_fichero="b.txt", actor="t"
        )
    assert exc.value.code == "extracto_duplicado"
    n = await db_session.scalar(select(func.count(ExtractoBancario.id)))
    assert n == 1


async def test_malformado_422_sin_persistencia(db_session: AsyncSession) -> None:
    await sembrar_empresa_pgc(db_session, 10)
    with pytest.raises(ImportacionError) as exc:
        await importar_extracto(
            db_session, empresa_id=10, file_bytes=_leer("extracto_43_19_malformado.txt"),
            nombre_fichero="mal.txt", actor="t",
        )
    assert exc.value.code == "layout_invalido"
    assert await db_session.scalar(select(func.count(ExtractoBancario.id))) == 0
    assert await db_session.scalar(select(func.count(MovimientoBancario.id))) == 0


async def test_cuenta_otra_empresa_404(db_session: AsyncSession) -> None:
    await sembrar_empresa_pgc(db_session, 10)
    await sembrar_empresa_pgc(db_session, 20)
    with pytest.raises(ImportacionError) as exc:
        await importar_extracto(
            db_session, empresa_id=10,
            file_bytes=_leer("extracto_43_19_otra_empresa.txt"),
            nombre_fichero="otra.txt", actor="t",
        )
    assert exc.value.code == "cuenta_no_encontrada"
