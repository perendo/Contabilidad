DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'calculo_is_estado') THEN
        CREATE TYPE calculo_is_estado AS ENUM ('borrador', 'calculado', 'contabilizado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_ajuste_extracontable') THEN
        CREATE TYPE tipo_ajuste_extracontable AS ENUM (
            'AJUSTE_POSITIVO', 'AJUSTE_NEGATIVO', 'DEDUCCION', 'BONIFICACION'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS configuracion_fiscal (
    empresa_id                     BIGINT PRIMARY KEY,
    recargo_equivalencia_habilitado BOOLEAN NOT NULL DEFAULT FALSE,
    cuenta_recargo                 VARCHAR(20),
    criterio_caja_habilitado       BOOLEAN NOT NULL DEFAULT FALSE,
    tipo_is                        NUMERIC(5,2) NOT NULL DEFAULT 25.00,
    fecha_vigencia_desde           DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_vigencia_hasta           DATE,
    updated_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_configuracion_fiscal_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id)
);

ALTER TABLE configuracion_fiscal
    ADD COLUMN IF NOT EXISTS recargo_equivalencia_habilitado BOOLEAN;
ALTER TABLE configuracion_fiscal
    ADD COLUMN IF NOT EXISTS cuenta_recargo VARCHAR(20);
ALTER TABLE configuracion_fiscal
    ADD COLUMN IF NOT EXISTS criterio_caja_habilitado BOOLEAN;
ALTER TABLE configuracion_fiscal
    ADD COLUMN IF NOT EXISTS tipo_is NUMERIC(5,2);
ALTER TABLE configuracion_fiscal
    ADD COLUMN IF NOT EXISTS fecha_vigencia_desde DATE;
ALTER TABLE configuracion_fiscal
    ADD COLUMN IF NOT EXISTS fecha_vigencia_hasta DATE;
ALTER TABLE configuracion_fiscal
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE configuracion_fiscal
SET recargo_equivalencia_habilitado = FALSE
WHERE recargo_equivalencia_habilitado IS NULL;
UPDATE configuracion_fiscal
SET criterio_caja_habilitado = FALSE
WHERE criterio_caja_habilitado IS NULL;
UPDATE configuracion_fiscal
SET tipo_is = 25.00
WHERE tipo_is IS NULL;
UPDATE configuracion_fiscal
SET fecha_vigencia_desde = CURRENT_DATE
WHERE fecha_vigencia_desde IS NULL;
UPDATE configuracion_fiscal
SET updated_at = now()
WHERE updated_at IS NULL;

