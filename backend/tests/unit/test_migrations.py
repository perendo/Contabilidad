"""Migration inventory (SPEC-001/002/003/004).

El DDL PostgreSQL no se puede ejecutar sin una instancia PG; estos tests
protegen el inventario y el orden de dependencias que aplica `db.migrate`.
"""

from __future__ import annotations

from db.migrate import MIGRATIONS_DIR, archivos_ordenados

ESPERADAS = [
    "000_audit_log.sql",
    "004_iam.sql",
    "001_account_plan.sql",
    "002_seed_pgc.sql",
    "003_journal.sql",
    "005_fiscal_invoice.sql",
    "006_apertura.sql",
    "007_rbac.sql",
    "008_forex.sql",
    "009_costcenters.sql",
    "010_templates.sql",
    "011_ngo.sql",
    "012_efectos.sql",
    "013_anticipos.sql",
    "014_impuesto_sociedades.sql",
    "015_retenciones_irpf.sql",
    "016_catalogo.sql",
    "017_presupuestos.sql",
    "018_cashflow.sql",
    "019_cierres.sql",
    "020_export.sql",
    "021_adjuntos_asiento.sql",
    "022_favoritos.sql",
]


def test_migraciones_esperadas_existen():
    nombres = {p.name for p in MIGRATIONS_DIR.glob("*.sql")}
    assert set(ESPERADAS) <= nombres


def test_orden_por_dependencias():
    assert [p.name for p in archivos_ordenados()] == ESPERADAS


def test_migraciones_no_vacias():
    for nombre in ESPERADAS:
        contenido = (MIGRATIONS_DIR / nombre).read_text(encoding="utf-8")
        assert contenido.strip()


def test_migracion_diario_declara_trigger_balance_diferido():
    contenido = (MIGRATIONS_DIR / "003_journal.sql").read_text(encoding="utf-8")
    assert "chk_journal_entry_balance" in contenido
    assert "DEFERRABLE INITIALLY DEFERRED" in contenido


def test_migracion_retenciones_incluye_backfill_y_triggers() -> None:
    contenido = (MIGRATIONS_DIR / "015_retenciones_irpf.sql").read_text(
        encoding="utf-8"
    )
    assert "'4751'" in contenido
    assert "to_regclass('public.tercero')" in contenido
    assert "trg_liquidacion_retenciones_final_update" in contenido
    assert "trg_modelo_190_append_only_delete" in contenido
    assert "trg_companies_seed_retenciones_4751" in contenido
    assert "ADD COLUMN IF NOT EXISTS tipo_retencion" in contenido
    assert "ADD COLUMN IF NOT EXISTS direccion_inmueble" in contenido


def test_migracion_presupuestos_declara_unicidad_parcial_y_snapshot() -> None:
    contenido = (MIGRATIONS_DIR / "017_presupuestos.sql").read_text(encoding="utf-8")
    assert "uq_presupuesto_sin_centro" in contenido
    assert "uq_presupuesto_con_centro" in contenido
    assert "uq_periodo_seguimiento_abierto" in contenido
    assert "trg_desviacion_append_only_update" in contenido
    assert "trg_desviacion_append_only_delete" in contenido
    assert "REFERENCES account_plan (tenant_id, id)" in contenido
    assert "REFERENCES centro_coste (empresa_id, id)" in contenido


def test_migracion_cashflow_declara_correlatividad_y_snapshot_efe() -> None:
    contenido = (MIGRATIONS_DIR / "018_cashflow.sql").read_text(encoding="utf-8")
    assert "uq_prevision_tesoreria_numero" in contenido
    assert "uq_alerta_liquidez_prevision_fecha" in contenido
    assert "uq_informe_efe_ejercicio" in contenido
    assert "trg_informe_efe_append_only_update" in contenido
    assert "trg_linea_efe_append_only_delete" in contenido
    assert "REFERENCES account_plan (tenant_id, id)" in contenido
    assert "alerta_liquidez_saldo_negativo CHECK (saldo_proyectado < 0)" in contenido
    # `vencimiento` (SPEC-011) no tiene migracion propia: la FK se anade solo si
    # existe, igual que `tercero` en 015_retenciones_irpf.sql.
    assert "to_regclass('public.vencimiento')" in contenido
    assert "REFERENCES vencimiento (empresa_id, id)" in contenido


