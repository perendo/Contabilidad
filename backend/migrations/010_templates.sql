-- ============================================================
--  010_templates.sql
--  Plantillas de asientos reutilizables (SPEC-018): cabecera, variables y
--  lineas con importes fijos/variables, mas la traza inmutable de los asientos
--  generados. Idempotente.
--
--  Multi-tenant estricto (constitucion III): `empresa_id` en PK/indices/FK de
--  todas las tablas. Inmutabilidad (constitucion II): `asiento_generado` es
--  append-only y una plantilla con asientos generados no se borra fisicamente.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'plantilla_estado') THEN
        CREATE TYPE plantilla_estado AS ENUM ('activa', 'inactiva');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'plantilla_posicion') THEN
        CREATE TYPE plantilla_posicion AS ENUM ('debe', 'haber');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'plantilla_variable_tipo') THEN
        CREATE TYPE plantilla_variable_tipo AS ENUM ('importe');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS plantilla_asiento (
    id              UUID PRIMARY KEY,
    empresa_id      BIGINT NOT NULL,
    nombre          VARCHAR(120) NOT NULL,
    descripcion     TEXT,
    categoria       VARCHAR(50),
    version_actual  INTEGER NOT NULL DEFAULT 1,
    estado          plantilla_estado NOT NULL DEFAULT 'activa',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_plantilla_asiento_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_plantilla_asiento_empresa_nombre UNIQUE (empresa_id, nombre),
    CONSTRAINT fk_plantilla_asiento_empresa FOREIGN KEY (empresa_id)
        REFERENCES companies (company_id)
);

CREATE INDEX IF NOT EXISTS ix_plantilla_asiento_empresa
    ON plantilla_asiento (empresa_id);
CREATE INDEX IF NOT EXISTS ix_plantilla_asiento_empresa_estado
    ON plantilla_asiento (empresa_id, estado);

CREATE TABLE IF NOT EXISTS variable_plantilla (
    id            UUID PRIMARY KEY,
    empresa_id    BIGINT NOT NULL,
    plantilla_id  UUID NOT NULL,
    nombre        VARCHAR(60) NOT NULL,
    tipo          plantilla_variable_tipo NOT NULL DEFAULT 'importe',
    es_requerida  BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_variable_plantilla_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT fk_variable_plantilla_empresa_plantilla
        FOREIGN KEY (empresa_id, plantilla_id)
        REFERENCES plantilla_asiento (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_variable_plantilla_empresa
    ON variable_plantilla (empresa_id);
CREATE INDEX IF NOT EXISTS ix_variable_plantilla_empresa_plantilla
    ON variable_plantilla (empresa_id, plantilla_id);

CREATE TABLE IF NOT EXISTS linea_plantilla (
    id            UUID PRIMARY KEY,
    empresa_id    BIGINT NOT NULL,
    plantilla_id  UUID NOT NULL,
    orden         SMALLINT NOT NULL,
    cuenta_id     BIGINT NOT NULL,
    posicion      plantilla_posicion NOT NULL,
    importe_fijo  NUMERIC(18, 4),
    variable_id   UUID,
    CONSTRAINT fk_linea_plantilla_empresa_plantilla
        FOREIGN KEY (empresa_id, plantilla_id)
        REFERENCES plantilla_asiento (empresa_id, id),
    CONSTRAINT fk_linea_plantilla_empresa_variable
        FOREIGN KEY (empresa_id, variable_id)
        REFERENCES variable_plantilla (empresa_id, id),
    CONSTRAINT fk_linea_plantilla_empresa_cuenta
        FOREIGN KEY (empresa_id, cuenta_id)
        REFERENCES account_plan (tenant_id, id),
    CONSTRAINT linea_plantilla_fijo_variable_excluyentes CHECK (
        (importe_fijo IS NOT NULL AND variable_id IS NULL)
        OR (importe_fijo IS NULL AND variable_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_linea_plantilla_empresa
    ON linea_plantilla (empresa_id);
CREATE INDEX IF NOT EXISTS ix_linea_plantilla_empresa_plantilla
    ON linea_plantilla (empresa_id, plantilla_id, orden);

CREATE TABLE IF NOT EXISTS asiento_generado (
    empresa_id          BIGINT NOT NULL,
    asiento_id          UUID NOT NULL,
    plantilla_id        UUID NOT NULL,
    version_plantilla   INTEGER NOT NULL,
    variables_aportadas JSONB NOT NULL,
    fecha_generacion    TIMESTAMPTZ NOT NULL DEFAULT now(),
    usuario_generador   BIGINT,
    CONSTRAINT pk_asiento_generado PRIMARY KEY (empresa_id, asiento_id),
    CONSTRAINT fk_asiento_generado_empresa_plantilla
        FOREIGN KEY (empresa_id, plantilla_id)
        REFERENCES plantilla_asiento (empresa_id, id),
    CONSTRAINT fk_asiento_generado_empresa_asiento
        FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_asiento_generado_empresa
    ON asiento_generado (empresa_id);
CREATE INDEX IF NOT EXISTS ix_asiento_generado_empresa_plantilla
    ON asiento_generado (empresa_id, plantilla_id);

-- La traza de generacion es append-only (constitucion II).
CREATE OR REPLACE FUNCTION f_asiento_generado_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'asiento_generado: la traza generada es inmutable';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_asiento_generado_immutable_update ON asiento_generado;
CREATE TRIGGER trg_asiento_generado_immutable_update
    BEFORE UPDATE ON asiento_generado
    FOR EACH ROW EXECUTE FUNCTION f_asiento_generado_immutable();

DROP TRIGGER IF EXISTS trg_asiento_generado_immutable_delete ON asiento_generado;
CREATE TRIGGER trg_asiento_generado_immutable_delete
    BEFORE DELETE ON asiento_generado
    FOR EACH ROW EXECUTE FUNCTION f_asiento_generado_immutable();

-- Proteccion del historico (FR-006): una plantilla con asientos generados no
-- se puede borrar fisicamente; solo inactivacion.
CREATE OR REPLACE FUNCTION f_plantilla_asiento_no_delete() RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM asiento_generado
        WHERE empresa_id = OLD.empresa_id AND plantilla_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'plantilla_asiento: no se puede eliminar una plantilla con asientos generados';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_plantilla_asiento_no_delete ON plantilla_asiento;
CREATE TRIGGER trg_plantilla_asiento_no_delete
    BEFORE DELETE ON plantilla_asiento
    FOR EACH ROW EXECUTE FUNCTION f_plantilla_asiento_no_delete();