ALTER TABLE configuracion_fiscal
    ALTER COLUMN recargo_equivalencia_habilitado SET DEFAULT FALSE,
    ALTER COLUMN recargo_equivalencia_habilitado SET NOT NULL,
    ALTER COLUMN criterio_caja_habilitado SET DEFAULT FALSE,
    ALTER COLUMN criterio_caja_habilitado SET NOT NULL,
    ALTER COLUMN tipo_is SET DEFAULT 25.00,
    ALTER COLUMN tipo_is SET NOT NULL,
    ALTER COLUMN fecha_vigencia_desde SET DEFAULT CURRENT_DATE,
    ALTER COLUMN fecha_vigencia_desde SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT now(),
    ALTER COLUMN updated_at SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'configuracion_fiscal'::regclass
          AND conname = 'fk_configuracion_fiscal_empresa'
    ) THEN
        ALTER TABLE configuracion_fiscal
            ADD CONSTRAINT fk_configuracion_fiscal_empresa
            FOREIGN KEY (empresa_id) REFERENCES companies (company_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'configuracion_fiscal'::regclass
          AND conname = 'chk_configuracion_fiscal_tipo_is'
    ) THEN
        ALTER TABLE configuracion_fiscal
            ADD CONSTRAINT chk_configuracion_fiscal_tipo_is
            CHECK (tipo_is > 0 AND tipo_is <= 100);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'configuracion_fiscal'::regclass
          AND conname = 'chk_configuracion_fiscal_vigencia'
    ) THEN
        ALTER TABLE configuracion_fiscal
            ADD CONSTRAINT chk_configuracion_fiscal_vigencia
            CHECK (
                fecha_vigencia_hasta IS NULL
                OR fecha_vigencia_hasta >= fecha_vigencia_desde
            );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS calculo_is (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id          BIGINT NOT NULL,
    ejercicio           INTEGER NOT NULL,
    resultado_contable  NUMERIC(18,4) NOT NULL DEFAULT 0,
    ajustes_positivos   NUMERIC(18,4) NOT NULL DEFAULT 0,
    ajustes_negativos   NUMERIC(18,4) NOT NULL DEFAULT 0,
    base_imponible      NUMERIC(18,4) NOT NULL DEFAULT 0,
    tipo_impositivo     NUMERIC(5,2) NOT NULL DEFAULT 25.00,
    cuota_integra       NUMERIC(18,4) NOT NULL DEFAULT 0,
    deducciones         NUMERIC(18,4) NOT NULL DEFAULT 0,
    cuota_liquida       NUMERIC(18,4) NOT NULL DEFAULT 0,
    pagos_a_cuenta      NUMERIC(18,4) NOT NULL DEFAULT 0,
    cuota_diferencial   NUMERIC(18,4) NOT NULL DEFAULT 0,
    provisional         BOOLEAN NOT NULL DEFAULT TRUE,
    estado              calculo_is_estado NOT NULL DEFAULT 'borrador',
    asiento_id          UUID,
    notas               TEXT,
    created_by          VARCHAR(120),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_calculo_is_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_calculo_is_tipo_positivo
        CHECK (tipo_impositivo > 0 AND tipo_impositivo <= 100),
    CONSTRAINT chk_calculo_is_ajustes_positivos CHECK (ajustes_positivos >= 0),
    CONSTRAINT chk_calculo_is_ajustes_negativos CHECK (ajustes_negativos >= 0),
    CONSTRAINT chk_calculo_is_deducciones CHECK (deducciones >= 0),
    CONSTRAINT chk_calculo_is_pagos CHECK (pagos_a_cuenta >= 0),
    CONSTRAINT fk_calculo_is_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id),
    CONSTRAINT fk_calculo_is_asiento
        FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_calculo_is_empresa_id
    ON calculo_is (empresa_id);
CREATE INDEX IF NOT EXISTS ix_calculo_is_empresa_estado
    ON calculo_is (empresa_id, estado);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calculo_is_definitivo
    ON calculo_is (empresa_id, ejercicio)
    WHERE provisional = FALSE;

