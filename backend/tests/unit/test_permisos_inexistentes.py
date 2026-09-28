"""SPEC-015 US2 (T025): rol/permiso/empresa inexistentes.

Rol sin vinculo en la empresa -> 403 `sin_rol`; operacion no catalogada -> 422;
acceso a una empresa sin rol -> 403.
"""

from __future__ import annotations

from sqlalchemy import delete

from models.rbac.matriz_permiso import MatrizPermiso
from models.rbac.rol import Rol


def test_empresa_sin_rol_deniega_sin_rol(rbac_client) -> None:
    rbac = rbac_client

    async def _borrar_roles(session):
        await session.execute(delete(MatrizPermiso).where(MatrizPermiso.empresa_id == 20))
        await session.execute(delete(Rol).where(Rol.empresa_id == 20))

    rbac.run(rbac.mutar(_borrar_roles))
    resp = rbac.get(20, "/api/v1/accounts/tree", "admin")
    assert resp.status_code == 403

    eventos = rbac.get(10, "/api/v1/permisos/auditoria", "admin").json()
    motivos_10 = {e["motivo"] for e in eventos["items"]}
    # el evento sin_rol se registra en la empresa 20, no en la 10
    assert "sin_rol" not in motivos_10

    async def _leer(session):
        from sqlalchemy import select

        from models.rbac.evento_auditoria_acceso import EventoAuditoriaAcceso

        return (
            await session.scalars(
                select(EventoAuditoriaAcceso).where(
                    EventoAuditoriaAcceso.empresa_id == 20,
                    EventoAuditoriaAcceso.motivo == "sin_rol",
                )
            )
        ).all()

    assert len(rbac.run(rbac.consultar(_leer))) == 1


def test_usuario_sin_relacion_en_empresa_403(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.get(30, "/api/v1/accounts/tree", "admin").status_code == 403


def test_operacion_no_catalogada_422(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post(
        "/api/v1/permisos/matriz",
        10,
        "admin",
        json={
            "rol_id": rbac.resolver_rol(10, "READ_ONLY"),
            "modulo": "acct",
            "operacion": "no_existe",
        },
    )
    assert resp.status_code == 422
