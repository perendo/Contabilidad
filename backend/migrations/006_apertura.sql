-- ============================================================
--  006_apertura.sql
--  Apertura del ejercicio (SPEC-009): estado del ciclo contable
--  y extensión del diario con asientos de apertura.
--  Idempotente. Dependencia: journal_entry (003_journal.sql).
-- ============================================================

-- 1) Extensión del diario: tipos OPENING / OPENING_REVERSAL
--    (PostgreSQL 12+ permite ADD VALUE dentro de una transacción;
--     el nuevo valor no se usa en esta misma transacción).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'journal_entry_tipo') THEN
        ALTER TYPE journal_entry_tipo ADD VALUE IF NOT EXISTS 'OPENING';
        ALTER TYPE journal_entry_tipo ADD VALUE IF NOT EXISTS 'OPENING_REVERSAL';
    END IF;
END
$$;

ALTER TABLE journal_entry
    ADD COLUMN IF NOT EXISTS referencia_cierre_id UUID NULL;

-- 2) Estado del ciclo por ejercicio (abierto/cerrado/con_apertura)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ejercicio_estado') THEN
        CREATE TYPE ejercicio_estado AS ENUM ('abierto', 'cerrado', 'con_apertura');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS ejercicio_contable (
    id                           UUID                  PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id                   BIGINT                NOT NULL,
    ejercicio                    INTEGER               NOT NULL,
    fecha_inicio                 DATE                  NOT NULL,
    fecha_fin                    DATE                  NOT NULL,
    estado                       ejercicio_estado      NOT NULL,
    apertura_entry_id            UUID                  NULL,
    apertura_reversal_entry_id   UUID                  NULL,
    created_by                   VARCHAR(120)          NULL,
    created_at                   TIMESTAMPTZ           NOT NULL DEFAULT now(),
    CONSTRAINT uq_ejercicio_contable_tenant_id
        UNIQUE (empresa_id, id),
    CONSTRAINT uq_ejercicio_contable_tenant_ejercicio
        UNIQUE (empresa_id, ejercicio),
    CONSTRAINT chk_ejercicio_contable_rango
        CHECK (fecha_inicio < fecha_fin),
    CONSTRAINT fk_ejercicio_apertura
        FOREIGN KEY (empresa_id, apertura_entry_id)
        REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT fk_ejercicio_apertura_reversal
        FOREIGN KEY (empresa_id, apertura_reversal_entry_id)
        REFERENCES journal_entry (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_ejercicio_contable_empresa_id
    ON ejercicio_contable (empresa_id);