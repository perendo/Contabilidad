from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import UniqueConstraint, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.fiscal.retenciones import (
    ContabilizarBody,
    LiquidacionBody,
    Modelo190Body,
    ModeloLiquidacionBody,
)
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.audit.audit_log import AuditLog
from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from models.fiscal.modelo_111 import Modelo111
from models.fiscal.modelo_115 import Modelo115
from models.fiscal.modelo_190 import Modelo190
from models.fiscal.retencion import RetencionPeriodo
from models.invoice.factura_linea import FacturaLinea
from services.fiscal.liquidacion_retenciones import contabilizar_liquidacion
from tests.conftest import sembrar_empresa_pgc

MODELOS_TENANT = (
    LiquidacionRetenciones,
    RetencionPeriodo,
    Modelo111,
    Modelo115,
    Modelo190,
    FacturaLinea,
)


async def _crear_liquidacion(
    db: AsyncSession,
    *,
    trimestre: int,
    total: Decimal,
) -> LiquidacionRetenciones:
    liquidacion = LiquidacionRetenciones(
        empresa_id=1,
        ejercicio=2025,
        trimestre=trimestre,
        periodo=f"2025-Q{trimestre}",
        total_base_retenciones=total * Decimal(10),
        total_retenciones=total,
        n_perceptores=1,
    )
    db.add(liquidacion)
    await db.flush()
    return liquidacion


async def test_asientos_de_liquidacion_cuadran_y_quedan_posted(
    db_session: AsyncSession,
) -> None:
    await sembrar_empresa_pgc(db_session, 1)
    liquificaciones = (
        (1, Decimal("1250.0000")),
        (2, Decimal("2375.5000")),
    )
    ids: list[tuple[uuid.UUID, Decimal]] = []

    for trimestre, total in liquificaciones:
        liquidacion = await _crear_liquidacion(
            db_session,
            trimestre=trimestre,
            total=total,
        )
        resultado = await contabilizar_liquidacion(
            db_session,
            liquidacion_id=liquidacion.id,
            empresa_id=1,
            fecha_asiento=date(2025, trimestre * 3, 30),
            actor="constitucion@test",
            ip="127.0.0.1",
        )
        await db_session.flush()
        ids.append((resultado["asiento_id"], total))

    await db_session.commit()

    for asiento_id, total in ids:
        asiento = await db_session.get(JournalEntry, asiento_id)
        assert asiento is not None
        assert asiento.empresa_id == 1
        assert asiento.estado == JournalEntryEstado.POSTED
        lineas = (
            await db_session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.empresa_id == 1,
                    JournalEntryLine.journal_entry_id == asiento_id,
                )
            )
        ).all()
        assert len(lineas) == 2
        assert sum((linea.debe for linea in lineas), Decimal("0.0000")) == total
        assert sum((linea.haber for linea in lineas), Decimal("0.0000")) == total

    auditorias = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.empresa_id == 1,
                AuditLog.operacion == "CONTABILIZAR_LIQUIDACION",
            )
        )
    ).all()
    assert len(auditorias) == len(ids)
    for auditoria in auditorias:
        payload = json.loads(auditoria.payload or "{}")
        assert Decimal(payload["total_retenciones"]) > 0
        assert auditoria.usuario == "constitucion@test"
        assert auditoria.ip == "127.0.0.1"


async def test_posted_de_liquidacion_bloquea_update_y_delete_en_db(
    db_session: AsyncSession,
) -> None:
    await sembrar_empresa_pgc(db_session, 1)
    liquidacion = await _crear_liquidacion(
        db_session,
        trimestre=3,
        total=Decimal("1000.0000"),
    )
    resultado = await contabilizar_liquidacion(
        db_session,
        liquidacion_id=liquidacion.id,
        empresa_id=1,
        fecha_asiento=date(2025, 9, 30),
    )
    asiento_id = resultado["asiento_id"]
    await db_session.commit()

    with pytest.raises(IntegrityError, match="inmutable"):
        await db_session.execute(
            text(
                "UPDATE journal_entry SET concepto = :concepto "
                "WHERE empresa_id = :empresa_id AND id = :id"
            ),
            {
                "concepto": "alterado",
                "empresa_id": 1,
                "id": asiento_id.hex,
            },
        )
    await db_session.rollback()

    with pytest.raises(IntegrityError, match="inmutable"):
        await db_session.execute(
            text(
                "DELETE FROM journal_entry "
                "WHERE empresa_id = :empresa_id AND id = :id"
            ),
            {"empresa_id": 1, "id": asiento_id.hex},
        )
    await db_session.rollback()

    linea_id = await db_session.scalar(
        select(JournalEntryLine.id).where(
            JournalEntryLine.empresa_id == 1,
            JournalEntryLine.journal_entry_id == asiento_id,
        )
    )
    assert linea_id is not None
    with pytest.raises(IntegrityError, match="inmutable"):
        await db_session.execute(
            text(
                "UPDATE journal_entry_line SET debe = :debe "
                "WHERE empresa_id = :empresa_id AND id = :id"
            ),
            {"debe": "1.0000", "empresa_id": 1, "id": linea_id.hex},
        )
    await db_session.rollback()

    with pytest.raises(IntegrityError, match="inmutable"):
        await db_session.execute(
            text(
                "DELETE FROM journal_entry_line "
                "WHERE empresa_id = :empresa_id AND id = :id"
            ),
            {"empresa_id": 1, "id": linea_id.hex},
        )
    await db_session.rollback()


@pytest.mark.parametrize("modelo", MODELOS_TENANT)
def test_todas_las_tablas_de_retenciones_tienen_empresa(modelo) -> None:
    tabla = modelo.__table__
    assert "empresa_id" in tabla.c
    assert any("empresa_id" in index.columns for index in tabla.indexes)
    assert any(
        isinstance(constraint, UniqueConstraint)
        and "empresa_id" in constraint.columns
        for constraint in tabla.constraints
    )


def test_cuerpos_y_servicios_cumplen_frontera_de_transaccion_y_decimal() -> None:
    for modelo in (LiquidacionBody, ModeloLiquidacionBody, Modelo190Body, ContabilizarBody):
        assert "empresa_id" not in modelo.model_fields

    raiz = Path(__file__).resolve().parents[2]
    api_source = (raiz / "src/api/fiscal/retenciones.py").read_text(encoding="utf-8")
    assert "NotImplementedError" not in api_source
    assert "status.HTTP_501_NOT_IMPLEMENTED" not in api_source
    for nombre in (
        "retenciones.py",
        "liquidacion_retenciones.py",
        "modelo_111_gen.py",
        "modelo_115_gen.py",
        "modelo_190_gen.py",
    ):
        source = (raiz / "src/services/fiscal" / nombre).read_text(encoding="utf-8")
        assert "session.begin" not in source
        assert "async_session.begin" not in source
        assert "float(" not in source
