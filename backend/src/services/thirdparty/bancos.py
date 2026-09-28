"""IBAN validation (SPEC-008): ISO 13616 MOD-97."""

from __future__ import annotations

import re

_LARGO_MIN = 15
_LARGO_MAX = 34


def normalizar_iban(iban: str) -> str:
    return re.sub(r"[\s-]", "", (iban or "").strip().upper())


def validar_iban(iban: str) -> bool:
    """True if the value is a structurally valid IBAN (MOD-97 == 1)."""
    limpio = normalizar_iban(iban)
    if not (_LARGO_MIN <= len(limpio) <= _LARGO_MAX):
        return False
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", limpio):
        return False
    reordenado = limpio[4:] + limpio[:4]
    numerico = "".join(
        str(ord(c) - 55) if c.isalpha() else c for c in reordenado
    )
    return int(numerico) % 97 == 1
