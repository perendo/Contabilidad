"""PostgreSQL schema verification (opt-in via ``TEST_DATABASE_URL``).

Verifica que las migraciones de ``backend/migrations`` se aplican sobre un
PostgreSQL real y que los triggers de inmutabilidad, apuntabilidad y seeding
quedan instalados. Se omite si no hay ``TEST_DATABASE_URL``; la suite normal
usa SQLite (``tests/conftest.py``).
"""

from __future__ import annotations

import os
import random
import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from db.migrate import archivos_ordenados

URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not URL, reason="TEST_DATABASE_URL no configurada (se omite PostgreSQL)"
)

TRIGGERS_ESPERADOS = {
    "trg_audit_log_immutable",
    "trg_journal_entry_immutable",
    "trg_journal_entry_line_immutable",
    "trg_journal_entry_balance",
    "trg_journal_entry_line_balance",
    "trg_journal_line_account_selectable",
    "trg_account_plan_structure",
    "trg_account_plan_selectable",
    "trg_account_plan_protected",
    "trg_companies_seed",
    "trg_companies_seed_retenciones_4751",
    "trg_calculo_is_contabilizado_immutable_update",
    "trg_calculo_is_contabilizado_immutable_delete",
    "trg_ajuste_extracontable_contabilizado_insert",
    "trg_ajuste_extracontable_contabilizado_update",
    "trg_ajuste_extracontable_contabilizado_delete",
    "trg_modelo_200_append_only_update",
    "trg_modelo_200_append_only_delete",
    "trg_liquidacion_retenciones_final_update",
    "trg_liquidacion_retenciones_final_delete",
    "trg_modelo_111_append_only_update",
    "trg_modelo_111_append_only_delete",
    "trg_modelo_115_append_only_update",
    "trg_modelo_115_append_only_delete",
    "trg_modelo_190_append_only_update",
    "trg_modelo_190_append_only_delete",
    "trg_catalogo_version_vigencia",
    "trg_desviacion_append_only_update",
    "trg_desviacion_append_only_delete",
    "trg_informe_efe_append_only_update",
    "trg_informe_efe_append_only_delete",
    "trg_linea_efe_append_only_update",
    "trg_linea_efe_append_only_delete",
    "trg_balanza_periodo_append_only_update",
    "trg_balanza_periodo_append_only_delete",
    "trg_balanza_periodo_linea_append_only_update",
    "trg_balanza_periodo_linea_append_only_delete",
    "trg_cierre_ejercicio_no_delete",
    "chk_journal_entry_fecha_abierta",
    "chk_exportacion_immutable_update",
    "chk_exportacion_immutable_delete",
    "trg_manifiesto_exportacion_append_only_update",
    "trg_manifiesto_exportacion_append_only_delete",
    "trg_manifiesto_bloque_append_only_update",
    "trg_manifiesto_bloque_append_only_delete",
    "trg_blob_exportacion_append_only_update",
    "trg_blob_exportacion_append_only_delete",
    "trg_documento_asiento_contenido_inmutable_update",
    "trg_documento_asiento_inmutable_delete",
}


TABLAS_ESPERADAS = {
    "audit_log",
    "companies",
    "users",
    "user_companies",
    "account_plan",
    "journal_entry",
    "journal_entry_line",
    "fiscal_year",
    "invoice",
    "configuracion_fiscal",
    "calculo_is",
    "ajuste_extracontable",
    "modelo_200",
    "liquidacion_retenciones",
    "retencion_periodo",
    "modelo_111",
    "modelo_115",
    "modelo_190",
    "catalogo_version",
    "catalogo_cuenta",
    "mapeo_cuenta",
    "reclasificacion_saldo",
    "periodo_seguimiento",
    "presupuesto",
    "desviacion",
    "prevision_tesoreria",
    "movimiento_prevision",
    "alerta_liquidez",
    "informe_efe",
    "linea_efe",
    "periodo_cerrado",
    "balanza_periodo",
    "balanza_periodo_linea",
    "secuencia_reapertura",
    "cierre_ejercicio",
    "cuentas_bancarias",
    "solicitud_reapertura",
    "exportacion",
    "manifiesto_exportacion",
    "manifiesto_bloque",
    "blob_exportacion",
    "config_sii",
    "documento_asiento",
    # SPEC-013. Estaban ausentes: la spec se cerro con todas sus puertas en verde y
    # estas seis tablas solo existian por `create_all` en SQLite, de modo que en
    # PostgreSQL la conciliacion era inservible. Anadidas en 024.
    "extracto_bancario",
    "movimiento_bancario",
    "conciliacion",
    "cruce_conciliacion",
    "periodo_conciliado",
    "alerta_conciliacion",
}



@pytest.fixture
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    assert URL is not None
    engine = create_async_engine(URL)
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection
        for archivo in archivos_ordenados():
            await driver.execute(archivo.read_text(encoding="utf-8"))
    yield engine
    await engine.dispose()


async def test_migraciones_crean_tablas(pg_engine: AsyncEngine):
    async with pg_engine.connect() as conn:
        tablas = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        ).scalars().all()
    assert TABLAS_ESPERADAS <= set(tablas)


async def test_triggers_instalados(pg_engine: AsyncEngine):
    async with pg_engine.connect() as conn:
        triggers = (
            await conn.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"))
        ).scalars().all()
    assert TRIGGERS_ESPERADOS <= set(triggers)


async def test_nueva_empresa_recibe_cuenta_4751(pg_engine: AsyncEngine):
    empresa_id = random.randint(700000, 799999)
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social) "
                "VALUES (:empresa_id, :nif, :razon_social)"
            ),
            {
                "empresa_id": empresa_id,
                "nif": f"T{empresa_id:08d}",
                "razon_social": "Empresa Retenciones Test",
            },
        )
        cuenta = await conn.scalar(
            text(
                "SELECT code FROM account_plan "
                "WHERE tenant_id = :empresa_id AND code = '4751'"
            ),
            {"empresa_id": empresa_id},
        )
    assert cuenta == "4751"


async def test_balance_diferido_se_valida_al_confirmar_transaccion(
    pg_engine: AsyncEngine,
):
    balanced_id = uuid.uuid4()
    async with pg_engine.connect() as conn:
        transaction = await conn.begin()
        await conn.execute(
            text(
                "INSERT INTO journal_entry "
                "(id, empresa_id, ejercicio, fecha, tipo, concepto, estado) "
                "VALUES (:id, 910001, 2026, '2026-09-17', 'GENERAL', 'balanceado', 'POSTED')"
            ),
            {"id": balanced_id},
        )
        await conn.execute(
            text(
                "INSERT INTO journal_entry_line "
                "(empresa_id, journal_entry_id, cuenta, debe, haber) "
                "VALUES (910001, :id, '572', 100.0000, 0.0000)"
            ),
            {"id": balanced_id},
        )
        await conn.execute(
            text(
                "INSERT INTO journal_entry_line "
                "(empresa_id, journal_entry_id, cuenta, debe, haber) "
                "VALUES (910001, :id, '430', 0.0000, 100.0000)"
            ),
            {"id": balanced_id},
        )
        await transaction.commit()

    unbalanced_id = uuid.uuid4()
    async with pg_engine.connect() as conn:
        transaction = await conn.begin()
        await conn.execute(
            text(
                "INSERT INTO journal_entry "
                "(id, empresa_id, ejercicio, fecha, tipo, concepto, estado) "
                "VALUES (:id, 910002, 2026, '2026-09-17', 'GENERAL', 'desbalanceado', 'POSTED')"
            ),
            {"id": unbalanced_id},
        )
        await conn.execute(
            text(
                "INSERT INTO journal_entry_line "
                "(empresa_id, journal_entry_id, cuenta, debe, haber) "
                "VALUES (910002, :id, '572', 100.0000, 0.0000)"
            ),
            {"id": unbalanced_id},
        )
        with pytest.raises(DBAPIError):
            await transaction.commit()


