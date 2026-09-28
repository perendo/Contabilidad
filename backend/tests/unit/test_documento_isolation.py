"""Aislamiento multi-empresa del alta de documentos (SPEC-030, constitucion III).

FR-004 y FR-013: un documento solo puede anclarse a un asiento de la empresa
activa. research D14: el rechazo es 404 con el mismo texto que un recurso
inexistente, y **no** se escribe ninguna fila.

Cada test comprueba las dos mitades —el error y el conteo por `empresa_id`— de
modo que un alta parcialmente escrita se detectaria.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models.acct.documento import DocumentoAsiento
from models.acct.journal import JournalEntry, JournalEntryEstado
from services.documentos.adjuntos import adjuntar_documentos
from services.documentos.errores import DocumentoError
from services.journal.entry_service import asentar, crear_borrador
from tests.conftest import sembrar_empresa_pgc
from tests.unit import documento_support as soporte

EMPRESA_A = 10
EMPRESA_B = 20


async def _asientos(db) -> dict[int, dict[str, uuid.UUID]]:
    """Un asiento DRAFT y otro POSTED por empresa, con el PGC sembrado."""
    from models.acct.account_plan import AccountPlan

    for empresa in (EMPRESA_A, EMPRESA_B):
        await sembrar_empresa_pgc(db, empresa)
    await db.flush()
    ids: dict[int, dict[str, uuid.UUID]] = {}
    for empresa in (EMPRESA_A, EMPRESA_B):
        # `crear_borrador` exige el `account_id` real de cada linea.
        cuentas = {
            code: ident
            for ident, code in (
                await db.execute(
                    select(AccountPlan.id, AccountPlan.code).where(
                        AccountPlan.tenant_id == empresa,
                        AccountPlan.code.in_(("6000", "4100")),
                    )
                )
            ).all()
        }
        lineas = [
            {
                "cuenta": "6000",
                "account_id": cuentas["6000"],
                "debit": Decimal("1210.0000"),
                "credit": Decimal("0.0000"),
            },
            {
                "cuenta": "4100",
                "account_id": cuentas["4100"],
                "debit": Decimal("0.0000"),
                "credit": Decimal("1210.0000"),
            },
        ]
        ids[empresa] = {}
        for estado in ("DRAFT", "POSTED"):
            borrador = await crear_borrador(
                db,
                empresa_id=empresa,
                fecha=date(2026, 3, 14),
                concepto=f"Compra con soporte {estado}",
                lineas=[dict(linea) for linea in lineas],
                actor="test",
            )
            if estado == "POSTED":
                await asentar(
                    db, empresa_id=empresa, entry_id=borrador.id, actor="test"
                )
            ids[empresa][estado] = borrador.id
    await db.flush()
    return ids


def _fichero(nombre: str = "factura.pdf") -> dict:
    return {"nombre": nombre, "contenido": soporte.pdf_bytes(), "extension": "pdf"}


async def _conteo(db, empresa_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(DocumentoAsiento)
            .where(DocumentoAsiento.empresa_id == empresa_id)
        )
        or 0
    )


async def test_el_alta_rechaza_un_asiento_de_otra_empresa(db_session) -> None:
    """Empresa activa 10, asiento de la 20: 404 y cero filas en la 10."""
    ids = await _asientos(db_session)
    with pytest.raises(DocumentoError) as exc:
        await adjuntar_documentos(
            db_session,
            empresa_id=EMPRESA_A,
            asiento_id=str(ids[EMPRESA_B]["DRAFT"]),
            ficheros=[_fichero()],
            tipo_documento="factura",
            actor="1",
        )
    assert exc.value.code == "asiento_no_encontrado"
    assert exc.value.status_code == 404
    # research D14: indistinguible de un asiento inexistente.
    assert exc.value.message == "El asiento no existe"
    assert await _conteo(db_session, EMPRESA_A) == 0
    assert await _conteo(db_session, EMPRESA_B) == 0


async def test_el_alta_rechaza_un_asiento_inexistente(db_session) -> None:
    with pytest.raises(DocumentoError) as exc:
        await adjuntar_documentos(
            db_session,
            empresa_id=EMPRESA_A,
            asiento_id=str(uuid.uuid4()),
            ficheros=[_fichero()],
            tipo_documento="factura",
            actor="1",
        )
    assert exc.value.code == "asiento_no_encontrado"
    assert exc.value.message == "El asiento no existe"


async def test_el_alta_rechaza_un_uuid_malformado(db_session) -> None:
    """Un id que no es UUID tampoco puede acabar en un 500."""
    with pytest.raises(DocumentoError) as exc:
        await adjuntar_documentos(
            db_session,
            empresa_id=EMPRESA_A,
            asiento_id="no-es-un-uuid",
            ficheros=[_fichero()],
            tipo_documento="factura",
            actor="1",
        )
    assert exc.value.code == "asiento_no_encontrado"


async def test_el_alta_solo_escribe_en_la_empresa_activa(db_session) -> None:
    """El documento se guarda con el `empresa_id` de la sesion, no con el del
    asiento: por eso el 404 de arriba es la unica salida posible."""
    ids = await _asientos(db_session)
    await adjuntar_documentos(
        db_session,
        empresa_id=EMPRESA_A,
        asiento_id=str(ids[EMPRESA_A]["DRAFT"]),
        ficheros=[_fichero()],
        tipo_documento="factura",
        actor="1",
    )
    await db_session.commit()

    assert await _conteo(db_session, EMPRESA_A) == 1
    assert await _conteo(db_session, EMPRESA_B) == 0
    empresas = (
        await db_session.execute(select(DocumentoAsiento.empresa_id))
    ).scalars().all()
    assert empresas == [EMPRESA_A]


async def test_el_mismo_fichero_sirve_en_las_dos_empresas(db_session) -> None:
    """SC-003 es sobre *visibilidad*, no sobre contenido: cada tenant adjunta el
    suyo y ambos conservan el suyo."""
    ids = await _asientos(db_session)
    for empresa in (EMPRESA_A, EMPRESA_B):
        await adjuntar_documentos(
            db_session,
            empresa_id=empresa,
            asiento_id=str(ids[empresa]["DRAFT"]),
            ficheros=[_fichero()],
            tipo_documento="factura",
            actor="1",
        )
    await db_session.commit()
    assert await _conteo(db_session, EMPRESA_A) == 1
    assert await _conteo(db_session, EMPRESA_B) == 1


async def test_se_puede_adjuntar_a_un_asiento_ya_contabilizado(db_session) -> None:
    """FR-010: la evidencia puede incorporarse DESPUES de contabilizar."""
    ids = await _asientos(db_session)
    posted = ids[EMPRESA_A]["POSTED"]
    antes = await db_session.scalar(
        select(JournalEntry.estado).where(JournalEntry.id == posted)
    )
    resultado = await adjuntar_documentos(
        db_session,
        empresa_id=EMPRESA_A,
        asiento_id=str(posted),
        ficheros=[_fichero()],
        tipo_documento="factura",
        actor="1",
    )
    await db_session.commit()
    assert len(resultado["aceptados"]) == 1
    despues = await db_session.scalar(
        select(JournalEntry.estado).where(JournalEntry.id == posted)
    )
    # constitution I/II: el estado contable del asiento no se toca.
    assert antes == JournalEntryEstado.POSTED
    assert despues == JournalEntryEstado.POSTED


async def test_la_siembra_crea_los_dos_estados(db_session) -> None:
    """Guard del propio helper: sin esto, el resto de tests pasarian por
    vacuedad si el sembrado se rompiera."""
    ids = await _asientos(db_session)
    estados = (
        (
            await db_session.execute(
                select(JournalEntry.empresa_id, JournalEntry.estado)
            )
        )
        .all()
    )
    assert len(estados) == 4
    assert {estado for _, estado in estados} == {
        JournalEntryEstado.DRAFT,
        JournalEntryEstado.POSTED,
    }
    assert set(ids) == {EMPRESA_A, EMPRESA_B}
    assert {empresa for empresa, _ in estados} == {EMPRESA_A, EMPRESA_B}
