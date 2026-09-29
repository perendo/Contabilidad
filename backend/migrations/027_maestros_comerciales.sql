-- Grupo 1 de las 27 · Maestros comerciales y facturacion: 5 tablas.
--
-- SPEC-008 (terceros) + SPEC-007 (facturacion), mas el par `factura_linea` que
-- SPEC-024 (retenciones) la amplio despues con la categoria IRPF.
--
-- Estas tablas NUNCA han tenido migracion. Los tests las crean con
-- `Base.metadata.create_all`, que si sabe lo que el ORM declara, asi que en SQLite
-- existen desde siempre. Contra PostgreSQL real no: `GET /api/v1/facturacion/facturas`
-- y los libros de IVA de SPEC-012 (que leen `Factura`) devuelven 500 con
-- `UndefinedTableError`. Es el mismo defecto que cerro la 024 para SPEC-013, y la
-- misma causa: una puerta que compara migraciones *declaradas* no ve un modelo sin
-- migracion. La puerta que si lo ve esta en `tests/integration/test_esquema_completo.py`.
--
-- **Se migra el modelo tal cual.** No se anaden claves foraneas que el ORM no declara
-- (decision del 2026-09-29): `tercero_subcuenta.tercero_id` y `vencimiento.*` quedan
-- como UUID sueltos, anotados en `tests/esquema_deuda.py::REFERENCIAS_SIN_FK`. Lo que si
-- declara el modelo, y por tanto se migra, son las cuatro FKs compuestas de `factura`.
--
-- `direcciones` es `JSONB` y no `JSON` porque las ocho columnas JSON que ya estan
-- migradas en este repositorio son `jsonb` (007, 010, 011, 014, 015), y el modelo declara
-- `JSON` por el motivo que explica `025_prevision_plan_manual.sql`. El comparador de
-- esquema los trata como equivalentes, asi que esto no es una divergencia.
--
-- `tipo_retencion_irpf` NO se crea aqui: lo crea 015_retenciones_irpf.sql (SPEC-024) y
-- `factura_linea` lo comparte con `retencion_periodo`. Se declara igualmente, con la
-- guardia de `pg_type`, para que esta migracion no dependa del orden de aplicacion.
--
-- Idempotente: se puede reaplicar sin efecto.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tercero_subcuenta_tipo') THEN
        CREATE TYPE tercero_subcuenta_tipo AS ENUM ('CLIENTE', 'PROVEEDOR');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'serie_factura_estado') THEN
        CREATE TYPE serie_factura_estado AS ENUM ('activa', 'inactiva');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'factura_tipo') THEN
        CREATE TYPE factura_tipo AS ENUM ('VENTA', 'COMPRA', 'RECTIFICATIVA');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'factura_estado') THEN
        CREATE TYPE factura_estado AS ENUM ('borrador', 'emitida', 'anulada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_retencion_irpf') THEN
        CREATE TYPE tipo_retencion_irpf AS ENUM (
            'IRPF_PROFESIONALES',
            'IRPF_ARRENDAMIENTOS',
            'IRPF_OBRAS',
            'IRPF_OTROS'
        );
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- tercero
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tercero (
    id          UUID         NOT NULL,
    empresa_id  BIGINT       NOT NULL,
    nombre      VARCHAR(200) NOT NULL,
    nif         VARCHAR(20),
    es_cliente  BOOLEAN      NOT NULL DEFAULT false,
    es_proveedor BOOLEAN     NOT NULL DEFAULT false,
    direcciones JSONB,
    telefono    VARCHAR(20),
    correo      VARCHAR(120),
    iban        VARCHAR(34),
    bic         VARCHAR(11),
    banco       VARCHAR(120),
    autofactura BOOLEAN      NOT NULL DEFAULT false,
    activo      BOOLEAN      NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ,
    CONSTRAINT pk_tercero PRIMARY KEY (id),
    -- `UNIQUE (empresa_id, id)` es lo que permite que las FKs compuestas de
    -- `factura` y de la spec 011 apunten a un tercero sin poder colarse de otra
    -- empresa. Es la pieza de constitution III a nivel de esquema.
    CONSTRAINT uq_tercero_empresa_id UNIQUE (empresa_id, id),
    -- El NIF es unico por empresa. Es NULL para terceros sin identificar, y NULL no
    -- colisiona en un UNIQUE normal, de modo que puede haber cuantos se quiera.
    CONSTRAINT uq_tercero_empresa_nif UNIQUE (empresa_id, nif),
    -- Un tercero es cliente, proveedor, o las dos cosas. Sin esto se podrian dar de
    -- alta filas que no son ninguna de las dos y no aparecen en ninguna cartera.
    CONSTRAINT chk_tercero_al_menos_un_rol
        CHECK (es_cliente IS TRUE OR es_proveedor IS TRUE)
);

