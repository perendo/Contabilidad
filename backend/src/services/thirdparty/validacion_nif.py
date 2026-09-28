"""NIF/CIF/NIE validation (SPEC-008): Spanish tax-id algorithms."""

from __future__ import annotations

import re

_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
_LETRAS_NIE = {"X": "0", "Y": "1", "Z": "2"}
_CIF_CONTROL = "JABCDEFGHI"


def normalizar_nif(nif: str) -> str:
    """Uppercase and strip spaces/hyphens."""
    return re.sub(r"[\s-]", "", (nif or "").strip().upper())


def _valido_dni(nif: str) -> bool:
    if not re.fullmatch(r"\d{8}[A-Z]", nif):
        return False
    return nif[8] == _LETRAS_DNI[int(nif[:8]) % 23]


def _valido_nie(nif: str) -> bool:
    if not re.fullmatch(r"[XYZ]\d{7}[A-Z]", nif):
        return False
    numero = int(_LETRAS_NIE[nif[0]] + nif[1:8])
    return nif[8] == _LETRAS_DNI[numero % 23]


def _valido_cif(nif: str) -> bool:
    if not re.fullmatch(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]", nif):
        return False
    digitos = [int(c) for c in nif[1:8]]
    suma = 0
    for i, d in enumerate(digitos):
        if i % 2 == 0:
            doble = d * 2
            suma += doble - 9 if doble > 9 else doble
        else:
            suma += d
    control_num = (10 - (suma % 10)) % 10
    control = str(control_num)
    control_letra = _CIF_CONTROL[control_num]
    return nif[8] in (control, control_letra)


def validar_nif(nif: str) -> bool:
    """True if the normalized value is a valid DNI, NIE or CIF."""
    limpio = normalizar_nif(nif)
    return _valido_dni(limpio) or _valido_nie(limpio) or _valido_cif(limpio)


def validar_cambio_nif(
    *,
    tiene_movimientos: bool,
    permiso_admin: bool,
) -> None:
    """Raise ValueError when changing a NIF with movements without admin rights."""
    if tiene_movimientos and not permiso_admin:
        raise ValueError("cambiar el NIF con movimientos requiere permiso de administrador")

