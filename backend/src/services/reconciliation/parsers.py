"""Parser de extractos bancarios (SPEC-013): norma 43/19 y CSV normalizado.

Servicio puro sin estado: devuelve un `ExtractoDTO` validado. Los importes se
construyen como `Decimal` a partir de cadenas (nunca `float`).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from services.reconciliation.layouts import (
    CODIGO_CONTROL,
    CODIGOS_CABECERA,
    CODIGOS_CREDITO,
    CODIGOS_DEBITO,
    LAYOUT_NORMA_43,
    LONGITUD_LINEA,
)

CABECERAS_CSV = ("numero", "fecha_operacion", "fecha_valor", "concepto", "importe", "signo")


class LayoutError(Exception):
    def __init__(self, code: str, registro: int, campo: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.registro = registro
        self.campo = campo


@dataclass
class MovimientoDTO:
    orden: int
    fecha_operacion: date
    fecha_valor: date | None
    concepto: str
    importe: Decimal
    signo: str
    referencia: str | None


@dataclass
class ExtractoDTO:
    cuenta: str
    fecha_inicio: date
    fecha_fin: date
    saldo_inicial: Decimal
    saldo_final: Decimal
    movimientos: list[MovimientoDTO] = field(default_factory=list)


def _dec_campo(valor: str, registro: int, campo: str) -> Decimal:
    texto = (valor or "").strip()
    if not texto:
        return Decimal("0.0000")
    if not texto.isdigit():
        raise LayoutError("layout_invalido", registro, campo, f"{campo} no numérico")
    if len(texto) <= 4:
        texto = texto.zfill(4)
    return Decimal(f"{texto[:-4] or '0'}.{texto[-4:]}")


def _fecha(valor: str, registro: int, campo: str) -> date:
    texto = (valor or "").strip()
    try:
        return date(int(texto[0:4]), int(texto[4:6]), int(texto[6:8]))
    except (ValueError, IndexError) as exc:
        raise LayoutError("layout_invalido", registro, campo, f"{campo} inválida: {valor}") from exc


def parse_norma_43(file_bytes: bytes) -> ExtractoDTO:
    """Parse a fixed-width norma 43/19 extract (ISO-8859-1)."""
    texto = file_bytes.decode("iso-8859-1")
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    if not lineas:
        raise LayoutError("layout_invalido", 0, "fichero", "El fichero está vacío")

    cabecera_cuenta: str | None = None
    fecha_inicio: date | None = None
    saldo_inicial: Decimal | None = None
    saldo_final: Decimal | None = None
    movimientos: list[MovimientoDTO] = []
    control: dict[str, int | Decimal] | None = None
    for i, linea in enumerate(lineas, start=1):
        if len(linea) != LONGITUD_LINEA:
            raise LayoutError(
                "layout_invalido", i, "longitud",
                f"Línea {i}: longitud {len(linea)} != {LONGITUD_LINEA}",
            )
        codigo = linea[0:2]
        if codigo in CODIGOS_CABECERA:
            off = LAYOUT_NORMA_43.cabecera
            cabecera_cuenta = linea[off["cuenta"][0]:off["cuenta"][1]].strip()
            fecha_inicio = _fecha(linea[off["fecha_datos"][0]:off["fecha_datos"][1]], i, "fecha_datos")
            saldo_inicial = _dec_campo(linea[off["saldo_inicial"][0]:off["saldo_inicial"][1]], i, "saldo_inicial")
            saldo_final = _dec_campo(linea[off["saldo_final"][0]:off["saldo_final"][1]], i, "saldo_final")
        elif codigo in CODIGOS_DEBITO or codigo in CODIGOS_CREDITO:
            off = LAYOUT_NORMA_43.operacion
            movimientos.append(
                MovimientoDTO(
                    orden=len(movimientos) + 1,
                    fecha_operacion=_fecha(linea[off["fecha_operacion"][0]:off["fecha_operacion"][1]], i, "fecha_operacion"),
                    fecha_valor=_fecha(linea[off["fecha_valor"][0]:off["fecha_valor"][1]], i, "fecha_valor"),
                    concepto=linea[off["concepto"][0]:off["concepto"][1]].strip(),
                    importe=_dec_campo(linea[off["importe"][0]:off["importe"][1]], i, "importe"),
                    signo="D" if codigo in CODIGOS_DEBITO else "H",
                    referencia=linea[off["referencia"][0]:off["referencia"][1]].strip() or None,
                )
            )
        elif codigo == CODIGO_CONTROL:
            off = LAYOUT_NORMA_43.control
            control = {
                "n_operaciones": int(linea[off["n_operaciones"][0]:off["n_operaciones"][1]] or "0"),
                "suma": _dec_campo(linea[off["suma"][0]:off["suma"][1]], i, "suma"),
            }
        else:
            raise LayoutError("layout_invalido", i, "codigo", f"Registro {i}: código desconocido {codigo}")

    if cabecera_cuenta is None or fecha_inicio is None or saldo_inicial is None or saldo_final is None:
        raise LayoutError("layout_invalido", 0, "cabecera", "Falta el registro de cabecera 01")
    if control is None:
        raise LayoutError("layout_invalido", 0, "control", "Falta el registro de control 98")
    if len(movimientos) < 1:
        raise LayoutError("layout_invalido", 0, "movimientos", "El extracto no tiene movimientos")
    if control["n_operaciones"] != len(movimientos):
        raise LayoutError(
            "layout_invalido", 0, "control",
            f"Control declara {control['n_operaciones']} movimientos, leídos {len(movimientos)}",
        )
    suma_abs = sum((m.importe for m in movimientos), Decimal(0))
    if suma_abs != control["suma"]:
        raise LayoutError("layout_invalido", 0, "cuadre", f"Suma control {control['suma']} != {suma_abs}")

    neto = sum(
        (m.importe if m.signo == "H" else -m.importe for m in movimientos), Decimal(0)
    )
    diff = saldo_final - saldo_inicial
    if neto != diff:
        raise LayoutError(
            "layout_invalido", 0, "cuadre",
            f"Σ movimientos {neto} != saldo_final − saldo_inicial {diff}",
        )

    return ExtractoDTO(
        cuenta=cabecera_cuenta,
        fecha_inicio=fecha_inicio,
        fecha_fin=max((m.fecha_operacion for m in movimientos), default=fecha_inicio),
        saldo_inicial=saldo_inicial,
        saldo_final=saldo_final,
        movimientos=movimientos,
    )


def parse_csv_normalizado(file_bytes: bytes) -> ExtractoDTO:
    """Parse the normalized CSV variant (UTF-8, ';')."""
    texto = file_bytes.decode("utf-8-sig")
    lector = csv.DictReader(io.StringIO(texto), delimiter=";")
    if lector.fieldnames is None or any(c not in lector.fieldnames for c in CABECERAS_CSV):
        raise LayoutError("layout_invalido", 1, "cabecera", "Faltan columnas del CSV normalizado")
    movimientos: list[MovimientoDTO] = []
    totales: Decimal | None = None
    for i, fila in enumerate(lector, start=2):
        numero = (fila.get("numero") or "").strip()
        if numero == "0":
            totales = _dec_campo((fila.get("importe") or "").replace(".", "").replace(",", ""), i, "importe")
            continue
        signo = (fila.get("signo") or "").strip().upper()
        if signo not in ("D", "H"):
            raise LayoutError("layout_invalido", i, "signo", f"Signo inválido: {signo}")
        try:
            importe = Decimal((fila.get("importe") or "").strip())
        except InvalidOperation as exc:
            raise LayoutError("layout_invalido", i, "importe", "Importe inválido") from exc
        if importe <= 0:
            raise LayoutError("layout_invalido", i, "importe", "El importe debe ser > 0")
        movimientos.append(
            MovimientoDTO(
                orden=len(movimientos) + 1,
                fecha_operacion=date.fromisoformat((fila.get("fecha_operacion") or "").strip()),
                fecha_valor=(
                    date.fromisoformat((fila.get("fecha_valor") or "").strip())
                    if (fila.get("fecha_valor") or "").strip()
                    else None
                ),
                concepto=(fila.get("concepto") or "").strip(),
                importe=importe,
                signo=signo,
                referencia=(fila.get("referencia") or "").strip() or None,
            )
        )
    if not movimientos:
        raise LayoutError("layout_invalido", 0, "movimientos", "El CSV no tiene movimientos")
    neto = sum((m.importe if m.signo == "H" else -m.importe for m in movimientos), Decimal(0))
    if totales is not None and neto != totales:
        raise LayoutError("layout_invalido", 0, "cuadre", f"CSV: {neto} != totales {totales}")
    saldo_inicial = Decimal("0.0000")
    saldo_final = neto
    return ExtractoDTO(
        cuenta="",
        fecha_inicio=min(m.fecha_operacion for m in movimientos),
        fecha_fin=max(m.fecha_operacion for m in movimientos),
        saldo_inicial=saldo_inicial,
        saldo_final=saldo_final,
        movimientos=movimientos,
    )


def parse_extracto(file_bytes: bytes, layout: str) -> ExtractoDTO:
    if layout == "csv_normalizado":
        return parse_csv_normalizado(file_bytes)
    return parse_norma_43(file_bytes)
