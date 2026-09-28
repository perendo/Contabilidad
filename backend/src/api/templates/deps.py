"""Tenant dependency for template endpoints."""

from api.deps import get_empresa_id

get_empresa_activa = get_empresa_id

__all__ = ["get_empresa_activa"]