async def test_inmutabilidad_is_en_postgresql(pg_engine: AsyncEngine):
    import random

    empresa_id = random.randint(100000, 999999)
    calculo_id = uuid.uuid4()
    modelo_id = uuid.uuid4()
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social) "
                "VALUES (:empresa_id, :nif, 'Empresa IS Test')"
            ),
            {"empresa_id": empresa_id, "nif": f"T{empresa_id:08d}"},
        )
        await conn.execute(
            text(
                "INSERT INTO calculo_is "
                "(id, empresa_id, ejercicio, resultado_contable, base_imponible, "
                "tipo_impositivo, cuota_integra, cuota_liquida, pagos_a_cuenta, "
                "cuota_diferencial, provisional, estado) "
                "VALUES (:id, :empresa_id, 2025, 100, 100, 25, 25, 25, 0, 25, "
                "FALSE, 'contabilizado')"
            ),
            {"id": calculo_id, "empresa_id": empresa_id},
        )
        await conn.execute(
            text(
                "INSERT INTO modelo_200 "
                "(id, empresa_id, calculo_is_id, contenido, hash_contenido) "
                "VALUES (:id, :empresa_id, :calculo_id, :contenido, :hash)"
            ),
            {
                "id": modelo_id,
                "empresa_id": empresa_id,
                "calculo_id": calculo_id,
                "contenido": '{"datos_declarante":{}}',
                "hash": "a" * 64,
            },
        )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE calculo_is SET notas = 'bloqueado' "
                    "WHERE empresa_id = :empresa_id AND id = :id"
                ),
                {"empresa_id": empresa_id, "id": calculo_id},
            )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO ajuste_extracontable "
                    "(empresa_id, calculo_is_id, tipo, descripcion, importe) "
                    "VALUES (:empresa_id, :calculo_id, 'DEDUCCION', 'Bloqueada', 1)"
                ),
                {"empresa_id": empresa_id, "calculo_id": calculo_id},
            )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE modelo_200 SET hash_contenido = :hash "
                    "WHERE empresa_id = :empresa_id AND id = :id"
                ),
                {"empresa_id": empresa_id, "id": modelo_id, "hash": "b" * 64},
            )


async def test_catalogo_vigencia_en_postgresql(pg_engine: AsyncEngine):
    import random

    empresa_id = random.randint(100000, 999999)
    version_id = uuid.uuid4()
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social) "
                "VALUES (:empresa_id, :nif, 'Empresa Catalogo Test')"
            ),
            {"empresa_id": empresa_id, "nif": f"C{empresa_id:08d}"},
        )
        await conn.execute(
            text(
                "INSERT INTO catalogo_version "
                "(id, empresa_id, numero_version, codigo, fecha_inicio, estado, "
                "es_migracion) "
                "VALUES (:id, :empresa_id, 1, 'PGC-TEST', '2026-01-01', "
                "'borrador', TRUE)"
            ),
            {"id": version_id, "empresa_id": empresa_id},
        )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO catalogo_version "
                    "(id, empresa_id, numero_version, codigo, fecha_inicio, "
                    "estado) "
                    "VALUES (:id, :empresa_id, 1, 'PGC-TEST-2', '2025-06-01', "
                    "'borrador')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id},
            )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO catalogo_version "
                    "(id, empresa_id, numero_version, codigo, fecha_inicio, "
                    "estado) "
                    "VALUES (:id, :empresa_id, 2, 'PGC-TEST', '2027-01-01', "
                    "'borrador')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id},
            )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE catalogo_version SET fecha_fin = '2020-01-01' "
                    "WHERE empresa_id = :empresa_id AND id = :id"
                ),
                {"empresa_id": empresa_id, "id": version_id},
            )



async def test_presupuestos_unicidad_y_snapshot_en_postgresql(pg_engine: AsyncEngine):
    """Migracion 017: unicidad por combinacion, un solo periodo abierto y
    snapshot append-only (constitucion II/IV, FR-005)."""
    empresa_id = random.randint(100000, 999999)
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social) "
                "VALUES (:empresa_id, :nif, 'Empresa Presupuestos Test')"
            ),
            {"empresa_id": empresa_id, "nif": f"P{empresa_id:08d}"},
        )
        cuenta = await conn.scalar(
            text(
                "SELECT id FROM account_plan WHERE tenant_id = :empresa_id "
                "AND code = '6400'"
            ),
            {"empresa_id": empresa_id},
        )
        assert cuenta is not None, "el seed del PGC debe crear la cuenta 6400"
        periodo_id = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO periodo_seguimiento "
                "(id, empresa_id, ejercicio, numero_periodo, fecha_inicio, "
                "fecha_fin, estado) VALUES (:id, :empresa_id, 2026, 1, "
                "'2026-01-01', '2026-12-31', 'abierto')"
            ),
            {"id": periodo_id, "empresa_id": empresa_id},
        )
        await conn.execute(
            text(
                "INSERT INTO presupuesto (id, empresa_id, ejercicio, cuenta_id, "
                "importe, tipo) VALUES (:id, :empresa_id, 2026, :cuenta, "
                "48000.0000, 'gasto')"
            ),
            {
                "id": uuid.uuid4(),
                "empresa_id": empresa_id,
                "cuenta": cuenta,
            },
        )

    # FR-005: misma combinacion sin centro -> viola el indice parcial.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO presupuesto (id, empresa_id, ejercicio, "
                    "cuenta_id, importe, tipo) VALUES (:id, :empresa_id, 2026, "
                    ":cuenta, 100.0000, 'gasto')"
                ),
                {
                    "id": uuid.uuid4(),
                    "empresa_id": empresa_id,
                    "cuenta": cuenta,
                },
            )

    # Constitucion IV + unicidad: un solo periodo abierto por ejercicio.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO periodo_seguimiento (id, empresa_id, ejercicio, "
                    "numero_periodo, fecha_inicio, fecha_fin, estado) VALUES "
                    "(:id, :empresa_id, 2026, 2, '2026-07-01', '2026-12-31', "
                    "'abierto')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id},
            )

    # Numero de periodo duplicado.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO periodo_seguimiento (id, empresa_id, ejercicio, "
                    "numero_periodo, fecha_inicio, fecha_fin, estado) VALUES "
                    "(:id, :empresa_id, 2026, 1, '2026-07-01', '2026-12-31', "
                    "'cerrado')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id},
            )

    # Constitucion II: el snapshot del cierre es append-only.
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO desviacion (id, empresa_id, periodo_id, cuenta_id, "
                "importe_presupuestado, importe_real, desviacion_absoluta, "
                "desviacion_relativa) VALUES (:id, :empresa_id, :periodo, "
                ":cuenta, 48000.0000, 45000.0000, -3000.0000, -0.0625)"
            ),
            {
                "id": uuid.uuid4(),
                "empresa_id": empresa_id,
                "periodo": periodo_id,
                "cuenta": cuenta,
            },
        )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE desviacion SET importe_real = 0.0000 "
                    "WHERE empresa_id = :empresa_id"
                ),
                {"empresa_id": empresa_id},
            )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM desviacion WHERE empresa_id = :empresa_id"),
                {"empresa_id": empresa_id},
            )

    # El ratio esta acotado al rango de NUMERIC(7,4) por el CHECK.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO desviacion (id, empresa_id, periodo_id, "
                    "cuenta_id, importe_presupuestado, importe_real, "
                    "desviacion_absoluta, desviacion_relativa) VALUES "
                    "(:id, :empresa_id, :periodo, :cuenta, 1.0000, 1000000.0000, "
                    "999999.0000, 1000000.0000)"
                ),
                {
                    "id": uuid.uuid4(),
                    "empresa_id": empresa_id,
                    "periodo": periodo_id,
                    "cuenta": cuenta,
                },
            )

