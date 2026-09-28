"""SPEC-015 Foundational (T010): aislamiento multi-tenant de los modelos rbac.

La matriz y los eventos de auditoria solo son visibles por su propia empresa;
las consultas de A nunca devuelven filas de B.
"""

from __future__ import annotations

from sqlalchemy import func, select

from models.rbac.evento_auditoria_acceso import EventoAuditoriaAcceso
from models.rbac.matriz_permiso import MatrizPermiso
from models.rbac.rol import Rol


def test_matriz_aislada_por_empresa(rbac_client) -> None:
    rbac = rbac_client

    async def _op(session):
        a = await session.scalar(
            select(func.count()).select_from(MatrizPermiso).where(MatrizPermiso.empresa_id == 10)
        )
        b = await session.scalar(
            select(func.count()).select_from(MatrizPermiso).where(MatrizPermiso.empresa_id == 20)
        )
        mixtas = await session.scalar(
            select(func.count())
            .select_from(MatrizPermiso)
            .where(MatrizPermiso.rol_id.in_(select(Rol.id).where(Rol.empresa_id == 20)))
            .where(MatrizPermiso.empresa_id == 10)
        )
        return a, b, mixtas

    a, b, mixtas = rbac.run(rbac.consultar(_op))
    assert a == 179
    assert b == 179
    assert mixtas == 0


def test_evento_de_auditoria_aislado_por_empresa(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.conceder(20, "READ_ONLY", "acct", "aprobar").status_code == 201

    async def _op(session):
        a = await session.scalar(
            select(func.count())
            .select_from(EventoAuditoriaAcceso)
            .where(EventoAuditoriaAcceso.empresa_id == 10)
        )
        b = await session.scalar(
            select(func.count())
            .select_from(EventoAuditoriaAcceso)
            .where(EventoAuditoriaAcceso.empresa_id == 20)
        )
        return a, b

    a, b = rbac.run(rbac.consultar(_op))
    assert a == 0
    assert b == 1
