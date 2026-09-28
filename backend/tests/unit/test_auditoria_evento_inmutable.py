"""SPEC-015 US3 (T035): el log de accesos es inmutable a nivel de base de datos.

UPDATE/DELETE sobre `EventoAuditoriaAcceso` son rechazados por trigger
(constitucion II aplicada a la auditoria).
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from models.rbac.evento_auditoria_acceso import EventoAuditoriaAcceso


def _primer_evento(rbac):
    async def _op(session):
        return await session.scalar(select(EventoAuditoriaAcceso).limit(1))

    return rbac.run(rbac.consultar(_op))


def test_update_de_evento_rechazado(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.conceder(10, "READ_ONLY", "acct", "aprobar").status_code == 201
    evento = _primer_evento(rbac)
    assert evento is not None

    async def _op(session):
        await session.execute(
            update(EventoAuditoriaAcceso)
            .where(EventoAuditoriaAcceso.id == evento.id)
            .values(ip="1.2.3.4")
        )

    with pytest.raises(IntegrityError):
        rbac.run(rbac.mutar(_op))


def test_delete_de_evento_rechazado(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.conceder(10, "READ_ONLY", "acct", "aprobar").status_code == 201
    evento = _primer_evento(rbac)
    assert evento is not None

    async def _op(session):
        await session.execute(
            delete(EventoAuditoriaAcceso).where(EventoAuditoriaAcceso.id == evento.id)
        )

    with pytest.raises(IntegrityError):
        rbac.run(rbac.mutar(_op))
