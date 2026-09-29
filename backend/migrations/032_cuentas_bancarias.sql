-- Migración 032 · Maestro de cuentas bancarias por empresa (multi-banco en tesorería)
-- Permite registrar múltiples cuentas bancarias (Banco Santander, BBVA, CaixaBank, etc.)
-- vinculadas a la empresa activa, asociándolas a una subcuenta contable (ej. 5720, 5721, etc.)
-- e identificándolas por IBAN, BIC y descripción.

CREATE TABLE IF NOT EXISTS cuentas_bancarias (
    id               UUID          NOT NULL,
    empresa_id       BIGINT        NOT NULL,
    nombre           VARCHAR(120)  NOT NULL,
    banco            VARCHAR(120),
    iban             VARCHAR(34)   NOT NULL,
    bic              VARCHAR(11),
    cuenta_contable  VARCHAR(20)   NOT NULL DEFAULT '572',
    activa           BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT pk_cuentas_bancarias PRIMARY KEY (id),
    CONSTRAINT uq_cuentas_bancarias_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_cuentas_bancarias_empresa_iban UNIQUE (empresa_id, iban)
);

CREATE INDEX IF NOT EXISTS ix_cuentas_bancarias_empresa_id ON cuentas_bancarias (empresa_id);
CREATE INDEX IF NOT EXISTS ix_cuentas_bancarias_activa ON cuentas_bancarias (empresa_id, activa);
