"""T117: Test exportación multilínea (SPEC-006 US4).

El exportador CSV del SPEC-005 escribe una fila por `JournalEntryLine`; un
asiento 3:2 se exporta como 5 filas, todas con el mismo `numero_asiento`.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from services.importexport.exportador import exportar_diario
from services.journal.motor import crear_asiento_multilinea
from tests.conftest import sembrar_empresa_pgc

LINEAS_3_2 = [
    {"cuenta": "6000", "debe": "300.0000", "haber": "0.0000", "detalle": "Compra"},
    {"cuenta": "6210", "debe": "150.0000", "haber": "0.0000", "detalle": "Alquiler"},
    {"cuenta": "6400", "debe": "50.0000", "haber": "0.0000", "detalle": "Sueldo"},
    {"cuenta": "4000", "debe": "0.0000", "haber": "400.0000", "detalle": "Prov A"},
    {"cuenta": "4100", "debe": "0.0000", "haber": "100.0000", "detalle": "Prov B"},
]


async def test_export_csv_una_fila_por_linea(db_session):
    await sembrar_empresa_pgc(db_session, 10)
    entrada = await crear_asiento_multilinea(
        db_session, empresa_id=10, fecha=date(2026, 9, 1),
        concepto="Gastos septiembre", lineas=LINEAS_3_2,
    )
    await db_session.flush()

    contenido, nombre, _ = await exportar_diario(
        db_session, empresa_id=10,
        fecha_desde=date(2026, 9, 1), fecha_hasta=date(2026, 9, 30),
        formato="csv",
    )
    assert nombre.endswith(".csv")
    assert contenido.startswith(b"\xef\xbb\xbf")

    texto = contenido.decode("utf-8-sig")
    lector = list(csv.reader(io.StringIO(texto), delimiter=";"))
    assert lector[0] == ["fecha", "numero_asiento", "concepto", "cuenta", "debe", "haber", "detalle"]
    datos = lector[1:]
    assert len(datos) == 5
    assert {fila[3] for fila in datos} == {"6000", "6210", "6400", "4000", "4100"}
    assert all(str(entrada.numero_asiento) == fila[1] for fila in datos)
    assert "0.0000" in datos[0][4] or "0.0000" in datos[0][5]