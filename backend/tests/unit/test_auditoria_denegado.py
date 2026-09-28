"""SPEC-015 US3 (T033): auditoria de denegaciones.

Un deny genera `EventoAuditoriaAcceso` con usuario, empresa, modulo, operacion,
motivo, timestamp UTC e IP, aunque la operacion principal aborte.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from models.rbac.evento_auditoria_acceso import EventoAuditoriaAcceso


def test_deny_audita_todos_los_campos(rbac_client) -> None:
    rbac = rbac_client
    resp = rbac.post(
        "/api/v1/accounts",
        10,
        "readonly",
        json={"code": "4401", "name": "Denegado"},
    )
    assert resp.status_code == 403

    async def _leer(session):
        return (
            await session.scalars(
                select(EventoAuditoriaAcceso)
                .where(EventoAuditoriaAcceso.empresa_id == 10)
                .order_by(EventoAuditoriaAcceso.timestamp_utc.desc())
            )
        ).all()

    eventos = rbac.run(rbac.consultar(_leer))
    assert len(eventos) == 1
    evento = eventos[0]
    assert int(evento.empresa_id) == 10
    assert int(evento.usuario_id) == 3  # READ_ONLY
    assert evento.modulo == "acct"
    assert evento.operacion == "crear"
    assert evento.resultado.value == "deny"
    assert evento.motivo.value == "sin_permiso"
    assert evento.ip is not None
    assert isinstance(evento.timestamp_utc, datetime)


def test_deny_no_deja_datos_de_negocio(rbac_client) -> None:
    rbac = rbac_client
    rbac.post("/api/v1/accounts", 10, "readonly", json={"code": "4402", "name": "Nope"})
    resp = rbac.get(10, "/api/v1/accounts/tree", "admin")
    assert all(n["code"] != "4402" for n in resp.json()["nodos"])
