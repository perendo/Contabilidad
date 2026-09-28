"""Router ngo (SPEC-019): re-export del router padre del paquete.

La definición vive en ``api/ngo/__init__.py``; este módulo es el punto de
montaje canónico desde ``main.py``.
"""

from api.ngo import router

__all__ = ["router"]