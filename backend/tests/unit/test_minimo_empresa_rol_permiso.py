"""SPEC-015 US2 (T024): el minimo es (empresa x rol x permiso).

Solo la interseccion de los tres concede; cualquiera de los tres ausente deniega.
"""

from __future__ import annotations

from sqlalchemy import delete

from models.rbac.matriz_permiso import MatrizPermiso


def test_rol_sin_permiso_deniega(rbac_client) -> None:
    rbac = rbac_client
    # READ_ONLY no tiene acct/crear en el seed
    assert rbac.matriz_id(10, "READ_ONLY", "acct", "crear") is None
    assert rbac.post(
        "/api/v1/accounts", 10, "readonly", json={"code": "4495", "name": "X"}
    ).status_code == 403


def test_empresa_sin_relacion_deniega(rbac_client) -> None:
    rbac = rbac_client
    # el usuario admin no tiene relacion en la empresa 99
    assert rbac.get(99, "/api/v1/accounts/tree", "admin").status_code == 403


def test_empresa_sin_matriz_deniega(rbac_client) -> None:
    rbac = rbac_client

    async def _vaciar(session):
        await session.execute(delete(MatrizPermiso).where(MatrizPermiso.empresa_id == 20))

    rbac.run(rbac.mutar(_vaciar))
    assert rbac.get(20, "/api/v1/accounts/tree", "admin").status_code == 403
    # la empresa A sigue funcionando
    assert rbac.get(10, "/api/v1/accounts/tree", "admin").status_code == 200
