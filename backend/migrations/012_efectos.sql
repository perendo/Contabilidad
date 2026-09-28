-- ============================================================
--  012_efectos.sql
--  Medios de pago y efectos (SPEC-021): cartera de efectos
--  (cheques, pagares, letras) con cobro/impago, cobros por medio
--  (TPV/tarjeta/transferencia) con comision y desglose de comisiones.
--  Idempotente. Alineado con backend/src/models/treasury/{efecto,
--  cobro_medio,comision}.py.
--
--  Multi-tenant estricto (constitucion III): `empresa_id` en PK claves/
--  indices/FK de todas las tablas. Inmutabilidad (constitucion II): los
--  estados `cobrado`/`impagado` del efecto son finales (se bloquea UPDATE
--  y DELETE sobre filas en esos estados; el asiento de impago es un
--  REVERSAL nuevo que no toca el original).
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_efecto') THEN
        CREATE TYPE tipo_efecto AS ENUM ('CHEQUE', 'PAGARE', 'LETRA');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'efecto_estado') THEN
        CREATE TYPE efecto_estado AS ENUM ('emitido', 'cobrado', 'impagado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'medio_cobro') THEN
        CREATE TYPE medio_cobro AS ENUM (
            'CHEQUE', 'PAGARE', 'LETRA', 'TARJETA', 'TRANSFERENCIA', 'CAJA'
        );
    END IF;
END
$$;

-- ---------- Cartera de efectos ----------

CREATE TABLE IF NOT EXISTS efecto (
    id                 UUID PRIMARY KEY,
    empresa_id         BIGINT NOT NULL,
    tercero_id         UUID NOT NULL,
    tipo_efecto        tipo_efecto NOT NULL,
    numero_documento   VARCHAR(50) NOT NULL,
    fecha_emision      DATE NOT NULL,
    fecha_vencimiento  DATE NOT NULL,
    importe            NUMERIC(18,4) NOT NULL,
    moneda             VARCHAR(3) NOT NULL DEFAULT 'EUR',
    estado             efecto_estado NOT NULL DEFAULT 'emitido',
    asiento_cobro_id   UUID,
    asiento_impago_id  UUID,
    notas              TEXT,
    created_by         VARCHAR(120),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_efecto_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_efecto_documento
        UNIQUE (empresa_id, tercero_id, tipo_efecto, numero_documento),
    CONSTRAINT chk_efecto_importe_positivo CHECK (importe > 0),
    CONSTRAINT chk_efecto_fechas CHECK (fecha_vencimiento >= fecha_emision)
);

CREATE INDEX IF NOT EXISTS ix_efecto_empresa
    ON efecto (empresa_id);
CREATE INDEX IF NOT EXISTS ix_efecto_empresa_estado_fecha
    ON efecto (empresa_id, estado, fecha_vencimiento);
CREATE INDEX IF NOT EXISTS ix_efecto_empresa_tercero
    ON efecto (empresa_id, tercero_id);

-- ---------- Cobros por medio (TPV/tarjeta/transferencia) ----------

CREATE TABLE IF NOT EXISTS cobro_medio (
    id                UUID PRIMARY KEY,
    empresa_id        BIGINT NOT NULL,
    vencimiento_id    UUID NOT NULL,
    medio_cobro       medio_cobro NOT NULL,
    fecha_cobro       DATE NOT NULL,
    importe_total     NUMERIC(18,4) NOT NULL,
    importe_comision  NUMERIC(18,4) NOT NULL DEFAULT 0,
    importe_neto      NUMERIC(18,4) NOT NULL,
    cuenta_banco      VARCHAR(12) NOT NULL DEFAULT '572',
    asiento_cobro_id  UUID,
    created_by        VARCHAR(120),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_cobro_medio_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_cobro_medio_total_positivo CHECK (importe_total > 0),
    CONSTRAINT chk_cobro_medio_comision_no_negativa CHECK (importe_comision >= 0),
    CONSTRAINT chk_cobro_medio_comision_lte CHECK (importe_comision <= importe_total),
    CONSTRAINT chk_cobro_medio_neto_no_negativo CHECK (importe_neto >= 0)
);

CREATE INDEX IF NOT EXISTS ix_cobro_medio_empresa
    ON cobro_medio (empresa_id);
CREATE INDEX IF NOT EXISTS ix_cobro_medio_empresa_fecha
    ON cobro_medio (empresa_id, fecha_cobro);
CREATE INDEX IF NOT EXISTS ix_cobro_medio_empresa_medio
    ON cobro_medio (empresa_id, medio_cobro);

-- ---------- Comisiones bancarias (desglose) ----------

CREATE TABLE IF NOT EXISTS comision_bancaria (
    id              UUID PRIMARY KEY,
    empresa_id      BIGINT NOT NULL,
    cobro_medio_id  UUID NOT NULL,
    banco_codigo    VARCHAR(12),
    tipo_comision   VARCHAR(50) NOT NULL DEFAULT 'OTRA',
    importe         NUMERIC(18,4) NOT NULL,
    porcentaje      NUMERIC(5,2),
    cuenta_contable VARCHAR(12) NOT NULL DEFAULT '626',
    created_by      VARCHAR(120),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_comision_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_comision_importe_no_negativo CHECK (importe >= 0),
    CONSTRAINT fk_comision_cobro_medio
        FOREIGN KEY (empresa_id, cobro_medio_id)
        REFERENCES cobro_medio (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_comision_empresa
    ON comision_bancaria (empresa_id);
CREATE INDEX IF NOT EXISTS ix_comision_empresa_cobro
    ON comision_bancaria (empresa_id, cobro_medio_id);

-- ---------- Triggers de inmutabilidad (constitucion II) ----------
-- Un efecto en estado final (`cobrado`/`impagado`) no se modifica ni se
-- borra; la correccion de un impago se gestiona con un asiento REVERSAL
-- nuevo (igual que el diario) y una re-emision del efecto.

CREATE OR REPLACE FUNCTION trg_efecto_final_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'efecto: un efecto en estado % es final y no puede modificarse', OLD.estado;
END
$$;

DROP TRIGGER IF EXISTS trg_efecto_final_immutable_update ON efecto;
CREATE TRIGGER trg_efecto_final_immutable_update
    BEFORE UPDATE ON efecto
    FOR EACH ROW
    WHEN (OLD.estado IN ('cobrado', 'impagado'))
    EXECUTE FUNCTION trg_efecto_final_immutable();

DROP TRIGGER IF EXISTS trg_efecto_final_immutable_delete ON efecto;
CREATE TRIGGER trg_efecto_final_immutable_delete
    BEFORE DELETE ON efecto
    FOR EACH ROW
    WHEN (OLD.estado IN ('cobrado', 'impagado'))
    EXECUTE FUNCTION trg_efecto_final_immutable();