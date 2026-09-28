-- Seed de demostración inicial: Empresa Demo, Usuario Admin y Ejercicio 2026
-- Permite que la aplicación arranque lista para interactuar desde el primer minuto.

DO $$
DECLARE
    v_user_id BIGINT;
    v_company_id BIGINT;
BEGIN
    -- 1. Crear Empresa Demo si no existe
    IF NOT EXISTS (SELECT 1 FROM companies WHERE nif = 'B12345678') THEN
        INSERT INTO companies (nif, razon_social, is_active)
        VALUES ('B12345678', 'Empresa Demo S.L.', TRUE)
        RETURNING company_id INTO v_company_id;
    ELSE
        SELECT company_id INTO v_company_id FROM companies WHERE nif = 'B12345678' LIMIT 1;
    END IF;

    -- 2. Crear Usuario Administrador si no existe (password: admin123)
    -- Hash bcrypt standard de 'admin123' con cost 12
    IF NOT EXISTS (SELECT 1 FROM users WHERE email = 'admin@contabilidad.es') THEN
        INSERT INTO users (email, password_hash, full_name, is_active)
        VALUES ('admin@contabilidad.es', '$2b$12$e80yqVpL29wU72dG81F54.ZkVhK2vE71H7s1HqUo6Rz1tq8M9dD8K', 'Administrador Demo', TRUE)
        RETURNING id INTO v_user_id;
    ELSE
        SELECT id INTO v_user_id FROM users WHERE email = 'admin@contabilidad.es' LIMIT 1;
    END IF;

    -- 3. Vincular Usuario con la Empresa Demo como ADMIN y por defecto
    IF NOT EXISTS (SELECT 1 FROM user_companies WHERE user_id = v_user_id AND company_id = v_company_id) THEN
        INSERT INTO user_companies (user_id, company_id, role, is_default, is_active)
        VALUES (v_user_id, v_company_id, 'ADMIN', TRUE, TRUE);
    ELSE
        UPDATE user_companies
        SET is_default = TRUE, is_active = TRUE, role = 'ADMIN'
        WHERE user_id = v_user_id AND company_id = v_company_id;
    END IF;

    -- 4. Crear Ejercicio Contable 2026 abierto en ejercicio_contable
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ejercicio_contable') THEN
        IF NOT EXISTS (SELECT 1 FROM ejercicio_contable WHERE empresa_id = v_company_id AND ejercicio = 2026) THEN
            INSERT INTO ejercicio_contable (id, empresa_id, ejercicio, fecha_inicio, fecha_fin, estado, created_by)
            VALUES (gen_random_uuid(), v_company_id, 2026, '2026-01-01', '2026-12-31', 'abierto', 'seed');
        END IF;
    END IF;

    -- 5. Crear FiscalYear 2026 en fiscal_year
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'fiscal_year') THEN
        IF NOT EXISTS (SELECT 1 FROM fiscal_year WHERE empresa_id = v_company_id AND year = 2026) THEN
            INSERT INTO fiscal_year (empresa_id, year, date_start, date_end, is_closed)
            VALUES (v_company_id, 2026, '2026-01-01', '2026-12-31', FALSE);
        END IF;
    END IF;

END $$;
