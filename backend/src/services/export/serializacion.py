"""Serializacion de valores del dominio a JSON sin perder precision (SPEC-029).

Research D7 / constitution: **prohibido `float` para dinero**. Todo `Decimal`
sale como cadena de exactamente 4 decimales (`"123.4500"`), de modo que el JSON
del ZIP se puede parsear con `Decimal(str)` sin perdida. Las fechas viajan en
ISO 8601 y los `datetime` en UTC con sufijo `Z`; los UUID como texto; los
`Enum` como su `.value`; los `LargeBinary` en base64 (ninguno de los 17 bloques
obligatorios los usa, pero el catalogo es extensible).
"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Any
from uuid import UUID

__all__ = ["DecimalEncoder", "cuatro_decimales", "iso_utc", "serializar", "volcar_json"]

#: Cuantizacion canonica del dominio (NUMERIC(18,4) en PostgreSQL).
CUATRO = Decimal("0.0001")


def cuatro_decimales(valor: Decimal) -> Decimal:
    """Cuantiza a 4 decimales con ROUND_HALF_EVEN (redondeo contable)."""
    return valor.quantize(CUATRO, rounding=ROUND_HALF_EVEN)


def iso_utc(valor: datetime) -> str:
    """`2026-09-16T12:00:00Z`; un `datetime` naive se interpreta como UTC."""
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def serializar(valor: Any) -> Any:
    """Convierte un valor de columna SQLAlchemy a algo que `json` sepa escribir.

    Nunca devuelve `float` para un importe: los `Decimal` se cuantizan a 4
    decimales y se emiten como cadena.
    """
    if valor is None or isinstance(valor, (bool, int, str)):
        return valor
    if isinstance(valor, Decimal):
        return f"{cuatro_decimales(valor):0.4f}"
    if isinstance(valor, float):
        return f"{cuatro_decimales(Decimal(str(valor))):0.4f}"
    if isinstance(valor, datetime):
        return iso_utc(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, time):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, Enum):
        return serializar(valor.value)
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(valor)).decode("ascii")
    if isinstance(valor, dict):
        return {str(clave): serializar(item) for clave, item in valor.items()}
    if isinstance(valor, (list, tuple, set, frozenset)):
        return [serializar(item) for item in valor]
    return str(valor)


class DecimalEncoder(json.JSONEncoder):
    """`json.dumps(..., cls=DecimalEncoder)` sin `float` en los importes."""

    def default(self, o: Any) -> Any:
        """Punto de entrada de json para tipos no nativos."""
        return serializar(o)


def volcar_json(payload: Any) -> bytes:
    """Serializa a bytes UTF-8 de forma determinista (mismo input, mismos bytes).

    No se usa `sort_keys`: el orden de las claves es el de construccion, que ya
    es estable, y asi el `manifest.json` conserva el orden documentado en
    `contracts/export-layout.md`.
    """
    return json.dumps(
        payload,
        cls=DecimalEncoder,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
