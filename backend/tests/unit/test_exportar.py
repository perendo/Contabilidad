"""Tests SPEC-005 US3 (T029-T031): exportación CSV/XLSX y aislamiento."""

from __future__ import annotations

import io
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from services.acct.seed import seed_default_pgc
from services.importexport.exportador import exportar_diario
from services.importexport.importador import importar_asientos

CABECERA = "fecha;numero_asiento;concepto;cuenta;debe;haber\n"


def _csv(*lineas: str) -> bytes:
    return (CABECERA + "\n".join(lineas)).encode("utf-8")


async def _empresa(db: AsyncSession, cid: int) -> None:
    db.add(Company(company_id=cid, nif=f"T{cid:08d}", razon_social=f"E{cid} SL"))
    await db.flush()
    await seed_default_pgc(db, cid)


async def _importar(db: AsyncSession, cid: int) -> None:
    await importar_asientos(
        db, empresa_id=cid, nombre="a.csv", actor="t",
        file_bytes=_csv(
            "2026-05-01;1;Venta;4300;100,50;0",
            "2026-05-01;1;Venta;5720;0;100,50",
        ),
    )


async def test_exportar_csv_bom_separador_y_decimales(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    await _importar(db_session, 10)
    contenido, nombre, media = await exportar_diario(
        db_session, empresa_id=10,
        fecha_desde=date(2026, 1, 1), fecha_hasta=date(2026, 12, 31), formato="CSV",
    )
    assert contenido.startswith(b"\xef\xbb\xbf")
    assert nombre.endswith(".csv")
    assert "text/csv" in media
    texto = contenido.decode("utf-8-sig")
    assert ";" in texto
    assert "100.5000" in texto
    assert texto.splitlines()[0].startswith("fecha;numero_asiento")


async def test_exportar_xlsx_hoja_diario(db_session: AsyncSession) -> None:
    import openpyxl

    await _empresa(db_session, 10)
    await _importar(db_session, 10)
    contenido, nombre, _ = await exportar_diario(
        db_session, empresa_id=10,
        fecha_desde=date(2026, 1, 1), fecha_hasta=date(2026, 12, 31), formato="XLSX",
    )
    assert nombre.endswith(".xlsx")
    libro = openpyxl.load_workbook(io.BytesIO(contenido))
    hoja = libro.active
    assert hoja.title == "Diario"
    assert [c.value for c in hoja[1]] == [
        "fecha", "numero_asiento", "concepto", "cuenta", "debe", "haber", "detalle",
    ]


async def test_exportar_aislamiento_entre_empresas(db_session: AsyncSession) -> None:
    await _empresa(db_session, 10)
    await _empresa(db_session, 20)
    await _importar(db_session, 10)
    contenido, _, _ = await exportar_diario(
        db_session, empresa_id=20,
        fecha_desde=date(2026, 1, 1), fecha_hasta=date(2026, 12, 31), formato="CSV",
    )
    lineas = contenido.decode("utf-8-sig").strip().splitlines()
    assert len(lineas) == 1  # solo cabecera
