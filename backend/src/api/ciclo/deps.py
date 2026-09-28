"""Dependencies shared by the ciclo (apertura) router.

Re-exports the platform-wide session guard (SPEC-003): the active company is
derived from the authenticated session (JWT + ``X-Empresa-Activa`` validated
against the user's active relations), never from client data.
"""

from api.deps import get_empresa_id

__all__ = ["get_empresa_id"]