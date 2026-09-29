-- Grupo 2 de las 27 · Cobros y vencimientos: 2 tablas.
--
-- SPEC-011 (cobros y pagos) y los campos que le anadio SPEC-020 (remesas: `remesa_id`
-- y el estado `remesado`) y SPEC-022 (cesion: el estado `cedido`).
--
-- Estas tablas NUNCA han tenido migracion: en SQLite las crea
-- `Base.metadata.create_all` y en PostgreSQL real no existian, de modo que
-- `GET /api/v1/vencimientos`, la antiguedad de saldos y el resto de la superficie de
-- cobros devolvian 500.
--
-- **Se migra el modelo tal cual** (decision del 2026-09-29): `tercero_id`,
-- `factura_id` y `remesa_id` quedan como UUID sueltos, y lo mismo `vencimiento_id` y
-- `journal_entry_id` en `cobro_pago`. Los cinco estan anotados en
-- `tests/esquema_deuda.py::REFERENCIAS_SIN_FK`. Anadir la FK a `factura` seria lo
-- natural, pero una FK que el ORM no conoce puede convertir en 500 un INSERT que hoy
-- funciona, y la constitucion III ya se cumple en `Depends(get_empresa_id)`.
--
-- `estado` NO lleva valor por defecto. El modelo tampoco lo lleva, y no es un descuido:
-- un vencimiento nace siempre en un estado concreto segun como se creo, y obligar a
-- decidirlo aqui seria inventar una regla que el servicio ya aplica. Poner un
-- `DEFAULT 'pendiente'` aqui haria que un INSERT que se ha olvidado del estado guardara un
-- vencimiento pendiente sin que nadie lo decidiera.
--
-- `acumulado` lleva `DEFAULT 0` y no `0.0000`: PostgreSQL reduce el literal a '0', y el
-- comparador de esquema lo daria por equivalente de todas formas.
--
-- Idempotente: se puede reaplicar sin efecto.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vencimiento_tipo') THEN
        CREATE TYPE vencimiento_tipo AS ENUM ('cobro', 'pago');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vencimiento_estado') THEN
        CREATE TYPE vencimiento_estado AS ENUM (
            'pendiente', 'parcial', 'cobrado', 'remesado', 'devuelto', 'anulado', 'cedido'
        );
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- vencimiento
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vencimiento (
    id               UUID          NOT NULL,
    empresa_id       BIGINT        NOT NULL,
    tercero_id       UUID          NOT NULL,
    factura_id       UUID,
    fecha_factura    DATE,
    recibo_num       VARCHAR(32)   NOT NULL,
    iban             VARCHAR(34)   NOT NULL,
    ejercicio        INTEGER       NOT NULL,
    tipo             vencimiento_tipo NOT NULL DEFAULT 'cobro',
    fecha_vencimiento DATE         NOT NULL,
    importe          NUMERIC(18,4) NOT NULL,
    acumulado        NUMERIC(18,4) NOT NULL DEFAULT 0,
    estado           vencimiento_estado NOT NULL,
    remesa_id        UUID,
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT pk_vencimiento PRIMARY KEY (id),
    CONSTRAINT uq_vencimiento_empresa_id UNIQUE (empresa_id, id),
    -- El importe pendiente se deriva como `importe - acumulado`, asi que un acumulado
    -- mayor que el importe daria un saldo negativo en la cartera, que es justo el
    -- estado que no puede existir. Este es el sitio donde se comprueba.
    CONSTRAINT chk_vencimiento_importe_positive CHECK (importe > 0),
    CONSTRAINT chk_vencimiento_acumulado_rango CHECK (acumulado >= 0 AND acumulado <= importe)
);

CREATE INDEX IF NOT EXISTS ix_vencimiento_empresa_id ON vencimiento (empresa_id);
-- Solo el indice que declara el modelo. La primera version de esta migracion anadia
-- ademas un `ix_vencimiento_empresa_fecha` sobre `fecha_ven`, que **no existe** (la
-- columna se llama `fecha_vencimiento`) y que el modelo tampoco declara: era un indice
-- de rendimiento inventado sobre una columna inventada, y revolvio la migracion entera
-- al aplicarse. Anadir indices que el modelo no declara es una decision con planes de
-- ejecucion delante, no un extra de este fichero.


-- ---------------------------------------------------------------------------
-- cobro_pago
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cobro_pago (
    id               UUID          NOT NULL,
    empresa_id       BIGINT        NOT NULL,
    numero_operacion BIGINT        NOT NULL,
    ejercicio        INTEGER       NOT NULL,
    vencimiento_id   UUID          NOT NULL,
    fecha            DATE          NOT NULL,
    importe          NUMERIC(18,4) NOT NULL,
    cuenta_tesoreria VARCHAR(20)   NOT NULL,
    journal_entry_id UUID,
    created_by       VARCHAR(120),
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT pk_cobro_pago PRIMARY KEY (id),
    CONSTRAINT uq_cobro_pago_empresa_id UNIQUE (empresa_id, id),
    -- Correlatividad de cobros sin huecos por (empresa, ejercicio). El numero lo
    -- asigna el servicio con un SELECT ... FOR UPDATE sobre la fila de secuencia de
    -- `cobro_pago`; este UNIQUE es la red por si dos peticiones lo pidieran a la vez.
    CONSTRAINT uq_cobro_pago_numero UNIQUE (empresa_id, ejercicio, numero_operacion),
    CONSTRAINT ck_cobro_pago_importe_positive CHECK (importe > 0)
);

CREATE INDEX IF NOT EXISTS ix_cobro_pago_empresa_id     ON cobro_pago (empresa_id);
CREATE INDEX IF NOT EXISTS ix_cobro_pago_vencimiento_id ON cobro_pago (vencimiento_id);
