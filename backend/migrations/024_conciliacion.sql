-- SPEC-013 · Conciliacion bancaria: las 4 tablas que faltaban.
--
-- Estas tablas NUNCA han tenido migracion. SPEC-013 se cerro en 2026-09-19 con
-- 54/54 tareas y sus puertas verdes, pero las puertas eran SQLite, y en SQLite las
-- tablas las crea `Base.metadata.create_all` en cada test. Contra PostgreSQL real
-- no existian, de modo que `POST /api/v1/extractos` respondia 500 con
-- `UndefinedTableError` y **toda** la superficie de conciliacion era inusable.
--
-- Por que no se vio antes: en las 20 specs siguientes cada una anadio su
-- migracion, y `test_migrations.py` solo comprueba que las migraciones *declaradas*
-- esten en el inventario, no que cada tabla del ORM tenga una. Un modelo sin
-- migracion es invisible para esa puerta.
--
-- `cuenta_id` es BIGINT y no UUID: es el id real de `account_plan` (SPEC-001).
-- Los enums van en mayusculas porque es lo que genera SQLAlchemy con `SqlEnum`
-- (a diferencia de 016_catalogo.sql, donde se escribieron en minusculas por mano y
-- hubo que recordarlo en el contrato).
--
-- Idempotente: se puede reaplicar sin efecto.

