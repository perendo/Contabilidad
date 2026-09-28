"""Dependencies del router de facturación (SPEC-007).

Re-exporta el guard de sesión compartido de SPEC-003: la empresa activa se
deriva de la sesión autenticada (JWT + ``X-Empresa-Activa``), nunca del cuerpo
o del path de la petición.
"""

from api.deps import get_empresa_id

__all__ = ["get_empresa_id"]