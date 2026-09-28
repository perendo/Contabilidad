"""SPEC-015 permission matrix models (catálogo, rol, matriz, auditoría)."""

from models.rbac.evento_auditoria_acceso import (
    EventoAuditoriaAcceso,
    MotivoAcceso,
    ResultadoAcceso,
)
from models.rbac.matriz_permiso import MatrizPermiso
from models.rbac.permiso_operacion import OperacionPermiso, PermisoOperacion
from models.rbac.rol import Rol

__all__ = [
    "EventoAuditoriaAcceso",
    "MatrizPermiso",
    "MotivoAcceso",
    "OperacionPermiso",
    "PermisoOperacion",
    "ResultadoAcceso",
    "Rol",
]