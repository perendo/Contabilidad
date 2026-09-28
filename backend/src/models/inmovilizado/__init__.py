"""Models de inmovilizado (SPEC-014): activo, plan, generación y baja.

Importar este paquete registra ``ActivoInmovilizado``, ``PlanAmortizacion``,
``AmortizacionGenerada`` y ``BajaActivo`` en ``Base.metadata`` (usado por
``models/__init__.py`` y por ``create_all`` en los tests).
"""

from models.inmovilizado.activo import (
    ActivoInmovilizado,
    EstadoActivo,
    MetodoAmortizacion,
)
from models.inmovilizado.amortizacion_generada import AmortizacionGenerada
from models.inmovilizado.baja_activo import BajaActivo, TipoBaja
from models.inmovilizado.plan_amortizacion import EstadoPlan, PlanAmortizacion

__all__ = [
    "ActivoInmovilizado",
    "AmortizacionGenerada",
    "BajaActivo",
    "EstadoActivo",
    "EstadoPlan",
    "MetodoAmortizacion",
    "PlanAmortizacion",
    "TipoBaja",
]