"""AEB CSB 19.19 direct debit file generator.

Text file, ISO-8859-15, fixed-width records of exactly 120 chars:
  - type 1: emisor header (name, charge date, total amount in cents, count)
  - type 2: receiving bank account header
  - type 3: one line per receivable (debtor data, amount in cents)
  - type 5: trailer (total amount and check digit)
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from models.ar.tercero import Tercero
from models.treasury.recibo_remesa import ReciboRemesa
from models.treasury.remesa import Remesa
from services.remittance.seleccion import Emisor

LONGITUD_REGISTRO = 120
ENCODING = "ISO-8859-15"


def _campo(texto: str, ancho: int, *, derecha: bool = False) -> str:
    """Fixed-width field, zero/space padded and safely truncated to `ancho`."""
    valor = (texto or "").encode(ENCODING, errors="replace").decode(ENCODING)
    if len(valor) > ancho:
        return valor[:ancho]
    if derecha:
        return valor.rjust(ancho, "0")
    return valor.ljust(ancho)


def _linea(*segmentos: str) -> str:
    return _campo("".join(segmentos), LONGITUD_REGISTRO)


def _importe_cents(importe: Decimal) -> int:
    return int(Decimal(importe).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def _iban_espanol(iban: str) -> tuple[str, str, str, str]:
    """Split a Spanish IBAN into (banco, sucursal, dc, cuenta)."""
    bbans = (iban or "").replace(" ", "").upper()
    if bbans.startswith("ES") and len(bbans) == 24:
        cuerpo = bbans[4:]
        return cuerpo[:4], cuerpo[4:8], cuerpo[8:10], cuerpo[10:]
    return "", "", "", bbans[4:] if len(bbans) >= 4 else ""


def generar_csb1919(
    remesa: Remesa,
    recibos: list[ReciboRemesa],
    deudores: Mapping[uuid.UUID, Tercero],
    emisor: Emisor,
    fecha_presentacion: date | None = None,
) -> bytes:
    """Generate CSB 19.19 content for an emitted remesa."""
    fecha_presentacion = fecha_presentacion or datetime.now(timezone.utc).date()
    n_recibos = len(recibos)
    importe_total = sum((recibo.importe for recibo in recibos), Decimal(0))
    importe_cents = _importe_cents(importe_total)
    fecha_txt = fecha_presentacion.strftime("%Y%m%d")

    banco_emisor, sucursal_emisor, _, _ = _iban_espanol(emisor.iban)

    cabecera = _linea(
        "1",
        _campo(emisor.nif, 9, derecha=True),
        _campo("000", 3, derecha=True),
        _campo(emisor.nombre, 40),
        _campo("", 5),
        _campo(fecha_txt, 8, derecha=True),
        _campo(str(importe_cents), 12, derecha=True),
        _campo(str(n_recibos), 6, derecha=True),
        _campo(banco_emisor, 8, derecha=True),
        _campo(sucursal_emisor, 8, derecha=True),
    )
    banco_receptor = _linea(
        "2",
        _campo(emisor.nombre[:40], 40),
        _campo(emisor.iban, 34),
        _campo(str(importe_cents), 12, derecha=True),
    )

    lineas_recibos: list[str] = []
    for recibo in recibos:
        banco, sucursal, dc, cuenta = _iban_espanol(recibo.iban)
        deudor = deudores.get(recibo.tercero_id)
        nombre_deudor = deudor.nombre if deudor is not None else recibo.recibo_num
        lineas_recibos.append(
            _linea(
                "3",
                _campo(recibo.recibo_num, 12, derecha=True),
                _campo(recibo.fecha_cargo.strftime("%Y%m%d"), 8, derecha=True),
                _campo(str(_importe_cents(recibo.importe)), 12, derecha=True),
                _campo(recibo.recibo_num, 20),
                _campo(banco, 8, derecha=True),
                _campo(sucursal, 8, derecha=True),
                _campo(dc, 2, derecha=True),
                _campo(cuenta, 10, derecha=True),
                _campo(nombre_deudor, 39),
            )
        )

    check_digitos = sum(_importe_cents(recibo.importe) for recibo in recibos) % 97
    pie = _linea(
        "5",
        _campo(str(importe_cents), 12, derecha=True),
        _campo(str(n_recibos), 6, derecha=True),
        _campo(str(check_digitos), 4, derecha=True),
        _campo(fecha_txt, 8, derecha=True),
    )

    lineas = [cabecera, banco_receptor, *lineas_recibos, pie]
    return "\r\n".join(lineas).encode(ENCODING)


def sha256_fichero(contenido: bytes) -> str:
    import hashlib

    return hashlib.sha256(contenido).hexdigest()