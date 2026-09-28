"""Exportación del libro diario a CSV/XLSX (SPEC-005 US3)."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
)

CABECERAS = ["fecha", "numero_asiento", "concepto", "cuenta", "debe", "haber", "detalle"]
CUATRO = Decimal("0.0000")


async def _asientos(
    db: AsyncSession, empresa_id: int, fecha_desde: date, fecha_hasta: date
) -> list[tuple]:
    entradas = (
        await db.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.empresa_id == empresa_id,
                JournalEntry.estado == JournalEntryEstado.POSTED,
                JournalEntry.fecha >= fecha_desde,
                JournalEntry.fecha <= fecha_hasta,
            )
            .order_by(JournalEntry.fecha, JournalEntry.numero_asiento)
        )
    ).all()
    filas: list[tuple] = []
    for entrada in entradas:
        lineas = (
            await db.scalars(
                select(JournalEntryLine)
                .where(
                    JournalEntryLine.empresa_id == empresa_id,
                    JournalEntryLine.journal_entry_id == entrada.id,
                )
                .order_by(JournalEntryLine.line_no)
            )
        ).all()
        for linea in lineas:
            filas.append((entrada, linea))
    return filas


def _fila_valores(entrada: JournalEntry, linea: JournalEntryLine) -> list:
    return [
        entrada.fecha.isoformat(),
        entrada.numero_asiento,
        entrada.concepto,
        linea.cuenta,
        f"{linea.debe.quantize(CUATRO)}",
        f"{linea.haber.quantize(CUATRO)}",
        linea.descripcion or "",
    ]


def generar_csv(filas: list[tuple]) -> bytes:
    """CSV with UTF-8 BOM, ';' separator and 4-decimal amounts."""
    buffer = io.StringIO()
    buffer.write(";".join(CABECERAS) + "\n")
    for entrada, linea in filas:
        valores = _fila_valores(entrada, linea)
        buffer.write(";".join("" if v is None else str(v) for v in valores) + "\n")
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def generar_xlsx(filas: list[tuple]) -> bytes:
    """XLSX with a 'Diario' sheet and 4-decimal numeric amounts."""
    import openpyxl

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Diario"
    hoja.append(CABECERAS)
    for entrada, linea in filas:
        valores = _fila_valores(entrada, linea)
        hoja.append(valores)
        hoja.cell(row=hoja.max_row, column=5).number_format = "0.0000"
        hoja.cell(row=hoja.max_row, column=6).number_format = "0.0000"
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


async def exportar_diario(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha_desde: date,
    fecha_hasta: date,
    formato: str,
) -> tuple[bytes, str, str]:
    """Return (contenido, nombre_fichero, media_type) for the active company."""
    filas = await _asientos(db, empresa_id, fecha_desde, fecha_hasta)
    base = f"diario_{fecha_desde.isoformat()}_{fecha_hasta.isoformat()}"
    if formato.upper() == "XLSX":
        return generar_xlsx(filas), f"{base}.xlsx", (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    return generar_csv(filas), f"{base}.csv", "text/csv; charset=utf-8"
