-- ============================================================
--  020_export.sql
--  Exportacion integral del tenant (SPEC-029): cabecera correlativa e
--  inmutable, inventario de bloques, binario BYTEA del ZIP y configuracion SII
--  por empresa. Idempotente.
--
--  Multi-tenancy estricto (constitucion III): `empresa_id` en indices,
--  unicidades y FKs compuestas de las cuatro tablas de la cabecera; el
--  `tenant_id` del manifiesto es redundante con `empresa_id` a proposito, para
--  poder verificar la tension desde el `manifest.json` interior sin API.
--  Correlatividad (constitucion IV): `numero_exportacion` es unico por
--  (empresa_id, anio_creacion) y lo asigna `services.export.persistir` bajo
--  SELECT ... FOR UPDATE.
--  Inmutabilidad (constitucion II, research D9): la exportacion es un snapshot
--  del estado del tenant; el manifiesto, sus lineas y el blob son append-only.
--  Solo se admite la transicion `en_proceso -> lista|fallida` que resuelve la
--  propia generacion.
--  Precision: los importes de la cabecera no los hay; los que viajan en el ZIP
--  se serializan como `NUMERIC(18,4)` en cadenas de 4 decimales (research D7).
--
--  Nota de tipos: los enums se crean con los mismos valores que en Python; los
--  de tipo van en mayusculas y los de estado en minusculas.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_exportacion') THEN
        CREATE TYPE tipo_exportacion AS ENUM ('INTEGRAL', 'SII');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_exportacion') THEN
        CREATE TYPE estado_exportacion AS ENUM ('en_proceso', 'lista', 'fallida');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS exportacion (
    id                  UUID PRIMARY KEY,
    empresa_id          BIGINT NOT NULL,
    anio_creacion       INTEGER NOT NULL,
    numero_exportacion  BIGINT NOT NULL,
    tipo                tipo_exportacion NOT NULL,
    ejercicio_desde     INTEGER,
    ejercicio_hasta     INTEGER,
    estado              estado_exportacion NOT NULL DEFAULT 'en_proceso',
    creado_por          VARCHAR(120),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completado_at       TIMESTAMPTZ,
    blob_id             UUID,
    sha256              CHAR(64),
    tamano_bytes        BIGINT,
    n_bloques           INTEGER NOT NULL DEFAULT 0,
    mensaje_error       TEXT,
    CONSTRAINT uq_exportacion_empresa_id UNIQUE (empresa_id, id),
    -- Constitucion IV: correlatividad sin saltos por (empresa, anio).
    CONSTRAINT uq_exportacion_numero UNIQUE
        (empresa_id, anio_creacion, numero_exportacion),
    CONSTRAINT chk_exportacion_rango CHECK (
        ejercicio_desde IS NULL OR ejercicio_hasta IS NULL
        OR ejercicio_desde <= ejercicio_hasta
    ),
    CONSTRAINT chk_exportacion_numero_positivo CHECK (numero_exportacion > 0),
    CONSTRAINT chk_exportacion_bloques CHECK (n_bloques >= 0),
    CONSTRAINT chk_exportacion_tamano CHECK (tamano_bytes IS NULL OR tamano_bytes >= 0)
);

CREATE INDEX IF NOT EXISTS ix_exportacion_empresa_id ON exportacion (empresa_id);
CREATE INDEX IF NOT EXISTS ix_exportacion_empresa_estado ON exportacion (empresa_id, estado);
CREATE INDEX IF NOT EXISTS ix_exportacion_empresa_anio ON exportacion (empresa_id, anio_creacion);

