DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_liquidacion_retenciones') THEN
        CREATE TYPE estado_liquidacion_retenciones AS ENUM ('pendiente', 'liquidado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_retencion_irpf') THEN
        CREATE TYPE tipo_retencion_irpf AS ENUM (
            'IRPF_PROFESIONALES',
            'IRPF_ARRENDAMIENTOS',
            'IRPF_OBRAS',
            'IRPF_OTROS'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF to_regclass('public.factura_linea') IS NOT NULL THEN
        ALTER TABLE factura_linea
            ADD COLUMN IF NOT EXISTS tipo_retencion tipo_retencion_irpf
            DEFAULT 'IRPF_OTROS';
        ALTER TABLE factura_linea
            ALTER COLUMN tipo_retencion DROP NOT NULL;
        ALTER TABLE factura_linea
            ADD COLUMN IF NOT EXISTS direccion_inmueble VARCHAR(200);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS liquidacion_retenciones (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id               BIGINT NOT NULL,
    ejercicio                INTEGER NOT NULL,
    trimestre                INTEGER NOT NULL,
    periodo                  VARCHAR(7) NOT NULL,
    total_base_retenciones   NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_retenciones        NUMERIC(18,4) NOT NULL DEFAULT 0,
    n_perceptores            INTEGER NOT NULL DEFAULT 0,
    estado                   estado_liquidacion_retenciones NOT NULL DEFAULT 'pendiente',
    fecha_liquidacion        DATE,
    asiento_id               UUID,
    modelo_111_id            UUID,
    modelo_115_id            UUID,
    notas                    TEXT,
    created_by               VARCHAR(120),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_liquidacion_retenciones_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_liquidacion_retenciones_ejercicio_trimestre
        UNIQUE (empresa_id, ejercicio, trimestre),
    CONSTRAINT fk_liquidacion_retenciones_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id),
    CONSTRAINT fk_liquidacion_retenciones_asiento
        FOREIGN KEY (empresa_id, asiento_id)
        REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT chk_liquidacion_retenciones_trimestre
        CHECK (trimestre BETWEEN 1 AND 4),
    CONSTRAINT chk_liquidacion_retenciones_base_no_negativo
        CHECK (total_base_retenciones >= 0),
    CONSTRAINT chk_liquidacion_retenciones_total_no_negativo
        CHECK (total_retenciones >= 0),
    CONSTRAINT chk_liquidacion_retenciones_perceptores
        CHECK (n_perceptores >= 0),
    CONSTRAINT chk_liquidacion_retenciones_liquidado_completo
        CHECK (
            estado <> 'liquidado'
            OR (fecha_liquidacion IS NOT NULL AND asiento_id IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS ix_liquidacion_retenciones_empresa_id
    ON liquidacion_retenciones (empresa_id);
CREATE INDEX IF NOT EXISTS ix_liquidacion_retenciones_empresa_estado
    ON liquidacion_retenciones (empresa_id, estado);

CREATE TABLE IF NOT EXISTS retencion_periodo (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id               BIGINT NOT NULL,
    liquidacion_retenciones_id UUID NOT NULL,
    tercero_id               UUID NOT NULL,
    nif                      VARCHAR(9) DEFAULT '',
    nombre                   VARCHAR(100) NOT NULL,
    tipo_retencion           tipo_retencion_irpf NOT NULL,
    base_imponible           NUMERIC(18,4) NOT NULL,
    tipo_porcentaje          NUMERIC(5,2) NOT NULL,
    retencion_practicada     NUMERIC(18,4) NOT NULL,
    facturas                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    notas                    TEXT,
    created_by               VARCHAR(120),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_retencion_periodo_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT fk_retencion_periodo_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id),
    CONSTRAINT fk_retencion_periodo_liquidacion
        FOREIGN KEY (empresa_id, liquidacion_retenciones_id)
        REFERENCES liquidacion_retenciones (empresa_id, id),
    CONSTRAINT chk_retencion_periodo_base
        CHECK (base_imponible > 0),
    CONSTRAINT chk_retencion_periodo_retencion
        CHECK (retencion_practicada > 0),
    CONSTRAINT chk_retencion_periodo_tipo
        CHECK (tipo_porcentaje > 0 AND tipo_porcentaje <= 100),
    CONSTRAINT chk_retencion_periodo_formula
        CHECK (
            ABS(
                retencion_practicada
                - ROUND(base_imponible * tipo_porcentaje / 100, 4)
            ) <= 0.01
        ),
    CONSTRAINT chk_retencion_periodo_facturas_array
        CHECK (jsonb_typeof(facturas) = 'array')
);

CREATE INDEX IF NOT EXISTS ix_retencion_periodo_empresa_id
    ON retencion_periodo (empresa_id);
CREATE INDEX IF NOT EXISTS ix_retencion_periodo_empresa_liquidacion
    ON retencion_periodo (empresa_id, liquidacion_retenciones_id);
CREATE INDEX IF NOT EXISTS ix_retencion_periodo_empresa_tercero
    ON retencion_periodo (empresa_id, tercero_id);

DO $$
BEGIN
    IF to_regclass('public.tercero') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conrelid = 'retencion_periodo'::regclass
             AND conname = 'fk_retencion_periodo_tercero'
       ) THEN
        ALTER TABLE retencion_periodo
            ADD CONSTRAINT fk_retencion_periodo_tercero
            FOREIGN KEY (empresa_id, tercero_id)
            REFERENCES tercero (empresa_id, id);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS modelo_111 (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id               BIGINT NOT NULL,
    liquidacion_retenciones_id UUID NOT NULL,
    ejercicio                INTEGER NOT NULL,
    trimestre                INTEGER NOT NULL,
    fecha_generacion         TIMESTAMPTZ NOT NULL DEFAULT now(),
    contenido                JSONB NOT NULL,
    hash_contenido           CHAR(64) NOT NULL,
    created_by               VARCHAR(120),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_modelo_111_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_modelo_111_liquidacion
        UNIQUE (empresa_id, liquidacion_retenciones_id),
    CONSTRAINT uq_modelo_111_ejercicio_trimestre
        UNIQUE (empresa_id, ejercicio, trimestre),
    CONSTRAINT fk_modelo_111_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id),
    CONSTRAINT fk_modelo_111_liquidacion
        FOREIGN KEY (empresa_id, liquidacion_retenciones_id)
        REFERENCES liquidacion_retenciones (empresa_id, id),
    CONSTRAINT chk_modelo_111_trimestre
        CHECK (trimestre BETWEEN 1 AND 4),
    CONSTRAINT chk_modelo_111_hash
        CHECK (length(hash_contenido) = 64)
);

