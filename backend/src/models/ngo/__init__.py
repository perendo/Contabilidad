"""Modelos del modulo ngo (SPEC-019): subvenciones, gastos imputados, libros
oficiales, legalizacion, caja y arqueo. Multi-tenant estricto (constitucion
III): `empresa_id` en PK/indices/FK de todas las tablas.
"""

from models.ngo.arqueo import (
    Arqueo,
    ArqueoDecision,
    ArqueoEstado,
    MovimientoCaja,
    MovimientoTipo,
)
from models.ngo.caja import Caja, CajaEstado, CajaTipo
from models.ngo.gasto_imputado import GastoImputado
from models.ngo.libros import Legalizacion, LibroOficial, LibroTipo
from models.ngo.subvencion import Subvencion, SubvencionEstado

__all__ = [
    "Arqueo",
    "ArqueoDecision",
    "ArqueoEstado",
    "Caja",
    "CajaEstado",
    "CajaTipo",
    "GastoImputado",
    "Legalizacion",
    "LibroOficial",
    "LibroTipo",
    "MovimientoCaja",
    "MovimientoTipo",
    "Subvencion",
    "SubvencionEstado",
]