CREATE INDEX IF NOT EXISTS ix_tercero_empresa_id ON tercero (empresa_id);


-- ---------------------------------------------------------------------------
-- tercero_subcuenta
-- ---------------------------------------------------------------------------
--
-- Sin FK a `tercero`: el modelo declara `tercero_id` como UUID suelto. Ver la nota de
-- cabecera y `REFERENCIAS_SIN_FK`.

CREATE TABLE IF NOT EXISTS tercero_subcuenta (
    id               UUID         NOT NULL,
    empresa_id       BIGINT       NOT NULL,
    tercero_id       UUID         NOT NULL,
    tipo             tercero_subcuenta_tipo NOT NULL,
    cuenta_codigo    VARCHAR(20)  NOT NULL,
    fecha_asignacion DATE         NOT NULL DEFAULT CURRENT_DATE,
    CONSTRAINT pk_tercero_subcuenta PRIMARY KEY (id),
    CONSTRAINT uq_tercero_subcuenta_empresa_id UNIQUE (empresa_id, id),
    -- Un tercero tiene como mucho una subcuenta por rol: no puede tener dos cuentas
    -- de cliente, porque entonces el saldo del tercero no tendria un solo sitio.
    CONSTRAINT uq_tercero_subcuenta_rol UNIQUE (empresa_id, tercero_id, tipo)
);

CREATE INDEX IF NOT EXISTS ix_tercero_subcuenta_empresa_id ON tercero_subcuenta (empresa_id);
CREATE INDEX IF NOT EXISTS ix_tercero_subcuenta_tercero_id ON tercero_subcuenta (tercero_id);


-- ---------------------------------------------------------------------------
-- serie_factura
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS serie_factura (
    id               UUID         NOT NULL,
    empresa_id       BIGINT       NOT NULL,
    codigo           VARCHAR(10)  NOT NULL,
    nombre           VARCHAR(100) NOT NULL,
    prefijo          VARCHAR(10)  NOT NULL,
    sufijo           VARCHAR(10)  NOT NULL,
    siguiente_numero BIGINT       NOT NULL DEFAULT 0,
    estado           serie_factura_estado NOT NULL DEFAULT 'activa',
    CONSTRAINT pk_serie_factura PRIMARY KEY (id),
    CONSTRAINT uq_serie_factura_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_serie_factura_tenant_codigo UNIQUE (empresa_id, codigo)
);

CREATE INDEX IF NOT EXISTS ix_serie_factura_empresa_id ON serie_factura (empresa_id);


-- ---------------------------------------------------------------------------
-- factura
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS factura (
    id                 UUID         NOT NULL,
    empresa_id         BIGINT       NOT NULL,
    serie_id           UUID         NOT NULL,
    numero             BIGINT,
    ejercicio          INTEGER      NOT NULL,
    fecha              DATE         NOT NULL,
    tipo               factura_tipo NOT NULL,
    tercero_id         UUID         NOT NULL,
    factura_original_id UUID,
    concepto_global    VARCHAR(255),
    importe_base       NUMERIC(18,4) NOT NULL DEFAULT 0,
    importe_iva        NUMERIC(18,4) NOT NULL DEFAULT 0,
    importe_recargo    NUMERIC(18,4) NOT NULL DEFAULT 0,
    importe_irpf       NUMERIC(18,4) NOT NULL DEFAULT 0,
    importe_total      NUMERIC(18,4) NOT NULL DEFAULT 0,
    regimen_caja       BOOLEAN      NOT NULL DEFAULT false,
    iva_devengado      BOOLEAN      NOT NULL DEFAULT true,
    estado             factura_estado NOT NULL DEFAULT 'borrador',
    asiento_id         UUID,
    created_by         VARCHAR(120),
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT pk_factura PRIMARY KEY (id),
    CONSTRAINT uq_factura_tenant_id UNIQUE (empresa_id, id),
    -- Correlatividad sin saltos por (empresa, serie, ejercicio). `numero` es NULL en
    -- los borradores, y NULL no colisiona en un UNIQUE normal, asi que puede haber
    -- cuantos borradores se quiera sin numero. El numero se asigna al emitir, dentro
    -- de un SELECT ... FOR UPDATE sobre `serie_factura` (`next_numero_factura`).
    CONSTRAINT uq_factura_serie_ejercicio_numero
        UNIQUE (empresa_id, serie_id, ejercicio, numero),
    CONSTRAINT fk_factura_serie
        FOREIGN KEY (empresa_id, serie_id)
        REFERENCES serie_factura (empresa_id, id),
    CONSTRAINT fk_factura_tercero
        FOREIGN KEY (empresa_id, tercero_id)
        REFERENCES tercero (empresa_id, id),
    -- Rectificativas: la factura hereda el `tipo` de la original, y por eso la
    -- referencia es COMPUESTA por empresa. Una FK de una sola columna a la PK habria
    -- dejado que una rectificativa de la empresa A encadene con la original de la B.
    CONSTRAINT fk_factura_original
        FOREIGN KEY (empresa_id, factura_original_id)
        REFERENCES factura (empresa_id, id)
);

