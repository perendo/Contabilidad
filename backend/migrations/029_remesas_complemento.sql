-- Grupo 3 de las 27 · Remesas SEPA: 9 tablas.
--
-- SPEC-020 (remesas SEPA y cobros), con las ampliaciones de SPEC-021 (mandatos y
-- medios de pago) y SPEC-022 (cesiones, que anade `condicion_pronto_pago`).
--
-- Ninguna ha tenido migracion nunca. En SQLite las creaba `Base.metadata.create_all`
-- y en PostgreSQL real no existian, de modo que toda la superficie de remesas
-- (`/remesas`, `/devoluciones`, `/terceros/condiciones`) devolvia 500.
--
-- **Esta feature no era migrable tal cual como estaba**, y no por un detalle: cinco
-- de sus nueve tablas declaraban **dos restricciones con el mismo nombre**. La
-- convencion de `base.py` es `uq_%(table_name)s_%(column_0_name)s`, que solo mira la
-- primera columna, asi que `UNIQUE (empresa_id, id)` y
-- `UNIQUE (empresa_id, ejercicio, numero_remesa)` recibian las dos
-- `uq_<tabla>_empresa_id`. En SQLite eso no importa y en PostgreSQL el `CREATE TABLE`
-- falla con "already contains constraint". Los nombres de aqui son los corregidos en
-- los modelos; guard en `tests/unit/test_enums_orm.py`.
--
-- Dos indices unicos **PARCIALES** que no son caprichos:
--
-- - `recibo_remesa` no puede estar en dos remesas a la vez mientras no se devuelva
--   (`WHERE estado != 'devuelto'`). Sin el `WHERE`, un recibo devuelto que se vuelve a
--   remesear dejaria el vencimiento bloqueado para siempre.
-- - `condicion_pronto_pago` admite una sola condicion vigente por tercero
--   (`WHERE vigente`), porque el descuento a aplicar no puede ser ambiguo. Al crear
--   una nueva se desactiva la anterior en el mismo servicio.
--
-- `asiento_cobro_id` y `asiento_reversal_id` son UUID sueltos: no declaran FK, y quedan
-- en `tests/esquema_deuda.py::REFERENCIAS_SIN_FK`. `fichero_id` apunta a `blob_fichero`
-- y tampoco la declara.
--
-- Idempotente: se puede reaplicar sin efecto.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'formato_remesa') THEN
        CREATE TYPE formato_remesa AS ENUM ('SEPA_DD', 'CSB_19_19');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_adeudo') THEN
        CREATE TYPE tipo_adeudo AS ENUM ('CORE', 'B2B');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'remesa_estado') THEN
        CREATE TYPE remesa_estado AS ENUM ('borrador', 'emitida', 'cobrada', 'devuelta');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recibo_estado') THEN
        CREATE TYPE recibo_estado AS ENUM ('pendiente', 'remesado', 'cobrado', 'devuelto');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_reclamacion') THEN
        CREATE TYPE estado_reclamacion AS ENUM (
            'sin_reclamacion', 'reclamada', 'resuelta', 'desestimada'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reclamacion_estado') THEN
        CREATE TYPE reclamacion_estado AS ENUM ('abierta', 'en_curso', 'resuelta', 'desestimada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'mandato_estado') THEN
        CREATE TYPE mandato_estado AS ENUM ('firmado', 'caducado', 'revocado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_blob') THEN
        CREATE TYPE tipo_blob AS ENUM ('remesa_sepa', 'remesa_csb1919', 'r19', 'c19');
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- secuencia_remesa
-- ---------------------------------------------------------------------------
--
-- Constitucion IV: la numeracion sin saltos se garantiza con un SELECT ... FOR UPDATE
-- sobre esta fila, dentro de la misma transaccion que guarda la remesa. La fila es
-- (empresa, ejercicio) y el ultimo numero usado.

CREATE TABLE IF NOT EXISTS secuencia_remesa (
    id            UUID    NOT NULL,
    empresa_id    BIGINT  NOT NULL,
    ejercicio     INTEGER NOT NULL,
    ultimo_numero BIGINT  NOT NULL DEFAULT 0,
    CONSTRAINT pk_secuencia_remesa PRIMARY KEY (id),
    CONSTRAINT uq_secuencia_remesa_empresa_ejercicio UNIQUE (empresa_id, ejercicio)
);

CREATE INDEX IF NOT EXISTS ix_secuencia_remesa_empresa_id ON secuencia_remesa (empresa_id);


-- ---------------------------------------------------------------------------
-- mandato_sepa
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mandato_sepa (
    id          UUID         NOT NULL,
    empresa_id  BIGINT       NOT NULL,
    tercero_id  UUID         NOT NULL,
    mandato_ref VARCHAR(35)  NOT NULL,
    fecha_firma DATE         NOT NULL,
    tipo        tipo_adeudo  NOT NULL,
    estado      mandato_estado NOT NULL,
    CONSTRAINT pk_mandato_sepa PRIMARY KEY (id),
    CONSTRAINT uq_mandato_sepa_empresa_id UNIQUE (empresa_id, id),
    -- Un tercero no puede tener dos vez el mismo `mandato_ref`, que es la referencia
    -- que va en el fichero SEPA. Es la deduplicacion de la firma.
    CONSTRAINT uq_mandato_sepa_empresa_tercero_ref UNIQUE (empresa_id, tercero_id, mandato_ref)
);

CREATE INDEX IF NOT EXISTS ix_mandato_sepa_empresa_id ON mandato_sepa (empresa_id);


-- ---------------------------------------------------------------------------
-- condicion_pronto_pago
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS condicion_pronto_pago (
    id                 UUID          NOT NULL,
    empresa_id         BIGINT        NOT NULL,
    tercero_id         UUID          NOT NULL,
    plazo_dias         INTEGER       NOT NULL,
    porcentaje         NUMERIC(5,2)  NOT NULL,
    vigente            BOOLEAN       NOT NULL DEFAULT true,
    override_factura_id UUID,
    CONSTRAINT pk_condicion_pronto_pago PRIMARY KEY (id),
    CONSTRAINT uq_condicion_pronto_pago_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT chk_condicion_plazo_dias_positive CHECK (plazo_dias > 0),
    -- El 100 % se admite (descuento total) y el 0 % no: un descuento del 0 % no es
    -- una condicion de pronto pago, es la ausencia de ella, y se modela no teniendo
    -- condicion.
    CONSTRAINT chk_condicion_porcentaje_range CHECK (porcentaje > 0 AND porcentaje <= 100)
);

CREATE INDEX IF NOT EXISTS ix_condicion_pronto_pago_empresa_id
    ON condicion_pronto_pago (empresa_id);

-- Unico PARCIAL: una sola condicion vigente por tercero. Sin el `WHERE`, crear la
-- nueva (que desactiva la anterior en el mismo servicio) fallaria contra la propia
-- fila que acaba de desactivarse. Un UNIQUE normal no serviria.
CREATE UNIQUE INDEX IF NOT EXISTS uq_condicion_pronto_pago_vigente
    ON condicion_pronto_pago (empresa_id, tercero_id)
    WHERE vigente;


-- ---------------------------------------------------------------------------
-- blob_fichero
-- ---------------------------------------------------------------------------
--
-- Los ficheros de remesa (PAIN.008 y cuaderno 19/19) y los retornos AEB R19/C19. El
-- contenido va en la base y no en disco a proposito: la constitution II pide que lo
-- ya emitido no cambie, y un fichero en el sistema de ficheros se puede pisar.

CREATE TABLE IF NOT EXISTS blob_fichero (
    id         UUID        NOT NULL,
    empresa_id BIGINT      NOT NULL,
    tipo       tipo_blob   NOT NULL,
    contenido  BYTEA       NOT NULL,
    sha256     VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_blob_fichero PRIMARY KEY (id),
    CONSTRAINT uq_blob_fichero_empresa_id UNIQUE (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_blob_fichero_empresa_id ON blob_fichero (empresa_id);


-- ---------------------------------------------------------------------------
-- remesa
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS remesa (
    id            UUID          NOT NULL,
    empresa_id    BIGINT        NOT NULL,
    ejercicio     INTEGER       NOT NULL,
    numero_remesa BIGINT        NOT NULL,
    fecha_emision DATE,
    fecha_cargo   DATE,
    formato       formato_remesa NOT NULL,
    tipo_adeudo   tipo_adeudo   NOT NULL,
    importe_total NUMERIC(18,4) NOT NULL,
    estado        remesa_estado NOT NULL,
    fichero_id    UUID,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT pk_remesa PRIMARY KEY (id),
    CONSTRAINT uq_remesa_empresa_id UNIQUE (empresa_id, id),
    -- Correlatividad sin saltos por (empresa, ejercicio). El numero lo toma
    -- `secuencia_remesa` con SELECT ... FOR UPDATE; este UNIQUE es la red por si dos
    -- peticiones lo pidieran a la vez.
    CONSTRAINT uq_remesa_empresa_ejercicio_numero UNIQUE (empresa_id, ejercicio, numero_remesa),
    -- Una remesa sin importe no es una remesa: se rechaza al seleccionarla, no al
    -- guardarla, pero que no llegue a existir simplifica el informe.
    CONSTRAINT ck_remesa_importe_total_positive CHECK (importe_total > 0)
);

CREATE INDEX IF NOT EXISTS ix_remesa_empresa_id ON remesa (empresa_id);


-- ---------------------------------------------------------------------------
-- recibo_remesa
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS recibo_remesa (
    id              UUID          NOT NULL,
    empresa_id      BIGINT        NOT NULL,
    remesa_id       UUID          NOT NULL,
    vencimiento_id  UUID          NOT NULL,
    recibo_num      VARCHAR(32)   NOT NULL,
    tercero_id      UUID          NOT NULL,
    iban            VARCHAR(34)   NOT NULL,
    importe         NUMERIC(18,4) NOT NULL,
    fecha_cargo     DATE          NOT NULL,
    descuento_id    UUID,
    estado          recibo_estado NOT NULL,
    asiento_cobro_id UUID,
    fecha_cobro     DATE,
    CONSTRAINT pk_recibo_remesa PRIMARY KEY (id),
    CONSTRAINT uq_recibo_remesa_empresa_id UNIQUE (empresa_id, id),
    -- Un recibo aparece una sola vez por remesa y vencimiento. Sin este UNIQUE, anular
    -- y volver a crear la remesa generaria recibos duplicados con el mismo vencimiento.
    CONSTRAINT uq_recibo_remesa_empresa_remesa_vencimiento
        UNIQUE (empresa_id, remesa_id, vencimiento_id),
    CONSTRAINT ck_recibo_remesa_importe_positive CHECK (importe > 0),
    CONSTRAINT fk_recibo_remesa
        FOREIGN KEY (empresa_id, remesa_id)
        REFERENCES remesa (empresa_id, id)
);

-- Unico PARCIAL: un vencimiento no puede estar en dos remesas mientras su recibo no se
-- haya devuelto. El `WHERE estado != 'devuelto'` es lo que deja que un recibo devuelto
-- vuelva a remesearse: sin el, el vencimiento quedaria bloqueado para siempre.
CREATE UNIQUE INDEX IF NOT EXISTS uq_recibo_remesa_empresa_vencimiento
    ON recibo_remesa (empresa_id, vencimiento_id)
    WHERE estado != 'devuelto';

CREATE INDEX IF NOT EXISTS ix_recibo_remesa_empresa_id ON recibo_remesa (empresa_id);


-- ---------------------------------------------------------------------------
-- devolucion_recibo
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS devolucion_recibo (
    id                    UUID          NOT NULL,
    empresa_id            BIGINT        NOT NULL,
    recibo_remesa_id      UUID          NOT NULL,
    codigo                VARCHAR(10)   NOT NULL,
    identificador_externo VARCHAR(64)   NOT NULL,
    motivo                VARCHAR(255)  NOT NULL,
    fecha_registro        DATE          NOT NULL,
    fecha_cargo_original  DATE          NOT NULL,
    importe               NUMERIC(18,4) NOT NULL,
    importe_gastos        NUMERIC(18,4) NOT NULL DEFAULT 0,
    asiento_reversal_id   UUID,
    estado_reclamacion    estado_reclamacion NOT NULL,
    CONSTRAINT pk_devolucion_recibo PRIMARY KEY (id),
    CONSTRAINT uq_devolucion_recibo_empresa_id UNIQUE (empresa_id, id),
    -- Idempotencia de la importacion del retorno R19/C19: el fichero se puede subir dos
    -- veces y la segunda no debe duplicar la devolucion. El identificador externo es el
    -- que da el banco, y lleva el tipo de retorno (R19/C19) en su construccion.
    CONSTRAINT uq_devolucion_recibo_empresa_identificador
        UNIQUE (empresa_id, identificador_externo),
    CONSTRAINT ck_devolucion_importe_non_negative CHECK (importe >= 0),
    CONSTRAINT ck_devolucion_importe_gastos_non_negative CHECK (importe_gastos >= 0),
    CONSTRAINT fk_devolucion_recibo
        FOREIGN KEY (empresa_id, recibo_remesa_id)
        REFERENCES recibo_remesa (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_devolucion_recibo_empresa_id ON devolucion_recibo (empresa_id);


-- ---------------------------------------------------------------------------
-- reclamacion
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reclamacion (
    id             UUID              NOT NULL,
    empresa_id     BIGINT            NOT NULL,
    devolucion_id  UUID              NOT NULL,
    fecha_registro DATE              NOT NULL,
    estado         reclamacion_estado NOT NULL,
    observaciones  TEXT,
    CONSTRAINT pk_reclamacion PRIMARY KEY (id),
    CONSTRAINT uq_reclamacion_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT fk_reclamacion
        FOREIGN KEY (empresa_id, devolucion_id)
        REFERENCES devolucion_recibo (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_reclamacion_empresa_id ON reclamacion (empresa_id);


-- ---------------------------------------------------------------------------
-- cobro_conciliado
-- ---------------------------------------------------------------------------
--
-- Puente entre SPEC-013 (conciliacion) y SPEC-020 (remesas): cuando se confirma un
-- cruce cuyo apunte es el asiento de cobro de un recibo, el recibo pasa a `cobrado` sin
-- segundo asiento. El UNIQUE (empresa, movimiento) es la deduplicacion: un movimiento
-- bancario no se cruza con dos recibos.

CREATE TABLE IF NOT EXISTS cobro_conciliado (
    id               UUID        NOT NULL,
    empresa_id       BIGINT      NOT NULL,
    movimiento_id    UUID        NOT NULL,
    recibo_remesa_id UUID        NOT NULL,
    journal_entry_id UUID        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_cobro_conciliado PRIMARY KEY (id),
    CONSTRAINT uq_cobro_conciliado_empresa_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_cobro_conciliado_empresa_movimiento UNIQUE (empresa_id, movimiento_id),
    CONSTRAINT fk_cobro_conciliado_recibo
        FOREIGN KEY (empresa_id, recibo_remesa_id)
        REFERENCES recibo_remesa (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_cobro_conciliado_empresa_id ON cobro_conciliado (empresa_id);

DO $$BEGIN
    IF to_regclass('journal_entry') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cobro_conciliado_asiento') THEN
        ALTER TABLE cobro_conciliado ADD CONSTRAINT fk_cobro_conciliado_asiento
            FOREIGN KEY (empresa_id, journal_entry_id) REFERENCES journal_entry (empresa_id, id);
    END IF;
    IF to_regclass('movimiento_bancario') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cobro_conciliado_movimiento') THEN
        -- `movimiento_bancario` la crea 024_conciliacion.sql (SPEC-013). El modelo no
        -- declara esta FK y por tanto no se migra: `movimiento_id` queda en
        -- REFERENCIAS_SIN_FK. Este bloque esta aqui para dejar constancia de que la
        -- dependencia existe y de que se ha decidido no tomarla.
        NULL;
    END IF;
END $$;