CREATE INDEX IF NOT EXISTS ix_modelo_111_empresa_id
    ON modelo_111 (empresa_id);

CREATE TABLE IF NOT EXISTS modelo_115 (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id               BIGINT NOT NULL,
    liquidacion_retenciones_id UUID NOT NULL,
    ejercicio                INTEGER NOT NULL,
    trimestre                INTEGER NOT NULL,
    fecha_generacion         TIMESTAMPTZ NOT NULL DEFAULT now(),
    contenido                JSONB NOT NULL,
    hash_contenido           CHAR(64) NOT NULL,
    created_by               VARCHAR(120),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_modelo_115_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_modelo_115_liquidacion
        UNIQUE (empresa_id, liquidacion_retenciones_id),
    CONSTRAINT uq_modelo_115_ejercicio_trimestre
        UNIQUE (empresa_id, ejercicio, trimestre),
    CONSTRAINT fk_modelo_115_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id),
    CONSTRAINT fk_modelo_115_liquidacion
        FOREIGN KEY (empresa_id, liquidacion_retenciones_id)
        REFERENCES liquidacion_retenciones (empresa_id, id),
    CONSTRAINT chk_modelo_115_trimestre
        CHECK (trimestre BETWEEN 1 AND 4),
    CONSTRAINT chk_modelo_115_hash
        CHECK (length(hash_contenido) = 64)
);

CREATE INDEX IF NOT EXISTS ix_modelo_115_empresa_id
    ON modelo_115 (empresa_id);

CREATE TABLE IF NOT EXISTS modelo_190 (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id               BIGINT NOT NULL,
    ejercicio                INTEGER NOT NULL,
    fecha_generacion         TIMESTAMPTZ NOT NULL DEFAULT now(),
    contenido                JSONB NOT NULL,
    hash_contenido           CHAR(64) NOT NULL,
    n_perceptores            INTEGER NOT NULL DEFAULT 0,
    created_by               VARCHAR(120),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_modelo_190_retenciones_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_modelo_190_ejercicio UNIQUE (empresa_id, ejercicio),
    CONSTRAINT fk_modelo_190_retenciones_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id),
    CONSTRAINT chk_modelo_190_perceptores
        CHECK (n_perceptores >= 0),
    CONSTRAINT chk_modelo_190_hash
        CHECK (length(hash_contenido) = 64)
);

