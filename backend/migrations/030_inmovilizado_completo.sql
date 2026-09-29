-- Grupo 4 de las 27 · Inmovilizado: 4 tablas.
--
-- SPEC-014 (amortizaciones). Las cuatro tablas de la feature: el activo, su plan
-- calculado, las cuotas ya generadas y su baja.
--
-- Ninguna ha tenido migracion nunca. En SQLite las crea `Base.metadata.create_all`, y
-- en PostgreSQL real no existian: `/inmovilizado` y sus cuatro endpoints devolvian 500.
--
-- Las cuentas del activo apuntan a `account_plan`, que crea 001_account_plan.sql, y
-- `account_plan` llama `tenant_id` a la columna de empresa (ver §49 de AGENTS.md). Las
-- tres FKs van por `to_regclass` y con la guardia de `pg_constraint` por lo mismo que
-- explica 024: `db.migrate` y el fixture `pg_engine` escriben los dos sobre la base de
-- verdad sin borrarla.
--
-- `amortizacion_generada` lleva un **indice unico PARCIAL**:
-- `UNIQUE (empresa_id, activo_id, ejercicio, periodo) WHERE reabierta = false`. Es lo
-- que impide amortizar dos veces el mismo periodo del mismo activo, y lo permite
-- justamente porque la reapertura crea una fila nueva con `reabierta = true` en vez de
-- tocar la anterior. Un UNIQUE normal lo impediria, asi que aqui si hace falta el
-- indice parcial. El modelo lo declara con `reabierta = false` para PostgreSQL y
-- `reabierta = 0` para SQLite (misma condicion, distinta forma de escribir el booleano).
--
-- Idempotente: se puede reaplicar sin efecto.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'metodo_amortizacion') THEN
        CREATE TYPE metodo_amortizacion AS ENUM ('lineal', 'regresivo');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_activo') THEN
        CREATE TYPE estado_activo AS ENUM ('en_uso', 'dado_de_baja');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_plan') THEN
        CREATE TYPE estado_plan AS ENUM ('pendiente', 'amortizado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_baja') THEN
        CREATE TYPE tipo_baja AS ENUM ('venta', 'retirada');
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- activo_inmovilizado
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS activo_inmovilizado (
    id                     UUID          NOT NULL,
    empresa_id             BIGINT        NOT NULL,
    numero_activo          VARCHAR(40)   NOT NULL,
    cuenta_id              BIGINT        NOT NULL,
    descripcion            VARCHAR(255)  NOT NULL,
    fecha_alta             DATE          NOT NULL,
    coste_amortizable      NUMERIC(18,4) NOT NULL,
    vida_util              SMALLINT      NOT NULL,
    metodo                 metodo_amortizacion NOT NULL,
    porcentaje_regresivo   NUMERIC(5,2),
    estado                 estado_activo NOT NULL DEFAULT 'en_uso',
    fecha_baja             DATE,
    cuenta_gasto_id        BIGINT,
    cuenta_acumulada_id    BIGINT,
    CONSTRAINT pk_activo_inmovilizado PRIMARY KEY (id),
    CONSTRAINT uq_activo_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_activo_tenant_numero UNIQUE (empresa_id, numero_activo),
    CONSTRAINT chk_activo_coste_positive CHECK (coste_amortizable > 0),
    CONSTRAINT chk_activo_vida_positive  CHECK (vida_util > 0),
    -- El metodo y el porcentaje van juntos: o es lineal y no lleva porcentaje, o es
    -- regresivo y lo lleva. Un activo con metodo regresivo y porcentaje NULL haria que
    -- `plan.py` dividiera entre cero al calcular la cuota.
    CONSTRAINT chk_activo_metodo_porcentaje CHECK (
        (metodo = 'regresivo' AND porcentaje_regresivo IS NOT NULL)
        OR (metodo = 'lineal' AND porcentaje_regresivo IS NULL)
    ),
    CONSTRAINT chk_activo_porcentaje_rango CHECK (
        porcentaje_regresivo IS NULL
        OR (porcentaje_regresivo > 0 AND porcentaje_regresivo < 100)
    )
);

CREATE INDEX IF NOT EXISTS ix_activo_inmovilizado_empresa_id ON activo_inmovilizado (empresa_id);

DO $$BEGIN
    IF to_regclass('account_plan') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_activo_cuenta') THEN
        ALTER TABLE activo_inmovilizado ADD CONSTRAINT fk_activo_cuenta
            FOREIGN KEY (empresa_id, cuenta_id) REFERENCES account_plan (tenant_id, id);
    END IF;
    IF to_regclass('account_plan') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_activo_cuenta_gasto') THEN
        ALTER TABLE activo_inmovilizado ADD CONSTRAINT fk_activo_cuenta_gasto
            FOREIGN KEY (empresa_id, cuenta_gasto_id) REFERENCES account_plan (tenant_id, id);
    END IF;
    IF to_regclass('account_plan') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_activo_cuenta_acumulada') THEN
        ALTER TABLE activo_inmovilizado ADD CONSTRAINT fk_activo_cuenta_acumulada
            FOREIGN KEY (empresa_id, cuenta_acumulada_id) REFERENCES account_plan (tenant_id, id);
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- plan_amortizacion
-- ---------------------------------------------------------------------------
--
-- El plan son las cuotas *calculadas*, antes de que exista el asiento. La tabla
-- `amortizacion_generada` es la que ya se contabilizo; las dos son distintas a proposito
-- y por eso hay dos tablas y no una con una columna de estado.

