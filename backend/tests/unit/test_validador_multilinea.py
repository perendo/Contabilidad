"""T004: Tests del validador multilínea (SPEC-006 Phase 2)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.journal.validador_multilinea import (
    MultilineaError,
    validar_asiento_multilinea,
)
from tests.conftest import sembrar_empresa_pgc

DEBE_6000 = {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000", "detalle": "compra"}
DEBE_6210 = {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000", "detalle": "alquiler"}
DEBE_6400 = {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000", "detalle": "sueldo"}
HABER_4000 = {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000", "detalle": "prov A"}
HABER_4100 = {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000", "detalle": "prov B"}
HABER_5720 = {"cuenta": "5720", "debe": "0.0000", "haber": "300.0000", "detalle": "banco"}


async def _contexto(db: AsyncSession) -> None:
    await sembrar_empresa_pgc(db, 10)
    await db.flush()


async def test_balance_3_2_pasa(db_session):
    await _contexto(db_session)
    lineas, cuentas = await validar_asiento_multilinea(
        db_session,
        empresa_id=10,
        lineas=[DEBE_6000, DEBE_6210, DEBE_6400, HABER_4000, HABER_4100],
    )
    assert len(lineas) == 5
    assert set(cuentas) == {"6000", "6210", "6400", "4000", "4100"}
    assert all(l["account_id"] is not None for l in lineas)


async def test_caso_clasico_1_1_pasa(db_session):
    await _contexto(db_session)
    lineas, cuentas = await validar_asiento_multilinea(
        db_session, empresa_id=10, lineas=[DEBE_6000, HABER_5720]
    )
    assert len(lineas) == 2
    assert set(cuentas) == {"6000", "5720"}


async def test_lado_vacio_haber(db_session):
    await _contexto(db_session)
    with pytest.raises(MultilineaError) as exc:
        await validar_asiento_multilinea(
            db_session, empresa_id=10, lineas=[DEBE_6000, DEBE_6210]
        )
    assert exc.value.code == "lado_vacio"
    assert "HABER" in str(exc.value)


async def test_lado_vacio_debe(db_session):
    await _contexto(db_session)
    with pytest.raises(MultilineaError) as exc:
        await validar_asiento_multilinea(
            db_session, empresa_id=10, lineas=[HABER_4000, HABER_4100]
        )
    assert exc.value.code == "lado_vacio"
    assert "DEBE" in str(exc.value)


async def test_desbalanceo(db_session):
    await _contexto(db_session)
    with pytest.raises(MultilineaError) as exc:
        await validar_asiento_multilinea(
            db_session,
            empresa_id=10,
            lineas=[{**DEBE_6000, "debe": "500.0000"}, HABER_4000],
        )
    assert exc.value.code == "desbalanceo"


async def test_linea_con_ambos_campos(db_session):
    await _contexto(db_session)
    mala = {"cuenta": "6000", "debe": "100.0000", "haber": "100.0000"}
    with pytest.raises(MultilineaError) as exc:
        await validar_asiento_multilinea(db_session, empresa_id=10, lineas=[mala, HABER_5720])
    assert exc.value.code == "linea_invalida"


async def test_linea_vacia(db_session):
    await _contexto(db_session)
    vacia = {"cuenta": "6000", "debe": "0.0000", "haber": "0.0000"}
    with pytest.raises(MultilineaError) as exc:
        await validar_asiento_multilinea(db_session, empresa_id=10, lineas=[vacia, HABER_5720])
    assert exc.value.code == "linea_invalida"


async def test_cuenta_inexistente(db_session):
    await _contexto(db_session)
    con = {"cuenta": "9990000", "debe": "300.0000", "haber": "0.0000"}
    with pytest.raises(MultilineaError) as exc:
        await validar_asiento_multilinea(db_session, empresa_id=10, lineas=[con, HABER_5720])
    assert exc.value.code == "cuenta_no_encontrada"


async def test_cuenta_no_apuntable(db_session):
    await _contexto(db_session)
    con = {"cuenta": "400", "debe": "300.0000", "haber": "0.0000"}
    with pytest.raises(MultilineaError) as exc:
        await validar_asiento_multilinea(db_session, empresa_id=10, lineas=[con, HABER_5720])
    assert exc.value.code == "cuenta_no_apuntable"


async def test_limite_lineas(db_session):
    await _contexto(db_session)
    lineas = [
        {"cuenta": "6000" if i % 2 else "6210", "debe": "1.0000", "haber": "0.0000"}
        for i in range(60)
    ]
    lineas += [
        {"cuenta": "4000", "debe": "0.0000", "haber": "5.0000"} for _ in range(60)
    ]
    with pytest.raises(MultilineaError) as exc:
        await validar_asiento_multilinea(db_session, empresa_id=10, lineas=lineas, limite=100)
    assert exc.value.code == "limite_lineas_excedido"


async def test_cuenta_repetida_admitida(db_session):
    await _contexto(db_session)
    lineas, _ = await validar_asiento_multilinea(
        db_session,
        empresa_id=10,
        lineas=[DEBE_6000, DEBE_6000, HABER_5720, HABER_5720],
    )
    assert len(lineas) == 4