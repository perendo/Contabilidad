from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from models.acct.journal import JournalEntry, JournalEntryLine
from models.fiscal.calculo_is import CalculoIS


def crear_calculo(
    api: Any,
    *,
    provisional: bool = False,
    ejercicio: int = 2025,
    empresa_id: int = 10,
) -> dict[str, Any]:
    response = api.post(
        "/api/v1/fiscal/is/calculos",
        empresa_id=empresa_id,
        json={"ejercicio": ejercicio, "provisional": provisional},
    )
    assert response.status_code == 201, response.text
    return response.json()


def agregar_ajuste(
    api: Any,
    calculo_id: str,
    *,
    tipo: str,
    importe: str,
    descripcion: str = "Ajuste IS",
    empresa_id: int = 10,
) -> dict[str, Any]:
    response = api.post(
        f"/api/v1/fiscal/is/calculos/{calculo_id}/ajustes",
        empresa_id=empresa_id,
        json={"tipo": tipo, "descripcion": descripcion, "importe": importe},
    )
    assert response.status_code == 201, response.text
    return response.json()


def contabilizar(
    api: Any,
    calculo_id: str,
    *,
    fecha: str = "2025-12-31",
    empresa_id: int = 10,
) -> dict[str, Any]:
    response = api.post(
        f"/api/v1/fiscal/is/calculos/{calculo_id}/contabilizar",
        empresa_id=empresa_id,
        json={"fecha_asiento": fecha},
    )
    assert response.status_code == 200, response.text
    return response.json()


def obtener_calculo(api: Any, calculo_id: str, empresa_id: int = 10) -> CalculoIS:
    async def _query(session):
        return await session.scalar(
            select(CalculoIS).where(
                CalculoIS.empresa_id == empresa_id,
                CalculoIS.id == uuid.UUID(calculo_id),
            )
        )

    calculo = api.run(api.consultar(_query))
    assert calculo is not None
    return calculo


def obtener_asiento(api: Any, asiento_id: str, empresa_id: int = 10) -> JournalEntry:
    async def _query(session):
        return await session.scalar(
            select(JournalEntry).where(
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.id == uuid.UUID(asiento_id),
            )
        )

    asiento = api.run(api.consultar(_query))
    assert asiento is not None
    return asiento


def obtener_lineas(
    api: Any, asiento_id: str, empresa_id: int = 10
) -> list[JournalEntryLine]:
    async def _query(session):
        return list(
            (
                await session.scalars(
                    select(JournalEntryLine)
                    .where(
                        JournalEntryLine.empresa_id == empresa_id,
                        JournalEntryLine.journal_entry_id == uuid.UUID(asiento_id),
                    )
                    .order_by(JournalEntryLine.line_no)
                )
            ).all()
        )

    return api.run(api.consultar(_query))


def sumas_lineas(lineas: list[JournalEntryLine]) -> tuple[Decimal, Decimal]:
    return (
        sum((linea.debe for linea in lineas), Decimal("0.0000")),
        sum((linea.haber for linea in lineas), Decimal("0.0000")),
    )
