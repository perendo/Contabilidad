"""Dependencias del módulo ngo (SPEC-019).

La empresa activa SIEMPRE se deriva de la sesión autenticada (cabecera
`X-Empresa-Activa`), nunca de path/body (constitución III). `get_empresa_activa`
es la dependencia compartida de SPEC-003 y ``require_permission`` la de SPEC-015
(modulo "ngo").
"""

from __future__ import annotations

from fastapi import Depends

from api.deps import get_empresa_id, require_permission

get_empresa_activa = get_empresa_id

__all__ = ["Depends", "get_empresa_activa", "get_empresa_id", "require_permission"]