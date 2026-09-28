"""Contrato del PDF de libros oficiales (SPEC-019 contracts/libros-pdf.md).

Verifica (a) cabecera/pie en todas las páginas, (b) importes con 4 decimales,
(c) suma de cierre Debe == Haber, (d) nº asientos del PDF == nº del diario del
ejercicio y (e) la huella canónica recalculada == libro_oficial.sha256.
"""

from __future__ import annotations

import hashlib
import io
import re
from decimal import Decimal

from pypdf import PdfReader

from services.ngo.libros_pdf import _entradas_ejercicio, canon_diario


def _entradas(ns) -> list[dict]:
    return ns.run(ns.consultar(lambda s: _entradas_ejercicio(s, 10, 2025)))


def _generar_diario_mayor(ns) -> dict:
    ns.cerrar(10, 2025)
    r = ns.post("/api/v1/libros/2025/generar", 10, {"tipos": ["diario", "mayor"]})
    assert r.status_code == 201, r.text
    return {i["tipo"]: i for i in r.json()["items"]}


def _texto_pdf(pdf_bytes: bytes) -> tuple[str, list[str]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    paginas = [(p.extract_text() or "") for p in reader.pages]
    return " ".join(" ".join(paginas).split()), paginas


def test_diario_pdf_esquema(ngo_client):
    ns = ngo_client
    items = _generar_diario_mayor(ns)
    entradas = _entradas(ns)

    pdf = ns.get(10, items["diario"]["url"])
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    texto, paginas = _texto_pdf(pdf.content)

    # (a) cabecera y pie por página
    assert len(paginas) >= 1
    assert "Libro Diario" in texto
    assert "Diez SL" in texto
    assert "A00000001" in texto
    assert "Ejercicio 2025" in texto
    assert all("Pagina" in p for p in paginas)

    # (d) nº asientos del PDF == nº asientos del diario
    assert texto.count("Asiento Nº") == len(entradas)
    assert texto.count("Asiento Nº") == 2
    for e in entradas:
        assert f"Asiento Nº {e['numero']}" in texto

    # (b) importes con 4 decimales, sin notación científica
    assert re.search(r"\b\d+\.\d{4}\b", texto)
    assert "10000.0000" in texto
    assert "2000.0000" in texto

    # (c) suma de cierre Debe == Haber (partida doble)
    total_debe = sum((l["debe"] for e in entradas for l in e["lineas"]), Decimal(0))
    total_haber = sum((l["haber"] for e in entradas for l in e["lineas"]), Decimal(0))
    assert total_debe == total_haber
    cierre = f"Debe = {total_debe:0.4f} | Haber = {total_haber:0.4f}"
    assert cierre in texto

    # (e) huella canónica recalculada == libro_oficial.sha256
    canon = canon_diario(10, 2025, entradas)
    huella = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    assert huella == items["diario"]["sha256"]

    lista = ns.get(10, "/api/v1/libros/2025").json()
    guardado = next(i for i in lista["items"] if i["tipo"] == "diario")
    assert guardado["sha256"] == huella


def test_mayor_pdf_esquema(ngo_client):
    ns = ngo_client
    items = _generar_diario_mayor(ns)

    pdf = ns.get(10, items["mayor"]["url"])
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    texto, paginas = _texto_pdf(pdf.content)

    assert "Libro Mayor" in texto
    assert "Diez SL" in texto
    assert "Ejercicio 2025" in texto
    assert "Cuenta 5720" in texto
    assert "Saldo final de la cuenta" in texto
    assert all("Pagina" in p for p in paginas)
    assert re.search(r"\b\d+\.\d{4}\b", texto)