CREATE TABLE IF NOT EXISTS ajuste_extracontable (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id            BIGINT NOT NULL,
    calculo_is_id         UUID NOT NULL,
    tipo                  tipo_ajuste_extracontable NOT NULL,
    descripcion           VARCHAR(500) NOT NULL,
    referencia_normativa  VARCHAR(255),
    importe               NUMERIC(18,4) NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ajuste_extracontable_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_ajuste_extracontable_importe CHECK (importe > 0),
    CONSTRAINT fk_ajuste_extracontable_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id),
    CONSTRAINT fk_ajuste_extracontable_calculo
        FOREIGN KEY (empresa_id, calculo_is_id)
        REFERENCES calculo_is (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_ajuste_extracontable_empresa_id
    ON ajuste_extracontable (empresa_id);
CREATE INDEX IF NOT EXISTS ix_ajuste_extracontable_empresa_calculo
    ON ajuste_extracontable (empresa_id, calculo_is_id);

CREATE TABLE IF NOT EXISTS modelo_200 (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id        BIGINT NOT NULL,
    calculo_is_id     UUID NOT NULL,
    fecha_generacion  TIMESTAMPTZ NOT NULL DEFAULT now(),
    contenido         JSONB NOT NULL,
    hash_contenido    CHAR(64) NOT NULL,
    created_by        VARCHAR(120),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_modelo_200_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_modelo_200_calculo UNIQUE (empresa_id, calculo_is_id),
    CONSTRAINT fk_modelo_200_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id),
    CONSTRAINT fk_modelo_200_calculo
        FOREIGN KEY (empresa_id, calculo_is_id)
        REFERENCES calculo_is (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_modelo_200_empresa_id
    ON modelo_200 (empresa_id);

CREATE OR REPLACE FUNCTION f_calculo_is_contabilizado_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'calculo_is: un calculo contabilizado es final y no puede modificarse';
END;
$$;

DROP TRIGGER IF EXISTS trg_calculo_is_contabilizado_immutable_update ON calculo_is;
CREATE TRIGGER trg_calculo_is_contabilizado_immutable_update
    BEFORE UPDATE ON calculo_is
    FOR EACH ROW
    WHEN (OLD.estado = 'contabilizado')
    EXECUTE FUNCTION f_calculo_is_contabilizado_immutable();

DROP TRIGGER IF EXISTS trg_calculo_is_contabilizado_immutable_delete ON calculo_is;
CREATE TRIGGER trg_calculo_is_contabilizado_immutable_delete
    BEFORE DELETE ON calculo_is
    FOR EACH ROW
    WHEN (OLD.estado = 'contabilizado')
    EXECUTE FUNCTION f_calculo_is_contabilizado_immutable();

CREATE OR REPLACE FUNCTION f_ajuste_extracontable_contabilizado_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM calculo_is
        WHERE id = NEW.calculo_is_id
          AND empresa_id = NEW.empresa_id
          AND estado = 'contabilizado'
    ) THEN
        RAISE EXCEPTION
            'ajuste_extracontable: el calculo padre esta contabilizado y no admite cambios';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION f_ajuste_extracontable_contabilizado_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM calculo_is
        WHERE id = OLD.calculo_is_id
          AND empresa_id = OLD.empresa_id
          AND estado = 'contabilizado'
    ) OR EXISTS (
        SELECT 1 FROM calculo_is
        WHERE id = NEW.calculo_is_id
          AND empresa_id = NEW.empresa_id
          AND estado = 'contabilizado'
    ) THEN
        RAISE EXCEPTION
            'ajuste_extracontable: el calculo padre esta contabilizado y no admite cambios';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION f_ajuste_extracontable_contabilizado_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM calculo_is
        WHERE id = OLD.calculo_is_id
          AND empresa_id = OLD.empresa_id
          AND estado = 'contabilizado'
    ) THEN
        RAISE EXCEPTION
            'ajuste_extracontable: el calculo padre esta contabilizado y no admite cambios';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_ajuste_extracontable_contabilizado_insert
    ON ajuste_extracontable;
CREATE TRIGGER trg_ajuste_extracontable_contabilizado_insert
    BEFORE INSERT ON ajuste_extracontable
    FOR EACH ROW
    EXECUTE FUNCTION f_ajuste_extracontable_contabilizado_insert();

DROP TRIGGER IF EXISTS trg_ajuste_extracontable_contabilizado_update
    ON ajuste_extracontable;
CREATE TRIGGER trg_ajuste_extracontable_contabilizado_update
    BEFORE UPDATE ON ajuste_extracontable
    FOR EACH ROW
    EXECUTE FUNCTION f_ajuste_extracontable_contabilizado_update();

DROP TRIGGER IF EXISTS trg_ajuste_extracontable_contabilizado_delete
    ON ajuste_extracontable;
CREATE TRIGGER trg_ajuste_extracontable_contabilizado_delete
    BEFORE DELETE ON ajuste_extracontable
    FOR EACH ROW
    EXECUTE FUNCTION f_ajuste_extracontable_contabilizado_delete();

CREATE OR REPLACE FUNCTION f_modelo_200_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'modelo_200: el modelo es append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_modelo_200_append_only_update ON modelo_200;
CREATE TRIGGER trg_modelo_200_append_only_update
    BEFORE UPDATE ON modelo_200
    FOR EACH ROW
    EXECUTE FUNCTION f_modelo_200_append_only();

DROP TRIGGER IF EXISTS trg_modelo_200_append_only_delete ON modelo_200;
CREATE TRIGGER trg_modelo_200_append_only_delete
    BEFORE DELETE ON modelo_200
    FOR EACH ROW
    EXECUTE FUNCTION f_modelo_200_append_only();

INSERT INTO account_plan (tenant_id, code, level, name, parent_id)
SELECT c.company_id, '63', 2, 'Impuestos sobre beneficios',
       (SELECT p.id FROM account_plan p
         WHERE p.tenant_id = c.company_id AND p.code = '6' AND p.level = 1)
