"""SPEC-015 US3 (T034): auditoria de operaciones concedidas.

Un allow sobre una operacion con `requiere_datos_contables=true` genera evento
con el par modulo/operacion; las operaciones de solo lectura de la matriz no.
"""

from __future__ import annotations

from sqlalchemy import func, select

from models.rbac.evento_auditoria_acceso import EventoAuditoriaAcceso


def _contar_allow(rbac, modulo: str, operacion: str) -> int:
    async def _op(session):
        return await session.scalar(
            select(func.count())
            .select_from(EventoAuditoriaAcceso)
            .where(
                EventoAuditoriaAcceso.empresa_id == 10,
                EventoAuditoriaAcceso.modulo == modulo,
                EventoAuditoriaAcceso.operacion == operacion,
                EventoAuditoriaAcceso.resultado == "allow",
            )
        )

    return rbac.run(rbac.consultar(_op))


def test_allow_sobre_datos_contables_audita(rbac_client) -> None:
    rbac = rbac_client
    assert rbac.conceder(10, "READ_ONLY", "acct", "crear").status_code == 201
    # el conceder ya registro 1 allow; la ejecucion de la operacion anade otro
    antes = _contar_allow(rbac, "acct", "crear")
    resp = rbac.post(
        "/api/v1/accounts",
        10,
        "readonly",
        json={"code": "4309", "name": "Auditado", "parent_id": _padre(rbac)},
    )
    assert resp.status_code == 201
    assert _contar_allow(rbac, "acct", "crear") == antes + 1


def test_lectura_de_matriz_no_audita_allow(rbac_client) -> None:
    rbac = rbac_client
    # rbac/ver no requiere datos contables: el guard no emite allow
    antes = rbac.conteo_eventos(10, "allow")
    assert rbac.get(10, "/api/v1/permisos/catalogo", "admin").status_code == 200
    assert rbac.conteo_eventos(10, "allow") == antes


def _buscar(nodos, code):
    pila = list(nodos)
    while pila:
        nodo = pila.pop()
        if nodo["code"] == code:
            return nodo["id"]
        pila.extend(nodo.get("children", []))
    raise AssertionError(f"cuenta {code} no encontrada")


def _padre(rbac):
    resp = rbac.get(10, "/api/v1/accounts/tree", "admin")
    return _buscar(resp.json()["nodos"], "430")
