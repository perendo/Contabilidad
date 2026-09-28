"""Dependencias del módulo inmovilizado (SPEC-014).

Re-exporta la dependencia compartida de SPEC-003: la empresa activa se
deriva de la cabecera de sesión autenticada (JWT + ``X-Empresa-Activa``),
nunca del path ni del body del cliente.
"""

from api.deps import get_empresa_id

__all__ = ["get_empresa_id"]