"""Servicios de inmovilizado (SPEC-014): plan, alta/edición, generación y baja.

Reutilizan el motor de asientos de SPEC-002/006 (`crear_asiento_multilinea`),
auditoría (constitución II) y filtrado multi-tenant por `empresa_id`.
"""

from services.inmovilizado import activo, baja, generacion, plan

__all__ = ["activo", "baja", "generacion", "plan"]