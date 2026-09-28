"""Integration tests SPEC-002 T022: aislamiento multi-tenant US1 (SC-002)."""

from __future__ import annotations

from sqlalchemy import func, select

from models.acct.journal import JournalEntry, JournalEntryLine


async def test_asiento_b_no_visible_por_a(journal_api):
    """El asiento de B no aparece en diario ni detalle de A."""
    creado_b = journal_api.crear(empresa_id=20, fecha="2026-10-01", concepto="Ventas B")
    entry_b = creado_b.json()["id"]
    assert journal_api.asentar(entry_b, empresa_id=20).status_code == 200

    # Detalle desde A → 404
    assert journal_api.detalle(entry_b, empresa_id=10).status_code == 404
    # Diario de A → 0 asientos
    diario_a = journal_api.diario(empresa_id=10, date_from="2026-10-01", date_to="2026-10-31")
    assert diario_a.status_code == 200
    assert diario_a.json()["total"] == 0


async def test_lineas_de_b_no_filtran_a_a(journal_api):
    creado_b = journal_api.crear(empresa_id=20, fecha="2026-10-01", concepto="B")
    entry_b = creado_b.json()["id"]
    assert journal_api.asentar(entry_b, empresa_id=20).status_code == 200

    async def _cuenta_lineas(s):
        return await s.scalar(
            select(func.count()).select_from(JournalEntryLine).where(
                JournalEntryLine.empresa_id == 10
            )
        )

    assert await journal_api.consultar(_cuenta_lineas) == 0


async def test_asentar_en_b_borrador_de_a_404(journal_api):
    creado_a = journal_api.crear(empresa_id=10, fecha="2026-10-01", concepto="Ventas A")
    entry_a = creado_a.json()["id"]
    respuesta = journal_api.asentar(entry_a, empresa_id=20)
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "asiento_no_encontrado"
    # Sigue DRAFT en A
    assert journal_api.detalle(entry_a, empresa_id=10).json()["estado"] == "DRAFT"


async def test_cuenta_de_b_en_borrador_de_a_403(journal_api):
    """Línea con cuenta de B presentada por A → 403 sin persistir."""
    c_b = journal_api.cuentas["b"]
    linea_b = {"account_id": c_b["5720"], "debit": "100", "credit": "0"}
    creado = journal_api.crear(
        empresa_id=10, fecha="2026-10-01", concepto="Cross",
        lineas=[
            linea_b,
            {"account_id": journal_api.cuentas["a"]["4300"], "debit": "0", "credit": "100"},
        ],
    )
    assert creado.status_code == 403
    assert creado.json()["detail"]["code"] == "cuenta_otra_empresa"

    async def _count(s):
        return await s.scalar(select(func.count()).select_from(JournalEntry))

    assert await journal_api.consultar(_count) == 0