-- El asiento es la unica FK de aqui que cruza a otra migracion (`003_journal.sql`).
-- Va con `to_regclass` y con la guardia de `pg_constraint` porque `db.migrate` y el
-- fixture `pg_engine` escriben los dos sobre la base de verdad, sin borrar el
-- esquema: un `ADD CONSTRAINT` sin reintento hace que el segundo pase tumbe la
-- migracion entera con `DuplicateObjectError`.
DO $$BEGIN
    IF to_regclass('journal_entry') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_factura_asiento') THEN
        ALTER TABLE factura
            ADD CONSTRAINT fk_factura_asiento
            FOREIGN KEY (empresa_id, asiento_id)
            REFERENCES journal_entry (empresa_id, id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_factura_empresa_id ON factura (empresa_id);
CREATE INDEX IF NOT EXISTS ix_factura_serie_id   ON factura (serie_id);
CREATE INDEX IF NOT EXISTS ix_factura_tercero_id ON factura (tercero_id);


-- ---------------------------------------------------------------------------
-- factura_linea
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS factura_linea (
    id                    UUID          NOT NULL,
    empresa_id            BIGINT        NOT NULL,
    factura_id            UUID          NOT NULL,
    line_no               INTEGER,
    descripcion           VARCHAR(255)  NOT NULL,
    cantidad              NUMERIC(18,4) NOT NULL,
    precio_unitario       NUMERIC(18,4) NOT NULL,
    porcentaje_descuento  NUMERIC(5,2)  NOT NULL DEFAULT 0,
    base                  NUMERIC(18,4) NOT NULL DEFAULT 0,
    tipo_iva              NUMERIC(5,2)  NOT NULL DEFAULT 0,
    cuota_iva             NUMERIC(18,4) NOT NULL DEFAULT 0,
    tipo_recargo          NUMERIC(5,2)  NOT NULL DEFAULT 0,
    cuota_recargo         NUMERIC(18,4) NOT NULL DEFAULT 0,
    tipo_irpf             NUMERIC(5,2)  NOT NULL DEFAULT 0,
    base_irpf             NUMERIC(18,4) NOT NULL DEFAULT 0,
    cuota_irpf            NUMERIC(18,4) NOT NULL DEFAULT 0,
    tipo_retencion        tipo_retencion_irpf DEFAULT 'IRPF_OTROS',
    direccion_inmueble    VARCHAR(200),
    CONSTRAINT pk_factura_linea PRIMARY KEY (id),
    CONSTRAINT uq_factura_linea_tenant_id UNIQUE (empresa_id, id),
    -- Una linea con cantidad o precio cero no es una linea, es un resto del
    -- redondeo, y las tres se comprueban en el servicio tambien. Aqui esta el
    -- punto mas cercano a la persistencia, que es donde la constitucion I quiere
    -- la validacion.
    CONSTRAINT chk_factura_linea_cantidad  CHECK (cantidad > 0),
    CONSTRAINT chk_factura_linea_precio    CHECK (precio_unitario > 0),
    CONSTRAINT chk_factura_linea_descuento CHECK (porcentaje_descuento BETWEEN 0 AND 100),
    CONSTRAINT fk_factura_linea_factura
        FOREIGN KEY (empresa_id, factura_id)
        REFERENCES factura (empresa_id, id)
);

CREATE INDEX IF NOT EXISTS ix_factura_linea_empresa_id ON factura_linea (empresa_id);
CREATE INDEX IF NOT EXISTS ix_factura_linea_factura_id ON factura_linea (factura_id);