CREATE TABLE IF NOT EXISTS plan_amortizacion (
    id        UUID          NOT NULL,
    empresa_id BIGINT       NOT NULL,
    activo_id UUID          NOT NULL,
    ejercicio INTEGER       NOT NULL,
    periodo   INTEGER       NOT NULL,
    cuota     NUMERIC(18,4) NOT NULL,
    acumulado NUMERIC(18,4) NOT NULL,
    estado    estado_plan NOT NULL DEFAULT 'pendiente',
    CONSTRAINT pk_plan_amortizacion PRIMARY KEY (id),
    -- Un activo no tiene dos cuotas del mismo ejercicio y periodo: el plan se
    -- recalcula entero (`_replanear` borra y reinserta), no se parchea.
    CONSTRAINT uq_plan_activo_periodo UNIQUE (empresa_id, activo_id, ejercicio, periodo),
    -- ON DELETE CASCADE: los planes cuelgan del activo y no tienen vida propia. Si se
    -- replantea el activo desde cero, sus cuotas no significan nada.
    CONSTRAINT fk_plan_activo
        FOREIGN KEY (empresa_id, activo_id)
        REFERENCES activo_inmovilizado (empresa_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_plan_amortizacion_empresa_id ON plan_amortizacion (empresa_id);
CREATE INDEX IF NOT EXISTS ix_plan_amortizacion_activo_id  ON plan_amortizacion (activo_id);


-- ---------------------------------------------------------------------------
-- amortizacion_generada
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS amortizacion_generada (
    id           UUID          NOT NULL,
    empresa_id   BIGINT        NOT NULL,
    activo_id    UUID          NOT NULL,
    ejercicio    INTEGER       NOT NULL,
    periodo      INTEGER       NOT NULL,
    asiento_id   UUID          NOT NULL,
    cuota        NUMERIC(18,4) NOT NULL,
    reapertura_de UUID,
    reabierta    BOOLEAN       NOT NULL DEFAULT false,
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT pk_amortizacion_generada PRIMARY KEY (id),
    -- `reapertura_de` apunta al UUID de otra `amortizacion_generada` de la MISMA
    -- empresa, pero el modelo **no** declara FK: queda en `REFERENCIAS_SIN_FK`. Es una
    -- traza, no una dependencia de la que dependa el borrado.
    CONSTRAINT fk_generada_activo
        FOREIGN KEY (empresa_id, activo_id)
        REFERENCES activo_inmovilizado (empresa_id, id)
        ON DELETE CASCADE
);

-- Unico PARCIAL. Sin el `WHERE`, la reapertura de una cuota no podria existir: la fila
-- nueva tendria el mismo (activo, ejercicio, periodo) que la que reabre, y un UNIQUE
-- normal lo rechazaria. Con el, solo colisionan las vigentes (`reabierta = false`).
CREATE UNIQUE INDEX IF NOT EXISTS uq_generada_activo_periodo_vigente
    ON amortizacion_generada (empresa_id, activo_id, ejercicio, periodo)
    WHERE reabierta = false;

CREATE INDEX IF NOT EXISTS ix_amortizacion_generada_empresa_id ON amortizacion_generada (empresa_id);
CREATE INDEX IF NOT EXISTS ix_amortizacion_generada_activo_id  ON amortizacion_generada (activo_id);

DO $$BEGIN
    IF to_regclass('journal_entry') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_generada_asiento') THEN
        ALTER TABLE amortizacion_generada ADD CONSTRAINT fk_generada_asiento
            FOREIGN KEY (empresa_id, asiento_id) REFERENCES journal_entry (empresa_id, id);
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- baja_activo
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS baja_activo (
    id                     UUID          NOT NULL,
    empresa_id             BIGINT        NOT NULL,
    activo_id              UUID          NOT NULL,
    fecha_baja             DATE          NOT NULL,
    precio_venta           NUMERIC(18,4) NOT NULL,
    amortizacion_hasta_baja NUMERIC(18,4) NOT NULL,
    amortizacion_acumulada  NUMERIC(18,4) NOT NULL,
    valor_neto_contable    NUMERIC(18,4) NOT NULL,
    resultado              NUMERIC(18,4) NOT NULL,
    asiento_id             UUID          NOT NULL,
    tipo                   tipo_baja NOT NULL,
    CONSTRAINT pk_baja_activo PRIMARY KEY (id),
    -- Un activo se da de baja una sola vez. Es lo que impide darlo de baja dos veces
    -- con dos asientos de resultado.
    CONSTRAINT uq_baja_activo UNIQUE (empresa_id, activo_id),
    CONSTRAINT chk_baja_precio_no_negativo   CHECK (precio_venta >= 0),
    -- Una amortizacion acumulada negativa significa que se ha amortizado mas de lo que
    -- costaba el activo, que es imposible con el metodo lineal o con el regresivo de
    -- este repositorio (ambos convergen a residual 0, nunca por debajo).
    CONSTRAINT chk_baja_amortizacion_no_negativa CHECK (amortizacion_hasta_baja >= 0),
    CONSTRAINT fk_baja_activo
        FOREIGN KEY (empresa_id, activo_id)
        REFERENCES activo_inmovilizado (empresa_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_baja_activo_empresa_id ON baja_activo (empresa_id);
CREATE INDEX IF NOT EXISTS ix_baja_activo_activo_id  ON baja_activo (activo_id);

DO $$BEGIN
    IF to_regclass('journal_entry') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_baja_asiento') THEN
        ALTER TABLE baja_activo ADD CONSTRAINT fk_baja_asiento
            FOREIGN KEY (empresa_id, asiento_id) REFERENCES journal_entry (empresa_id, id);
    END IF;
END $$;
