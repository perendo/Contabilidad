-- SPEC-016 · Multi-divisa (PG 16+).
-- Moneda funcional/divisas, tipos de cambio sellados (constitución II),
-- asientos en divisa y diferencias de cambio. Idempotente.

DO $$
BEGIN
    CREATE TYPE diferencia_cambio_estado AS ENUM (
        'calculada', 'asentada'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS moneda (
    id UUID PRIMARY KEY,
    empresa_id BIGINT NOT NULL,
    codigo_iso CHAR(3) NOT NULL,
    es_funcional BOOLEAN NOT NULL DEFAULT FALSE,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_moneda_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_moneda_codigo_iso CHECK (codigo_iso ~ '^[A-Z]{3}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_moneda_funcional_unica
    ON moneda (empresa_id) WHERE es_funcional = true;

CREATE TABLE IF NOT EXISTS tipo_cambio (
    id UUID PRIMARY KEY,
    empresa_id BIGINT NOT NULL,
    divisa_id UUID NOT NULL,
    fecha DATE NOT NULL,
    ratio NUMERIC(18, 8) NOT NULL,
    usos_posteados BIGINT NOT NULL DEFAULT 0,
    sellado BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_tipo_cambio_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_tipo_cambio_divisa_fecha UNIQUE (empresa_id, divisa_id, fecha),
    CONSTRAINT fk_tipo_cambio_moneda FOREIGN KEY (empresa_id, divisa_id)
        REFERENCES moneda (empresa_id, id),
    CONSTRAINT chk_tipo_cambio_ratio_positivo CHECK (ratio > 0),
    CONSTRAINT chk_tipo_cambio_precision_8 CHECK (ratio = ROUND(ratio, 8)),
    CONSTRAINT chk_tipo_cambio_sellado_consistente CHECK (sellado = (usos_posteados > 0))
);

CREATE TABLE IF NOT EXISTS asiento_divisa (
    id UUID PRIMARY KEY,
    empresa_id BIGINT NOT NULL,
    asiento_id UUID NOT NULL,
    divisa_id UUID NOT NULL,
    tipo_cambio_id UUID NOT NULL,
    fecha DATE NOT NULL,
    concepto VARCHAR(255) NOT NULL,
    importe_total_divisa NUMERIC(18, 4) NOT NULL,
    importe_total_funcional NUMERIC(18, 4) NOT NULL,
    CONSTRAINT uq_asiento_divisa_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_asiento_divisa_asiento UNIQUE (empresa_id, asiento_id),
    CONSTRAINT fk_asiento_divisa_asiento FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT fk_asiento_divisa_moneda FOREIGN KEY (empresa_id, divisa_id)
        REFERENCES moneda (empresa_id, id),
    CONSTRAINT fk_asiento_divisa_tipo FOREIGN KEY (empresa_id, tipo_cambio_id)
        REFERENCES tipo_cambio (empresa_id, id),
    CONSTRAINT chk_asiento_divisa_importe CHECK (importe_total_divisa > 0),
    CONSTRAINT chk_asiento_divisa_importe_funcional CHECK (importe_total_funcional > 0)
);

CREATE TABLE IF NOT EXISTS linea_divisa (
    id UUID PRIMARY KEY,
    empresa_id BIGINT NOT NULL,
    asiento_divisa_id UUID NOT NULL,
    linea_id UUID NOT NULL,
    importe_divisa NUMERIC(18, 4) NOT NULL DEFAULT 0,
    importe_funcional NUMERIC(18, 4) NOT NULL,
    es_linea_redondeo BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_linea_divisa_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_linea_divisa_por_asiento UNIQUE (empresa_id, asiento_divisa_id, linea_id),
    CONSTRAINT fk_linea_divisa_asiento FOREIGN KEY (empresa_id, asiento_divisa_id)
        REFERENCES asiento_divisa (empresa_id, id),
    CONSTRAINT fk_linea_divisa_linea FOREIGN KEY (empresa_id, linea_id)
        REFERENCES journal_entry_line (empresa_id, id)
);

CREATE TABLE IF NOT EXISTS diferencia_cambio (
    id UUID PRIMARY KEY,
    empresa_id BIGINT NOT NULL,
    ejercicio INTEGER NOT NULL,
    fecha_valoracion DATE NOT NULL,
    cuenta_id BIGINT NOT NULL,
    divisa_id UUID NOT NULL,
    tipo_cierre_id UUID NOT NULL,
    saldo_divisa NUMERIC(18, 4) NOT NULL,
    saldo_funcional_previo NUMERIC(18, 4) NOT NULL,
    valoracion NUMERIC(18, 4) NOT NULL,
    diferencia NUMERIC(18, 4) NOT NULL,
    estado diferencia_cambio_estado NOT NULL DEFAULT 'asentada',
    asiento_id UUID,
    CONSTRAINT uq_diferencia_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_diferencia_cierre_unica
        UNIQUE (empresa_id, ejercicio, fecha_valoracion, cuenta_id, divisa_id),
    CONSTRAINT fk_diferencia_cuenta FOREIGN KEY (empresa_id, cuenta_id)
        REFERENCES account_plan (tenant_id, id),
    CONSTRAINT fk_diferencia_moneda FOREIGN KEY (empresa_id, divisa_id)
        REFERENCES moneda (empresa_id, id),
    CONSTRAINT fk_diferencia_tipo FOREIGN KEY (empresa_id, tipo_cierre_id)
        REFERENCES tipo_cambio (empresa_id, id),
    CONSTRAINT fk_diferencia_asiento FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT chk_diferencia_no_nula CHECK (diferencia <> 0)
);

-- Inmutabilidad del tipo sellado a nivel DB (constitución II).
CREATE OR REPLACE FUNCTION f_tipo_cambio_sellado_update() RETURNS trigger AS $$
BEGIN
    IF OLD.sellado = true AND (
        NEW.ratio IS DISTINCT FROM OLD.ratio
        OR NEW.divisa_id IS DISTINCT FROM OLD.divisa_id
        OR NEW.fecha IS DISTINCT FROM OLD.fecha
    ) THEN
        RAISE EXCEPTION 'tipo_cambio: tipo sellado inmutable (UPDATE denegado)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tipo_cambio_sellado_update ON tipo_cambio;
CREATE TRIGGER trg_tipo_cambio_sellado_update
    BEFORE UPDATE ON tipo_cambio
    FOR EACH ROW EXECUTE FUNCTION f_tipo_cambio_sellado_update();

CREATE OR REPLACE FUNCTION f_tipo_cambio_sellado_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'tipo_cambio: tipo sellado inmutable (DELETE denegado)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tipo_cambio_sellado_delete ON tipo_cambio;
CREATE TRIGGER trg_tipo_cambio_sellado_delete
    BEFORE DELETE ON tipo_cambio
    FOR EACH ROW WHEN (OLD.sellado = true)
    EXECUTE FUNCTION f_tipo_cambio_sellado_delete();

-- La valoración es inmutable (append-only), como la auditoría.
CREATE OR REPLACE FUNCTION f_diferencia_cambio_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'diferencia_cambio: la valoracion es inmutable';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_diferencia_cambio_immutable_update ON diferencia_cambio;
CREATE TRIGGER trg_diferencia_cambio_immutable_update
    BEFORE UPDATE ON diferencia_cambio
    FOR EACH ROW EXECUTE FUNCTION f_diferencia_cambio_immutable();

DROP TRIGGER IF EXISTS trg_diferencia_cambio_immutable_delete ON diferencia_cambio;
CREATE TRIGGER trg_diferencia_cambio_immutable_delete
    BEFORE DELETE ON diferencia_cambio
    FOR EACH ROW EXECUTE FUNCTION f_diferencia_cambio_immutable();