async def test_cashflow_correlatividad_y_snapshot_efe_en_postgresql(
    pg_engine: AsyncEngine,
):
    """Migracion 018: correlatividad de la prevision, unicidad de la alerta por
    bucket, CHECK de saldo negativo y snapshot del EFE append-only
    (constitucion II/IV, FR-003/FR-004)."""
    empresa_id = random.randint(100000, 999999)
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social) "
                "VALUES (:empresa_id, :nif, 'Empresa Tesoreria Test')"
            ),
            {"empresa_id": empresa_id, "nif": f"T{empresa_id:08d}"},
        )
        cuenta = await conn.scalar(
            text(
                "SELECT id FROM account_plan WHERE tenant_id = :empresa_id "
                "AND code = '6400'"
            ),
            {"empresa_id": empresa_id},
        )
        assert cuenta is not None, "el seed del PGC debe crear la cuenta 6400"
        prevision_id = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO prevision_tesoreria (id, empresa_id, numero_prevision, "
                "desde_fecha, hasta_fecha, granularidad, saldo_inicial, saldo_final) "
                "VALUES (:id, :empresa_id, 1, '2026-09-16', '2026-10-31', 'dia', "
                "1000.0000, 1000.0000)"
            ),
            {"id": prevision_id, "empresa_id": empresa_id},
        )
        movimiento_id = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO movimiento_prevision (id, empresa_id, prevision_id, "
                "origen, tipo, importe, fecha_prevista) VALUES (:id, :empresa_id, "
                ":prevision, 'pago_recurrente', 'pago', 500.0000, '2026-09-20')"
            ),
            {"id": movimiento_id, "empresa_id": empresa_id, "prevision": prevision_id},
        )

    # Constitucion IV: `numero_prevision` es unico por empresa.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO prevision_tesoreria (id, empresa_id, "
                    "numero_prevision, desde_fecha, hasta_fecha, granularidad) "
                    "VALUES (:id, :empresa_id, 1, '2026-09-16', '2026-10-31', 'dia')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id},
            )

    # Rango de fechas y numero positivo.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO prevision_tesoreria (id, empresa_id, "
                    "numero_prevision, desde_fecha, hasta_fecha, granularidad) "
                    "VALUES (:id, :empresa_id, 2, '2026-12-31', '2026-01-01', 'mes')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id},
            )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO prevision_tesoreria (id, empresa_id, "
                    "numero_prevision, desde_fecha, hasta_fecha, granularidad) "
                    "VALUES (:id, :empresa_id, 0, '2026-01-01', '2026-12-31', 'mes')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id},
            )

    # `importe > 0` y el motivo obligatorio al excluir.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO movimiento_prevision (id, empresa_id, prevision_id, "
                    "origen, tipo, importe, fecha_prevista) VALUES (:id, :empresa_id, "
                    ":prevision, 'cobro_estimado', 'cobro', 0.0000, '2026-09-20')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id, "prevision": prevision_id},
            )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO movimiento_prevision (id, empresa_id, prevision_id, "
                    "origen, tipo, importe, incluido) VALUES (:id, :empresa_id, "
                    ":prevision, 'cobro_estimado', 'cobro', 10.0000, FALSE)"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id, "prevision": prevision_id},
            )

    # FR-003: una alerta por bucket y solo con saldo negativo.
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO alerta_liquidez (id, empresa_id, prevision_id, fecha, "
                "saldo_proyectado, importe_deficit) VALUES (:id, :empresa_id, "
                ":prevision, '2026-09-20', -500.0000, 500.0000)"
            ),
            {"id": uuid.uuid4(), "empresa_id": empresa_id, "prevision": prevision_id},
        )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO alerta_liquidez (id, empresa_id, prevision_id, "
                    "fecha, saldo_proyectado, importe_deficit) VALUES (:id, "
                    ":empresa_id, :prevision, '2026-09-20', -100.0000, 100.0000)"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id, "prevision": prevision_id},
            )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO alerta_liquidez (id, empresa_id, prevision_id, "
                    "fecha, saldo_proyectado, importe_deficit) VALUES (:id, "
                    ":empresa_id, :prevision, '2026-09-21', 0.0000, 100.0000)"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id, "prevision": prevision_id},
            )

    # Constitucion II: el EFE formulado es un snapshot inmutable.
    informe_id = uuid.uuid4()
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO informe_efe (id, empresa_id, ejercicio, saldo_inicial, "
                "saldo_final, variacion_neta, cuadre, estado) VALUES (:id, "
                ":empresa_id, 2026, 1000.0000, 1500.0000, 500.0000, TRUE, "
                "'formulado')"
            ),
            {"id": informe_id, "empresa_id": empresa_id},
        )
        await conn.execute(
            text(
                "INSERT INTO linea_efe (id, empresa_id, informe_id, bloque, "
                "cuenta_id, codigo_cuenta, importe) VALUES (:id, :empresa_id, "
                ":informe, 'operativa', :cuenta, '6400', -500.0000)"
            ),
            {
                "id": uuid.uuid4(),
                "empresa_id": empresa_id,
                "informe": informe_id,
                "cuenta": cuenta,
            },
        )

    # Un solo EFE por empresa y ejercicio.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO informe_efe (id, empresa_id, ejercicio, cuadre) "
                    "VALUES (:id, :empresa_id, 2026, TRUE)"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_id},
            )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE informe_efe SET cuadre = FALSE WHERE empresa_id = :e"
                ),
                {"e": empresa_id},
            )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM informe_efe WHERE empresa_id = :e"),
                {"e": empresa_id},
            )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("UPDATE linea_efe SET importe = 0.0000 WHERE empresa_id = :e"),
                {"e": empresa_id},
            )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM linea_efe WHERE empresa_id = :e"),
                {"e": empresa_id},
            )


async def test_cashflow_aisla_las_empresas_en_postgresql(
    pg_engine: AsyncEngine,
):
    """Constitucion III: las FKs compuestas impiden enlazar datos de otra empresa
    (una prevision de A no admite un movimiento de B)."""
    empresa_a = random.randint(100000, 499999)
    empresa_b = random.randint(500000, 999999)
    async with pg_engine.begin() as conn:
        for empresa_id in (empresa_a, empresa_b):
            await conn.execute(
                text(
                    "INSERT INTO companies (company_id, nif, razon_social) "
                    "VALUES (:empresa_id, :nif, 'Empresa Aislada Test')"
                ),
                {"empresa_id": empresa_id, "nif": f"I{empresa_id:08d}"},
            )
        prevision_b = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO prevision_tesoreria (id, empresa_id, numero_prevision, "
                "desde_fecha, hasta_fecha, granularidad) VALUES (:id, :empresa_id, "
                "1, '2026-01-01', '2026-12-31', 'mes')"
            ),
            {"id": prevision_b, "empresa_id": empresa_b},
        )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO movimiento_prevision (id, empresa_id, prevision_id, "
                    "origen, tipo, importe, fecha_prevista) VALUES (:id, :empresa_id, "
                    ":prevision, 'pago_recurrente', 'pago', 10.0000, '2026-03-01')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_a, "prevision": prevision_b},
            )


