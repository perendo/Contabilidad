"""Inmutabilidad, duplicados y limites del alta (SPEC-030 US3, constitution II).

Los triggers de `documento_asiento` se prueban **por la via directa** (SQL
crudo), que es la unica que demuestra que la garantia vive en la base de datos
y no en la aplicacion (constitucion II, research D3): los triggers se disparan
al ejecutar el `UPDATE` o el `DELETE`, de modo que el `execute` va envuelto en
`pytest.raises(IntegrityError)` y no se re-consulta la fila despues (un
`rollback()` la deja expirada y `MissingGreenlet` revienta el test).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from config import settings
from models.acct.documento import (
    COLUMNAS_INMUTABLES,
    DocumentoAsiento,
    EstadoDocumento,
    TipoDocumento,
)
from services.documentos.adjuntos import adjuntar_documentos
from services.documentos.errores import DocumentoError
from tests.unit import documento_support as soporte
from tests.unit.test_documento_isolation import EMPRESA_A, _asientos


def _fichero(nombre: str = "factura.pdf", marcador: str | None = None) -> dict:
    return {
        "nombre": nombre,
        "contenido": soporte.pdf_bytes(marcador=marcador or nombre),
        "extension": "pdf",
    }


async def _adjuntar(db, asiento, ficheros=None, **kwargs) -> dict:
    return await adjuntar_documentos(
        db,
        empresa_id=EMPRESA_A,
        asiento_id=str(asiento),
        ficheros=ficheros if ficheros is not None else [_fichero()],
        tipo_documento=kwargs.pop("tipo_documento", "factura"),
        actor="1",
        **kwargs,
    )


async def _fila(db, documento_id: uuid.UUID) -> DocumentoAsiento:
    fila = await db.scalar(
        select(DocumentoAsiento).where(
            DocumentoAsiento.id == documento_id, DocumentoAsiento.empresa_id == EMPRESA_A
        )
    )
    assert fila is not None
    return fila


# --------------------------------------------- constitution II


async def test_el_trigger_congela_el_contenido(db_session) -> None:
    """FR-009 / SC-005: sustituir el contenido por la via directa revienta."""
    ids = await _asientos(db_session)
    resultado = await _adjuntar(db_session, ids[EMPRESA_A]["DRAFT"])
    documento_id = uuid.UUID(resultado["aceptados"][0]["id"])

    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text("UPDATE documento_asiento SET contenido = :binario WHERE id = :id"),
            {"id": documento_id.hex, "binario": b"%PDF-1.4 otro"},
        )
    assert "documento_asiento inmutable" in str(exc.value)
    await db_session.rollback()


async def test_el_trigger_congela_el_nombre_original(db_session) -> None:
    ids = await _asientos(db_session)
    resultado = await _adjuntar(db_session, ids[EMPRESA_A]["DRAFT"])
    documento_id = uuid.UUID(resultado["aceptados"][0]["id"])

    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text("UPDATE documento_asiento SET nombre_original = 'otro.pdf' WHERE id = :id"),
            {"id": documento_id.hex},
        )
    assert "documento_asiento inmutable" in str(exc.value)
    await db_session.rollback()


@pytest.mark.parametrize("columna", ["sha256", "extension", "size_bytes", "created_by"])
async def test_el_trigger_congela_el_resto_de_la_evidencia(
    db_session, columna: str
) -> None:
    """data-model.md seccion 3: la lista de columnas congeladas es cerrada."""
    assert columna in COLUMNAS_INMUTABLES
    ids = await _asientos(db_session)
    resultado = await _adjuntar(db_session, ids[EMPRESA_A]["DRAFT"])
    documento_id = uuid.UUID(resultado["aceptados"][0]["id"])

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(f"UPDATE documento_asiento SET {columna} = :valor WHERE id = :id"),
            {"id": documento_id.hex, "valor": "x" * 64},
        )
    await db_session.rollback()


async def test_el_borrado_fisico_si_se_rechaza(db_session) -> None:
    """FR-012: la baja es logica; el DELETE lo veta el trigger."""
    ids = await _asientos(db_session)
    resultado = await _adjuntar(db_session, ids[EMPRESA_A]["DRAFT"])
    documento_id = uuid.UUID(resultado["aceptados"][0]["id"])

    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            delete(DocumentoAsiento).where(DocumentoAsiento.id == documento_id)
        )
    assert "documento_asiento inmutable" in str(exc.value)
    await db_session.rollback()


async def test_el_trigger_admite_el_update_de_la_baja(db_session) -> None:
    """research D3: lo unico que cambia son las cuatro columnas de la baja, y
    el CHECK exige que la baja venga completa."""
    ids = await _asientos(db_session)
    resultado = await _adjuntar(db_session, ids[EMPRESA_A]["DRAFT"])
    documento_id = uuid.UUID(resultado["aceptados"][0]["id"])

    await db_session.execute(
        text(
            "UPDATE documento_asiento SET estado = 'dado_de_baja', "
            "baja_motivo = 'ilegible', baja_usuario = '1', baja_at = CURRENT_TIMESTAMP "
            "WHERE id = :id"
        ),
        {"id": documento_id.hex},
    )
    await db_session.commit()
    fila = await _fila(db_session, documento_id)
    assert fila.estado == EstadoDocumento.dado_de_baja
    assert fila.dado_de_baja is True
    assert fila.baja_motivo == "ilegible"
    # El contenido y la huella intactos (FR-012).
    assert fila.sha256 == resultado["aceptados"][0]["sha256"]
    assert bytes(fila.contenido).startswith(b"%PDF-")


async def test_una_baja_incompleta_la_rechaza_el_check(db_session) -> None:
    ids = await _asientos(db_session)
    resultado = await _adjuntar(db_session, ids[EMPRESA_A]["DRAFT"])
    documento_id = uuid.UUID(resultado["aceptados"][0]["id"])

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("UPDATE documento_asiento SET estado = 'dado_de_baja' WHERE id = :id"),
            {"id": documento_id.hex},
        )
    await db_session.rollback()


# --------------------------------------------- FR-006 duplicados


async def test_la_huella_es_unica_dentro_del_asiento(db_session) -> None:
    ids = await _asientos(db_session)
    asiento = ids[EMPRESA_A]["DRAFT"]
    # Mismo marcador -> mismos bytes -> misma huella, con nombre distinto.
    primero = await _adjuntar(db_session, asiento, [_fichero("a.pdf", "mismo")])
    repetido = await _adjuntar(db_session, asiento, [_fichero("b.pdf", "mismo")])

    assert len(primero["aceptados"]) == 1
    assert repetido["aceptados"] == []
    assert repetido["rechazados"][0]["code"] == "documento_duplicado"
    total = await db_session.scalar(
        select(func.count())
        .select_from(DocumentoAsiento)
        .where(DocumentoAsiento.journal_entry_id == asiento)
    )
    assert total == 1


async def test_el_mismo_fichero_en_otro_asiento_si_se_admite(db_session) -> None:
    """FR-006: la duplicidad es por asiento, no global."""
    ids = await _asientos(db_session)
    await _adjuntar(db_session, ids[EMPRESA_A]["DRAFT"], [_fichero("a.pdf", "comun")])
    otro = await _adjuntar(
        db_session, ids[EMPRESA_A]["POSTED"], [_fichero("b.pdf", "comun")]
    )
    assert len(otro["aceptados"]) == 1


async def test_un_duplicado_dentro_del_mismo_lote(db_session) -> None:
    """D13: los dos ficheros identicos del mismo POST, el segundo se rechaza."""
    ids = await _asientos(db_session)
    resultado = await _adjuntar(
        db_session,
        ids[EMPRESA_A]["DRAFT"],
        [_fichero("a.pdf", "igual"), _fichero("b.pdf", "igual")],
    )
    assert len(resultado["aceptados"]) == 1
    assert resultado["rechazados"][0]["code"] == "documento_duplicado"


# --------------------------------------------- limites


async def test_el_limite_por_asiento(db_session) -> None:
    """`documento_max_por_asiento` (50) es el tope de SC-008 con margen."""
    ids = await _asientos(db_session)
    asiento = ids[EMPRESA_A]["DRAFT"]
    for i in range(settings.documento_max_por_asiento):
        await _adjuntar(db_session, asiento, [_fichero(f"f{i}.pdf")])

    rebasado = await _adjuntar(db_session, asiento, [_fichero("extra.pdf")])
    assert rebasado["aceptados"] == []
    assert rebasado["rechazados"][0]["code"] == "limite_documentos_alcanzado"
    total = await db_session.scalar(
        select(func.count())
        .select_from(DocumentoAsiento)
        .where(DocumentoAsiento.journal_entry_id == asiento)
    )
    assert total == settings.documento_max_por_asiento


async def test_el_tipo_fuera_del_enum_se_rechaza(db_session) -> None:
    ids = await _asientos(db_session)
    with pytest.raises(DocumentoError) as exc:
        await _adjuntar(
            db_session, ids[EMPRESA_A]["DRAFT"], tipo_documento="albaran"
        )
    assert exc.value.code == "tipo_documento_invalido"
    total = await db_session.scalar(
        select(func.count()).select_from(DocumentoAsiento)
    )
    assert total == 0


async def test_una_lista_vacia_se_rechaza(db_session) -> None:
    ids = await _asientos(db_session)
    with pytest.raises(DocumentoError) as exc:
        await _adjuntar(db_session, ids[EMPRESA_A]["DRAFT"], [])
    assert exc.value.code == "documento_vacio"


# --------------------------------------------- persistencia


async def test_lo_persistido_cumple_el_data_model(db_session) -> None:
    ids = await _asientos(db_session)
    resultado = await _adjuntar(
        db_session,
        ids[EMPRESA_A]["DRAFT"],
        [_fichero("Factura nº 42.pdf", "m1")],
        descripcion="Factura del proveedor",
        importe_informativo="1210.5",
    )
    await db_session.commit()
    fila = await _fila(db_session, uuid.UUID(resultado["aceptados"][0]["id"]))

    assert fila.empresa_id == EMPRESA_A
    assert fila.journal_entry_id == ids[EMPRESA_A]["DRAFT"]
    assert fila.extension == "pdf"
    assert fila.content_type == "application/pdf"
    assert fila.num_paginas == 1
    assert fila.tipo_documento == TipoDocumento.factura
    assert fila.estado == EstadoDocumento.activo
    assert fila.created_by == "1"
    assert fila.created_at is not None
    assert fila.size_bytes == len(bytes(fila.contenido))
    assert len(fila.sha256) == 64
    # research D19: el importe es `Decimal` con 4 decimales, nunca `float`.
    assert isinstance(fila.importe_informativo, Decimal)
    assert fila.importe_informativo == Decimal("1210.5000")
    # El enum de estado se serializa en minusculas, como en la migracion.
    assert (
        await db_session.scalar(
            text(
                "SELECT estado FROM documento_asiento WHERE id = :id"
            ),
            {"id": fila.id.hex},
        )
        == "activo"
    )
