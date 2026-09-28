-- ============================================================
--  011_ngo.sql
--  Gestion ONG (SPEC-019): subvenciones con control de gasto por linea,
--  libros oficiales PDF (FR-005) y legalizacion con huella (FR-006/FR-007),
--  cajas y caja chica con asientos reales sobre subcuenta 570 (FR-008/FR-009).
--  Idempotente. Alineado con backend/src/models/ngo/*.
--
--  Multi-tenant estricto (constitucion III): `empresa_id` en PK/indices/FK de
--  todas las tablas. Inmutabilidad (constitucion II): `libro_oficial` y
--  `movimiento_caja` son append-only; `gasto_imputado` admite DELETE (la
--  desimputacion de US1 se audita); `legalizacion` no se borra (la re-emision
--  actualiza `valido` en el servicio, FR-006).
--
--  FR-007: una legalizacion vigente (`valido = true`) bloquea nuevos asientos
--  con fecha dentro del ejercicio legalizado (refuerza el cierre de SPEC-004 en
--  el motor; aqui a nivel DB).
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'subvencion_estado') THEN
        CREATE TYPE subvencion_estado AS ENUM ('concedida', 'en_curso', 'justificada', 'reintegrada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'libro_tipo') THEN
        CREATE TYPE libro_tipo AS ENUM ('diario', 'mayor', 'cuentas_anuales');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'caja_tipo') THEN
        CREATE TYPE caja_tipo AS ENUM ('caja', 'caja_chica');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'caja_estado') THEN
        CREATE TYPE caja_estado AS ENUM ('activa', 'inactiva');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movimiento_caja_tipo') THEN
        CREATE TYPE movimiento_caja_tipo AS ENUM ('entrada', 'salida');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'arqueo_estado') THEN
        CREATE TYPE arqueo_estado AS ENUM ('cuadra', 'con_diferencia');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'arqueo_decision') THEN
        CREATE TYPE arqueo_decision AS ENUM ('pendiente', 'aprobada', 'archivada');
    END IF;
END
$$;

-- ---------- Subvenciones ----------

CREATE TABLE IF NOT EXISTS subvencion (
    id                 UUID PRIMARY KEY,
    empresa_id         BIGINT NOT NULL,
    entidad_concedente VARCHAR(120) NOT NULL,
    programa           VARCHAR(120) NOT NULL,
    referencia         VARCHAR(40),
    importe_concedido  NUMERIC(18,4) NOT NULL,
    ejercicio          SMALLINT NOT NULL,
    estado             subvencion_estado NOT NULL DEFAULT 'concedida',
    partidas           JSONB,
    observaciones      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_subvencion_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_subvencion_importe_positivo CHECK (importe_concedido > 0)
);

CREATE INDEX IF NOT EXISTS ix_subvencion_empresa
    ON subvencion (empresa_id);
CREATE INDEX IF NOT EXISTS ix_subvencion_empresa_estado
    ON subvencion (empresa_id, estado, ejercicio);
CREATE INDEX IF NOT EXISTS ix_subvencion_empresa_referencia
    ON subvencion (empresa_id, referencia);

CREATE TABLE IF NOT EXISTS gasto_imputado (
    id              UUID PRIMARY KEY,
    empresa_id      BIGINT NOT NULL,
    subvencion_id   UUID NOT NULL,
    asiento_id      UUID NOT NULL,
    linea_id        UUID NOT NULL,
    importe_asignado NUMERIC(18,4) NOT NULL,
    partida         VARCHAR(80),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_gasto_imputado_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_gasto_imputado_importe_positivo CHECK (importe_asignado > 0),
    CONSTRAINT fk_gasto_imputado_subvencion
        FOREIGN KEY (empresa_id, subvencion_id)
        REFERENCES subvencion (empresa_id, id),
    CONSTRAINT fk_gasto_imputado_asiento
        FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT fk_gasto_imputado_linea
        FOREIGN KEY (empresa_id, linea_id)
        REFERENCES journal_entry_line (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_gasto_imputado_empresa_subvencion
    ON gasto_imputado (empresa_id, subvencion_id);
CREATE INDEX IF NOT EXISTS ix_gasto_imputado_empresa_linea
    ON gasto_imputado (empresa_id, subvencion_id, linea_id);

-- ---------- Libros oficiales y legalizacion ----------

CREATE TABLE IF NOT EXISTS libro_oficial (
    id            UUID PRIMARY KEY,
    empresa_id    BIGINT NOT NULL,
    ejercicio     SMALLINT NOT NULL,
    tipo          libro_tipo NOT NULL,
    periodo_desde DATE NOT NULL,
    periodo_hasta DATE NOT NULL,
    contenido_pdf BYTEA NOT NULL,
    sha256        CHAR(64) NOT NULL,
    size_bytes    BIGINT NOT NULL,
    generado_por  VARCHAR(120),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_libro_oficial_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_libro_oficial_empresa_ejercicio_tipo
        UNIQUE (empresa_id, ejercicio, tipo)
);

CREATE INDEX IF NOT EXISTS ix_libro_oficial_empresa
    ON libro_oficial (empresa_id);
CREATE INDEX IF NOT EXISTS ix_libro_oficial_empresa_ejercicio
    ON libro_oficial (empresa_id, ejercicio);

CREATE TABLE IF NOT EXISTS legalizacion (
    id                  UUID PRIMARY KEY,
    empresa_id          BIGINT NOT NULL,
    ejercicio           SMALLINT NOT NULL,
    rango_asientos_desde BIGINT NOT NULL,
    rango_asientos_hasta BIGINT NOT NULL,
    total_asientos      INTEGER NOT NULL,
    huella              CHAR(64) NOT NULL,
    fichero             BYTEA,
    fecha_emision       TIMESTAMPTZ NOT NULL,
    fecha_legalizacion  DATE,
    valido              BOOLEAN NOT NULL DEFAULT TRUE,
    motivo_reemision    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_legalizacion_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_legalizacion_empresa_ejercicio UNIQUE (empresa_id, ejercicio),
    CONSTRAINT chk_legalizacion_rango CHECK (rango_asientos_hasta >= rango_asientos_desde)
);

CREATE INDEX IF NOT EXISTS ix_legalizacion_empresa
    ON legalizacion (empresa_id);
CREATE INDEX IF NOT EXISTS ix_legalizacion_empresa_ejercicio
    ON legalizacion (empresa_id, ejercicio);

-- ---------- Cajas y arqueos ----------

CREATE TABLE IF NOT EXISTS caja (
    id           UUID PRIMARY KEY,
    empresa_id   BIGINT NOT NULL,
    nombre       VARCHAR(80) NOT NULL,
    cuenta_570_id BIGINT NOT NULL,
    tipo         caja_tipo NOT NULL DEFAULT 'caja',
    estado       caja_estado NOT NULL DEFAULT 'activa',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_caja_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_caja_empresa_nombre UNIQUE (empresa_id, nombre),
    CONSTRAINT uq_caja_empresa_570 UNIQUE (empresa_id, cuenta_570_id),
    CONSTRAINT chk_caja_nombre_len CHECK (length(nombre) BETWEEN 1 AND 80),
    CONSTRAINT fk_caja_cuenta_570
        FOREIGN KEY (empresa_id, cuenta_570_id)
        REFERENCES account_plan (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS ix_caja_empresa
    ON caja (empresa_id);
CREATE INDEX IF NOT EXISTS ix_caja_empresa_estado
    ON caja (empresa_id, estado);

CREATE TABLE IF NOT EXISTS movimiento_caja (
    id          UUID PRIMARY KEY,
    empresa_id  BIGINT NOT NULL,
    caja_id     UUID NOT NULL,
    asiento_id  UUID NOT NULL,
    linea_id    UUID NOT NULL,
    tipo        movimiento_caja_tipo NOT NULL,
    importe     NUMERIC(18,4) NOT NULL,
    fecha       DATE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_movimiento_caja_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_movimiento_caja_asiento_linea UNIQUE (empresa_id, asiento_id, linea_id),
    CONSTRAINT chk_movimiento_caja_importe_positivo CHECK (importe > 0),
    CONSTRAINT fk_movimiento_caja_caja
        FOREIGN KEY (empresa_id, caja_id) REFERENCES caja (empresa_id, id),
    CONSTRAINT fk_movimiento_caja_asiento
        FOREIGN KEY (empresa_id, asiento_id) REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT fk_movimiento_caja_linea
        FOREIGN KEY (empresa_id, linea_id) REFERENCES journal_entry_line (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_movimiento_caja_empresa_caja
    ON movimiento_caja (empresa_id, caja_id);
CREATE INDEX IF NOT EXISTS ix_movimiento_caja_empresa_fecha
    ON movimiento_caja (empresa_id, caja_id, fecha);

CREATE TABLE IF NOT EXISTS arqueo (
    id                  UUID PRIMARY KEY,
    empresa_id          BIGINT NOT NULL,
    caja_id             UUID NOT NULL,
    fecha               DATE NOT NULL,
    saldo_libros        NUMERIC(18,4) NOT NULL,
    efectivo_contado    NUMERIC(18,4) NOT NULL,
    diferencia          NUMERIC(18,4) NOT NULL,
    estado              arqueo_estado NOT NULL,
    decision            arqueo_decision,
    asiento_ajuste_id   UUID,
    archivado           BOOLEAN NOT NULL DEFAULT FALSE,
    detalle_diferencia  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_arqueo_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_arqueo_efectivo_positivo CHECK (efectivo_contado >= 0),
    CONSTRAINT fk_arqueo_caja
        FOREIGN KEY (empresa_id, caja_id) REFERENCES caja (empresa_id, id),
    CONSTRAINT fk_arqueo_ajuste
        FOREIGN KEY (empresa_id, asiento_ajuste_id) REFERENCES journal_entry (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_arqueo_empresa_caja
    ON arqueo (empresa_id, caja_id, fecha);
CREATE INDEX IF NOT EXISTS ix_arqueo_empresa_estado
    ON arqueo (empresa_id, estado, decision);

-- ---------- Triggers de inmutabilidad y FR-007 ----------

CREATE OR REPLACE FUNCTION trg_ngo_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '%: registro inmutable (solo APPEND)', TG_TABLE_NAME;
END
$$;

-- gasto_imputado NO es append-only: la desimputacion (US1) es un DELETE
-- legitimo que se audita; la inmutabilidad real reside en el diario.

DROP TRIGGER IF EXISTS trg_libro_oficial_immutable_update ON libro_oficial;
CREATE TRIGGER trg_libro_oficial_immutable_update
    BEFORE UPDATE ON libro_oficial
    FOR EACH ROW EXECUTE FUNCTION trg_ngo_append_only();

DROP TRIGGER IF EXISTS trg_libro_oficial_immutable_delete ON libro_oficial;
CREATE TRIGGER trg_libro_oficial_immutable_delete
    BEFORE DELETE ON libro_oficial
    FOR EACH ROW EXECUTE FUNCTION trg_ngo_append_only();

DROP TRIGGER IF EXISTS trg_movimiento_caja_immutable_update ON movimiento_caja;
CREATE TRIGGER trg_movimiento_caja_immutable_update
    BEFORE UPDATE ON movimiento_caja
    FOR EACH ROW EXECUTE FUNCTION trg_ngo_append_only();

DROP TRIGGER IF EXISTS trg_movimiento_caja_immutable_delete ON movimiento_caja;
CREATE TRIGGER trg_movimiento_caja_immutable_delete
    BEFORE DELETE ON movimiento_caja
    FOR EACH ROW EXECUTE FUNCTION trg_ngo_append_only();

DROP TRIGGER IF EXISTS trg_legalizacion_immutable_delete ON legalizacion;
CREATE TRIGGER trg_legalizacion_immutable_delete
    BEFORE DELETE ON legalizacion
    FOR EACH ROW EXECUTE FUNCTION trg_ngo_append_only();

CREATE OR REPLACE FUNCTION trg_journal_entry_legalizado()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM legalizacion l
        WHERE l.empresa_id = NEW.empresa_id
          AND l.ejercicio = EXTRACT(YEAR FROM NEW.fecha)
          AND l.valido = TRUE
    ) THEN
        RAISE EXCEPTION 'journal_entry: ejercicio legalizado. No admite nuevos asientos (FR-007)';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_journal_entry_legalizado_insert ON journal_entry;
CREATE TRIGGER trg_journal_entry_legalizado_insert
    BEFORE INSERT ON journal_entry
    FOR EACH ROW EXECUTE FUNCTION trg_journal_entry_legalizado();