"""Dependencias del módulo forex (SPEC-016).

La empresa activa SIEMPRE se deriva de la sesión autenticada (cabecera
`X-Empresa-Activa`), nunca de path/body (constitución III). ``get_empresa_id``
es la dependencia compartida de SPEC-003 y ``require_permission`` la de SPEC-015
(modulo "divisas").
"""

from __future__ import annotations

from fastapi import Depends

from api.deps import get_empresa_id, require_permission

__all__ = ["Depends", "get_empresa_id", "require_permission"]