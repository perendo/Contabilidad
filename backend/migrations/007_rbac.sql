-- ============================================================
--  007_rbac.sql
--  Matriz de permisos por rol (SPEC-015): catálogo global de operaciones,
--  roles por empresa, matriz de concesiones y log de auditoría de accesos
--  (inmutable). Idempotente. Alineado con backend/src/models/rbac/*.py.
--
--  Equivalente a los seeds de services/security/catalogo.py y al trigger
--  SQLite trg_companies_rbac_seed de db/triggers.py: la creación de una
--  empresa siembra catálogo + roles base + matriz por defecto.
--
--  `evento_auditoria_acceso` es WORM (constitución II): solo INSERT.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'permiso_operacion_tipo') THEN
        CREATE TYPE permiso_operacion_tipo AS ENUM (
            'ver', 'crear', 'editar', 'aprobar',
            'importar_exportar', 'configurar', 'baja', 'cerrar'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'resultado_acceso') THEN
        CREATE TYPE resultado_acceso AS ENUM ('allow', 'deny');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'motivo_acceso') THEN
        CREATE TYPE motivo_acceso AS ENUM (
            'sin_permiso', 'sin_rol', 'operacion_inexistente',
            'sin_empresa', 'concedido'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS permiso_operacion (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    modulo                     VARCHAR(40) NOT NULL,
    operacion                  permiso_operacion_tipo NOT NULL,
    descripcion                VARCHAR(255) NOT NULL,
    requiere_datos_contables   BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_permiso_operacion_modulo_operacion UNIQUE (modulo, operacion)
);

CREATE INDEX IF NOT EXISTS ix_permiso_operacion_modulo
    ON permiso_operacion (modulo);

CREATE TABLE IF NOT EXISTS roles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      BIGINT NOT NULL,
    nombre          VARCHAR(40) NOT NULL,
    es_global_flag  BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_roles_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_roles_tenant_nombre UNIQUE (empresa_id, nombre),
    CONSTRAINT fk_roles_empresa
        FOREIGN KEY (empresa_id) REFERENCES companies (company_id)
);

CREATE INDEX IF NOT EXISTS ix_roles_empresa_id
    ON roles (empresa_id);

CREATE TABLE IF NOT EXISTS matriz_permiso (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id   BIGINT NOT NULL,
    rol_id       UUID NOT NULL,
    permiso_id   UUID NOT NULL,
    concesion_id UUID,
    CONSTRAINT uq_matriz_permiso_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT uq_matriz_permiso_rol_permiso UNIQUE (empresa_id, rol_id, permiso_id),
    CONSTRAINT fk_matriz_permiso_rol
        FOREIGN KEY (empresa_id, rol_id) REFERENCES roles (empresa_id, id),
    CONSTRAINT fk_matriz_permiso_operacion
        FOREIGN KEY (permiso_id) REFERENCES permiso_operacion (id)
);

CREATE INDEX IF NOT EXISTS ix_matriz_permiso_empresa_id
    ON matriz_permiso (empresa_id);
CREATE INDEX IF NOT EXISTS ix_matriz_permiso_evaluacion
    ON matriz_permiso (empresa_id, rol_id, permiso_id);

CREATE TABLE IF NOT EXISTS evento_auditoria_acceso (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id    BIGINT NOT NULL,
    usuario_id    BIGINT NOT NULL,
    rol_id        UUID,
    modulo        VARCHAR(40) NOT NULL,
    operacion     VARCHAR(40) NOT NULL,
    resultado     resultado_acceso NOT NULL,
    motivo        motivo_acceso NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip            VARCHAR(45),
    payload       JSONB,
    CONSTRAINT uq_evento_acceso_tenant_id UNIQUE (empresa_id, id),
    CONSTRAINT fk_evento_acceso_usuario
        FOREIGN KEY (usuario_id) REFERENCES users (id),
    CONSTRAINT fk_evento_acceso_rol
        FOREIGN KEY (rol_id) REFERENCES roles (id)
);

CREATE INDEX IF NOT EXISTS ix_evento_acceso_empresa_id
    ON evento_auditoria_acceso (empresa_id);
CREATE INDEX IF NOT EXISTS ix_evento_acceso_usuario_id
    ON evento_auditoria_acceso (usuario_id);
CREATE INDEX IF NOT EXISTS ix_evento_acceso_rol_id
    ON evento_auditoria_acceso (rol_id);

CREATE OR REPLACE FUNCTION seed_seguridad_empresa()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_modulos TEXT[] := ARRAY['acct','ar','treasury','bank','inmovilizado',
                              'divisas','reporting','fiscal','invoicing',
                              'centros','ngo','presupuestos','cierres'];
    v_ops     TEXT[] := ARRAY['ver','crear','editar','aprobar',
                              'importar_exportar','configurar','baja','cerrar'];
    -- SPEC-029: modulo propio de la exportacion integral con solo las tres
    -- operaciones que usa `api/export.py` (ver, crear, configurar). Coincide
    -- con `services.security.catalogo.CATALOGO["export"]` y con el trigger
    -- SQLite de `db/triggers.py`.
    v_mod_export TEXT[] := ARRAY['export'];
    v_ops_export TEXT[] := ARRAY['ver','crear','configurar'];
    m TEXT; o TEXT; r_nombre TEXT;
    v_empresa BIGINT := NEW.company_id;
    v_rol_admin UUID; v_rol_acc UUID; v_rol_ro UUID;
BEGIN
    -- catálogo global (idempotente)
    FOREACH m IN ARRAY v_modulos LOOP
        FOREACH o IN ARRAY v_ops LOOP
            INSERT INTO permiso_operacion (modulo, operacion, descripcion, requiere_datos_contables)
            VALUES (m, o::permiso_operacion_tipo, o || ' ' || m,
                    CASE WHEN o = 'ver' THEN FALSE ELSE TRUE END)
            ON CONFLICT (modulo, operacion) DO NOTHING;
        END LOOP;
    END LOOP;
    FOREACH m IN ARRAY v_mod_export LOOP
        FOREACH o IN ARRAY v_ops_export LOOP
            INSERT INTO permiso_operacion (modulo, operacion, descripcion, requiere_datos_contables)
            VALUES (m, o::permiso_operacion_tipo, o || ' ' || m,
                    CASE WHEN o = 'ver' THEN FALSE ELSE TRUE END)
            ON CONFLICT (modulo, operacion) DO NOTHING;
        END LOOP;
    END LOOP;
    FOREACH o IN ARRAY v_ops LOOP
        IF o IN ('ver', 'configurar') THEN
            INSERT INTO permiso_operacion (modulo, operacion, descripcion, requiere_datos_contables)
            VALUES ('rbac', o::permiso_operacion_tipo, o || ' rbac', FALSE)
            ON CONFLICT (modulo, operacion) DO NOTHING;
        END IF;
    END LOOP;

    -- roles base
    FOREACH r_nombre IN ARRAY ARRAY['ADMIN','ACCOUNTANT','READ_ONLY'] LOOP
        INSERT INTO roles (empresa_id, nombre)
        VALUES (v_empresa, r_nombre)
        ON CONFLICT (empresa_id, nombre) DO NOTHING;
    END LOOP;

    -- matriz por defecto (coincide con _ops_por_rol)
    SELECT id INTO v_rol_admin   FROM roles WHERE empresa_id = v_empresa AND nombre = 'ADMIN';
    SELECT id INTO v_rol_acc     FROM roles WHERE empresa_id = v_empresa AND nombre = 'ACCOUNTANT';
    SELECT id INTO v_rol_ro      FROM roles WHERE empresa_id = v_empresa AND nombre = 'READ_ONLY';

    -- ADMIN: todo
    INSERT INTO matriz_permiso (empresa_id, rol_id, permiso_id)
    SELECT v_empresa, v_rol_admin, p.id FROM permiso_operacion p
    ON CONFLICT (empresa_id, rol_id, permiso_id) DO NOTHING;
    -- Todos los roles: rbac/ver (FR-006)
    INSERT INTO matriz_permiso (empresa_id, rol_id, permiso_id)
    SELECT v_empresa, r.id, p.id
      FROM roles r, permiso_operacion p
     WHERE r.empresa_id = v_empresa AND p.modulo = 'rbac' AND p.operacion = 'ver'
    ON CONFLICT (empresa_id, rol_id, permiso_id) DO NOTHING;
    -- ACCOUNTANT: ver/crear/editar/baja fuera de rbac
    INSERT INTO matriz_permiso (empresa_id, rol_id, permiso_id)
    SELECT v_empresa, v_rol_acc, p.id
      FROM permiso_operacion p
     WHERE p.modulo <> 'rbac' AND p.operacion IN ('ver','crear','editar','baja')
    ON CONFLICT (empresa_id, rol_id, permiso_id) DO NOTHING;
    -- READ_ONLY: ver fuera de rbac
    INSERT INTO matriz_permiso (empresa_id, rol_id, permiso_id)
    SELECT v_empresa, v_rol_ro, p.id
      FROM permiso_operacion p
     WHERE p.modulo <> 'rbac' AND p.operacion = 'ver'
    ON CONFLICT (empresa_id, rol_id, permiso_id) DO NOTHING;

    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_companies_rbac_seed ON companies;
CREATE TRIGGER trg_companies_rbac_seed
    AFTER INSERT ON companies
    FOR EACH ROW
    EXECUTE FUNCTION seed_seguridad_empresa();

CREATE OR REPLACE FUNCTION trg_evento_acceso_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'evento_auditoria_acceso: el log de accesos es inmutable (solo INSERT)';
END
$$;

DROP TRIGGER IF EXISTS trg_evento_acceso_immutable_update ON evento_auditoria_acceso;
CREATE TRIGGER trg_evento_acceso_immutable_update
    BEFORE UPDATE ON evento_auditoria_acceso
    FOR EACH ROW EXECUTE FUNCTION trg_evento_acceso_immutable();

DROP TRIGGER IF EXISTS trg_evento_acceso_immutable_delete ON evento_auditoria_acceso;
CREATE TRIGGER trg_evento_acceso_immutable_delete
    BEFORE DELETE ON evento_auditoria_acceso
    FOR EACH ROW EXECUTE FUNCTION trg_evento_acceso_immutable();