"""Router costcenters (SPEC-017): re-export del router padre del paquete.

La definición vive en ``api/costcenters/__init__.py``; este módulo es el punto
de montaje canónico desde ``main.py``.
"""

from api.costcenters import router

__all__ = ["router"]