"""Dependencies del router de cuentas anuales (SPEC-010).

Re-exporta el guard de sesion compartido (SPEC-003): la empresa activa se
deriva de la sesion autenticada (JWT + ``X-Empresa-Activa``).
"""

from api.deps import get_empresa_id

__all__ = ["get_empresa_id"]