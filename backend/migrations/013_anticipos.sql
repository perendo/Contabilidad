-- ============================================================
--  013_anticipos.sql
--  Anticipos y cesion de cobros (SPEC-022): anticipos de clientes
--  (438) y a proveedores (407) con liquidacion contra facturas, y
--  cesion de cobros (factoring/confirming) con comision y notificacion.
--  Idempotente. Alineado con los modelos
--  backend/src/models/treasury/{anticipo,liquidacion_anticipo,cesion,
--  notificacion_cesion}.py
--
--  Multi-tenant estricto (constitucion III): `empresa_id` en claves/
--  indices/FKs de todas las tablas. Importes NUMERIC(18,4) (regla fiscal).
--
--  DESVIACION documentada: las tablas `tercero`, `vencimiento` y `factura`
--  (SPEC-008/011/007) aun no tienen migracion propia (se crean por
--  create_all en SQLite); siguiendo el precedente de 012_efectos.sql, sus
--  columnas se declaran aqui como UUID plano (sin FK). Las FKs compuestas
--  existen en los modelos SQLAlchemy y se verifican en SQLite.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'anticipo_tipo') THEN
        CREATE TYPE anticipo_tipo AS ENUM ('CLIENTE', 'PROVEEDOR');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'anticipo_estado') THEN
        CREATE TYPE anticipo_estado AS ENUM (
            'pendiente', 'parcialmente_aplicado', 'totalmente_aplicado'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_comision_cesion') THEN
        CREATE TYPE tipo_comision_cesion AS ENUM ('IMPORTE_FIJO', 'PORCENTAJE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cesion_estado') THEN
        CREATE TYPE cesion_estado AS ENUM ('activa', 'saldada', 'cancelada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'medio_notificacion_cesion') THEN
        CREATE TYPE medio_notificacion_cesion AS ENUM ('EMAIL', 'CORREO', 'REGISTRO');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_notificacion_cesion') THEN
        CREATE TYPE estado_notificacion_cesion AS ENUM ('pendiente', 'enviada');
    END IF;
END
$$;

-- ---------- Anticipos (438 CLIENTE / 407 proveedor) ----------

CREATE TABLE IF NOT EXISTS anticipo (
    id                UUID PRIMARY KEY,
    empresa_id        BIGINT NOT NULL,
    tercero_id        UUID NOT NULL,
    tipo              anticipo_tipo NOT NULL,
    cuenta_contable   VARCHAR(12) NOT NULL,
    fecha             DATE NOT NULL,
    importe           NUMERIC(18,4) NOT NULL,
    concepto          VARCHAR(255) NOT NULL,
    estado            anticipo_estado NOT NULL DEFAULT 'pendiente',
    saldo_pendiente   NUMERIC(18,4) NOT NULL,
    asiento_id        UUID,
    notas             TEXT,
    created_by        VARCHAR(120),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_anticipo_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_anticipo_importe_positivo CHECK (importe > 0),
    CONSTRAINT chk_anticipo_saldo_no_negativo CHECK (saldo_pendiente >= 0),
    CONSTRAINT fk_anticipo_asiento
        FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_anticipo_empresa
    ON anticipo (empresa_id);
CREATE INDEX IF NOT EXISTS ix_anticipo_empresa_tercero_tipo
    ON anticipo (empresa_id, tercero_id, tipo);
CREATE INDEX IF NOT EXISTS ix_anticipo_empresa_estado
    ON anticipo (empresa_id, estado);

-- ---------- Liquidaciones de anticipo contra facturas ----------

CREATE TABLE IF NOT EXISTS liquidacion_anticipo (
    id                UUID PRIMARY KEY,
    empresa_id        BIGINT NOT NULL,
    anticipo_id       UUID NOT NULL,
    factura_id        UUID NOT NULL,
    fecha_aplicacion  DATE NOT NULL,
    importe_aplicado  NUMERIC(18,4) NOT NULL,
    asiento_id        UUID,
    notas             TEXT,
    created_by        VARCHAR(120),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_liquidacion_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_liquidacion_importe_positivo CHECK (importe_aplicado > 0),
    CONSTRAINT fk_liquidacion_anticipo
        FOREIGN KEY (empresa_id, anticipo_id)
        REFERENCES anticipo (empresa_id, id),
    CONSTRAINT fk_liquidacion_asiento
        FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_liquidacion_empresa
    ON liquidacion_anticipo (empresa_id);
CREATE INDEX IF NOT EXISTS ix_liquidacion_empresa_anticipo
    ON liquidacion_anticipo (empresa_id, anticipo_id);
CREATE INDEX IF NOT EXISTS ix_liquidacion_empresa_factura
    ON liquidacion_anticipo (empresa_id, factura_id);

-- ---------- Cesion de cobros (factoring/confirming) ----------

CREATE TABLE IF NOT EXISTS cesion_cobro (
    id                    UUID PRIMARY KEY,
    empresa_id            BIGINT NOT NULL,
    entidad_financiera    VARCHAR(100) NOT NULL,
    fecha_cesion          DATE NOT NULL,
    comision              NUMERIC(18,4) NOT NULL DEFAULT 0,
    tipo_comision         tipo_comision_cesion NOT NULL,
    importe_total_cedido  NUMERIC(18,4) NOT NULL,
    importe_neto_recibido NUMERIC(18,4) NOT NULL,
    estado                cesion_estado NOT NULL DEFAULT 'activa',
    asiento_id            UUID,
    notas                 TEXT,
    created_by            VARCHAR(120),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_cesion_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_cesion_comision_no_negativa CHECK (comision >= 0),
    CONSTRAINT chk_cesion_total_positivo CHECK (importe_total_cedido > 0),
    CONSTRAINT chk_cesion_neto_no_negativo CHECK (importe_neto_recibido >= 0),
    CONSTRAINT fk_cesion_asiento
        FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_cesion_empresa
    ON cesion_cobro (empresa_id);
CREATE INDEX IF NOT EXISTS ix_cesion_empresa_fecha
    ON cesion_cobro (empresa_id, fecha_cesion);
CREATE INDEX IF NOT EXISTS ix_cesion_empresa_estado
    ON cesion_cobro (empresa_id, estado);

CREATE TABLE IF NOT EXISTS cesion_cobro_detalle (
    id              UUID PRIMARY KEY,
    empresa_id      BIGINT NOT NULL,
    cesion_id       UUID NOT NULL,
    vencimiento_id  UUID NOT NULL,
    importe         NUMERIC(18,4) NOT NULL,
    CONSTRAINT uq_cesion_detalle_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_cesion_vencimiento UNIQUE (empresa_id, cesion_id, vencimiento_id),
    CONSTRAINT chk_cesion_detalle_importe_positivo CHECK (importe > 0),
    CONSTRAINT fk_cesion_detalle_cesion
        FOREIGN KEY (empresa_id, cesion_id)
        REFERENCES cesion_cobro (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_cesion_detalle_empresa
    ON cesion_cobro_detalle (empresa_id);
CREATE INDEX IF NOT EXISTS ix_cesion_detalle_empresa_cesion
    ON cesion_cobro_detalle (empresa_id, cesion_id);
CREATE INDEX IF NOT EXISTS ix_cesion_detalle_empresa_vencimiento
    ON cesion_cobro_detalle (empresa_id, vencimiento_id);

-- ---------- Notificaciones de cesion al deudor ----------

CREATE TABLE IF NOT EXISTS notificacion_cesion (
    id                  UUID PRIMARY KEY,
    empresa_id          BIGINT NOT NULL,
    cesion_id           UUID NOT NULL,
    cliente_id          UUID NOT NULL,
    fecha_notificacion  DATE NOT NULL,
    medio               medio_notificacion_cesion NOT NULL,
    estado              estado_notificacion_cesion NOT NULL DEFAULT 'enviada',
    notas               TEXT,
    created_by          VARCHAR(120),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_notificacion_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT fk_notificacion_cesion
        FOREIGN KEY (empresa_id, cesion_id)
        REFERENCES cesion_cobro (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_notificacion_empresa
    ON notificacion_cesion (empresa_id);
CREATE INDEX IF NOT EXISTS ix_notificacion_empresa_cesion
    ON notificacion_cesion (empresa_id, cesion_id);
CREATE INDEX IF NOT EXISTS ix_notificacion_empresa_cliente
    ON notificacion_cesion (empresa_id, cliente_id);