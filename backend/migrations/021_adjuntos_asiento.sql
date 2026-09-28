-- ============================================================
--  021_adjuntos_asiento.sql
--  Documentos adjuntos al asiento del diario (SPEC-030): contenido BYTEA
--  inmutable con huella SHA-256, FK compuesta a `journal_entry` por
--  `empresa_id`, unicidad de huella dentro del asiento y baja logica.
--  Idempotente.
--
--  Constitution:
--   I  Partida doble: esta tabla no toca `journal_entry` ni
--      `journal_entry_line`. Adjuntar o dar de baja un documento no altera
--      Debe, Haber, numero, fecha ni estado del asiento (FR-015, SC-007).
--   II Inmutabilidad: el contenido, su nombre y su huella no se reescriben
--      NUNCA (research D3). Se admite unicamente el cambio de las cuatro
--      columnas de la baja logica, porque FR-012 exige conservar el soporte
--      durante el plazo legal y FR-010 la restringe a asientos en borrador.
--      El borrado fisico se rechaza siempre: no hay ruta de borrado.
--   III Multi-tenancy: `empresa_id` en clave unica, cuatro indices y FK
--      compuesta; la BD impide anclar un documento a un asiento de otra
--      empresa aunque la aplicacion fallara (data-model.md 7.5).
--   IV Correlatividad: no aplica. El documento no lleva numero ni secuencia.
--   V  Pruebas: el cuadre intacto y el aislamiento por `empresa_id` se
--      comprueban en `tests/integration/test_documentos_routes.py` y
--      `test_documentos_tenant.py`.
--  Precision: `importe_informativo` es NUMERIC(18,4) y solo referencia
--  visual; nunca se suma ni se traslada al asiento (research D19).
--  Opcionalidad: la adjuncion es opcional (FR-020). No hay ninguna restriccion
--  aqui que la vuelva obligatoria, y ningun flujo contable la consulta.
--
--  Desviacion del data-model: el numero de migracion previsto era 018, que ya
--  ocupa `018_cashflow.sql` (SPEC-027). Se usa 021, el siguiente libre.
--
--  Nota de tipos: los enums van en minusculas, igual que en Python.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'documento_tipo') THEN
        CREATE TYPE documento_tipo AS ENUM (
            'factura', 'recibo', 'extracto', 'justificante', 'contrato', 'otro'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'documento_estado') THEN
        CREATE TYPE documento_estado AS ENUM ('activo', 'dado_de_baja');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS documento_asiento (
    id                    UUID PRIMARY KEY,
    empresa_id            BIGINT NOT NULL,
    journal_entry_id      UUID NOT NULL,
    contenido             BYTEA NOT NULL,
    sha256                VARCHAR(64) NOT NULL,
    nombre_original       VARCHAR(255) NOT NULL,
    content_type          VARCHAR(100) NOT NULL,
    extension             VARCHAR(10) NOT NULL,
    size_bytes            BIGINT NOT NULL,
    num_paginas           INTEGER,
    tipo_documento        documento_tipo NOT NULL,
    descripcion           VARCHAR(500),
    importe_informativo   NUMERIC(18, 4),
    estado                documento_estado NOT NULL DEFAULT 'activo',
    baja_motivo           VARCHAR(500),
    baja_usuario          VARCHAR(120),
    baja_at               TIMESTAMPTZ,
    created_by            VARCHAR(120),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_documento_asiento_empresa_id UNIQUE (empresa_id, id),
    -- FR-006 / research D6: unicidad incondicional (no hay indice parcial):
    -- la baja es logica, la huella sigue ocupada y el mismo fichero no puede
    -- volver a adjuntarse al mismo asiento. En asientos distintos si puede.
    CONSTRAINT uq_documento_asiento_huella UNIQUE
        (empresa_id, journal_entry_id, sha256),
    CONSTRAINT fk_documento_asiento_entrada
        FOREIGN KEY (empresa_id, journal_entry_id)
        REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT chk_documento_asiento_tamano CHECK (size_bytes > 0),
    -- Una baja siempre esta completa y trazada (FR-011, FR-012).
    CONSTRAINT chk_documento_asiento_baja CHECK (
        (estado = 'activo'
            AND baja_motivo IS NULL AND baja_usuario IS NULL AND baja_at IS NULL)
        OR
        (estado = 'dado_de_baja'
            AND baja_motivo IS NOT NULL
            AND baja_usuario IS NOT NULL
            AND baja_at IS NOT NULL)
    ),
    -- research D19: referencia visual sin importes negativos.
    CONSTRAINT chk_documento_asiento_importe CHECK (
        importe_informativo IS NULL OR importe_informativo >= 0
    )
);

