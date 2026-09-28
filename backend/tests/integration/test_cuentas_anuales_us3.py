"""Tests de integracion US3 de cuentas anuales (SPEC-010): formulacion oficial."""

from __future__ import annotations

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryEstado
from models.reporting.formulacion import FormulacionCuentasAnuales
from services.reporting.formulacion import _hash_snapshot


def _formular(fac, empresa_id=10, observaciones="Formulacion 2026"):
    return fac.post(
        "/api/v1/cuentas-anuales/2026/formular",
        empresa_id=empresa_id,
        json={"observaciones": observaciones},
    )


def _anular(fac, empresa_id=10, motivo="Correccion"):
    return fac.post(
        "/api/v1/cuentas-anuales/2026/anular-formulacion",
        empresa_id=empresa_id,
        json={"motivo": motivo},
    )


def test_formular_requiere_cierre(cuentas_client) -> None:
    fac = cuentas_client
    r = _formular(fac)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ejercicio_no_cerrado"


def test_formular_completo(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    r = _formular(fac)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["numero_formulacion"] == 1
    assert data["estado"] == "formulada"
    assert len(data["contenido_hash"]) == 64

    lista = fac.get(10, "/api/v1/cuentas-anuales/2026/formulaciones").json()
    assert len(lista["items"]) == 1


def test_formular_duplicada_409(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    assert _formular(fac).status_code == 201
    r = _formular(fac)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ya_formulada"


def test_anular_y_reformular(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    assert _formular(fac).status_code == 201
    r = _anular(fac)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "anulada"
    assert r.json()["motivo_anulacion"] == "Correccion"

    segunda = _formular(fac, observaciones="Reformulacion")
    assert segunda.status_code == 201
    assert segunda.json()["numero_formulacion"] == 2

    items = fac.get(10, "/api/v1/cuentas-anuales/2026/formulaciones").json()["items"]
    assert [i["numero_formulacion"] for i in items] == [1, 2]
    assert items[0]["estado"] == "anulada"
    assert items[1]["estado"] == "formulada"


def test_anular_sin_formulacion(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    r = _anular(fac)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "sin_formulacion"


def test_hash_coincide_con_snapshot(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    data = _formular(fac).json()

    async def _obtener(session):
        return await session.scalar(
            select(FormulacionCuentasAnuales).where(
                FormulacionCuentasAnuales.empresa_id == 10,
                FormulacionCuentasAnuales.ejercicio == 2026,
            )
        )

    formulacion = fac.run(fac.consultar(_obtener))
    assert formulacion is not None
    assert _hash_snapshot(formulacion.snapshot) == data["contenido_hash"]
    assert set(formulacion.snapshot) == {"balance", "pyg", "efe"}


def test_asientos_no_modificados_tras_formular(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)

    async def _contar(session):
        return int(
            await session.scalar(
                select(func.count())
                .select_from(JournalEntry)
                .where(
                    JournalEntry.empresa_id == 10,
                    JournalEntry.estado == JournalEntryEstado.POSTED,
                )
            )
            or 0
        )

    antes = fac.run(fac.consultar(_contar))
    assert _formular(fac).status_code == 201
    assert _anular(fac).status_code == 200
    assert fac.run(fac.consultar(_contar)) == antes


def test_formulacion_multi_tenant(cuentas_client) -> None:
    fac = cuentas_client
    fac.cerrar(empresa_id=10, year=2026)
    assert _formular(fac, empresa_id=10).status_code == 201

    b = fac.get(20, "/api/v1/cuentas-anuales/2026/formulaciones").json()
    assert b["items"] == []
    r = _anular(fac, empresa_id=20)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "sin_formulacion"