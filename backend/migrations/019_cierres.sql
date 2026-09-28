-- ============================================================
--  019_cierres.sql
--  Cierre intermedio y reapertura controlada (SPEC-028): periodos
--  cerrados (mes/trimestre), snapshot inmutable del balance de comprobacion,
--  registro del cierre anual completo y solicitudes de reapertura. Idempotente.
--
--  Multi-tenancy estricto (constitucion III): `empresa_id` en indices,
--  unicidades y FKs compuestas de las cinco tablas; la FK al plan de cuentas es
--  `account_plan (tenant_id, id)` porque alli la columna de empresa se llama
--  `tenant_id` (SPEC-001).
--  Correlatividad (constitucion IV): `numero_solicitud` y el auxiliar
--  `secuencia_reapertura` son unicos por (empresa, ejercicio), asignados bajo
--  SELECT ... FOR UPDATE.
--  Inmutabilidad (constitucion II): el balance de un periodo cerrado es un
--  snapshot append-only; el trigger `chk_journal_entry_fecha_abierta` bloquea
--  el INSERT de asientos cuya fecha cae en un periodo bloqueante (FR-001).
--  Partida doble (constitucion I): `total_debe = total_haber` como CHECK.
--
--  Nota de tipos: los enums se crean con los mismos valores que en Python; los
--  de estado van en minusculas y los de tipo de periodo en mayusculas, tal y
--  como los declara `contracts/api-contracts.md`.
-- ============================================================

-- SPEC-028 T009 (research D8): el motor de asientos de SPEC-002 se amplia con
-- los tipos del paquete de cierre. `REVERSAL`, `ADJUSTMENT` y `OPENING` ya
-- existen; `REGULARIZACION` y `CIERRE` son nuevos. Los campos `reverses_id` y
-- `cierre_id` del data-model ya existen como `original_id` y
-- `referencia_cierre_id`, de modo que no se anaden columnas.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'journal_entry_tipo') THEN
        ALTER TYPE journal_entry_tipo ADD VALUE IF NOT EXISTS 'REGULARIZACION';
        ALTER TYPE journal_entry_tipo ADD VALUE IF NOT EXISTS 'CIERRE';
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_periodo') THEN
        CREATE TYPE tipo_periodo AS ENUM ('MES', 'TRIMESTRE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_periodo') THEN
        CREATE TYPE estado_periodo AS ENUM
            ('abierto', 'cerrado', 'reabierto_ajuste', 'cerrado_ajustado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_periodo_reapertura') THEN
        CREATE TYPE tipo_periodo_reapertura AS ENUM ('MES', 'TRIMESTRE', 'ANUAL');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_solicitud_reapertura') THEN
        CREATE TYPE estado_solicitud_reapertura AS ENUM
            ('pendiente', 'aprobada', 'reabierta', 'cerrada', 'rechazada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_cierre_ejercicio') THEN
        CREATE TYPE estado_cierre_ejercicio AS ENUM
            ('completado', 'reapertura_pendiente');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS periodo_cerrado (
    id              UUID PRIMARY KEY,
    empresa_id      BIGINT NOT NULL,
    ejercicio       INTEGER NOT NULL,
    tipo            tipo_periodo NOT NULL,
    periodo         INTEGER NOT NULL,
    fecha_ini       DATE NOT NULL,
    fecha_fin       DATE NOT NULL,
    estado          estado_periodo NOT NULL DEFAULT 'cerrado',
    cerrado_por     VARCHAR(120),
    cerrado_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    balanza_id      UUID,
    n_reaperturas   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_periodo_cerrado_empresa_id UNIQUE (empresa_id, id),
    -- Clave natural del data-model: un registro por periodo y empresa.
    CONSTRAINT uq_periodo_cerrado_natural UNIQUE (empresa_id, ejercicio, tipo, periodo),
    CONSTRAINT chk_periodo_cerrado_periodo CHECK (periodo >= 1 AND periodo <= 12),
    CONSTRAINT chk_periodo_cerrado_reaperturas CHECK (n_reaperturas >= 0),
    CONSTRAINT chk_periodo_cerrado_rango CHECK (fecha_fin >= fecha_ini),
    CONSTRAINT fk_periodo_cerrado_empresa FOREIGN KEY (empresa_id)
        REFERENCES companies (company_id)
);