-- Filtro de tenant en toda consulta (constitucion III).
CREATE INDEX IF NOT EXISTS ix_documento_asiento_empresa_id
    ON documento_asiento (empresa_id);
-- Listado del asiento en orden determinista (research D15: created_at, id).
CREATE INDEX IF NOT EXISTS ix_documento_asiento_entrada
    ON documento_asiento (empresa_id, journal_entry_id, created_at, id);
-- Listado global por ejercicio (FR-017).
CREATE INDEX IF NOT EXISTS ix_documento_asiento_ejercicio
    ON documento_asiento (empresa_id, created_at);
-- Filtro por tipo de documento (FR-017).
CREATE INDEX IF NOT EXISTS ix_documento_asiento_tipo
    ON documento_asiento (empresa_id, tipo_documento);

-- ============================================================
--  Inmutabilidad (constitucion II, research D3)
-- ============================================================

CREATE OR REPLACE FUNCTION f_documento_asiento_inmutable_update() RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Cualquier cambio en la evidencia aborta la sentencia. `IS DISTINCT FROM`
    -- trata los NULL de forma correcta, a diferencia de `<>`.
    IF OLD.empresa_id IS DISTINCT FROM NEW.empresa_id
        OR OLD.journal_entry_id IS DISTINCT FROM NEW.journal_entry_id
        OR OLD.contenido IS DISTINCT FROM NEW.contenido
        OR OLD.sha256 IS DISTINCT FROM NEW.sha256
        OR OLD.nombre_original IS DISTINCT FROM NEW.nombre_original
        OR OLD.content_type IS DISTINCT FROM NEW.content_type
        OR OLD.extension IS DISTINCT FROM NEW.extension
        OR OLD.size_bytes IS DISTINCT FROM NEW.size_bytes
        OR OLD.num_paginas IS DISTINCT FROM NEW.num_paginas
        OR OLD.tipo_documento IS DISTINCT FROM NEW.tipo_documento
        OR OLD.descripcion IS DISTINCT FROM NEW.descripcion
        OR OLD.importe_informativo IS DISTINCT FROM NEW.importe_informativo
        OR OLD.created_by IS DISTINCT FROM NEW.created_by
        OR OLD.created_at IS DISTINCT FROM NEW.created_at
    THEN
        RAISE EXCEPTION 'documento_asiento inmutable: el contenido no se reescribe'
            USING ERRCODE = 'restrict_violation';
    END IF;
    -- Lo unico admitido es la baja logica: `estado`, `baja_motivo`,
    -- `baja_usuario` y `baja_at`. El CHECK chk_documento_asiento_baja exige
    -- ademas que la baja venga completa.
    RETURN NEW;
END
$$;

-- El borrado fisico no existe como operacion: FR-012 obliga a conservar el
-- soporte durante el plazo legal de conservacion (art. 30 LGT).
CREATE OR REPLACE FUNCTION f_documento_asiento_inmutable_delete() RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'documento_asiento inmutable: la baja es logica (DELETE denegado)'
        USING ERRCODE = 'restrict_violation';
END
$$;

-- CREATE OR REPLACE TRIGGER (PostgreSQL 14+) en vez de DROP + CREATE: es
-- atomico e idempotente, y reaplicar el lote no depende del orden de dos
-- sentencias (mismo criterio que 020_export.sql).
CREATE OR REPLACE TRIGGER trg_documento_asiento_contenido_inmutable_update
    BEFORE UPDATE ON documento_asiento
    FOR EACH ROW EXECUTE FUNCTION f_documento_asiento_inmutable_update();

CREATE OR REPLACE TRIGGER trg_documento_asiento_inmutable_delete
    BEFORE DELETE ON documento_asiento
    FOR EACH ROW EXECUTE FUNCTION f_documento_asiento_inmutable_delete();