CREATE INDEX IF NOT EXISTS ix_modelo_190_retenciones_empresa_id
    ON modelo_190 (empresa_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'liquidacion_retenciones'::regclass
          AND conname = 'fk_liquidacion_retenciones_modelo_111'
    ) THEN
        ALTER TABLE liquidacion_retenciones
            ADD CONSTRAINT fk_liquidacion_retenciones_modelo_111
            FOREIGN KEY (empresa_id, modelo_111_id)
            REFERENCES modelo_111 (empresa_id, id);
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'liquidacion_retenciones'::regclass
          AND conname = 'fk_liquidacion_retenciones_modelo_115'
    ) THEN
        ALTER TABLE liquidacion_retenciones
            ADD CONSTRAINT fk_liquidacion_retenciones_modelo_115
            FOREIGN KEY (empresa_id, modelo_115_id)
            REFERENCES modelo_115 (empresa_id, id);
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION f_liquidacion_retenciones_final_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.estado = 'liquidado' THEN
        RAISE EXCEPTION 'liquidacion_retenciones: estado liquidado es final (UPDATE denegado)';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_liquidacion_retenciones_final_update
    ON liquidacion_retenciones;
CREATE TRIGGER trg_liquidacion_retenciones_final_update
    BEFORE UPDATE ON liquidacion_retenciones
    FOR EACH ROW
    WHEN (OLD.estado = 'liquidado')
    EXECUTE FUNCTION f_liquidacion_retenciones_final_update();

CREATE OR REPLACE FUNCTION f_liquidacion_retenciones_final_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.estado = 'liquidado' THEN
        RAISE EXCEPTION 'liquidacion_retenciones: estado liquidado es final (DELETE denegado)';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_liquidacion_retenciones_final_delete
    ON liquidacion_retenciones;
CREATE TRIGGER trg_liquidacion_retenciones_final_delete
    BEFORE DELETE ON liquidacion_retenciones
    FOR EACH ROW
    WHEN (OLD.estado = 'liquidado')
    EXECUTE FUNCTION f_liquidacion_retenciones_final_delete();

CREATE OR REPLACE FUNCTION f_modelo_111_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'modelo_111: el modelo es append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_modelo_111_append_only_update ON modelo_111;
CREATE TRIGGER trg_modelo_111_append_only_update
    BEFORE UPDATE ON modelo_111
    FOR EACH ROW
    EXECUTE FUNCTION f_modelo_111_append_only();

DROP TRIGGER IF EXISTS trg_modelo_111_append_only_delete ON modelo_111;
CREATE TRIGGER trg_modelo_111_append_only_delete
    BEFORE DELETE ON modelo_111
    FOR EACH ROW
    EXECUTE FUNCTION f_modelo_111_append_only();

CREATE OR REPLACE FUNCTION f_modelo_115_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'modelo_115: el modelo es append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_modelo_115_append_only_update ON modelo_115;
CREATE TRIGGER trg_modelo_115_append_only_update
    BEFORE UPDATE ON modelo_115
    FOR EACH ROW
    EXECUTE FUNCTION f_modelo_115_append_only();

DROP TRIGGER IF EXISTS trg_modelo_115_append_only_delete ON modelo_115;
CREATE TRIGGER trg_modelo_115_append_only_delete
    BEFORE DELETE ON modelo_115
    FOR EACH ROW
    EXECUTE FUNCTION f_modelo_115_append_only();

CREATE OR REPLACE FUNCTION f_modelo_190_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'modelo_190: el modelo es append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_modelo_190_append_only_update ON modelo_190;
CREATE TRIGGER trg_modelo_190_append_only_update
    BEFORE UPDATE ON modelo_190
    FOR EACH ROW
    EXECUTE FUNCTION f_modelo_190_append_only();

DROP TRIGGER IF EXISTS trg_modelo_190_append_only_delete ON modelo_190;
CREATE TRIGGER trg_modelo_190_append_only_delete
    BEFORE DELETE ON modelo_190
    FOR EACH ROW
    EXECUTE FUNCTION f_modelo_190_append_only();

INSERT INTO account_plan (tenant_id, code, level, name, parent_id, is_selectable)
SELECT c.company_id,
       '4751',
       4,
       'H.P. acreedora por retenciones e ingresos a cuenta',
       p.id,
       TRUE
FROM companies c
JOIN account_plan p
  ON p.tenant_id = c.company_id
 AND p.code = '475'
 AND p.level = 3
ON CONFLICT (tenant_id, code) DO NOTHING;

CREATE OR REPLACE FUNCTION f_seed_retenciones_4751()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO account_plan
        (tenant_id, code, level, name, parent_id, is_selectable)
    SELECT NEW.company_id,
           '4751',
           4,
           'H.P. acreedora por retenciones e ingresos a cuenta',
           parent.id,
           TRUE
    FROM account_plan parent
    WHERE parent.tenant_id = NEW.company_id
      AND parent.code = '475'
      AND parent.level = 3
    ON CONFLICT (tenant_id, code) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_companies_seed_retenciones_4751 ON companies;
CREATE TRIGGER trg_companies_seed_retenciones_4751
AFTER INSERT ON companies
FOR EACH ROW
EXECUTE FUNCTION f_seed_retenciones_4751();