CREATE INDEX IF NOT EXISTS ix_periodo_cerrado_empresa_ejercicio
    ON periodo_cerrado (empresa_id, ejercicio);
CREATE INDEX IF NOT EXISTS ix_periodo_cerrado_empresa_estado
    ON periodo_cerrado (empresa_id, estado);

CREATE TABLE IF NOT EXISTS balanza_periodo (
    id                    UUID PRIMARY KEY,
    empresa_id            BIGINT NOT NULL,
    periodo_id            UUID NOT NULL,
    ejercicio             INTEGER NOT NULL,
    fecha_ini             DATE NOT NULL,
    fecha_fin             DATE NOT NULL,
    fecha_generacion      TIMESTAMPTZ NOT NULL DEFAULT now(),
    generado_por          VARCHAR(120),
    n_lineas              INTEGER NOT NULL DEFAULT 0,
    total_debe            NUMERIC(18, 4) NOT NULL DEFAULT 0,
    total_haber           NUMERIC(18, 4) NOT NULL DEFAULT 0,
    resultado_provisional NUMERIC(18, 4) NOT NULL DEFAULT 0,
    sha256                CHAR(64) NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_balanza_periodo_empresa_id UNIQUE (empresa_id, id),
    -- Un balance por cierre (data-model).
    CONSTRAINT uq_balanza_periodo_periodo UNIQUE (empresa_id, periodo_id),
    -- Constitucion I: el snapshot solo se persiste si el Debe iguala al Haber.
    CONSTRAINT chk_balanza_periodo_cuadre CHECK (total_debe = total_haber),
    CONSTRAINT chk_balanza_periodo_lineas CHECK (n_lineas >= 0),
    CONSTRAINT chk_balanza_periodo_rango CHECK (fecha_fin >= fecha_ini),
    CONSTRAINT fk_balanza_periodo_periodo
        FOREIGN KEY (empresa_id, periodo_id)
        REFERENCES periodo_cerrado (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_balanza_periodo_empresa_ejercicio
    ON balanza_periodo (empresa_id, ejercicio);

CREATE TABLE IF NOT EXISTS balanza_periodo_linea (
    id          UUID PRIMARY KEY,
    empresa_id  BIGINT NOT NULL,
    balanza_id  UUID NOT NULL,
    cuenta_id   BIGINT NOT NULL,
    codigo      VARCHAR(8) NOT NULL,
    nombre      VARCHAR(200) NOT NULL,
    nivel       INTEGER NOT NULL DEFAULT 4,
    debe        NUMERIC(18, 4) NOT NULL DEFAULT 0,
    haber       NUMERIC(18, 4) NOT NULL DEFAULT 0,
    saldo       NUMERIC(18, 4) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_balanza_periodo_linea_empresa_id UNIQUE (empresa_id, id),
    -- Una linea por cuenta en cada snapshot.
    CONSTRAINT uq_balanza_periodo_linea_cuenta
        UNIQUE (empresa_id, balanza_id, cuenta_id),
    CONSTRAINT chk_balanza_linea_debe CHECK (debe >= 0),
    CONSTRAINT chk_balanza_linea_haber CHECK (haber >= 0),
    CONSTRAINT chk_balanza_linea_nivel CHECK (nivel >= 1 AND nivel <= 5),
    CONSTRAINT fk_balanza_periodo_linea_cabecera
        FOREIGN KEY (empresa_id, balanza_id)
        REFERENCES balanza_periodo (empresa_id, id),
    CONSTRAINT fk_balanza_periodo_linea_cuenta
        FOREIGN KEY (empresa_id, cuenta_id)
        REFERENCES account_plan (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS ix_balanza_periodo_linea_empresa_balanza
    ON balanza_periodo_linea (empresa_id, balanza_id);

CREATE TABLE IF NOT EXISTS secuencia_reapertura (
    id            BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    empresa_id    BIGINT NOT NULL,
    ejercicio     BIGINT NOT NULL,
    ultimo_numero BIGINT NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_secuencia_reapertura_pair UNIQUE (empresa_id, ejercicio)
);

CREATE TABLE IF NOT EXISTS cierre_ejercicio (
    id                           UUID PRIMARY KEY,
    empresa_id                   BIGINT NOT NULL,
    ejercicio                    INTEGER NOT NULL,
    estado                       estado_cierre_ejercicio NOT NULL DEFAULT 'completado',
    fecha_cierre                 DATE NOT NULL,
    resultado_ejercicio          NUMERIC(18, 4) NOT NULL DEFAULT 0,
    asiento_regularizacion_id    UUID,
    asiento_cierre_id            UUID,
    asiento_apertura_id          UUID,
    cerrado_por                  VARCHAR(120),
    cerrado_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_cierre_ejercicio_empresa_id UNIQUE (empresa_id, id),
    -- Idempotencia del flujo anual: un cierre por ejercicio y empresa.
    CONSTRAINT uq_cierre_ejercicio_ejercicio UNIQUE (empresa_id, ejercicio),
    CONSTRAINT chk_cierre_ejercicio_rango
        CHECK (ejercicio >= 2000 AND ejercicio <= 2100),
    CONSTRAINT fk_cierre_ejercicio_empresa FOREIGN KEY (empresa_id)
        REFERENCES companies (company_id),
    CONSTRAINT fk_cierre_ejercicio_regularizacion
        FOREIGN KEY (empresa_id, asiento_regularizacion_id)
        REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT fk_cierre_ejercicio_cierre
        FOREIGN KEY (empresa_id, asiento_cierre_id)
        REFERENCES journal_entry (empresa_id, id),
    CONSTRAINT fk_cierre_ejercicio_apertura
        FOREIGN KEY (empresa_id, asiento_apertura_id)
        REFERENCES journal_entry (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_cierre_ejercicio_empresa_ejercicio
    ON cierre_ejercicio (empresa_id, ejercicio);

CREATE TABLE IF NOT EXISTS solicitud_reapertura (
    id                        UUID PRIMARY KEY,
    empresa_id                BIGINT NOT NULL,
    ejercicio                 INTEGER NOT NULL,
    numero_solicitud          BIGINT NOT NULL,
    periodo_id                UUID,
    tipo_periodo              tipo_periodo_reapertura NOT NULL,
    periodo                   INTEGER,
    motivo                    TEXT NOT NULL,
    estado                    estado_solicitud_reapertura NOT NULL DEFAULT 'pendiente',
    usuario_solicitante       VARCHAR(120),
    fecha_solicitud           TIMESTAMPTZ NOT NULL DEFAULT now(),
    aprobada_por              VARCHAR(120),
    fecha_aprobacion          TIMESTAMPTZ,
    asiento_rectificacion_id  UUID,
    fecha_cierre_efectivo     TIMESTAMPTZ,
    nota_impacto              TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_solicitud_reapertura_empresa_id UNIQUE (empresa_id, id),
    -- Constitucion IV: correlatividad por (empresa, ejercicio), sin saltos.
    CONSTRAINT uq_solicitud_reapertura_numero
        UNIQUE (empresa_id, ejercicio, numero_solicitud),
    CONSTRAINT chk_solicitud_reapertura_numero CHECK (numero_solicitud > 0),
    -- FR-006: la justificacion es obligatoria y no puede quedar en blanco.
    CONSTRAINT chk_solicitud_reapertura_motivo CHECK (length(trim(motivo)) > 0),
    -- El tipo ANUAL no puede colgar de un periodo intermedio.
    CONSTRAINT chk_solicitud_reapertura_periodo CHECK (
        (tipo_periodo = 'ANUAL' AND periodo_id IS NULL)
        OR (tipo_periodo <> 'ANUAL' AND periodo_id IS NOT NULL)
    ),
    CONSTRAINT fk_solicitud_reapertura_periodo
        FOREIGN KEY (empresa_id, periodo_id)
        REFERENCES periodo_cerrado (empresa_id, id),
    CONSTRAINT fk_solicitud_reapertura_asiento
        FOREIGN KEY (empresa_id, asiento_rectificacion_id)
        REFERENCES journal_entry (empresa_id, id)
);

-- FR-005: una sola solicitud activa por periodo. `periodo_id` es NULLABLE, asi
-- que hacen falta dos indices parciales (NULL no colisiona en un UNIQUE
-- normal, mismo patron que `017_presupuestos.sql`).
CREATE UNIQUE INDEX IF NOT EXISTS uq_solicitud_reapertura_activa
    ON solicitud_reapertura (empresa_id, periodo_id)
    WHERE estado IN ('pendiente', 'aprobada', 'reabierta');
CREATE INDEX IF NOT EXISTS ix_solicitud_reapertura_empresa_ejercicio
    ON solicitud_reapertura (empresa_id, ejercicio);
CREATE INDEX IF NOT EXISTS ix_solicitud_reapertura_empresa_estado
    ON solicitud_reapertura (empresa_id, estado);

-- El balance de un periodo cerrado es un snapshot inmutable (constitucion II):
-- ni cabecera ni lineas se actualizan ni se borran. El servicio valida el
-- cuadre antes de insertar; los triggers lo hacen definitivo en el punto mas
-- cercano a la persistencia.
CREATE OR REPLACE FUNCTION f_balanza_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'balanza_periodo: el balance del periodo es inmutable (operacion % denegada)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_balanza_periodo_append_only_update ON balanza_periodo;
CREATE TRIGGER trg_balanza_periodo_append_only_update
    BEFORE UPDATE ON balanza_periodo
    FOR EACH ROW EXECUTE FUNCTION f_balanza_append_only();

DROP TRIGGER IF EXISTS trg_balanza_periodo_append_only_delete ON balanza_periodo;
CREATE TRIGGER trg_balanza_periodo_append_only_delete
    BEFORE DELETE ON balanza_periodo
    FOR EACH ROW EXECUTE FUNCTION f_balanza_append_only();

DROP TRIGGER IF EXISTS trg_balanza_periodo_linea_append_only_update ON balanza_periodo_linea;
CREATE TRIGGER trg_balanza_periodo_linea_append_only_update
    BEFORE UPDATE ON balanza_periodo_linea
    FOR EACH ROW EXECUTE FUNCTION f_balanza_append_only();

DROP TRIGGER IF EXISTS trg_balanza_periodo_linea_append_only_delete ON balanza_periodo_linea;
CREATE TRIGGER trg_balanza_periodo_linea_append_only_delete
    BEFORE DELETE ON balanza_periodo_linea
    FOR EACH ROW EXECUTE FUNCTION f_balanza_append_only();

-- SPEC-028 FR-001 / research D9: segunda proteccion del bloqueo de periodos, a
-- nivel de motor, para preservar el bypass del servicio con scripts o
-- importaciones directas. Solo bloquean `cerrado` y `cerrado_ajustado`: un
-- periodo en `reabierto_ajuste` admite el asiento de rectificacion (FR-004).
-- Los tipos del paquete de cierre estan exentos porque el cierre anual se
-- fecha el ultimo dia del ejercicio, que pertenece al ultimo mes cerrado.
CREATE OR REPLACE FUNCTION f_journal_entry_fecha_abierta() RETURNS trigger AS $$
DECLARE
    v_bloqueado BOOLEAN;
BEGIN
    IF NEW.tipo IN ('REGULARIZACION', 'CIERRE', 'OPENING', 'OPENING_REVERSAL') THEN
        RETURN NEW;
    END IF;
    SELECT EXISTS (
        SELECT 1
        FROM periodo_cerrado p
        WHERE p.empresa_id = NEW.empresa_id
          AND p.estado IN ('cerrado', 'cerrado_ajustado')
          AND p.fecha_ini <= NEW.fecha
          AND p.fecha_fin >= NEW.fecha
    ) INTO v_bloqueado;
    IF v_bloqueado THEN
        RAISE EXCEPTION
            'journal_entry: la fecha % cae en un periodo cerrado (FR-001 periodo_cerrado)',
            NEW.fecha;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chk_journal_entry_fecha_abierta ON journal_entry;
CREATE TRIGGER chk_journal_entry_fecha_abierta
    BEFORE INSERT ON journal_entry
    FOR EACH ROW EXECUTE FUNCTION f_journal_entry_fecha_abierta();

-- El cierre anual es un registro auditable: la transicion
-- `completado -> reapertura_pendiente` es legitima (UPDATE), pero la fila no se
-- borra nunca, igual que los asientos que la respaldan.
CREATE OR REPLACE FUNCTION f_cierre_ejercicio_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'cierre_ejercicio: el cierre anual es un registro auditable (DELETE denegado)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cierre_ejercicio_no_delete ON cierre_ejercicio;
CREATE TRIGGER trg_cierre_ejercicio_no_delete
    BEFORE DELETE ON cierre_ejercicio
    FOR EACH ROW EXECUTE FUNCTION f_cierre_ejercicio_no_delete();