async def test_cierres_bloquean_el_asiento_y_snapshots_en_postgresql(
    pg_engine: AsyncEngine,
):
    """Migracion 019: bloqueo de periodos, snapshot inmutable y correlatividad."""
    # Identificador de empresa aleatorio por corrida: la base de la contrato no
    # se recrea entre ejecuciones y la clave natural del periodo es unica.
    empresa = random.randrange(10_000_000, 99_999_999)
    async with pg_engine.begin() as conn:

        await conn.execute(
            text("INSERT INTO companies (company_id, nif, razon_social) "
                 "VALUES (:id, :nif, :razon) ON CONFLICT (company_id) DO NOTHING"),
            {"id": empresa, "nif": "X00000700", "razon": "Cierres PG SL"},
        )
        periodo = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO periodo_cerrado (id, empresa_id, ejercicio, tipo, periodo, "
                "fecha_ini, fecha_fin, estado, n_reaperturas) "
                "VALUES (:id, :empresa_id, 2026, 'MES', 3, '2026-03-01', '2026-03-31', "
                "'cerrado', 0)"
            ),
            {"id": periodo, "empresa_id": empresa},
        )
        balanza = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO balanza_periodo (id, empresa_id, periodo_id, ejercicio, "
                "fecha_ini, fecha_fin, n_lineas, total_debe, total_haber, "
                "resultado_provisional, sha256) "
                "VALUES (:id, :empresa_id, :periodo, 2026, '2026-03-01', '2026-03-31', "
                "0, 0, 0, 0, :sha)"
            ),
            {"id": balanza, "empresa_id": empresa, "periodo": periodo, "sha": "0" * 64},
        )
    # Los inserts anteriores ya estan confirmados: cada comprobacion negativa
    # corre en su propia transaccion (si se anidara, otra conexion no veria
    # las filas sin confirmar y el trigger no llegaria a dispararse).

    # Constitucion I: el CHECK del snapshot exige el cuadre exacto.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO balanza_periodo (id, empresa_id, periodo_id, "
                    "ejercicio, fecha_ini, fecha_fin, n_lineas, total_debe, "
                    "total_haber, resultado_provisional, sha256) "
                    "VALUES (:id, :empresa_id, :periodo, 2026, '2026-03-01', "
                    "'2026-03-31', 0, 100.0000, 90.0000, 0, :sha)"
                ),
                {
                    "id": uuid.uuid4(),
                    "empresa_id": empresa,
                    "periodo": periodo,
                    "sha": "0" * 64,
                },
            )
    # Constitucion II: el snapshot es append-only.
        with pytest.raises(DBAPIError):
            async with pg_engine.begin() as conn:
                await conn.execute(
                    text("UPDATE balanza_periodo SET n_lineas = 99 WHERE id = :id"),
                    {"id": balanza},
                )
        with pytest.raises(DBAPIError):
            async with pg_engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM balanza_periodo WHERE id = :id"), {"id": balanza}
                )
        # FR-001 / research D9: el trigger bloquea el INSERT en periodo cerrado.
        with pytest.raises(DBAPIError):
            async with pg_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO journal_entry (id, empresa_id, ejercicio, fecha, "
                        "tipo, concepto, estado) "
                        "VALUES (:id, :empresa_id, 2026, '2026-03-15', 'GENERAL', "
                        "'bypass', 'POSTED')"
                    ),
                    {"id": uuid.uuid4(), "empresa_id": empresa},
                )
        # Los tipos de cierre estan exentos: el cierre anual se fecha el ultimo dia.
        exempto = uuid.uuid4()
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO journal_entry (id, empresa_id, ejercicio, fecha, tipo, "
                    "concepto, estado) VALUES (:id, :empresa_id, 2026, '2026-03-31', "
                    "'CIERRE', 'cierre del ejercicio', 'POSTED')"
                ),
                {"id": exempto, "empresa_id": empresa},
            )
        # Constitucion IV: una sola solicitud activa por periodo.
        solicitud = uuid.uuid4()
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO solicitud_reapertura (id, empresa_id, ejercicio, "
                    "numero_solicitud, periodo_id, tipo_periodo, periodo, motivo, "
                    "estado) VALUES (:id, :empresa_id, 2026, 1, :periodo, 'MES', 3, "
                    "'Error de imputacion', 'pendiente')"
                ),
                {"id": solicitud, "empresa_id": empresa, "periodo": periodo},
            )
        with pytest.raises(DBAPIError):
            async with pg_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO solicitud_reapertura (id, empresa_id, ejercicio, "
                        "numero_solicitud, periodo_id, tipo_periodo, periodo, motivo, "
                        "estado) VALUES (:id, :empresa_id, 2026, 2, :periodo, 'MES', 3, "
                        "'Segunda', 'pendiente')"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "empresa_id": empresa,
                        "periodo": periodo,
                    },
                )
        # FR-006: el motivo no puede quedar en blanco.
        with pytest.raises(DBAPIError):
            async with pg_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO solicitud_reapertura (id, empresa_id, ejercicio, "
                        "numero_solicitud, periodo_id, tipo_periodo, periodo, motivo, "
                        "estado) VALUES (:id, :empresa_id, 2026, 3, NULL, 'ANUAL', NULL, "
                        "'   ', 'pendiente')"
                    ),
                    {"id": uuid.uuid4(), "empresa_id": empresa},
                )


async def test_cierres_aislan_las_empresas_en_postgresql(pg_engine: AsyncEngine):
    """Constitucion III: un periodo de A no enlaza desde B."""
    empresa_a = random.randrange(10_000_000, 90_000_000)
    empresa_b = empresa_a + 1

    async with pg_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO companies (company_id, nif, razon_social) "
                 "VALUES (:id, :nif, :razon) ON CONFLICT (company_id) DO NOTHING"),
            {"id": empresa_a, "nif": "X00000710", "razon": "Cierres A SL"},
        )
        await conn.execute(
            text("INSERT INTO companies (company_id, nif, razon_social) "
                 "VALUES (:id, :nif, :razon) ON CONFLICT (company_id) DO NOTHING"),
            {"id": empresa_b, "nif": "X00000720", "razon": "Cierres B SL"},
        )
        periodo_a = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO periodo_cerrado (id, empresa_id, ejercicio, tipo, periodo, "
                "fecha_ini, fecha_fin, estado, n_reaperturas) "
                "VALUES (:id, :empresa_id, 2026, 'MES', 3, '2026-03-01', '2026-03-31', "
                "'cerrado', 0)"
            ),
            {"id": periodo_a, "empresa_id": empresa_a},
        )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO solicitud_reapertura (id, empresa_id, ejercicio, "
                    "numero_solicitud, periodo_id, tipo_periodo, periodo, motivo, "
                    "estado) VALUES (:id, :empresa_id, 2026, 1, :periodo, 'MES', 3, "
                    "'Cruce de tenant', 'pendiente')"
                ),
                {
                    "id": uuid.uuid4(),
                    "empresa_id": empresa_b,
                    "periodo": periodo_a,
                },
            )


