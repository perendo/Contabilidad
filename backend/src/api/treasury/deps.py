"""Dependencies shared by treasury endpoints.

Re-exports the platform-wide session guard (SPEC-003): the active company
is derived from the authenticated session (JWT + ``X-Empresa-Activa``
validated against the user's active relations), never from client data.
Kept as a module so treasury routers keep a stable import path.
"""

from api.deps import get_empresa_id

__all__ = ["get_empresa_id"]
