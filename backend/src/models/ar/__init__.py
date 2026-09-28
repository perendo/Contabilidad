"""Minimal AR scaffolds (SPEC-008/011) required by SPEC-020 US1.

Not a full implementation of SPEC-008/011; only the fields used by remittance
creation and document generation.
"""

from models.ar.invoice import Invoice, InvoiceTipo
from models.ar.tercero import Tercero
from models.ar.tercero_subcuenta import TerceroSubcuenta, TipoSubcuenta
from models.ar.vencimiento import EstadoVencimiento, Vencimiento

__all__ = [
    "EstadoVencimiento",
    "Invoice",
    "InvoiceTipo",
    "Tercero",
    "TerceroSubcuenta",
    "TipoSubcuenta",
    "Vencimiento",
]