async def test_exportacion_inmutable_y_aislada_en_postgresql(pg_engine: AsyncEngine):
    """SPEC-029: el snapshot es inmutable y la numeracion es por (empresa, anio)."""
    empresa_a = random.randrange(10_000_000, 90_000_000)
    empresa_b = empresa_a + 1
    exportacion_id = uuid.uuid4()

    async with pg_engine.begin() as conn:
        for empresa, nif in ((empresa_a, "X00000810"), (empresa_b, "X00000820")):
            await conn.execute(
                text(
                    "INSERT INTO companies (company_id, nif, razon_social) "
                    "VALUES (:id, :nif, 'Export SL') ON CONFLICT (company_id) DO NOTHING"
                ),
                {"id": empresa, "nif": nif},
            )
        await conn.execute(
            text(
                "INSERT INTO exportacion (id, empresa_id, anio_creacion, numero_exportacion, "
                "tipo, estado, n_bloques) "
                "VALUES (:id, :empresa_id, 2026, 1, 'INTEGRAL', 'en_proceso', 0)"
            ),
            {"id": exportacion_id, "empresa_id": empresa_a},
        )

    # Constitucion IV: el mismo numero puede existir en otra empresa, no en la misma.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO exportacion (id, empresa_id, anio_creacion, "
                    "numero_exportacion, tipo, estado, n_bloques) "
                    "VALUES (:id, :empresa_id, 2026, 1, 'INTEGRAL', 'en_proceso', 0)"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa_a},
            )
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO exportacion (id, empresa_id, anio_creacion, numero_exportacion, "
                "tipo, estado, n_bloques) "
                "VALUES (:id, :empresa_id, 2026, 1, 'INTEGRAL', 'en_proceso', 0)"
            ),
            {"id": uuid.uuid4(), "empresa_id": empresa_b},
        )

    # Constitucion II: la transicion en_proceso -> lista si se admite.
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE exportacion SET estado = 'lista', sha256 = :sha, "
                "tamano_bytes = 42, n_bloques = 17, completado_at = now() WHERE id = :id"
            ),
            {"id": exportacion_id, "sha": "a" * 64},
        )
    # A partir de `lista` no admite UPDATE ni DELETE.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("UPDATE exportacion SET n_bloques = 0 WHERE id = :id"),
                {"id": exportacion_id},
            )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM exportacion WHERE id = :id"), {"id": exportacion_id}
            )


async def test_manifiesto_y_blob_append_only_en_postgresql(pg_engine: AsyncEngine):
    """El manifiesto, sus lineas y el blob no admiten UPDATE ni DELETE."""
    empresa = random.randrange(10_000_000, 90_000_000)
    exportacion_id = uuid.uuid4()
    manifiesto_id = uuid.uuid4()
    blob_id = uuid.uuid4()

    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social) "
                "VALUES (:id, :nif, 'Append SL') ON CONFLICT (company_id) DO NOTHING"
            ),
            {"id": empresa, "nif": "X00000830"},
        )
        await conn.execute(
            text(
                "INSERT INTO exportacion (id, empresa_id, anio_creacion, numero_exportacion, "
                "tipo, estado, n_bloques) "
                "VALUES (:id, :empresa_id, 2026, 1, 'INTEGRAL', 'lista', 17)"
            ),
            {"id": exportacion_id, "empresa_id": empresa},
        )
        await conn.execute(
            text(
                "INSERT INTO manifiesto_exportacion (id, empresa_id, exportacion_id, "
                "formato_version, fecha_generacion, tenant_id, n_bloques, sha256_fichero) "
                "VALUES (:id, :empresa_id, :exportacion, '1.0.0', now(), :empresa_id, 17, :sha)"
            ),
            {"id": manifiesto_id, "empresa_id": empresa, "exportacion": exportacion_id, "sha": "b" * 64},
        )
        await conn.execute(
            text(
                "INSERT INTO manifiesto_bloque (id, empresa_id, manifiesto_id, bloque, "
                "entidades_exportadas, conteo_registros) "
                "VALUES (:id, :empresa_id, :manifiesto, 'asientos', 'JournalEntry', 3)"
            ),
            {"id": uuid.uuid4(), "empresa_id": empresa, "manifiesto": manifiesto_id},
        )
        await conn.execute(
            text(
                "INSERT INTO blob_exportacion (id, empresa_id, exportacion_id, contenido, "
                "sha256, tamano_bytes) VALUES (:id, :empresa_id, :exportacion, :contenido, :sha, 12)"
            ),
            {
                "id": blob_id,
                "empresa_id": empresa,
                "exportacion": exportacion_id,
                "contenido": b"PK\x03\x04datos",
                "sha": "b" * 64,
            },
        )

    for sentencia, parametros in (
        ("UPDATE manifiesto_exportacion SET n_bloques = 0 WHERE id = :id", {"id": manifiesto_id}),
        ("DELETE FROM manifiesto_exportacion WHERE id = :id", {"id": manifiesto_id}),
        ("UPDATE manifiesto_bloque SET conteo_registros = 0 WHERE manifiesto_id = :id", {"id": manifiesto_id}),
        ("DELETE FROM manifiesto_bloque WHERE manifiesto_id = :id", {"id": manifiesto_id}),
        ("UPDATE blob_exportacion SET tamano_bytes = 0 WHERE id = :id", {"id": blob_id}),
        ("DELETE FROM blob_exportacion WHERE id = :id", {"id": blob_id}),
    ):
        with pytest.raises(DBAPIError):
            async with pg_engine.begin() as conn:
                await conn.execute(text(sentencia), parametros)


async def test_exportacion_aisla_las_empresas_en_postgresql(pg_engine: AsyncEngine):
    """Constitucion III: la FK compuesta impide enlazar cabeceras de otra empresa."""
    empresa_a = random.randrange(10_000_000, 90_000_000)
    empresa_b = empresa_a + 1
    exportacion_id = uuid.uuid4()

    async with pg_engine.begin() as conn:
        for empresa, nif in ((empresa_a, "X00000840"), (empresa_b, "X00000850")):
            await conn.execute(
                text(
                    "INSERT INTO companies (company_id, nif, razon_social) "
                    "VALUES (:id, :nif, 'Aisla SL') ON CONFLICT (company_id) DO NOTHING"
                ),
                {"id": empresa, "nif": nif},
            )
        await conn.execute(
            text(
                "INSERT INTO exportacion (id, empresa_id, anio_creacion, numero_exportacion, "
                "tipo, estado, n_bloques) "
                "VALUES (:id, :empresa_id, 2026, 1, 'INTEGRAL', 'en_proceso', 0)"
            ),
            {"id": exportacion_id, "empresa_id": empresa_a},
        )

    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO manifiesto_exportacion (id, empresa_id, exportacion_id, "
                    "formato_version, fecha_generacion, tenant_id, n_bloques, sha256_fichero) "
                    "VALUES (:id, :empresa_id, :exportacion, '1.0.0', now(), :empresa_id, 17, :sha)"
                ),
                {
                    "id": uuid.uuid4(),
                    "empresa_id": empresa_b,
                    "exportacion": exportacion_id,
                    "sha": "c" * 64,
                },
            )


async def test_config_sii_unica_por_empresa_en_postgresql(pg_engine: AsyncEngine):
    empresa = random.randrange(10_000_000, 90_000_000)
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social) "
                "VALUES (:id, :nif, 'SII SL') ON CONFLICT (company_id) DO NOTHING"
            ),
            {"id": empresa, "nif": "X00000860"},
        )
        await conn.execute(
            text(
                "INSERT INTO config_sii (id, empresa_id, obligado_sii, clave_regimen) "
                "VALUES (:id, :empresa_id, TRUE, '01')"
            ),
            {"id": uuid.uuid4(), "empresa_id": empresa},
        )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO config_sii (id, empresa_id, obligado_sii, clave_regimen) "
                    "VALUES (:id, :empresa_id, TRUE, '02')"
                ),
                {"id": uuid.uuid4(), "empresa_id": empresa},
            )


