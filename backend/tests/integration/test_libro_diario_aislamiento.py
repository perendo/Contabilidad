"""Integration tests SPEC-002 T024: aislamiento del libro diario (US2)."""

from __future__ import annotations


async def test_diario_de_a_no_sin_filtrar_b(journal_api):
    for empresa in (10, 20):
        for i in range(3):
            creado = journal_api.crear(
                empresa_id=empresa,
                fecha="2026-10-01",
                concepto=f"Emp {empresa} n{i+1}",
            )
            assert creado.status_code == 201
            assert journal_api.asentar(creado.json()["id"], empresa_id=empresa).status_code == 200

    diario_a = journal_api.diario(
        empresa_id=10, date_from="2026-10-01", date_to="2026-10-31"
    )
    assert diario_a.json()["total"] == 3
    assert {item["concepto"] for item in diario_a.json()["items"]} == {
        "Emp 10 n1",
        "Emp 10 n2",
        "Emp 10 n3",
    }

    diario_b = journal_api.diario(
        empresa_id=20, date_from="2026-10-01", date_to="2026-10-31"
    )
    assert diario_b.json()["total"] == 3
    assert {item["concepto"] for item in diario_b.json()["items"]} == {
        "Emp 20 n1",
        "Emp 20 n2",
        "Emp 20 n3",
    }


async def test_mismos_numeros_entre_empresas_no_se_mezclan(journal_api):
    """A y B tienen numero 1; cada diario devuelve exclusivamente el suyo."""
    for empresa in (10, 20):
        creado = journal_api.crear(
            empresa_id=empresa, fecha="2026-10-01", concepto=f"Unico {empresa}"
        )
        assert journal_api.asentar(creado.json()["id"], empresa_id=empresa).status_code == 200

    for empresa, concepto in ((10, "Unico 10"), (20, "Unico 20")):
        diario = journal_api.diario(
            empresa_id=empresa, date_from="2026-10-01", date_to="2026-10-31"
        )
        items = diario.json()["items"]
        assert len(items) == 1
        assert items[0]["numero"] == 1
        assert items[0]["concepto"] == concepto


async def test_borrador_de_b_no_cuenta_en_diario_de_b(journal_api):
    borrador = journal_api.crear(empresa_id=20, fecha="2026-10-01", concepto="No post")
    assert borrador.status_code == 201
    diario = journal_api.diario(
        empresa_id=20, date_from="2026-10-01", date_to="2026-10-31"
    )
    assert diario.json()["total"] == 0