FROM companies c
WHERE EXISTS (
    SELECT 1 FROM account_plan p
    WHERE p.tenant_id = c.company_id AND p.code = '6' AND p.level = 1
)
ON CONFLICT (tenant_id, code) DO NOTHING;

INSERT INTO account_plan (tenant_id, code, level, name, parent_id)
SELECT c.company_id, '630', 3, 'Impuesto sobre beneficios',
       (SELECT p.id FROM account_plan p
         WHERE p.tenant_id = c.company_id AND p.code = '63' AND p.level = 2)
FROM companies c
WHERE EXISTS (
    SELECT 1 FROM account_plan p
    WHERE p.tenant_id = c.company_id AND p.code = '63' AND p.level = 2
)
ON CONFLICT (tenant_id, code) DO NOTHING;

INSERT INTO account_plan (tenant_id, code, level, name, parent_id, is_selectable)
SELECT c.company_id, '6300', 4, 'Impuesto sobre beneficios. Autoliquidacion',
       (SELECT p.id FROM account_plan p
         WHERE p.tenant_id = c.company_id AND p.code = '630' AND p.level = 3),
       TRUE
FROM companies c
WHERE EXISTS (
    SELECT 1 FROM account_plan p
    WHERE p.tenant_id = c.company_id AND p.code = '630' AND p.level = 3
)
ON CONFLICT (tenant_id, code) DO NOTHING;

INSERT INTO account_plan (tenant_id, code, level, name, parent_id)
SELECT c.company_id, '473', 3, 'H.P. deudora por Impuesto sobre Sociedades',
       (SELECT p.id FROM account_plan p
         WHERE p.tenant_id = c.company_id AND p.code = '47' AND p.level = 2)
FROM companies c
WHERE EXISTS (
    SELECT 1 FROM account_plan p
    WHERE p.tenant_id = c.company_id AND p.code = '47' AND p.level = 2
)
ON CONFLICT (tenant_id, code) DO NOTHING;

INSERT INTO account_plan (tenant_id, code, level, name, parent_id, is_selectable)
SELECT c.company_id, '4730', 4, 'H.P. deudora por Impuesto sobre Sociedades',
       (SELECT p.id FROM account_plan p
         WHERE p.tenant_id = c.company_id AND p.code = '473' AND p.level = 3),
       TRUE
FROM companies c
WHERE EXISTS (
    SELECT 1 FROM account_plan p
    WHERE p.tenant_id = c.company_id AND p.code = '473' AND p.level = 3
)
ON CONFLICT (tenant_id, code) DO NOTHING;

INSERT INTO account_plan (tenant_id, code, level, name, parent_id)
SELECT c.company_id, '475', 3, 'H.P. acreedora por conceptos fiscales',
       (SELECT p.id FROM account_plan p
         WHERE p.tenant_id = c.company_id AND p.code = '47' AND p.level = 2)
FROM companies c
WHERE EXISTS (
    SELECT 1 FROM account_plan p
    WHERE p.tenant_id = c.company_id AND p.code = '47' AND p.level = 2
)
ON CONFLICT (tenant_id, code) DO NOTHING;

INSERT INTO account_plan (tenant_id, code, level, name, parent_id, is_selectable)
SELECT c.company_id, '4752', 4, 'H.P. acreedora por retenciones e ingresos a cuenta',
       (SELECT p.id FROM account_plan p
         WHERE p.tenant_id = c.company_id AND p.code = '475' AND p.level = 3),
       TRUE
FROM companies c
WHERE EXISTS (
    SELECT 1 FROM account_plan p
    WHERE p.tenant_id = c.company_id AND p.code = '475' AND p.level = 3
)
ON CONFLICT (tenant_id, code) DO NOTHING;

INSERT INTO account_plan (tenant_id, code, level, name, parent_id, is_selectable)
SELECT c.company_id, '4709', 4, 'H.P. acreedora por devoluciones',
       (SELECT p.id FROM account_plan p
         WHERE p.tenant_id = c.company_id AND p.code = '470' AND p.level = 3),
       TRUE
FROM companies c
WHERE EXISTS (
    SELECT 1 FROM account_plan p
    WHERE p.tenant_id = c.company_id AND p.code = '470' AND p.level = 3
)
ON CONFLICT (tenant_id, code) DO NOTHING;
