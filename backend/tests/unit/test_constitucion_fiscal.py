"""Constitucion V aplicada al modulo fiscal (SPEC-012 FR-012/T050)."""

from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.fiscal.exportacion_modelo import ExportacionModelo

IMPORTE = re.compile(r"^-?\d+\.\d{4}$")


def _importes(payload) -> list[str]:
    encontrados: list[str] = []
    if isinstance(payload, dict):
        for clave, valor in payload.items():
            if isinstance(valor, str) and ("importe" in clave or "total" in clave or "cuota" in clave or "base" in clave):
                encontrados.append(valor)
            else:
                encontrados.extend(_importes(valor))
    elif isinstance(payload, list):
        for item in payload:
            encontrados.extend(_importes(item))
    return encontrados


def test_importes_precision_fiscal(fiscal_client) -> None:
    fac = fiscal_client
    libro = fac.get(
        10, "/api/v1/libros-iva/emitidas", ejercicio=2026, periodo=1, tipo_periodo="TRIMESTRE"
    ).json()
    for importe in _importes(libro):
        assert IMPORTE.match(importe), importe
    m303 = fac.get(
        10, "/api/v1/modelos/303", ejercicio=2026, periodo=1, tipo_periodo="TRIMESTRE"
    ).json()
    for importe in _importes(m303):
        assert IMPORTE.match(importe), importe


def test_asientos_que_sustentan_libros_cuadran(fiscal_client) -> None:
    fac = fiscal_client

    async def _saldos(session):
        debe = await session.scalar(
            select(func.sum(JournalEntryLine.debe)).where(
                JournalEntryLine.empresa_id == 10
            )
        )
        haber = await session.scalar(
            select(func.sum(JournalEntryLine.haber)).where(
                JournalEntryLine.empresa_id == 10
            )
        )
        return Decimal(debe or 0), Decimal(haber or 0)

    debe, haber = fac.run(fac.consultar(_saldos))
    assert debe == haber


def test_exportacion_no_muta_asientos(fiscal_client) -> None:
    fac = fiscal_client

    async def _contar(session):
        return int(
            await session.scalar(
                select(func.count())
                .select_from(JournalEntry)
                .where(
                    JournalEntry.empresa_id == 10,
                    JournalEntry.estado == JournalEntryEstado.POSTED,
                )
            )
            or 0
        )

    antes = fac.run(fac.consultar(_contar))
    r = fac.post(
        "/api/v1/fiscal/exportaciones",
        json={"modelo": "303", "ejercicio": 2026, "periodo": 1},
    )
    assert r.status_code == 201
    assert fac.run(fac.consultar(_contar)) == antes


def test_tablas_fiscales_aisladas_por_empresa(fiscal_client) -> None:
    fac = fiscal_client
    fac.post(
        "/api/v1/fiscal/exportaciones",
        json={"modelo": "303", "ejercicio": 2026, "periodo": 1},
    )

    async def _comprobar(session):
        a = await session.scalar(
            select(func.count())
            .select_from(ExportacionModelo)
            .where(ExportacionModelo.empresa_id == 10)
        )
        b = await session.scalar(
            select(func.count())
            .select_from(ExportacionModelo)
            .where(ExportacionModelo.empresa_id == 20)
        )
        return a, b

    a, b = fac.run(fac.consultar(_comprobar))
    assert a == 1
    assert b == 0