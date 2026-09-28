-- ============================================================
--  018_cashflow.sql
--  Prevision de tesoreria y Estado de Flujos de Efectivo (SPEC-027):
--  cabecera de prevision, movimientos proyectados, alertas de liquidez y el
--  snapshot del EFE con sus lineas por bloque de actividad. Idempotente.
--
--  Multi-tenancy estricto (constitucion III): `empresa_id` en indices,
--  unicidades y FKs compuestas de las cuatro tablas; la FK a `vencimiento` es
--  compuesta, de modo que un vencimiento de otra empresa no puede enlazarse.
--  Correlatividad (constitucion IV): `numero_prevision` unico por empresa.
--  Inmutabilidad (constitucion II): al formularse, `informe_efe` y
--  `linea_efe` quedan append-only (snapshot del ejercicio).
--
--  Nota de tipos: los enums se crean en minusculas, igual que sus valores en
--  Python, para que el contrato de PostgreSQL los acepte sin traduccion.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'prevision_granularidad') THEN
        CREATE TYPE prevision_granularidad AS ENUM ('dia', 'semana', 'mes');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'prevision_estado') THEN
        CREATE TYPE prevision_estado AS ENUM ('borrador', 'generada', 'anulada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movimiento_prevision_origen') THEN
        CREATE TYPE movimiento_prevision_origen AS ENUM
            ('vencimiento', 'remesa_cobro', 'pago_recurrente', 'cobro_estimado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movimiento_prevision_tipo') THEN
        CREATE TYPE movimiento_prevision_tipo AS ENUM ('cobro', 'pago');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movimiento_prevision_frecuencia') THEN
        CREATE TYPE movimiento_prevision_frecuencia AS ENUM
            ('unico', 'semanal', 'mensual', 'anual');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alerta_liquidez_estado') THEN
        CREATE TYPE alerta_liquidez_estado AS ENUM ('abierta', 'atendida', 'ignorada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alerta_liquidez_accion') THEN
        CREATE TYPE alerta_liquidez_accion AS ENUM ('reprogramar_pago', 'incluir_ingreso');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'informe_efe_estado') THEN
        CREATE TYPE informe_efe_estado AS ENUM ('borrador', 'formulado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'linea_efe_bloque') THEN
        CREATE TYPE linea_efe_bloque AS ENUM ('operativa', 'inversion', 'financiacion');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS prevision_tesoreria (
    id                      UUID PRIMARY KEY,
    empresa_id              BIGINT NOT NULL,
    numero_prevision        BIGINT NOT NULL,
    fecha_generacion        TIMESTAMPTZ NOT NULL DEFAULT now(),
    desde_fecha             DATE NOT NULL,
    hasta_fecha             DATE NOT NULL,
    granularidad            prevision_granularidad NOT NULL,
    saldo_inicial           NUMERIC(18, 4) NOT NULL DEFAULT 0,
    saldo_final             NUMERIC(18, 4) NOT NULL DEFAULT 0,
    origen_saldo_inicial    VARCHAR(40),
    estado                  prevision_estado NOT NULL DEFAULT 'generada',
    creado_por              VARCHAR(120),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_prevision_tesoreria_empresa_id UNIQUE (empresa_id, id),
    -- Constitucion IV: correlatividad por empresa, sin saltos ni duplicados.
    CONSTRAINT uq_prevision_tesoreria_numero UNIQUE (empresa_id, numero_prevision),
    CONSTRAINT prevision_rango_fechas CHECK (hasta_fecha >= desde_fecha),
    CONSTRAINT prevision_numero_positivo CHECK (numero_prevision > 0),
    CONSTRAINT fk_prevision_tesoreria_empresa FOREIGN KEY (empresa_id)
        REFERENCES companies (company_id)
);

CREATE INDEX IF NOT EXISTS ix_prevision_tesoreria_empresa_fecha
    ON prevision_tesoreria (empresa_id, desde_fecha);
CREATE INDEX IF NOT EXISTS ix_prevision_tesoreria_empresa_estado
    ON prevision_tesoreria (empresa_id, estado);

CREATE TABLE IF NOT EXISTS movimiento_prevision (
    id                    UUID PRIMARY KEY,
    empresa_id            BIGINT NOT NULL,
    prevision_id          UUID,
    origen                movimiento_prevision_origen NOT NULL,
    vencimiento_id        UUID,
    numero_recibo         VARCHAR(64),
    tipo                  movimiento_prevision_tipo NOT NULL,
    importe               NUMERIC(18, 4) NOT NULL DEFAULT 0,
    fecha_prevista        DATE,
    frecuencia            movimiento_prevision_frecuencia NOT NULL DEFAULT 'unico',
    concepto              VARCHAR(200),
    incluido              BOOLEAN NOT NULL DEFAULT TRUE,
    motivo_exclusion      VARCHAR(40),
    orden_repeticion      BIGINT NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_movimiento_prevision_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT movimiento_prevision_importe_positivo CHECK (importe > 0),
    -- `incluido = false` exige un motivo; `incluido = true` no lo admite.
    CONSTRAINT movimiento_prevision_motivo CHECK (
        (incluido AND motivo_exclusion IS NULL)
        OR (NOT incluido AND motivo_exclusion IS NOT NULL)
    ),
    CONSTRAINT fk_movimiento_prevision_prevision
        FOREIGN KEY (empresa_id, prevision_id)
        REFERENCES prevision_tesoreria (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_movimiento_prevision_empresa_prevision
    ON movimiento_prevision (empresa_id, prevision_id);
CREATE INDEX IF NOT EXISTS ix_movimiento_prevision_empresa_fecha
    ON movimiento_prevision (empresa_id, fecha_prevista);
CREATE INDEX IF NOT EXISTS ix_movimiento_prevision_empresa_vencimiento
    ON movimiento_prevision (empresa_id, vencimiento_id);

-- FK compuesta a `Vencimiento` (SPEC-011): impide enlazar un vencimiento de otra
-- empresa (constitucion III). La tabla `vencimiento` la crea el modelo, no una
-- migracion propia, asi que -igual que `tercero` en 015_retenciones_irpf.sql- la
-- FK solo se anade cuando la tabla existe. El modelo SQLAlchemy si la declara
-- siempre, y `create_all` la respeta en el esquema de pruebas.
DO $$
BEGIN
    IF to_regclass('public.vencimiento') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conrelid = 'movimiento_prevision'::regclass
             AND conname = 'fk_movimiento_prevision_vencimiento'
       ) THEN
        ALTER TABLE movimiento_prevision
            ADD CONSTRAINT fk_movimiento_prevision_vencimiento
            FOREIGN KEY (empresa_id, vencimiento_id)
            REFERENCES vencimiento (empresa_id, id);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS alerta_liquidez (
    id                    UUID PRIMARY KEY,
    empresa_id            BIGINT NOT NULL,
    prevision_id          UUID NOT NULL,
    fecha                 DATE NOT NULL,
    saldo_proyectado      NUMERIC(18, 4) NOT NULL DEFAULT 0,
    importe_deficit       NUMERIC(18, 4) NOT NULL DEFAULT 0,
    estado                alerta_liquidez_estado NOT NULL DEFAULT 'abierta',
    accion_sugerida       alerta_liquidez_accion NOT NULL DEFAULT 'reprogramar_pago',
    movimiento_origen_id  UUID,
    atendida_por          VARCHAR(120),
    fecha_atencion        TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_alerta_liquidez_empresa_id UNIQUE (empresa_id, id),
    -- Una alerta por bucket de la prevision.
    CONSTRAINT uq_alerta_liquidez_prevision_fecha
        UNIQUE (empresa_id, prevision_id, fecha),
    CONSTRAINT alerta_liquidez_saldo_negativo CHECK (saldo_proyectado < 0),
    CONSTRAINT alerta_liquidez_deficit_positivo CHECK (importe_deficit > 0),
    CONSTRAINT fk_alerta_liquidez_prevision
        FOREIGN KEY (empresa_id, prevision_id)
        REFERENCES prevision_tesoreria (empresa_id, id),
    CONSTRAINT fk_alerta_liquidez_movimiento
        FOREIGN KEY (empresa_id, movimiento_origen_id)
        REFERENCES movimiento_prevision (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_alerta_liquidez_empresa_prevision
    ON alerta_liquidez (empresa_id, prevision_id);
CREATE INDEX IF NOT EXISTS ix_alerta_liquidez_empresa_estado
    ON alerta_liquidez (empresa_id, estado);

CREATE TABLE IF NOT EXISTS informe_efe (
    id                  UUID PRIMARY KEY,
    empresa_id          BIGINT NOT NULL,
    ejercicio           INTEGER NOT NULL,
    saldo_inicial       NUMERIC(18, 4) NOT NULL DEFAULT 0,
    saldo_final         NUMERIC(18, 4) NOT NULL DEFAULT 0,
    variacion_neta      NUMERIC(18, 4) NOT NULL DEFAULT 0,
    cuadre              BOOLEAN NOT NULL DEFAULT FALSE,
    sin_conciliar      BOOLEAN NOT NULL DEFAULT FALSE,
    saldo_conciliacion  NUMERIC(18, 4),
    estado              informe_efe_estado NOT NULL DEFAULT 'borrador',
    formulado_por       VARCHAR(120),
    fecha_formulacion   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_informe_efe_empresa_id UNIQUE (empresa_id, id),
    -- Un solo EFE por empresa y ejercicio (research D7).
    CONSTRAINT uq_informe_efe_ejercicio UNIQUE (empresa_id, ejercicio),
    CONSTRAINT fk_informe_efe_empresa FOREIGN KEY (empresa_id)
        REFERENCES companies (company_id)
);

CREATE INDEX IF NOT EXISTS ix_informe_efe_empresa_ejercicio
    ON informe_efe (empresa_id, ejercicio);

CREATE TABLE IF NOT EXISTS linea_efe (
    id                UUID PRIMARY KEY,
    empresa_id        BIGINT NOT NULL,
    informe_id        UUID NOT NULL,
    bloque            linea_efe_bloque NOT NULL,
    cuenta_id         BIGINT NOT NULL,
    codigo_cuenta     VARCHAR(16) NOT NULL DEFAULT '',
    importe           NUMERIC(18, 4) NOT NULL DEFAULT 0,
    override_usuario  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_linea_efe_empresa_id UNIQUE (empresa_id, id),
    -- Una cuenta, un solo bloque por informe (data-model de LineaEFE).
    CONSTRAINT uq_linea_efe_informe_cuenta UNIQUE (empresa_id, informe_id, cuenta_id),
    CONSTRAINT fk_linea_efe_informe
        FOREIGN KEY (empresa_id, informe_id)
        REFERENCES informe_efe (empresa_id, id),
    CONSTRAINT fk_linea_efe_cuenta
        FOREIGN KEY (empresa_id, cuenta_id)
        REFERENCES account_plan (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS ix_linea_efe_empresa_informe
    ON linea_efe (empresa_id, informe_id);
CREATE INDEX IF NOT EXISTS ix_linea_efe_empresa_bloque
    ON linea_efe (empresa_id, bloque);

-- El EFE formulado es un snapshot inmutable (constitucion II): ni sus cabeceras
-- ni sus lineas se actualizan ni se borran. El servicio garantiza el 409 de
-- doble formulacion; los triggers lo hacen definitivo en el punto mas cercano
-- a la persistencia.
CREATE OR REPLACE FUNCTION f_efe_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'EFE: el snapshot formulado es inmutable (operacion % denegada)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_informe_efe_append_only_update ON informe_efe;
CREATE TRIGGER trg_informe_efe_append_only_update
    BEFORE UPDATE ON informe_efe
    FOR EACH ROW EXECUTE FUNCTION f_efe_append_only();

DROP TRIGGER IF EXISTS trg_informe_efe_append_only_delete ON informe_efe;
CREATE TRIGGER trg_informe_efe_append_only_delete
    BEFORE DELETE ON informe_efe
    FOR EACH ROW EXECUTE FUNCTION f_efe_append_only();

DROP TRIGGER IF EXISTS trg_linea_efe_append_only_update ON linea_efe;
CREATE TRIGGER trg_linea_efe_append_only_update
    BEFORE UPDATE ON linea_efe
    FOR EACH ROW EXECUTE FUNCTION f_efe_append_only();

DROP TRIGGER IF EXISTS trg_linea_efe_append_only_delete ON linea_efe;
CREATE TRIGGER trg_linea_efe_append_only_delete
    BEFORE DELETE ON linea_efe
    FOR EACH ROW EXECUTE FUNCTION f_efe_append_only();