CREATE TABLE IF NOT EXISTS manifiesto_exportacion (
    id                 UUID PRIMARY KEY,
    empresa_id         BIGINT NOT NULL,
    exportacion_id     UUID NOT NULL,
    formato_version    VARCHAR(20) NOT NULL,
    fecha_generacion   TIMESTAMPTZ NOT NULL,
    tenant_id          BIGINT NOT NULL,
    n_bloques          INTEGER NOT NULL,
    sha256_fichero     CHAR(64) NOT NULL,
    CONSTRAINT uq_manifiesto_exportacion_empresa_id UNIQUE (empresa_id, id),
    -- Un unico manifiesto por exportacion.
    CONSTRAINT uq_manifiesto_exportacion_exportacion UNIQUE (empresa_id, exportacion_id),
    CONSTRAINT fk_manifiesto_exportacion_exportacion
        FOREIGN KEY (empresa_id, exportacion_id)
        REFERENCES exportacion (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_manifiesto_exportacion_empresa
    ON manifiesto_exportacion (empresa_id);

CREATE TABLE IF NOT EXISTS manifiesto_bloque (
    id                     UUID PRIMARY KEY,
    empresa_id             BIGINT NOT NULL,
    manifiesto_id          UUID NOT NULL,
    bloque                 VARCHAR(64) NOT NULL,
    entidades_exportadas   VARCHAR(100) NOT NULL,
    conteo_registros       BIGINT NOT NULL DEFAULT 0,
    sha256                 CHAR(64),
    fecha_min              DATE,
    fecha_max              DATE,
    ejercicio_min          INTEGER,
    ejercicio_max          INTEGER,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_manifiesto_bloque_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT fk_manifiesto_bloque_manifiesto
        FOREIGN KEY (empresa_id, manifiesto_id)
        REFERENCES manifiesto_exportacion (empresa_id, id),
    CONSTRAINT chk_manifiesto_bloque_conteo CHECK (conteo_registros >= 0)
);

CREATE INDEX IF NOT EXISTS ix_manifiesto_bloque_manifiesto
    ON manifiesto_bloque (empresa_id, manifiesto_id);

CREATE TABLE IF NOT EXISTS blob_exportacion (
    id              UUID PRIMARY KEY,
    empresa_id      BIGINT NOT NULL,
    exportacion_id  UUID NOT NULL,
    contenido       BYTEA NOT NULL,
    sha256          CHAR(64) NOT NULL,
    tamano_bytes    BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_blob_exportacion_empresa_id UNIQUE (empresa_id, id),
    -- Un unico binario por exportacion (inmutable: re-descargar es identical).
    CONSTRAINT uq_blob_exportacion_exportacion UNIQUE (empresa_id, exportacion_id),
    CONSTRAINT fk_blob_exportacion_exportacion
        FOREIGN KEY (empresa_id, exportacion_id)
        REFERENCES exportacion (empresa_id, id),
    CONSTRAINT chk_blob_exportacion_tamano CHECK (tamano_bytes >= 0)
);

CREATE INDEX IF NOT EXISTS ix_blob_exportacion_empresa ON blob_exportacion (empresa_id);

CREATE TABLE IF NOT EXISTS config_sii (
    id                          UUID PRIMARY KEY,
    empresa_id                  BIGINT NOT NULL,
    obligado_sii                BOOLEAN NOT NULL DEFAULT FALSE,
    sin_anexo                   BOOLEAN NOT NULL DEFAULT FALSE,
    clave_regimen               VARCHAR(10),
    entidad_representante_id    UUID,
    fecha_alta                  DATE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_config_sii_empresa_id UNIQUE (empresa_id, id),
    -- Una sola configuracion SII por empresa.
    CONSTRAINT uq_config_sii_empresa UNIQUE (empresa_id)
);

-- ============================================================
--  Inmutabilidad (constitucion II, research D9)
-- ============================================================

-- La cabecera solo admite la transicion que resuelve la propia generacion.
CREATE OR REPLACE FUNCTION chk_exportacion_inmutable() RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.estado IN ('lista', 'fallida') THEN
        RAISE EXCEPTION
            'exportacion: la exportacion es un snapshot inmutable (estado %)',
            OLD.estado
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS chk_exportacion_immutable_update ON exportacion;
CREATE TRIGGER chk_exportacion_immutable_update
    BEFORE UPDATE ON exportacion
    FOR EACH ROW
    EXECUTE FUNCTION chk_exportacion_inmutable();

DROP TRIGGER IF EXISTS chk_exportacion_immutable_delete ON exportacion;
CREATE TRIGGER chk_exportacion_immutable_delete
    BEFORE DELETE ON exportacion
    FOR EACH ROW
    EXECUTE FUNCTION chk_exportacion_inmutable();

-- El manifiesto, sus lineas y el blob son la evidencia de integridad: no
-- admiten UPDATE ni DELETE en ningun estado. Se usan CREATE OR REPLACE
-- TRIGGER (PostgreSQL 14+) en vez de DROP + CREATE: es atomico e
-- idempotente, y asi reaplicar el lote no depende del orden de dos sentencias.
CREATE OR REPLACE FUNCTION export_append_only() RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '%: registro inmutable (% denegado)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END
$$;

CREATE OR REPLACE TRIGGER trg_manifiesto_exportacion_append_only_update
    BEFORE UPDATE ON manifiesto_exportacion
    FOR EACH ROW EXECUTE FUNCTION export_append_only();

CREATE OR REPLACE TRIGGER trg_manifiesto_exportacion_append_only_delete
    BEFORE DELETE ON manifiesto_exportacion
    FOR EACH ROW EXECUTE FUNCTION export_append_only();

CREATE OR REPLACE TRIGGER trg_manifiesto_bloque_append_only_update
    BEFORE UPDATE ON manifiesto_bloque
    FOR EACH ROW EXECUTE FUNCTION export_append_only();

CREATE OR REPLACE TRIGGER trg_manifiesto_bloque_append_only_delete
    BEFORE DELETE ON manifiesto_bloque
    FOR EACH ROW EXECUTE FUNCTION export_append_only();

CREATE OR REPLACE TRIGGER trg_blob_exportacion_append_only_update
    BEFORE UPDATE ON blob_exportacion
    FOR EACH ROW EXECUTE FUNCTION export_append_only();

CREATE OR REPLACE TRIGGER trg_blob_exportacion_append_only_delete
    BEFORE DELETE ON blob_exportacion
    FOR EACH ROW EXECUTE FUNCTION export_append_only();