async def test_rbac_incluye_el_modulo_export_en_postgresql(pg_engine: AsyncEngine):
    async with pg_engine.connect() as conn:
        filas = (
            await conn.execute(
                text(
                    "SELECT operacion FROM permiso_operacion WHERE modulo = 'export'"
                )
            )
        ).scalars().all()
    # El enum `permiso_operacion_tipo` ordena por su valor de declaracion.
    assert set(filas) == {"ver", "crear", "configurar"}


async def test_documentos_unicidad_huella_y_triggers_en_postgresql(
    pg_engine: AsyncEngine,
):
    """SPEC-030: la huella es unica por asiento, la FK compuesta aísla el
    tenant y el contenido no se reescribe ni se borra (constitucion II)."""
    empresa_a = random.randrange(10_000_000, 90_000_000)
    empresa_b = empresa_a + 1
    nif_a = f"X{empresa_a % 100_000_000:08d}"
    nif_b = f"X{empresa_b % 100_000_000:08d}"
    entrada_a = uuid.uuid4()
    entrada_b = uuid.uuid4()
    huella = "b" * 64

    async def _empresa(conn, empresa: int, nif: str) -> None:
        await conn.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social) "
                "VALUES (:id, :nif, 'Documentos SL') ON CONFLICT (company_id) DO NOTHING"
            ),
            {"id": empresa, "nif": nif},
        )

    async def _asiento(conn, entrada: uuid.UUID, empresa: int, numero: int) -> None:
        """Asiento balanceado.

        Hace falta porque `trg_journal_entry_balance` es un trigger **diferido**
        de constitution I: rechaza en el `COMMIT` cualquier asiento cuyas lineas
        no cuadren, y un asiento sin apuntes tiene Debe 0 y Haber 0. Es la misma
        garantia que aplica en SQLite, y el test se apoya en ella de paso.
        """
        await conn.execute(
            text(
                "INSERT INTO journal_entry (id, empresa_id, ejercicio, fecha, tipo, "
                "concepto, numero_asiento, estado) "
                "VALUES (:id, :empresa_id, 2026, '2026-03-01', 'GENERAL', "
                "'Con soporte', :numero, 'POSTED')"
            ),
            {"id": entrada, "empresa_id": empresa, "numero": numero},
        )
        await conn.execute(
            text(
                "INSERT INTO journal_entry_line "
                "(empresa_id, journal_entry_id, cuenta, debe, haber) "
                "VALUES (:empresa_id, :id, '572', 100.0000, 0.0000)"
            ),
            {"empresa_id": empresa, "id": entrada},
        )
        await conn.execute(
            text(
                "INSERT INTO journal_entry_line "
                "(empresa_id, journal_entry_id, cuenta, debe, haber) "
                "VALUES (:empresa_id, :id, '430', 0.0000, 100.0000)"
            ),
            {"empresa_id": empresa, "id": entrada},
        )

    async def _documento(conn, doc: uuid.UUID, empresa: int, entrada: uuid.UUID, sha: str):
        await conn.execute(
            text(
                "INSERT INTO documento_asiento (id, empresa_id, journal_entry_id, "
                "contenido, sha256, nombre_original, content_type, extension, "
                "size_bytes, tipo_documento) "
                "VALUES (:id, :empresa_id, :entrada, :contenido, :sha, 'factura.pdf', "
                "'application/pdf', 'pdf', 9, 'factura')"
            ),
            {
                "id": doc,
                "empresa_id": empresa,
                "entrada": entrada,
                "contenido": b"%PDF-1.4\\0",
                "sha": sha,
            },
        )

    documento_id = uuid.uuid4()
    async with pg_engine.begin() as conn:
        await _empresa(conn, empresa_a, nif_a)
        await _empresa(conn, empresa_b, nif_b)
        await _asiento(conn, entrada_a, empresa_a, 1)
        await _asiento(conn, entrada_b, empresa_b, 1)
        await _documento(conn, documento_id, empresa_a, entrada_a, huella)

    # FR-006: la misma huella en el mismo asiento se rechaza.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await _documento(conn, uuid.uuid4(), empresa_a, entrada_a, huella)

    # Constitucion III: la FK compuesta impide anclar un documento de la
    # empresa A a un asiento de la empresa B.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await _documento(conn, uuid.uuid4(), empresa_a, entrada_b, "c" * 64)

    # La misma huella en OTRO asiento si se admite (FR-006: la duplicidad es
    # por asiento, no global).
    async with pg_engine.begin() as conn:
        await _documento(conn, uuid.uuid4(), empresa_b, entrada_b, huella)

    # Constitucion II / research D3: el contenido no se reescribe.
    for sentencia in (
        "UPDATE documento_asiento SET contenido = :binario WHERE id = :id",
        "UPDATE documento_asiento SET nombre_original = 'otro.pdf' WHERE id = :id",
        "UPDATE documento_asiento SET sha256 = :sha WHERE id = :id",
    ):
        with pytest.raises(DBAPIError):
            async with pg_engine.begin() as conn:
                await conn.execute(
                    text(sentencia),
                    {"id": documento_id, "binario": b"%PDF-1.4\\0\\0", "sha": "d" * 64},
                )

    # FR-012: la baja logica si se admite, y es completa por CHECK.
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE documento_asiento SET estado = 'dado_de_baja', "
                "baja_motivo = 'Escaneo ilegible', baja_usuario = '1', "
                "baja_at = now() WHERE id = :id"
            ),
            {"id": documento_id},
        )
    # Una baja incompleta la rechaza el CHECK chk_documento_asiento_baja.
    otro = uuid.uuid4()
    async with pg_engine.begin() as conn:
        await _documento(conn, otro, empresa_a, entrada_a, "e" * 64)
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE documento_asiento SET estado = 'dado_de_baja' WHERE id = :id"
                ),
                {"id": otro},
            )

    # El borrado fisico no existe: el trigger lo rechaza siempre.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM documento_asiento WHERE id = :id"), {"id": documento_id}
            )


async def test_documentos_aislan_las_empresas_en_postgresql(pg_engine: AsyncEngine):
    """SC-003: ningun documento de una empresa es visible desde otra. El
    UNIQUE (empresa_id, id) es la clave que consume la FK compuesta."""
    empresa_a = random.randrange(10_000_000, 90_000_000)
    empresa_b = empresa_a + 1
    async with pg_engine.begin() as conn:
        for empresa in (empresa_a, empresa_b):
            await conn.execute(
                text(
                    "INSERT INTO companies (company_id, nif, razon_social) "
                    "VALUES (:id, :nif, 'Aislado SL') ON CONFLICT (company_id) DO NOTHING"
                ),
                {
                    "id": empresa,
                    "nif": f"Y{empresa % 100_000_000:08d}",
                },
            )
    # El mismo par (empresa_id, id) en dos empresas viola el UNIQUE de clave
    # tenant: es la garantia estructural de que un id de documento no se
    # confunde entre tenants.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            compartido = uuid.uuid4()
            entradas = []
            for empresa in (empresa_a, empresa_b):
                entrada = uuid.uuid4()
                await conn.execute(
                    text(
                        "INSERT INTO journal_entry (id, empresa_id, ejercicio, fecha, "
                        "tipo, concepto, numero_asiento, estado) "
                        "VALUES (:id, :empresa_id, 2026, '2026-04-01', 'GENERAL', "
                        "'Aislamiento', 1, 'DRAFT')"
                    ),
                    {"id": entrada, "empresa_id": empresa},
                )
                # El asiento debe cuadrar: `trg_journal_entry_balance` es diferido
                # y revisa en el COMMIT (constitution I).
                await conn.execute(
                    text(
                        "INSERT INTO journal_entry_line "
                        "(empresa_id, journal_entry_id, cuenta, debe, haber) "
                        "VALUES (:empresa_id, :entrada, '572', 100.0000, 0.0000)"
                    ),
                    {"empresa_id": empresa, "entrada": entrada},
                )
                await conn.execute(
                    text(
                        "INSERT INTO journal_entry_line "
                        "(empresa_id, journal_entry_id, cuenta, debe, haber) "
                        "VALUES (:empresa_id, :entrada, '430', 0.0000, 100.0000)"
                    ),
                    {"empresa_id": empresa, "entrada": entrada},
                )
                entradas.append((entrada, empresa))
            for entrada, empresa in entradas:
                await conn.execute(
                    text(
                        "INSERT INTO documento_asiento (id, empresa_id, "
                        "journal_entry_id, contenido, sha256, nombre_original, "
                        "content_type, extension, size_bytes, tipo_documento) "
                        "VALUES (:id, :empresa_id, :entrada, :contenido, :sha, "
                        "'a.pdf', 'application/pdf', 'pdf', 5, 'factura')"
                    ),
                    {
                        "id": compartido,
                        "empresa_id": empresa,
                        "entrada": entrada,
                        "contenido": b"%PDF-1.4\\0",
                        "sha": "f" * 64,
                    },
                )


