-- ============================================================
--  016_catalogo.sql
--  Catalogo versionado del plan de cuentas (SPEC-025): cabeceras de version
--  con vigencia sin solapes, proyeccion de cuentas, mapeos entre versiones y
--  reclasificacion de saldos de apertura. Idempotente.
--
--  Multi-tenant estricto (constitucion III): `empresa_id` en PK/indices/FK de
--  todas las tablas. Correlatividad (constitucion IV): `numero_version` unico
--  por empresa. Vigencia sin solapes (FR-006/SC-004): trigger
--  `trg_catalogo_version_vigencia` en el punto mas cercano a la persistencia.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'catalogo_version_estado') THEN
        CREATE TYPE catalogo_version_estado AS ENUM ('borrador', 'vigente', 'anulada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'catalogo_cuenta_estado') THEN
        CREATE TYPE catalogo_cuenta_estado AS ENUM ('igual', 'nueva', 'renombrada', 'suprimida');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'mapeo_tipo_movimiento') THEN
        CREATE TYPE mapeo_tipo_movimiento AS ENUM ('igual', 'renombrada', 'suprimida', 'nueva');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'mapeo_origen') THEN
        CREATE TYPE mapeo_origen AS ENUM ('manifiesto', 'autogenerado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reclasificacion_estado') THEN
        CREATE TYPE reclasificacion_estado AS ENUM ('borrador', 'contabilizado', 'cuadrado');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS catalogo_version (
    id              UUID PRIMARY KEY,
    empresa_id      BIGINT NOT NULL,
    numero_version  BIGINT NOT NULL,
    codigo          VARCHAR(20) NOT NULL,
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE,
    estado          catalogo_version_estado NOT NULL DEFAULT 'borrador',
    es_migracion    BOOLEAN NOT NULL DEFAULT FALSE,
    creado_por      VARCHAR(120),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_catalogo_version_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_catalogo_version_empresa_numero UNIQUE (empresa_id, numero_version),
    CONSTRAINT chk_catalogo_version_rango CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio),
    CONSTRAINT fk_catalogo_version_empresa FOREIGN KEY (empresa_id)
        REFERENCES companies (company_id)
);

CREATE INDEX IF NOT EXISTS ix_catalogo_version_empresa
    ON catalogo_version (empresa_id);
CREATE INDEX IF NOT EXISTS ix_catalogo_version_empresa_vigencia
    ON catalogo_version (empresa_id, fecha_inicio, fecha_fin);