-- Los enums se crean con `CREATE TYPE` dentro del `IF NOT EXISTS` de `pg_type`, que
-- es la forma que usan 012/021 y la unica que es idempotente en PostgreSQL:
-- `CREATE TYPE ... AS ENUM` no admite todavia `IF NOT EXISTS`.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'extracto_estado') THEN
        CREATE TYPE extracto_estado AS ENUM ('importado', 'duplicado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'conciliacion_estado') THEN
        CREATE TYPE conciliacion_estado AS ENUM ('abierta', 'cerrada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movimiento_signo') THEN
        CREATE TYPE movimiento_signo AS ENUM ('D', 'H');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'movimiento_estado') THEN
        CREATE TYPE movimiento_estado AS ENUM ('pendiente', 'conciliado', 'alertado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cruce_origen') THEN
        CREATE TYPE cruce_origen AS ENUM ('auto', 'manual');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cruce_prioridad') THEN
        CREATE TYPE cruce_prioridad AS ENUM ('propuesto', 'candidato');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cruce_estado') THEN
        CREATE TYPE cruce_estado AS ENUM ('pendiente_confirmar', 'confirmado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alerta_tipo') THEN
        CREATE TYPE alerta_tipo AS ENUM (
            'movimiento_sin_apunte', 'apunte_sin_extracto', 'importe_concepto_dudoso'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alerta_estado') THEN
        CREATE TYPE alerta_estado AS ENUM ('abierta', 'resuelta');
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- extracto_bancario
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS extracto_bancario (
    id                 UUID         NOT NULL,
    empresa_id         BIGINT       NOT NULL,
    cuenta_id          BIGINT       NOT NULL,
    fecha_inicio       DATE         NOT NULL,
    fecha_fin          DATE         NOT NULL,
    saldo_inicial      NUMERIC(18,4) NOT NULL,
    saldo_final        NUMERIC(18,4) NOT NULL,
    nombre_fichero     VARCHAR(255) NOT NULL,
    sha256             VARCHAR(64)  NOT NULL,
    estado             extracto_estado NOT NULL DEFAULT 'importado',
    n_movimientos      INTEGER      NOT NULL,
    fecha_importacion  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    creado_por         VARCHAR(120),
    CONSTRAINT pk_extracto_bancario PRIMARY KEY (id),
    CONSTRAINT uq_extracto_empresa_id UNIQUE (empresa_id, id),
    -- Deduplicacion por contenido (importacion.py): el mismo fichero dos veces.
    CONSTRAINT uq_extracto_empresa_sha256 UNIQUE (empresa_id, sha256),
    CONSTRAINT chk_extracto_rango CHECK (fecha_fin >= fecha_inicio),
    CONSTRAINT chk_extracto_movimientos CHECK (n_movimientos > 0)
);

CREATE INDEX IF NOT EXISTS ix_extracto_bancario_empresa_id ON extracto_bancario (empresa_id);
CREATE INDEX IF NOT EXISTS ix_extracto_bancario_cuenta_id  ON extracto_bancario (cuenta_id);

-- `account_plan.company_id` es `tenant_id` en el modelo de SPEC-001, y la tabla la
-- crea 001_account_plan.sql, asi que la FK cruzada se declara dentro de un
-- `IF to_regclass(...) IS NOT NULL` (el mismo patron que 015 y 018) y, ADEMAS, con
-- un `IF NOT EXISTS` sobre `pg_constraint`.
--
-- Lo segundo no es opcional. `db.migrate` reaplica los ficheros ya aplicados, y el
-- fixture `pg_engine` de los tests de PostgreSQL **tampoco** borra el esquema antes
-- de aplicarlos: los dos escriben sobre la base de verdad. Un `ADD CONSTRAINT` sin
-- guardia hace que el segundo pase reviente con `DuplicateObjectError` y se cae
-- entera la migracion. (Leccion de la seccion 50 de AGENTS.md: "editar una migracion ya
-- aplicada obliga a que siga siendo idempotente; si no, `db.migrate` falla sin saber
-- en que estado quedo la base".)
DO $$BEGIN
    IF to_regclass('account_plan') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_extracto_empresa_cuenta') THEN
        ALTER TABLE extracto_bancario
            ADD CONSTRAINT fk_extracto_empresa_cuenta
            FOREIGN KEY (empresa_id, cuenta_id)
            REFERENCES account_plan (tenant_id, id);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- movimiento_bancario
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS movimiento_bancario (
    id                UUID          NOT NULL,
    empresa_id        BIGINT        NOT NULL,
    extracto_id       UUID          NOT NULL,
    orden             INTEGER       NOT NULL,
    fecha_operacion   DATE          NOT NULL,
    fecha_valor       DATE,
    concepto          VARCHAR(255)  NOT NULL,
    importe           NUMERIC(18,4) NOT NULL,
    signo             movimiento_signo NOT NULL,
    referencia        VARCHAR(80),
    estado            movimiento_estado NOT NULL DEFAULT 'pendiente',
    CONSTRAINT pk_movimiento_bancario PRIMARY KEY (id),
    CONSTRAINT uq_movimiento_empresa_id UNIQUE (empresa_id, id),
    -- El orden dentro del extracto es unico, y es lo que permite leer el extracto
    -- como se leia en el banco.
    CONSTRAINT uq_movimiento_extracto_orden UNIQUE (empresa_id, extracto_id, orden),
    -- `importe > 0` y el signo va en su propia columna: es lo que traduce el
    -- XLSX del banco, donde el signo va DENTRO del importe.
    CONSTRAINT movimiento_importe_positive CHECK (importe > 0),
    CONSTRAINT fk_movimiento_empresa_extracto
        FOREIGN KEY (empresa_id, extracto_id)
        REFERENCES extracto_bancario (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_movimiento_bancario_empresa_id  ON movimiento_bancario (empresa_id);
CREATE INDEX IF NOT EXISTS ix_movimiento_bancario_extracto_id ON movimiento_bancario (extracto_id);

-- ---------------------------------------------------------------------------
-- conciliacion
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS conciliacion (
    id                    UUID          NOT NULL,
    empresa_id            BIGINT        NOT NULL,
    cuenta_id             BIGINT        NOT NULL,
    ejercicio             INTEGER       NOT NULL,
    fecha_inicio          DATE          NOT NULL,
    fecha_fin             DATE          NOT NULL,
    extracto_id           UUID,
    saldo_banco           NUMERIC(18,4) NOT NULL,
    saldo_libros          NUMERIC(18,4) NOT NULL,
    diferencia            NUMERIC(18,4) NOT NULL,
    estado                conciliacion_estado NOT NULL DEFAULT 'abierta',
    periodo_conciliado_id UUID,
    CONSTRAINT pk_conciliacion PRIMARY KEY (id),
    CONSTRAINT uq_conciliacion_empresa_id UNIQUE (empresa_id, id),
    -- `diferencia` NO es un campo que se escribe: es `saldo_banco - saldo_libros`.
    -- La diferencia entre banco y libros no depende de como se concentricen los
    -- cruces, y se define como esa resta, no como un numero que alguien teclea.
    CONSTRAINT chk_conciliacion_diferencia CHECK (diferencia = saldo_banco - saldo_libros),
    CONSTRAINT chk_conciliacion_rango CHECK (fecha_fin >= fecha_inicio)
);

CREATE INDEX IF NOT EXISTS ix_conciliacion_empresa_id ON conciliacion (empresa_id);
CREATE INDEX IF NOT EXISTS ix_conciliacion_cuenta_id  ON conciliacion (cuenta_id);

DO $$
BEGIN
    IF to_regclass('account_plan') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_conciliacion_empresa_cuenta') THEN
        ALTER TABLE conciliacion
            ADD CONSTRAINT fk_conciliacion_empresa_cuenta
            FOREIGN KEY (empresa_id, cuenta_id)
            REFERENCES account_plan (tenant_id, id);
    END IF;
    IF to_regclass('extracto_bancario') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_conciliacion_empresa_extracto') THEN
        ALTER TABLE conciliacion
            ADD CONSTRAINT fk_conciliacion_empresa_extracto
            FOREIGN KEY (empresa_id, extracto_id)
            REFERENCES extracto_bancario (empresa_id, id);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- cruce_conciliacion
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cruce_conciliacion (
    id                       UUID          NOT NULL,
    empresa_id               BIGINT        NOT NULL,
    conciliacion_id          UUID          NOT NULL,
    movimiento_id            UUID          NOT NULL,
    apunte_id                UUID,
    importe                  NUMERIC(18,4) NOT NULL,
    signo                    VARCHAR(1)    NOT NULL,
    origen                   cruce_origen NOT NULL,
    prioridad                cruce_prioridad NOT NULL,
    estado                   cruce_estado NOT NULL DEFAULT 'pendiente_confirmar',
    fecha_cruce              DATE,
    usuario_id               BIGINT,
    confirmado_por_remesa    BOOLEAN       NOT NULL DEFAULT FALSE,
    CONSTRAINT pk_cruce_conciliacion PRIMARY KEY (id),
    CONSTRAINT uq_cruce_empresa_id UNIQUE (empresa_id, id),
    -- Un movimiento no se cruza dos veces en la misma conciliacion.
    CONSTRAINT uq_cruce_empresa_movimiento UNIQUE (empresa_id, movimiento_id),
    CONSTRAINT chk_cruce_signo CHECK (signo IN ('D', 'H')),
    CONSTRAINT chk_cruce_importe CHECK (importe > 0),
    CONSTRAINT fk_cruce_empresa_conciliacion
        FOREIGN KEY (empresa_id, conciliacion_id)
        REFERENCES conciliacion (empresa_id, id),
    CONSTRAINT fk_cruce_empresa_movimiento
        FOREIGN KEY (empresa_id, movimiento_id)
        REFERENCES movimiento_bancario (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_cruce_conciliacion_empresa_id      ON cruce_conciliacion (empresa_id);
CREATE INDEX IF NOT EXISTS ix_cruce_conciliacion_conciliacion_id ON cruce_conciliacion (conciliacion_id);

-- ---------------------------------------------------------------------------
-- periodo_conciliado (archivado, diferencia cero)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS periodo_conciliado (
    id                UUID          NOT NULL,
    empresa_id        BIGINT        NOT NULL,
    conciliacion_id   UUID          NOT NULL,
    cuenta_id         BIGINT        NOT NULL,
    ejercicio         INTEGER       NOT NULL,
    numero_periodo    BIGINT        NOT NULL,
    fecha_inicio      DATE          NOT NULL,
    fecha_fin         DATE          NOT NULL,
    saldo_banco       NUMERIC(18,4) NOT NULL,
    saldo_libros      NUMERIC(18,4) NOT NULL,
    diferencia        NUMERIC(18,4) NOT NULL,
    fecha_cierre      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    usuario_id        BIGINT,
    CONSTRAINT pk_periodo_conciliado PRIMARY KEY (id),
    CONSTRAINT uq_periodo_empresa_id UNIQUE (empresa_id, id),
    -- Correlatividad (constitucion IV): el numero de periodo es unico por
    -- (empresa, ejercicio), que es lo que hace que dos conciliaciones del mismo
    -- trimestre no se numeren las dos como 1.
    CONSTRAINT uq_periodo_numero UNIQUE (empresa_id, ejercicio, numero_periodo),
    CONSTRAINT chk_periodo_diferencia_cero CHECK (diferencia = 0),
    CONSTRAINT chk_periodo_rango CHECK (fecha_fin >= fecha_inicio),
    CONSTRAINT fk_periodo_empresa_conciliacion
        FOREIGN KEY (empresa_id, conciliacion_id)
        REFERENCES conciliacion (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_periodo_conciliado_empresa_id  ON periodo_conciliado (empresa_id);
CREATE INDEX IF NOT EXISTS ix_periodo_conciliado_cuenta_id   ON periodo_conciliado (cuenta_id);

-- ---------------------------------------------------------------------------
-- alerta_conciliacion
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS alerta_conciliacion (
    id               UUID          NOT NULL,
    empresa_id       BIGINT        NOT NULL,
    conciliacion_id  UUID          NOT NULL,
    tipo             alerta_tipo   NOT NULL,
    movimiento_id    UUID,
    descripcion      VARCHAR(255)  NOT NULL,
    estado           alerta_estado NOT NULL DEFAULT 'abierta',
    CONSTRAINT pk_alerta_conciliacion PRIMARY KEY (id),
    CONSTRAINT uq_alerta_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT fk_alerta_empresa_conciliacion
        FOREIGN KEY (empresa_id, conciliacion_id)
        REFERENCES conciliacion (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_alerta_conciliacion_empresa_id      ON alerta_conciliacion (empresa_id);
CREATE INDEX IF NOT EXISTS ix_alerta_conciliacion_conciliacion_id ON alerta_conciliacion (conciliacion_id);

-- ---------------------------------------------------------------------------
-- Inmutabilidad (constitucion II)
-- ---------------------------------------------------------------------------

-- Un movimiento importado **no se reescribe**: fecha, importe, signo, concepto,
-- referencia y extracto son los que dijo el banco, y tocarlos es falsear el
-- extracto. Lo que SI cambia es `estado`, porque confirmar un cruce lo pasa a
-- `conciliado` y deshacerlo lo devuelve a `pendiente`
-- (`services/reconciliation/cruce.py`). Por eso el trigger compara columna a
-- columna en vez de reventar cualquier UPDATE: un trigger que reventase el UPDATE
-- entero haria la conciliacion inutilizable, que es justo su funcion.
CREATE OR REPLACE FUNCTION f_movimiento_bancario_inmutable() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.extracto_id IS DISTINCT FROM OLD.extracto_id
       OR NEW.orden IS DISTINCT FROM OLD.orden
       OR NEW.fecha_operacion IS DISTINCT FROM OLD.fecha_operacion
       OR NEW.fecha_valor IS DISTINCT FROM OLD.fecha_valor
       OR NEW.concepto IS DISTINCT FROM OLD.concepto
       OR NEW.importe IS DISTINCT FROM OLD.importe
       OR NEW.signo IS DISTINCT FROM OLD.signo
       OR NEW.referencia IS DISTINCT FROM OLD.referencia THEN
        RAISE EXCEPTION
            'movimiento_bancario es inmutable: un movimiento descargado del banco no se reescribe (solo cambia su estado)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_movimiento_bancario_contenido_inmutable_update ON movimiento_bancario;
CREATE TRIGGER trg_movimiento_bancario_contenido_inmutable_update
    BEFORE UPDATE ON movimiento_bancario
    FOR EACH ROW EXECUTE FUNCTION f_movimiento_bancario_inmutable();

-- El `DELETE` no lo admite nadie: para retirar un movimiento se anula el extracto
-- entero y se vuelve a importar, que es una operacion con traza.
CREATE OR REPLACE FUNCTION f_movimiento_bancario_no_delete() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'movimiento_bancario no se borra (operacion DELETE sobre un extracto ya importado)'
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_movimiento_bancario_inmutable_delete ON movimiento_bancario;
CREATE TRIGGER trg_movimiento_bancario_inmutable_delete
    BEFORE DELETE ON movimiento_bancario
    FOR EACH ROW EXECUTE FUNCTION f_movimiento_bancario_no_delete();

-- El periodo conciliado es un cierre: se archiva y no se toca. Es lo que impide
-- que un periodo "cerrado con diferencia cero" se reescriba a mano despues.
CREATE OR REPLACE FUNCTION f_periodo_conciliado_append_only() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'periodo_conciliado es inmutable (operacion % sobre un periodo ya archivado)', TG_OP
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_periodo_conciliado_inmutable_update ON periodo_conciliado;
CREATE TRIGGER trg_periodo_conciliado_inmutable_update
    BEFORE UPDATE ON periodo_conciliado
    FOR EACH ROW EXECUTE FUNCTION f_periodo_conciliado_append_only();

DROP TRIGGER IF EXISTS trg_periodo_conciliado_inmutable_delete ON periodo_conciliado;
CREATE TRIGGER trg_periodo_conciliado_inmutable_delete
    BEFORE DELETE ON periodo_conciliado
    FOR EACH ROW EXECUTE FUNCTION f_periodo_conciliado_append_only();
