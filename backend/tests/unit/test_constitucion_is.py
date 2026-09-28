import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntry
from models.audit.audit_log import AuditLog
from models.fiscal.ajuste_extracontable import AjusteExtracontable
from models.fiscal.calculo_is import CalculoIS
from tests.unit.is_support import (
    agregar_ajuste,
    contabilizar,
    crear_calculo,
    obtener_asiento,
    obtener_calculo,
    obtener_lineas,
    sumas_lineas,
)


def test_asiento_is_positivo_y_balanceado(is_client):
    calculo = crear_calculo(is_client)
    asiento_id = contabilizar(is_client, calculo["id"])["asiento_id"]
    debe, haber = sumas_lineas(obtener_lineas(is_client, asiento_id))
    assert debe > 0
    assert debe == haber


def test_asiento_is_posted_es_inmutable_en_db(is_client):
    calculo = crear_calculo(is_client)
    asiento_id = contabilizar(is_client, calculo["id"])["asiento_id"]

    async def _mutar(session):
        asiento = await session.get(JournalEntry, uuid.UUID(asiento_id))
        assert asiento is not None
        asiento.concepto = "Mutacion prohibida"
        await session.flush()

    with pytest.raises(IntegrityError, match="inmutable"):
        is_client.run(is_client.mutar(_mutar))


def test_tabla_is_aislada_por_empresa(is_client):
    calculo = crear_calculo(is_client)
    ajuste = agregar_ajuste(
        is_client,
        calculo["id"],
        tipo="DEDUCCION",
        importe="100.0000",
    )

    async def _query(session):
        return {
            "calculos_a": len(
                (
                    await session.scalars(
                        select(CalculoIS).where(CalculoIS.empresa_id == 10)
                    )
                ).all()
            ),
            "calculos_b": len(
                (
                    await session.scalars(
                        select(CalculoIS).where(CalculoIS.empresa_id == 20)
                    )
                ).all()
            ),
            "ajustes_b": len(
                (
                    await session.scalars(
                        select(AjusteExtracontable).where(
                            AjusteExtracontable.empresa_id == 20,
                            AjusteExtracontable.id == uuid.UUID(ajuste["id"]),
                        )
                    )
                ).all()
            ),
        }

    counts = is_client.run(is_client.consultar(_query))
    assert counts == {"calculos_a": 1, "calculos_b": 0, "ajustes_b": 0}


def test_auditoria_is_usa_importes_decimal_como_strings(is_client):
    calculo = crear_calculo(is_client)
    agregar_ajuste(
        is_client,
        calculo["id"],
        tipo="DEDUCCION",
        importe="100.1234",
    )
    contabilizar(is_client, calculo["id"])

    async def _query(session):
        return list(
            (
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.empresa_id == 10,
                        AuditLog.operacion.in_(
                            ["CALCULAR_IS", "AGREGAR_AJUSTE_IS", "CONTABILIZAR_IS"]
                        ),
                    )
                )
            ).all()
        )

    registros = is_client.run(is_client.consultar(_query))
    operaciones = {registro.operacion for registro in registros}
    assert {"CALCULAR_IS", "AGREGAR_AJUSTE_IS", "CONTABILIZAR_IS"} <= operaciones
    assert all(registro.ip is not None for registro in registros)
    adjustment = next(
        registro
        for registro in registros
        if registro.operacion == "AGREGAR_AJUSTE_IS"
    )
    payload = json.loads(adjustment.payload)
    assert payload["importe"] == "100.1234"
    assert isinstance(payload["cuota_diferencial"], str)
    assert Decimal(payload["importe"]) == Decimal("100.1234")


def test_calculo_contabilizado_conserva_asiento_y_audit(is_client):
    calculo = crear_calculo(is_client)
    resultado = contabilizar(is_client, calculo["id"])
    persistido = obtener_calculo(is_client, calculo["id"])
    asiento = obtener_asiento(is_client, resultado["asiento_id"])

    assert persistido.estado.value == "contabilizado"
    assert persistido.asiento_id == asiento.id
    assert asiento.estado.value == "POSTED"
