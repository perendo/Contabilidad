-- ============================================================
--  009_costcenters.sql
--  Centros de coste (SPEC-017): catálogo jerárquico por empresa, closure table
--  y traza de imputación por apunte (dimensión opcional de línea del motor
--  multilínea SPEC-006). Idempotente.
--
--  Multi-tenant estricto (constitución III): `empresa_id` en PK/índices/FK de
--  todas las tablas. Inmutabilidad (constitución II): `imputacion_centro` es
--  append-only y los centros con imputaciones/descendientes no se borran.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'centro_tipo') THEN
        CREATE TYPE centro_tipo AS ENUM (
            'departamento', 'proyecto', 'subvencion', 'delegacion'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'centro_estado') THEN
        CREATE TYPE centro_estado AS ENUM ('activo', 'inactivo');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS centro_coste (
    id             UUID PRIMARY KEY,
    empresa_id     BIGINT NOT NULL,
    codigo         VARCHAR(20) NOT NULL,
    nombre         VARCHAR(120) NOT NULL,
    tipo           centro_tipo NOT NULL,
    parent_id      UUID,
    subvencion_id  UUID,
    estado         centro_estado NOT NULL DEFAULT 'activo',
    es_hoja        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_centro_coste_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_centro_coste_empresa_codigo UNIQUE (empresa_id, codigo),
    CONSTRAINT chk_centro_coste_codigo_len CHECK (char_length(codigo) BETWEEN 1 AND 20),
    CONSTRAINT chk_centro_coste_nombre_len CHECK (char_length(nombre) BETWEEN 1 AND 120),
    CONSTRAINT chk_centro_coste_no_auto_raiz CHECK (parent_id IS DISTINCT FROM id),
    CONSTRAINT fk_centro_coste_parent FOREIGN KEY (empresa_id, parent_id)
        REFERENCES centro_coste (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_centro_coste_empresa ON centro_coste (empresa_id);
CREATE INDEX IF NOT EXISTS ix_centro_coste_empresa_parent
    ON centro_coste (empresa_id, parent_id);
CREATE INDEX IF NOT EXISTS ix_centro_coste_empresa_tipo
    ON centro_coste (empresa_id, tipo, estado);

CREATE TABLE IF NOT EXISTS jerarquia_centro (
    empresa_id       BIGINT NOT NULL,
    ancestro_id      UUID NOT NULL,
    descendiente_id  UUID NOT NULL,
    profundidad      SMALLINT NOT NULL,
    CONSTRAINT pk_jerarquia_centro PRIMARY KEY (empresa_id, ancestro_id, descendiente_id),
    CONSTRAINT fk_jerarquia_centro_ancestro FOREIGN KEY (empresa_id, ancestro_id)
        REFERENCES centro_coste (empresa_id, id),
    CONSTRAINT fk_jerarquia_centro_descendiente FOREIGN KEY (empresa_id, descendiente_id)
        REFERENCES centro_coste (empresa_id, id)
);

CREATE TABLE IF NOT EXISTS imputacion_centro (
    id                UUID PRIMARY KEY,
    empresa_id        BIGINT NOT NULL,
    asiento_id        UUID NOT NULL,
    linea_id          UUID NOT NULL,
    centro_coste_id   UUID NOT NULL,
    periodo           SMALLINT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_imputacion_centro_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_imputacion_centro_linea UNIQUE (empresa_id, asiento_id, linea_id),
    CONSTRAINT fk_imputacion_centro_asiento FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT fk_imputacion_centro_linea FOREIGN KEY (empresa_id, linea_id)
        REFERENCES journal_entry_line (empresa_id, id),
    CONSTRAINT fk_imputacion_centro_centro FOREIGN KEY (empresa_id, centro_coste_id)
        REFERENCES centro_coste (empresa_id, id),
    CONSTRAINT chk_imputacion_centro_periodo CHECK (periodo BETWEEN 1 AND 12)
);

-- Dimensión opcional de línea (SPEC-006): centro de coste de la empresa de la
-- línea. La FK compuesta (empresa_id, centro_coste_id) impide técnicamente
-- imputar a un centro cross-tenant.
ALTER TABLE journal_entry_line
    ADD COLUMN IF NOT EXISTS centro_coste_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_journal_line_centro_coste'
    ) THEN
        ALTER TABLE journal_entry_line
            ADD CONSTRAINT fk_journal_line_centro_coste
            FOREIGN KEY (empresa_id, centro_coste_id)
            REFERENCES centro_coste (empresa_id, id);
    END IF;
END
$$;

-- La traza de imputación es append-only cuando el asiento está POSTED/CANCELLED
-- (constitución II); en borrador se admite reasignación/borrado controlado.
CREATE OR REPLACE FUNCTION f_imputacion_centro_immutable() RETURNS trigger AS $$
BEGIN
    IF (
        SELECT estado FROM journal_entry WHERE id = OLD.asiento_id
    ) IN ('POSTED', 'CANCELLED') THEN
        RAISE EXCEPTION 'imputacion_centro: la imputacion de un asiento POSTED/CANCELLED es inmutable';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_imputacion_centro_immutable_update ON imputacion_centro;
CREATE TRIGGER trg_imputacion_centro_immutable_update
    BEFORE UPDATE ON imputacion_centro
    FOR EACH ROW EXECUTE FUNCTION f_imputacion_centro_immutable();

DROP TRIGGER IF EXISTS trg_imputacion_centro_immutable_delete ON imputacion_centro;
CREATE TRIGGER trg_imputacion_centro_immutable_delete
    BEFORE DELETE ON imputacion_centro
    FOR EACH ROW EXECUTE FUNCTION f_imputacion_centro_immutable();

-- Protección del histórico (FR-005): un centro con imputaciones o descendientes
-- no se puede borrar físicamente; solo inactivación.
CREATE OR REPLACE FUNCTION f_centro_coste_no_delete() RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM imputacion_centro
        WHERE empresa_id = OLD.empresa_id AND centro_coste_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'centro_coste: no se puede eliminar un centro con imputaciones';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jerarquia_centro
        WHERE empresa_id = OLD.empresa_id
          AND ancestro_id = OLD.id AND descendiente_id <> OLD.id
    ) THEN
        RAISE EXCEPTION 'centro_coste: no se puede eliminar un centro con descendientes';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_centro_coste_no_delete ON centro_coste;
CREATE TRIGGER trg_centro_coste_no_delete
    BEFORE DELETE ON centro_coste
    FOR EACH ROW EXECUTE FUNCTION f_centro_coste_no_delete();