async def test_favoritos_unicidad_y_fk_de_vinculo_en_postgresql(
    pg_engine: AsyncEngine,
):
    """Migracion 022: el UNIQUE correcto y la FK que hace valido el aislamiento.

    En SQLite, `tests/integration/test_favoritos_tenant.py` ya comprueba que un
    favorito sin vinculacion se rechaza. Aqui se repite contra **PostgreSQL**, que es
    donde la FK se aplica de verdad y donde los indices se crean como los declara la
    migracion.

    Lo que se verifica:

    1. `UNIQUE (empresa_id, usuario_id, destino)` — el mismo destino marcado dos veces
       para el mismo par, falla.
    2. `UNIQUE (empresa_id, id)` — el mismo id en dos empresas, falla. Es la clave que
       hace que un id de favorito no se confunda entre tenants.
    3. `FOREIGN KEY (usuario_id, empresa_id) -> user_companies (user_id, company_id)` —
       un favorito de un usuario no vinculado a esa empresa, falla. Esta es la garantia
       fuerte: el dato no es invisible, es **invalido**.
    4. El mismo destino en dos empresas **si** se puede tener: son conjuntos distintos y
       un UNIQUE mas estrecho habria hecho imposible tener favoritos en las dos.
    """
    empresa_a = random.randrange(10_000_000, 90_000_000)
    empresa_b = empresa_a + 1
    usuario = random.randrange(10_000, 90_000)

    async with pg_engine.begin() as conn:
        for empresa in (empresa_a, empresa_b):
            await conn.execute(
                text(
                    "INSERT INTO companies (company_id, nif, razon_social) "
                    "VALUES (:id, :nif, 'Favoritos SL') ON CONFLICT DO NOTHING"
                ),
                {"id": empresa, "nif": f"F{empresa % 100_000_000:08d}"},
            )
        await conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name) "
                "VALUES (:id, :email, 'x', 'Fav') ON CONFLICT (id) DO NOTHING"
            ),
            {"id": usuario, "email": f"fav{usuario}@pg.es"},
        )
        # Vinculo del usuario con la empresa A, y SOLO con la A: el caso 3 necesita
        # una empresa a la que no pertenece.
        await conn.execute(
            text(
                "INSERT INTO user_companies (id, user_id, company_id, role, is_default) "
                "VALUES (:id, :usuario, :empresa, 'ADMIN', true)"
            ),
            {"id": random.randrange(10_000, 90_000), "usuario": usuario, "empresa": empresa_a},
        )
        await conn.execute(
            text(
                "INSERT INTO favorito_usuario "
                "(id, empresa_id, usuario_id, destino, orden) "
                "VALUES (:id, :empresa, :usuario, 'vencimientos', 1)"
            ),
            {"id": uuid.uuid4(), "empresa": empresa_a, "usuario": usuario},
        )

    def _insertar(conn, **kwargs):
        return conn.execute(
            text(
                "INSERT INTO favorito_usuario "
                "(id, empresa_id, usuario_id, destino, orden) "
                "VALUES (:id, :empresa, :usuario, :destino, :orden)"
            ),
            kwargs,
        )

    # 1. Mismo destino dos veces para el mismo par.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await _insertar(
                conn,
                id=uuid.uuid4(),
                empresa=empresa_a,
                usuario=usuario,
                destino="vencimientos",
                orden=2,
            )

    # 2. El mismo id en la otra empresa.
    compartido = uuid.uuid4()
    async with pg_engine.begin() as conn:
        await _insertar(
            conn,
            id=compartido,
            empresa=empresa_a,
            usuario=usuario,
            destino="asientos",
            orden=3,
        )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await _insertar(
                conn,
                id=compartido,
                empresa=empresa_b,
                usuario=usuario,
                destino="asientos",
                orden=3,
            )

    # 3. Empresa a la que el usuario no esta vinculado. Cada `pytest.raises` va en su
    #    propia transaccion a NIVEL DE FUNCION: anidado dentro de la transaccion de los
    #    inserts abre otra conexion que no ve las filas sin confirmar, y el error sale
    #    por otra causa y no prueba nada.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await _insertar(
                conn,
                id=uuid.uuid4(),
                empresa=empresa_b,
                usuario=usuario,
                destino="asientos",
                orden=4,
            )

    # 4. El mismo destino en las dos empresas, con dos vinculos distintos, si se puede.
    vinculo_b = random.randrange(10_000, 90_000)
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO user_companies (id, user_id, company_id, role) "
                "VALUES (:id, :usuario, :empresa, 'ADMIN')"
            ),
            {"id": vinculo_b, "usuario": usuario, "empresa": empresa_b},
        )
        await _insertar(
            conn,
            id=uuid.uuid4(),
            empresa=empresa_b,
            usuario=usuario,
            destino="vencimientos",
            orden=1,
        )


