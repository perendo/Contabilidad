-- Grupo 5 de las 27 · Informes anuales y libros de IVA: 7 tablas.
--
-- SPEC-010 (cuentas anuales) + SPEC-012 (libros de IVA, modelos fiscales, criterio de
-- caja y SII). La ultima de las 27.
--
-- Ninguna ha tenido migracion. Ademas de sus endpoints, **los resumenes de navegacion
-- las leian**: `services/navigation/resumenes.py` consulta `periodo_fiscal` y
-- `formulacion_cuentas_anuales` para pintar los paneles de superficie, asi que
-- `GET /api/v1/resumenes/{superficie}` tampoco podia funcionar. Eso explica que algunos
-- paneles se vieran incompletos sin que se notara el motivo.
--
-- **Dos enums que hay que mirar**, y que son la razon de que este fichero tenga mas
-- comentarios de los que le tocarian:
--
-- - `estado_periodo_fiscal` y `estado_exportacion_modelo` estan **renombrados** a proposito.
--   `estado_periodo` ya lo usa `periodo_cerrado` (019, SPEC-028) con los valores
--   'abierto', 'cerrado', 'reabierto_ajuste', 'cerrado_ajustado', y
--   `estado_exportacion` lo usa `exportacion` (020, SPEC-029) con 'en_proceso', 'lista',
--   'fallida'. En PostgreSQL un tipo se define una vez, asi que las de aqui no pueden
--   llamarse igual. Se renombraron en el modelo (`periodo_fiscal.py`,
--   `exportacion_modelo.py`); guard en `tests/unit/test_enums_orm.py`. En SQLite no hay
--   ENUM y las 31 specs pasaron sin notarlo.
--
-- - `tipo_periodo` SI se reutiliza, sin renombrar: lo crean 019_cierres.sql con
--   ('MES', 'TRIMESTRE') y `periodo_fiscal` quiere los mismos dos valores. El orden en
--   que el modelo los declara es ('TRIMESTRE', 'MES'), pero el orden de un enum solo
--   afecta a `ORDER BY` y el modelo manda el valor por texto.
--
-- `configuracion_sii` esta **duplicada** con la `ConfigSii` de SPEC-029 (`020_export.sql`,
-- tabla `config_sii`), que si esta migrada. Son dos configuraciones de lo mismo en dos
-- specs distintas; se migra la de aqui tal cual porque el codigo de SPEC-012 la lee, y la
-- duplicidad queda declarada como deuda de diseño, no como deuda de esquema.
--
-- `configuracion_sii` tiene la `empresa_id` como clave primaria y no tiene `id`. Es la
-- unica tabla del grupo con esa forma: es una fila por empresa, no un historico.
--
-- Idempotente: se puede reaplicar sin efecto.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'informe_tipo') THEN
        CREATE TYPE informe_tipo AS ENUM ('BALANCE', 'PYG', 'EFE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'actividad_efe') THEN
        CREATE TYPE actividad_efe AS ENUM ('operativa', 'inversion', 'financiacion');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'formulacion_estado') THEN
        CREATE TYPE formulacion_estado AS ENUM ('formulada', 'anulada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'modelo_fiscal') THEN
        CREATE TYPE modelo_fiscal AS ENUM ('m303', 'm347', 'm349');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_diferido') THEN
        CREATE TYPE estado_diferido AS ENUM ('diferido', 'liquidado');
    END IF;
    -- Los dos renombrados. Los nombres viejos estan en uso por 019 y 020, asi que
    -- declararlos aqui con esos nombres seria un `CREATE TYPE` sobre un tipo que ya
    -- existe con OTROS valores: o falla, o (si se reaplicase) la columna acabaria
    -- guardando valores que su enumerado no conoce.
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_periodo_fiscal') THEN
        CREATE TYPE estado_periodo_fiscal AS ENUM (
            'pendiente', 'libros_generados', 'calculado_303', 'exportado'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_exportacion_modelo') THEN
        CREATE TYPE estado_exportacion_modelo AS ENUM ('generado', 'regenerado', 'anulado');
    END IF;
    -- `tipo_periodo` NO se crea: lo crea 019_cierres.sql. Se declara solo para que este
    -- fichero no dependa del orden de aplicacion.
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_periodo') THEN
        CREATE TYPE tipo_periodo AS ENUM ('MES', 'TRIMESTRE');
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- configuracion_informe
-- ---------------------------------------------------------------------------
--
-- Como se agrupan las cuentas en cada informe. Sin estas reglas, `agrupacion.py` cae
-- en "Otros" para todo lo que no este declarado aqui, y el balance sale corto sin que
-- nada avise.

CREATE TABLE IF NOT EXISTS configuracion_informe (
    id                 UUID            NOT NULL,
    empresa_id         BIGINT          NOT NULL,
    ejercicio          INTEGER         NOT NULL,
    informe_tipo       informe_tipo    NOT NULL,
    agrupacion_codigo  VARCHAR(20)     NOT NULL,
    agrupacion_nombre  VARCHAR(120)    NOT NULL,
    cuenta_ini         VARCHAR(20)     NOT NULL,
    cuenta_fin         VARCHAR(20),
    actividad_efe      actividad_efe,
    orden              INTEGER         NOT NULL DEFAULT 0,
    creado_por         VARCHAR(120),
    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT pk_configuracion_informe PRIMARY KEY (id),
    CONSTRAINT uq_config_informe_tenant_id UNIQUE (empresa_id, id),
    -- Una empresa no puede tener dos reglas que emparecen en el mismo informe, ejercicio
    -- y cuenta de inicio: la resolucion coge la primera y la otra no se aplicaria nunca,
    -- sin ningun aviso.
    CONSTRAINT uq_config_informe_regla
        UNIQUE (empresa_id, ejercicio, informe_tipo, agrupacion_codigo, cuenta_ini)
);

CREATE INDEX IF NOT EXISTS ix_configuracion_informe_empresa_id
    ON configuracion_informe (empresa_id);


-- ---------------------------------------------------------------------------
-- formulacion_cuentas_anuales
-- ---------------------------------------------------------------------------
--
-- El snapshot de unas cuentas anuales ya formuladas. Es la constitution II aplicada a un
-- informe: lo formulado no se modifica, se anula y se vuelve a formular. `snapshot`
-- lleva el contenido integro y `contenido_hash` su SHA-256, para poder demostrar que lo
-- que se consulto es lo que se formulo.

CREATE TABLE IF NOT EXISTS formulacion_cuentas_anuales (
    id                 UUID               NOT NULL,
    empresa_id         BIGINT             NOT NULL,
    ejercicio          INTEGER            NOT NULL,
    numero_formulacion BIGINT             NOT NULL,
    fecha_formulacion  TIMESTAMPTZ        NOT NULL,
    usuario_id         VARCHAR(120),
    contenido_hash     VARCHAR(64)        NOT NULL,
    estado             formulacion_estado NOT NULL DEFAULT 'formulada',
    motivo_anulacion   VARCHAR(255),
    anulada_por        VARCHAR(120),
    anulada_en         TIMESTAMPTZ,
    snapshot           JSONB              NOT NULL,
    observaciones      VARCHAR(255),
    created_at         TIMESTAMPTZ        NOT NULL DEFAULT now(),
    CONSTRAINT pk_formulacion_cuentas_anuales PRIMARY KEY (id),
    CONSTRAINT uq_formulacion_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_formulacion_numero UNIQUE (empresa_id, ejercicio, numero_formulacion)
);

CREATE INDEX IF NOT EXISTS ix_formulacion_cuentas_anuales_empresa_id
    ON formulacion_cuentas_anuales (empresa_id);
CREATE INDEX IF NOT EXISTS ix_formulacion_cuentas_anuales_ejercicio
    ON formulacion_cuentas_anuales (ejercicio);


-- ---------------------------------------------------------------------------
-- clasificacion_efe
-- ---------------------------------------------------------------------------
--
-- El ajuste manual de la linea de un movimiento al bloque del estado de flujos de
-- efectivo que le corresponde. `services/reporting/efe.py` la genera por contrapartida y
-- esta tabla es la correccion humana. `linea_id` NO declara FK (queda en
-- REFERENCIAS_SIN_FK): apunta a `journal_entry_line`, que la crea 003, y la correccion
-- debe poder sobrevivir a un borrado que en la base esta protegido.
--
-- `actividad_efe` es un tipo propio, distinto del `linea_efe_bloque` de 018, con los
-- mismos tres valores. No se comparten: mezclar los dos haria que un cambio en el uno
-- obligase a migrar el otro.

CREATE TABLE IF NOT EXISTS clasificacion_efe (
    id         UUID           NOT NULL,
    empresa_id BIGINT         NOT NULL,
    ejercicio  INTEGER        NOT NULL,
    linea_id   UUID           NOT NULL,
    actividad  actividad_efe  NOT NULL,
    motivo     VARCHAR(255),
    creado_por VARCHAR(120),
    created_at TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT pk_clasificacion_efe PRIMARY KEY (id),
    CONSTRAINT uq_clasificacion_efe_tenant_id UNIQUE (empresa_id, id),
    -- Una correccion por linea y ejercicio: la segunda sobre la misma linea no tendria
    -- sentido, y el EFE usaria la que encontrase.
    CONSTRAINT uq_clasificacion_efe_linea UNIQUE (empresa_id, ejercicio, linea_id)
);

CREATE INDEX IF NOT EXISTS ix_clasificacion_efe_empresa_id ON clasificacion_efe (empresa_id);
CREATE INDEX IF NOT EXISTS ix_clasificacion_efe_linea_id    ON clasificacion_efe (linea_id);


-- ---------------------------------------------------------------------------
-- periodo_fiscal
-- ---------------------------------------------------------------------------
--
-- El trimestre o mes de IVA, y por donde va. `tipo_periodo` reutiliza el tipo de
-- 019_cierres.sql; `estado` usa `estado_periodo_fiscal`, que es un tipo distinto del
-- `estado_periodo` de cierre por el motivo de la cabecera de este fichero.

CREATE TABLE IF NOT EXISTS periodo_fiscal (
    id              UUID                  NOT NULL,
    empresa_id      BIGINT                NOT NULL,
    ejercicio       INTEGER               NOT NULL,
    tipo_periodo    tipo_periodo          NOT NULL,
    numero_periodo  INTEGER               NOT NULL,
    fecha_inicio    DATE                  NOT NULL,
    fecha_fin       DATE                  NOT NULL,
    estado          estado_periodo_fiscal NOT NULL DEFAULT 'pendiente',
    created_at      TIMESTAMPTZ           NOT NULL DEFAULT now(),
    CONSTRAINT pk_periodo_fiscal PRIMARY KEY (id),
    CONSTRAINT uq_periodo_fiscal_tenant_id UNIQUE (empresa_id, id),
    -- Un trimestre no se abre dos veces para la misma empresa. El ciclo del modelo 303
    -- depende de que haya exactamente uno por trimestre.
    CONSTRAINT uq_periodo_fiscal_numero
        UNIQUE (empresa_id, ejercicio, tipo_periodo, numero_periodo),
    CONSTRAINT chk_periodo_fiscal_rango CHECK (fecha_fin >= fecha_inicio)
);

CREATE INDEX IF NOT EXISTS ix_periodo_fiscal_empresa_id ON periodo_fiscal (empresa_id);
CREATE INDEX IF NOT EXISTS ix_periodo_fiscal_ejercicio   ON periodo_fiscal (ejercicio);


-- ---------------------------------------------------------------------------
-- exportacion_modelo
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS exportacion_modelo (
    id                 UUID                         NOT NULL,
    empresa_id         BIGINT                       NOT NULL,
    ejercicio          INTEGER                      NOT NULL,
    modelo             modelo_fiscal                NOT NULL,
    numero_exportacion BIGINT                       NOT NULL,
    periodo_id         UUID,
    formato            VARCHAR(10)                  NOT NULL DEFAULT 'csv',
    fecha_exportacion  TIMESTAMPTZ                  NOT NULL,
    usuario_id         VARCHAR(120),
    contenido_hash     VARCHAR(64)                  NOT NULL,
    fichero_json       JSONB                        NOT NULL,
    estado             estado_exportacion_modelo    NOT NULL DEFAULT 'generado',
    created_at         TIMESTAMPTZ                  NOT NULL DEFAULT now(),
    CONSTRAINT pk_exportacion_modelo PRIMARY KEY (id),
    CONSTRAINT uq_exportacion_modelo_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_exportacion_modelo_numero
        UNIQUE (empresa_id, ejercicio, modelo, numero_exportacion)
);

CREATE INDEX IF NOT EXISTS ix_exportacion_modelo_empresa_id ON exportacion_modelo (empresa_id);
CREATE INDEX IF NOT EXISTS ix_exportacion_modelo_ejercicio   ON exportacion_modelo (ejercicio);


-- ---------------------------------------------------------------------------
-- configuracion_sii
-- ---------------------------------------------------------------------------
--
-- La configuracion de SPEC-012. **Duplica** la `config_sii` de SPEC-029, que si esta
-- migrada (020_export.sql) y que si usa la cabecera de la exportacion integral. Se migra
-- esta tal cual porque `services/vat/sii.py` la lee; la duplicidad es deuda de diseño
-- y queda escrita aqui para que no se descubra de nuevo al buscar por que hay dos
-- tablas de configuracion del SII.
--
-- `empresa_id` es la clave primaria: una fila por empresa, sin historico. Por eso es la
-- unica de las siete que no lleva `id`.

CREATE TABLE IF NOT EXISTS configuracion_sii (
    empresa_id           BIGINT      NOT NULL,
    habilitado           BOOLEAN     NOT NULL DEFAULT false,
    obligatorio          BOOLEAN     NOT NULL DEFAULT false,
    identificador_emisor VARCHAR(20),
    endpoint_ejecucion   TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_configuracion_sii PRIMARY KEY (empresa_id)
);


-- ---------------------------------------------------------------------------
-- iva_diferido_caja
-- ---------------------------------------------------------------------------
--
-- El IVA diferido del regimen de criterio de caja: la cuota que se ha devengado pero que
-- no se ha液体ado porque la factura sigue impagada. `factura_id` y `vencimiento_id` no
-- declaran FK (REFERENCIAS_SIN_FK).

CREATE TABLE IF NOT EXISTS iva_diferido_caja (
    id                UUID          NOT NULL,
    empresa_id        BIGINT        NOT NULL,
    factura_id        UUID          NOT NULL,
    vencimiento_id    UUID,
    cuota_diferida    NUMERIC(18,4) NOT NULL,
    fecha_devengo_real DATE,
    estado            estado_diferido NOT NULL DEFAULT 'diferido',
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT pk_iva_diferido_caja PRIMARY KEY (id),
    CONSTRAINT uq_iva_diferido_caja_tenant_id UNIQUE (empresa_id, id),
    -- Una sola cuota diferida por factura: el diferido de una factura es una cifra, y
    -- tenerla partida en varias filas haria que el total dependiera de como se mire.
    CONSTRAINT uq_iva_diferido_caja_factura UNIQUE (empresa_id, factura_id),
    -- El importe diferido no puede ser negativo: un diferido negativo seria un IVA
    -- devuelto dentro del mismo criterio de caja, que no es lo que este modelo guarda.
    CONSTRAINT chk_iva_diferido_no_negativo CHECK (cuota_diferida >= 0)
);

CREATE INDEX IF NOT EXISTS ix_iva_diferido_caja_empresa_id ON iva_diferido_caja (empresa_id);
CREATE INDEX IF NOT EXISTS ix_iva_diferido_caja_factura_id ON iva_diferido_caja (factura_id);