CREATE TABLE IF NOT EXISTS catalogo_cuenta (
    id                 UUID PRIMARY KEY,
    empresa_id         BIGINT NOT NULL,
    version_id         UUID NOT NULL,
    account_id         BIGINT NOT NULL,
    codigo_version     VARCHAR(8) NOT NULL,
    nombre_version     VARCHAR(200) NOT NULL,
    estado             catalogo_cuenta_estado NOT NULL DEFAULT 'igual',
    parent_version_id  UUID,
    CONSTRAINT uq_catalogo_cuenta_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_catalogo_cuenta_version_account UNIQUE (empresa_id, version_id, account_id),
    CONSTRAINT uq_catalogo_cuenta_version_codigo UNIQUE (empresa_id, version_id, codigo_version),
    CONSTRAINT fk_catalogo_cuenta_version
        FOREIGN KEY (empresa_id, version_id)
        REFERENCES catalogo_version (empresa_id, id),
    CONSTRAINT fk_catalogo_cuenta_account
        FOREIGN KEY (empresa_id, account_id)
        REFERENCES account_plan (tenant_id, id),
    CONSTRAINT fk_catalogo_cuenta_parent
        FOREIGN KEY (empresa_id, parent_version_id)
        REFERENCES catalogo_cuenta (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_catalogo_cuenta_empresa_version
    ON catalogo_cuenta (empresa_id, version_id);

CREATE TABLE IF NOT EXISTS mapeo_cuenta (
    id                       UUID PRIMARY KEY,
    empresa_id               BIGINT NOT NULL,
    version_origen_id        UUID NOT NULL,
    version_destino_id       UUID NOT NULL,
    cuenta_origen_id         UUID,
    cuenta_destino_id        UUID,
    tipo_movimiento          mapeo_tipo_movimiento NOT NULL DEFAULT 'igual',
    requiere_reclasificacion BOOLEAN NOT NULL DEFAULT FALSE,
    origen                   mapeo_origen NOT NULL DEFAULT 'manifiesto',
    CONSTRAINT uq_mapeo_cuenta_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_mapeo_cuenta_clave
        UNIQUE (empresa_id, version_origen_id, version_destino_id, cuenta_origen_id),
    CONSTRAINT fk_mapeo_cuenta_version_origen
        FOREIGN KEY (empresa_id, version_origen_id)
        REFERENCES catalogo_version (empresa_id, id),
    CONSTRAINT fk_mapeo_cuenta_version_destino
        FOREIGN KEY (empresa_id, version_destino_id)
        REFERENCES catalogo_version (empresa_id, id),
    CONSTRAINT fk_mapeo_cuenta_origen
        FOREIGN KEY (empresa_id, cuenta_origen_id)
        REFERENCES catalogo_cuenta (empresa_id, id),
    CONSTRAINT fk_mapeo_cuenta_destino
        FOREIGN KEY (empresa_id, cuenta_destino_id)
        REFERENCES catalogo_cuenta (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_mapeo_cuenta_empresa_destino
    ON mapeo_cuenta (empresa_id, version_destino_id);

CREATE TABLE IF NOT EXISTS reclasificacion_saldo (
    id                  UUID PRIMARY KEY,
    empresa_id          BIGINT NOT NULL,
    version_destino_id  UUID NOT NULL,
    mapeo_id            UUID NOT NULL,
    cuenta_origen_id    BIGINT NOT NULL,
    cuenta_destino_id   UUID NOT NULL,
    importe             NUMERIC(18, 4) NOT NULL,
    asiento_id          UUID,
    estado              reclasificacion_estado NOT NULL DEFAULT 'borrador',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_reclasificacion_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_reclasificacion_importe_positivo CHECK (importe >= 0),
    CONSTRAINT fk_reclasificacion_version
        FOREIGN KEY (empresa_id, version_destino_id)
        REFERENCES catalogo_version (empresa_id, id),
    CONSTRAINT fk_reclasificacion_mapeo
        FOREIGN KEY (empresa_id, mapeo_id)
        REFERENCES mapeo_cuenta (empresa_id, id),
    CONSTRAINT fk_reclasificacion_cuenta_origen
        FOREIGN KEY (empresa_id, cuenta_origen_id)
        REFERENCES account_plan (tenant_id, id),
    CONSTRAINT fk_reclasificacion_cuenta_destino
        FOREIGN KEY (empresa_id, cuenta_destino_id)
        REFERENCES catalogo_cuenta (empresa_id, id),
    CONSTRAINT fk_reclasificacion_asiento
        FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_reclasificacion_empresa_version
    ON reclasificacion_saldo (empresa_id, version_destino_id);

-- Vigencia SIN solapes por empresa (FR-006/SC-004): la garantia definitiva vive
-- en el punto mas cercano a la persistencia; el servicio replica la regla para
-- devolver 422 legibles.
CREATE OR REPLACE FUNCTION f_catalogo_version_vigencia() RETURNS trigger AS $$
BEGIN
    IF NEW.estado <> 'anulada' AND EXISTS (
        SELECT 1 FROM catalogo_version
        WHERE empresa_id = NEW.empresa_id
          AND (TG_OP = 'INSERT' OR id <> OLD.id)
          AND estado <> 'anulada'
          AND fecha_inicio <= COALESCE(NEW.fecha_fin, DATE '9999-12-31')
          AND COALESCE(fecha_fin, DATE '9999-12-31') >= NEW.fecha_inicio
    ) THEN
        RAISE EXCEPTION 'catalogo_version: solape de vigencia por empresa';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_catalogo_version_vigencia ON catalogo_version;
CREATE TRIGGER trg_catalogo_version_vigencia
    BEFORE INSERT OR UPDATE ON catalogo_version
    FOR EACH ROW EXECUTE FUNCTION f_catalogo_version_vigencia();