def test_migracion_cierres_declara_bloqueo_y_snapshots() -> None:
    """T009/T018/T044: bloqueo de periodos, snapshot inmutable y correlatividad."""
    contenido = (MIGRATIONS_DIR / "019_cierres.sql").read_text(encoding="utf-8")
    # Bloqueo de periodos a nivel de motor (FR-001, research D9).
    assert "chk_journal_entry_fecha_abierta" in contenido
    assert "p.estado IN ('cerrado', 'cerrado_ajustado')" in contenido
    # Snapshot del balance de comprobacion inmutable (constitucion II).
    assert "trg_balanza_periodo_append_only_update" in contenido
    assert "trg_balanza_periodo_linea_append_only_delete" in contenido
    # Partida doble en el propio CHECK (constitucion I).
    assert "CHECK (total_debe = total_haber)" in contenido
    # Clave natural del periodo y unicidad del balance por cierre.
    assert "uq_periodo_cerrado_natural" in contenido
    assert "uq_balanza_periodo_periodo" in contenido
    # Correlatividad de la solicitud de reapertura (constitucion IV).
    assert "secuencia_reapertura" in contenido
    assert "uq_solicitud_reapertura_numero" in contenido
    # FR-005: una sola solicitud activa por periodo (`periodo_id` es NULLABLE).
    assert "uq_solicitud_reapertura_activa" in contenido
    assert "chk_solicitud_reapertura_motivo" in contenido
    # Multi-tenancy: FKs compuestas y plan por `tenant_id` (SPEC-001).
    assert "REFERENCES account_plan (tenant_id, id)" in contenido
    assert "REFERENCES periodo_cerrado (empresa_id, id)" in contenido
    # T009: ampliacion del enum de tipos del motor de SPEC-002.
    assert "ADD VALUE IF NOT EXISTS 'REGULARIZACION'" in contenido
    assert "ADD VALUE IF NOT EXISTS 'CIERRE'" in contenido


def test_migracion_documentos_declara_inmutabilidad_y_huella() -> None:
    """T010: unicidad de huella, FK compuesta al diario e inmutabilidad real."""
    contenido = (MIGRATIONS_DIR / "021_adjuntos_asiento.sql").read_text(
        encoding="utf-8"
    )
    # FR-006 / research D6: unicidad incondicional, sin indice parcial.
    assert "uq_documento_asiento_huella UNIQUE" in contenido
    assert "(empresa_id, journal_entry_id, sha256)" in contenido
    # Constitucion III: la BD impide el anclaje cross-tenant.
    assert "fk_documento_asiento_entrada" in contenido
    assert "REFERENCES journal_entry (empresa_id, id)" in contenido
    # Constitucion II / research D3: contenido congelado y borrado fisico veto.
    assert "f_documento_asiento_inmutable_update" in contenido
    assert "trg_documento_asiento_contenido_inmutable_update" in contenido
    assert "trg_documento_asiento_inmutable_delete" in contenido
    # FR-012: la baja logica esta completa y trazada.
    assert "chk_documento_asiento_baja" in contenido
    # research D19: NUMERIC(18,4), jamas float.
    assert "importe_informativo   NUMERIC(18, 4)" in contenido
    # FR-020 / research D11: la adjuncion es opcional. La migracion no anade
    # ninguna columna ni restriccion al diario: no hay recuento de documentos
    # ni un NOT NULL que obligue a tenerlos.
    assert "ALTER TABLE journal_entry" not in contenido
    assert "ADD COLUMN" not in contenido
