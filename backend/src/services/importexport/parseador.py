"""Parseo de archivos de asientos (SPEC-005 Foundational).

Soporta CSV (auto-encoding/separador) y XLSX (openpyxl). Todos los importes
se manejan como `Decimal`; nunca se usa `float`.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

CABECERAS_REQUERIDAS = ("fecha", "numero_asiento", "concepto", "cuenta", "debe", "haber")
CABECERA_OPCIONAL = "detalle"
SEPARADORES = (";", ",", "\t")


class ParseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class FilaCruda:
    fila: int
    grupo: str
    fecha: str
    concepto: str
    cuenta: str
    debe: Decimal
    haber: Decimal
    detalle: str | None = None


def parse_decimal(valor: str) -> Decimal:
    """Parse '1.250,50' / '1250.50' / '1250' → Decimal (no negative, no float)."""
    if valor is None:
        raise ParseError("importe_invalido", "Importe vacío")
    texto = str(valor).strip().replace(" ", "")
    if texto == "":
        return Decimal(0)
    texto = texto.replace("€", "")
    if texto.startswith("-"):
        raise ParseError("importe_invalido", f"Importe negativo no permitido: {valor}")
    if "." in texto and "," in texto:
        decimal_sep = "." if texto.rfind(".") > texto.rfind(",") else ","
        miles_sep = "," if decimal_sep == "." else "."
        texto = texto.replace(miles_sep, "").replace(decimal_sep, ".")
    elif "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation as exc:
        raise ParseError("importe_invalido", f"Importe inválido: {valor}") from exc
    if numero < 0:
        raise ParseError("importe_invalido", f"Importe negativo no permitido: {valor}")
    return numero


def _decodificar(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "iso-8859-1"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("formato_no_soportado", "No se pudo decodificar el archivo")


def _detectar_separador(muestra: str) -> str:
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters="".join(SEPARADORES))
        return dialecto.delimiter
    except csv.Error:
        for sep in SEPARADORES:
            if sep in muestra.splitlines()[0]:
                return sep
        return ";"


def _normalizar_cabecera(nombre: str) -> str:
    return (nombre or "").strip().lower()


def _validar_cabeceras(cabeceras: list[str]) -> dict[str, int]:
    indices = {_normalizar_cabecera(c): i for i, c in enumerate(cabeceras)}
    faltan = [c for c in CABECERAS_REQUERIDAS if c not in indices]
    if faltan:
        raise ParseError(
            "columnas_faltantes", f"Faltan columnas requeridas: {', '.join(faltan)}"
        )
    return indices


def _fila_desde_celdas(indices: dict[str, int], celdas: list, numero_fila: int) -> FilaCruda:
    def celda(nombre: str) -> str:
        idx = indices.get(nombre)
        if idx is None or idx >= len(celdas):
            return ""
        valor = celdas[idx]
        return "" if valor is None else str(valor).strip()

    grupo = celda("numero_asiento")
    if not grupo:
        raise ParseError("formato", f"Fila {numero_fila}: numero_asiento vacío")
    return FilaCruda(
        fila=numero_fila,
        grupo=grupo,
        fecha=celda("fecha"),
        concepto=celda("concepto"),
        cuenta=celda("cuenta"),
        debe=parse_decimal(celda("debe")),
        haber=parse_decimal(celda("haber")),
        detalle=celda(CABECERA_OPCIONAL) or None,
    )


def parsear_csv(file_bytes: bytes, empresa_id: int) -> list[FilaCruda]:
    """Parse a CSV into raw rows (headers validated, delimiter auto-detected)."""
    texto = _decodificar(file_bytes)
    if not texto.strip():
        raise ParseError("formato_no_soportado", "El archivo está vacío")
    separador = _detectar_separador(texto[:4096])
    lector = csv.reader(io.StringIO(texto), delimiter=separador)
    filas = list(lector)
    if not filas:
        raise ParseError("columnas_faltantes", "El archivo no contiene filas")
    indices = _validar_cabeceras(filas[0])
    crudas: list[FilaCruda] = []
    for numero, celdas in enumerate(filas[1:], start=2):
        if not any(str(c).strip() for c in celdas):
            continue
        crudas.append(_fila_desde_celdas(indices, celdas, numero))
    return crudas


def parsear_xlsx(file_bytes: bytes, empresa_id: int) -> list[FilaCruda]:
    """Parse the active sheet of an XLSX into raw rows."""
    import openpyxl

    try:
        libro = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as exc:
        raise ParseError("formato_no_soportado", "XLSX corrupto o no soportado") from exc
    hoja = libro.active
    filas = list(hoja.iter_rows(values_only=True))
    if not filas:
        raise ParseError("columnas_faltantes", "El archivo no contiene filas")
    indices = _validar_cabeceras([str(c) if c is not None else "" for c in filas[0]])
    crudas: list[FilaCruda] = []
    for numero, celdas in enumerate(filas[1:], start=2):
        if not any(c is not None and str(c).strip() for c in celdas):
            continue
        crudas.append(_fila_desde_celdas(indices, list(celdas), numero))
    return crudas


def parsear_archivo(file_bytes: bytes, nombre: str, empresa_id: int) -> list[FilaCruda]:
    """Dispatch by extension (defaults to CSV)."""
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        return parsear_xlsx(file_bytes, empresa_id)
    return parsear_csv(file_bytes, empresa_id)


def agrupar_por_asiento(filas: list[FilaCruda]) -> dict[str, list[FilaCruda]]:
    grupos: dict[str, list[FilaCruda]] = {}
    for fila in filas:
        grupos.setdefault(fila.grupo, []).append(fila)
    return grupos


def parsear_fecha(valor: str) -> date:
    """Parse YYYY-MM-DD (also accepts DD/MM/YYYY)."""
    texto = (valor or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).replace(tzinfo=timezone.utc).date()
        except ValueError:
            continue
    raise ParseError("fecha_invalida", f"Fecha inválida: {valor}")
