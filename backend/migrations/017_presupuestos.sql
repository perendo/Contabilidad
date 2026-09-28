-- ============================================================
--  017_presupuestos.sql
--  Control presupuestario (SPEC-026): presupuesto anual por combinacion
--  cuenta-centro-ejercicio, periodos de seguimiento con numeracion correlativa
--  y snapshot inmutable de desviaciones al cierre. Idempotente.
--
--  Multi-tenancy estricto (constitucion III): `empresa_id` en indices, unicidades
--  y FKs compuestas de las tres tablas. Correlatividad (constitucion IV):
--  `numero_periodo` unico por (empresa, ejercicio). Inmutabilidad del snapshot
--  (constitucion II): triggers append-only sobre `desviacion`. Unicidad de la
--  combinacion presupuesto (FR-005) y de las cuentas sin presupuesto (D4) via
--  indices parciales, porque `centro_coste_id` es NULLABLE y NULL no colisiona
--  en un UNIQUE normal.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_presupuesto') THEN
        CREATE TYPE tipo_presupuesto AS ENUM ('gasto', 'ingreso');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'periodo_seguimiento_estado') THEN
        CREATE TYPE periodo_seguimiento_estado AS ENUM ('abierto', 'cerrado');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS periodo_seguimiento (
    id                        UUID PRIMARY KEY,
    empresa_id                BIGINT NOT NULL,
    ejercicio                 INTEGER NOT NULL,
    numero_periodo            BIGINT NOT NULL,
    fecha_inicio              DATE NOT NULL,
    fecha_fin                 DATE NOT NULL,
    estado                    periodo_seguimiento_estado NOT NULL DEFAULT 'abierto',
    fecha_cierre              TIMESTAMPTZ,
    cerrado_por               VARCHAR(200),
    desviaciones_registradas  INTEGER NOT NULL DEFAULT 0,
    notas                     TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_periodo_seguimiento_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_periodo_seguimiento_numero UNIQUE (empresa_id, ejercicio, numero_periodo),
    CONSTRAINT chk_periodo_seguimiento_rango CHECK (fecha_fin > fecha_inicio),
    CONSTRAINT chk_periodo_seguimiento_numero_pos CHECK (numero_periodo > 0),
    CONSTRAINT fk_periodo_seguimiento_empresa FOREIGN KEY (empresa_id)
        REFERENCES companies (company_id)
);

CREATE INDEX IF NOT EXISTS ix_periodo_seguimiento_empresa_ejercicio
    ON periodo_seguimiento (empresa_id, ejercicio, numero_periodo);
-- Solo un periodo abierto por (empresa, ejercicio).
CREATE UNIQUE INDEX IF NOT EXISTS uq_periodo_seguimiento_abierto
    ON periodo_seguimiento (empresa_id, ejercicio) WHERE estado = 'abierto';

CREATE TABLE IF NOT EXISTS presupuesto (
    id               UUID PRIMARY KEY,
    empresa_id       BIGINT NOT NULL,
    ejercicio        INTEGER NOT NULL,
    cuenta_id        BIGINT NOT NULL,
    centro_coste_id  UUID,
    periodo_id       UUID,
    importe          NUMERIC(18, 4) NOT NULL DEFAULT 0,
    tipo             tipo_presupuesto NOT NULL DEFAULT 'gasto',
    observaciones    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_presupuesto_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT fk_presupuesto_cuenta
        FOREIGN KEY (empresa_id, cuenta_id)
        REFERENCES account_plan (tenant_id, id),
    CONSTRAINT fk_presupuesto_centro
        FOREIGN KEY (empresa_id, centro_coste_id)
        REFERENCES centro_coste (empresa_id, id),
    CONSTRAINT fk_presupuesto_periodo
        FOREIGN KEY (empresa_id, periodo_id)
        REFERENCES periodo_seguimiento (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_presupuesto_empresa_ejercicio
    ON presupuesto (empresa_id, ejercicio);
CREATE INDEX IF NOT EXISTS ix_presupuesto_empresa_centro
    ON presupuesto (empresa_id, centro_coste_id);
-- FR-005: unicidad de (empresa, ejercicio, cuenta, centro) sin duplicar las
-- lineas sin centro, que en SQL dejarian pasar con un UNIQUE normal.
CREATE UNIQUE INDEX IF NOT EXISTS uq_presupuesto_sin_centro
    ON presupuesto (empresa_id, ejercicio, cuenta_id) WHERE centro_coste_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_presupuesto_con_centro
    ON presupuesto (empresa_id, ejercicio, cuenta_id, centro_coste_id)
    WHERE centro_coste_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS desviacion (
    id                    UUID PRIMARY KEY,
    empresa_id            BIGINT NOT NULL,
    periodo_id            UUID NOT NULL,
    cuenta_id             BIGINT NOT NULL,
    centro_coste_id       UUID,
    importe_presupuestado NUMERIC(18, 4) NOT NULL DEFAULT 0,
    importe_real          NUMERIC(18, 4) NOT NULL DEFAULT 0,
    desviacion_absoluta    NUMERIC(18, 4) NOT NULL DEFAULT 0,
    desviacion_relativa   NUMERIC(7, 4),
    sin_presupuesto       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_desviacion_periodo
        FOREIGN KEY (empresa_id, periodo_id)
        REFERENCES periodo_seguimiento (empresa_id, id),
    CONSTRAINT fk_desviacion_cuenta
        FOREIGN KEY (empresa_id, cuenta_id)
        REFERENCES account_plan (tenant_id, id),
    CONSTRAINT fk_desviacion_centro
        FOREIGN KEY (empresa_id, centro_coste_id)
        REFERENCES centro_coste (empresa_id, id),
    CONSTRAINT chk_desviacion_relativa
        CHECK (desviacion_relativa IS NULL OR ABS(desviacion_relativa) <= 999.9999)
);

CREATE INDEX IF NOT EXISTS ix_desviacion_empresa_periodo
    ON desviacion (empresa_id, periodo_id);
CREATE INDEX IF NOT EXISTS ix_desviacion_empresa_cuenta
    ON desviacion (empresa_id, cuenta_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_desviacion_sin_centro
    ON desviacion (empresa_id, periodo_id, cuenta_id) WHERE centro_coste_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_desviacion_con_centro
    ON desviacion (empresa_id, periodo_id, cuenta_id, centro_coste_id)
    WHERE centro_coste_id IS NOT NULL;

-- El snapshot del cierre es append-only (constitucion II): no se actualiza ni
-- se borra jamas. El servicio garantiza la unicidad (409) y los triggers la
-- hacen definitiva en el punto mas cercano a la persistencia.
CREATE OR REPLACE FUNCTION f_desviacion_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'desviacion: el snapshot del cierre es inmutable (operacion % denegada)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_desviacion_append_only_update ON desviacion;
CREATE TRIGGER trg_desviacion_append_only_update
    BEFORE UPDATE ON desviacion
    FOR EACH ROW EXECUTE FUNCTION f_desviacion_append_only();

DROP TRIGGER IF EXISTS trg_desviacion_append_only_delete ON desviacion;
CREATE TRIGGER trg_desviacion_append_only_delete
    BEFORE DELETE ON desviacion
    FOR EACH ROW EXECUTE FUNCTION f_desviacion_append_only();
