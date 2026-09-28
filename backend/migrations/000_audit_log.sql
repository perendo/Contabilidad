-- ============================================================
--  000_audit_log.sql
--  Log de auditoría inmutable (WORM), multi-tenant.
--  Fuente: plan.md raíz §5.e y constitución II.
--  Alineado con backend/src/models/audit/audit_log.py (naming `empresa_id`).
--  Idempotente: puede reaplicarse sobre un esquema existente.
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id  BIGINT       NULL,
    usuario     VARCHAR(120) NULL,
    ip          VARCHAR(45)  NULL,
    operacion   VARCHAR(64)  NOT NULL,
    entidad     VARCHAR(64)  NOT NULL,
    entidad_id  VARCHAR(96)  NULL,
    payload     TEXT         NULL,
    timestamp   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_audit_log_empresa_id
    ON audit_log (empresa_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_log_empresa_id
    ON audit_log (empresa_id, id);

-- Inmutabilidad del log: PROHIBIDO UPDATE y DELETE (WORM)
CREATE OR REPLACE FUNCTION chk_audit_log_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log: el log de auditoría es inmutable (operación % denegada)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log;
CREATE TRIGGER trg_audit_log_immutable
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION chk_audit_log_immutable();
