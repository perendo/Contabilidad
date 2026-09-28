"""API del módulo inmovilizado (SPEC-014).

La empresa activa se deriva SIEMPRE de la sesión autenticada
(``api.deps.get_empresa_id``); nunca viaja en path ni en body
(constitución III). Los importes se devuelven como strings decimales
de 4 posiciones (prohibido ``float``).
"""

from api.inmovilizado.activos import router as activos_router
from api.inmovilizado.amortizaciones import router as amortizaciones_router

__all__ = ["activos_router", "amortizaciones_router"]