async def test_conciliacion_tiene_migracion_y_su_trigger_permite_cruzar(
    pg_engine: AsyncEngine,
):
    """Migracion 024: las 6 tablas de conciliacion y su inmutabilidad.

    **Por que este test existe.** SPEC-013 se cerro con 54/54 tareas y todas sus
    puertas en verde, y aun asi sus tablas no tenian migracion: vivian solo en el
    `create_all` de los tests de SQLite. Contra PostgreSQL real no existian, de modo
    que `POST /api/v1/extractos` devolvia 500 y **toda** la superficie de
    conciliacion era inusable en la aplicacion real. Ninguna puerta lo veia porque
    `test_migrations.py` solo comprueba que las migraciones *declaradas* esten en el
    inventario, no que cada tabla del ORM tenga una. Un modelo sin migracion es
    invisible para esa puerta.

    Lo que se verifica:

    1. Las 6 tablas existen en PostgreSQL. Es la asercion que habria fallado antes.
    2. `UPDATE ... SET estado` **si** se admite: confirmar un cruce pasa el
       movimiento a `conciliado` y deshacerlo lo devuelve a `pendiente`
       (`services/reconciliation/cruce.py`). Un trigger que reventase cualquier
       UPDATE dejaria la conciliacion inservible, que es justo su funcion.
    3. `UPDATE` de una columna de contenido (importe, signo, fecha, concepto) se
       **rechaza**: lo que dice el banco no se reescribe (constitucion II).
    4. `DELETE` se rechaza siempre, y `periodo_conciliado` es append-only entero.
    5. `importe > 0` y la unicidad de `sha256` por empresa, que es la deduplicacion
       de la importacion hecha a nivel de esquema.
    """
    empresa = random.randrange(10_000_000, 90_000_000)
    nif = f"C{empresa % 100_000_000:08d}"

    async with pg_engine.begin() as conn:
        # 1. Las 6 tablas.
        existentes = {
            fila[0]
            for fila in (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = ANY(:nombres)"
                    ),
                    {"nombres": [
                        "extracto_bancario", "movimiento_bancario", "conciliacion",
                        "cruce_conciliacion", "periodo_conciliado", "alerta_conciliacion",
                    ]},
                )
            ).all()
        }
        faltan = {
            "extracto_bancario", "movimiento_bancario", "conciliacion",
            "cruce_conciliacion", "periodo_conciliado", "alerta_conciliacion",
        } - existentes
        assert not faltan, (
            f"sin migracion en PostgreSQL: {sorted(faltan)}. La migracion 024 "
            "deberia estar aplicada (`python -m db.migrate`)"
        )

        await conn.execute(
            text(
                "INSERT INTO companies (company_id, nif, razon_social) "
                "VALUES (:id, :nif, 'Conciliacion SL') ON CONFLICT DO NOTHING"
            ),
            {"id": empresa, "nif": nif},
        )
        # `cuenta_id` tiene FK a `account_plan`. No hace falta plantar el arbol: al
        # insertar la empresa, `trg_companies_seed` corre `seed_default_pgc` y deja
        # el PGC entero, `5720` incluida. Intentar plantar una cuenta suelta choca
        # con `chk_account_plan_structure`, que exige el padre de cada nivel.
        cuenta = (
            await conn.execute(
                text("SELECT id FROM account_plan WHERE tenant_id = :t AND code = '5720'"),
                {"t": empresa},
            )
        ).scalar()
        assert cuenta is not None, "el seed del PGC deberia haber creado la cuenta 5720"
        extracto = uuid.uuid4()
        movimiento = uuid.uuid4()
        sha = f"{empresa:064d}"[:64]
        await conn.execute(
            text(
                "INSERT INTO extracto_bancario (id, empresa_id, cuenta_id, fecha_inicio, "
                "fecha_fin, saldo_inicial, saldo_final, nombre_fichero, sha256, n_movimientos) "
                "VALUES (:id, :empresa, :cuenta, '2026-01-02', '2026-02-27', 1863.7400, "
                "5281.9900, 'x.xlsx', :sha, 1)"
            ),
            {"id": extracto, "empresa": empresa, "cuenta": cuenta, "sha": sha},
        )
        await conn.execute(
            text(
                "INSERT INTO movimiento_bancario (id, empresa_id, extracto_id, orden, "
                "fecha_operacion, concepto, importe, signo) "
                "VALUES (:id, :empresa, :extracto, 1, '2026-01-02', 'Abono', 1125.0000, 'H')"
            ),
            {"id": movimiento, "empresa": empresa, "extracto": extracto},
        )

    # 2. `estado` SI se puede cambiar: es lo que hace confirmar y deshacer un cruce.
    async with pg_engine.begin() as conn:
        await conn.execute(
            text("UPDATE movimiento_bancario SET estado = 'conciliado' WHERE id = :id"),
            {"id": movimiento},
        )
        estado = (
            await conn.execute(
                text("SELECT estado FROM movimiento_bancario WHERE id = :id"),
                {"id": movimiento},
            )
        ).scalar()
        assert estado == "conciliado"
    async with pg_engine.begin() as conn:
        await conn.execute(
            text("UPDATE movimiento_bancario SET estado = 'pendiente' WHERE id = :id"),
            {"id": movimiento},
        )

    # 3. El contenido descargado del banco no se reescribe. Cada `pytest.raises` en su
    #    propia transaccion a NIVEL DE FUNCION (leccion de la seccion anterior).
    for columna, valor in (
        ("importe", "999999.0000"),
        ("signo", "'D'"),
        ("concepto", "'Otro concepto'"),
        ("fecha_operacion", "'2026-03-01'"),
    ):
        with pytest.raises(DBAPIError) as exc:
            async with pg_engine.begin() as conn:
                await conn.execute(
                    text(f"UPDATE movimiento_bancario SET {columna} = {valor} WHERE id = :id"),
                    {"id": movimiento},
                )
        assert "inmutable" in str(exc.value), (
            f"cambiar {columna} deberia decir que es inmutable, y dice: {exc.value}"
        )

    # 4. DELETE rechazado, y el periodo conciliado inmutable entero.
    with pytest.raises(DBAPIError) as exc:
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM movimiento_bancario WHERE id = :id"), {"id": movimiento}
            )
    assert "no se borra" in str(exc.value)

    conciliacion = uuid.uuid4()
    periodo = uuid.uuid4()
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO conciliacion (id, empresa_id, cuenta_id, ejercicio, fecha_inicio, "
                "fecha_fin, extracto_id, saldo_banco, saldo_libros, diferencia) "
                "VALUES (:id, :empresa, :cuenta, 2026, '2026-01-02', '2026-02-27', :extracto, "
                "100.0000, 100.0000, 0.0000)"
            ),
            {"id": conciliacion, "empresa": empresa, "cuenta": cuenta, "extracto": extracto},
        )
        await conn.execute(
            text(
                "INSERT INTO periodo_conciliado (id, empresa_id, conciliacion_id, cuenta_id, "
                "ejercicio, numero_periodo, fecha_inicio, fecha_fin, saldo_banco, saldo_libros, "
                "diferencia) VALUES (:id, :empresa, :conc, :cuenta, 2026, 1, '2026-01-02', "
                "'2026-02-27', 100.0000, 100.0000, 0.0000)"
            ),
            {"id": periodo, "empresa": empresa, "conc": conciliacion, "cuenta": cuenta},
        )
    with pytest.raises(DBAPIError) as exc:
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("UPDATE periodo_conciliado SET diferencia = 5.0000 WHERE id = :id"),
                {"id": periodo},
            )
    assert "inmutable" in str(exc.value)
    with pytest.raises(DBAPIError) as exc:
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM periodo_conciliado WHERE id = :id"), {"id": periodo}
            )
    assert "inmutable" in str(exc.value)

    # 5. `importe > 0` y unicidad de `sha256` por empresa: la deduplicacion de la
    #    importacion hecha a nivel de esquema, no solo en el servicio.
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO movimiento_bancario (id, empresa_id, extracto_id, orden, "
                    "fecha_operacion, concepto, importe, signo) "
                    "VALUES (:id, :empresa, :extracto, 9, '2026-01-03', 'C', -5.0000, 'D')"
                ),
                {"id": uuid.uuid4(), "empresa": empresa, "extracto": extracto},
            )
    with pytest.raises(DBAPIError):
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO extracto_bancario (id, empresa_id, cuenta_id, fecha_inicio, "
                    "fecha_fin, saldo_inicial, saldo_final, nombre_fichero, sha256, "
                    "n_movimientos) VALUES (:id, :empresa, :cuenta, '2026-01-02', '2026-02-27', "
                    "1863.7400, 5281.9900, 'otro.xlsx', :sha, 1)"
                ),
                {"id": uuid.uuid4(), "empresa": empresa, "cuenta": cuenta, "sha": sha},
            )
