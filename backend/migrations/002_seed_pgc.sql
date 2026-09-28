-- ============================================================
--  002_seed_pgc.sql
--  Seeding automático del catálogo base del PGC por tenant (SPEC-001 T008,
--  plan.md raíz §4). Idempotente y en la misma transacción ACID que el alta
--  de la empresa (trigger trg_companies_seed).
--
--  Dependencias: account_plan (001), audit_log (000) y companies (004).
--  El runner aplica 004 antes que 002 por la FK/trigger sobre companies.
--
--  Adaptación: `audit_log` en este repositorio usa `empresa_id`/`usuario`/
--  `operacion`/`entidad`/`payload TEXT` (modelo audit_log.py), no las
--  columnas `tenant_id`/`actor`/`action`/`entity` del plan raíz.
-- ============================================================

CREATE OR REPLACE FUNCTION seed_default_pgc(p_tenant_id BIGINT)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM account_plan
               WHERE tenant_id = p_tenant_id AND level = 1) THEN
        RAISE NOTICE 'seed_default_pgc: plan ya existe para tenant %', p_tenant_id;
        RETURN;
    END IF;

    INSERT INTO account_plan (tenant_id, code, level, name)
    VALUES
        (p_tenant_id, '1', 1, 'Financiación básica'),
        (p_tenant_id, '2', 1, 'Inmovilizado'),
        (p_tenant_id, '3', 1, 'Existencias'),
        (p_tenant_id, '4', 1, 'Acreedores y deudores por operaciones comerciales'),
        (p_tenant_id, '5', 1, 'Cuentas financieras'),
        (p_tenant_id, '6', 1, 'Compras y gastos'),
        (p_tenant_id, '7', 1, 'Ventas e ingresos');

    INSERT INTO account_plan (tenant_id, code, level, name, parent_id)
    SELECT p_tenant_id, s.code, 2, s.name,
           (SELECT a.id FROM account_plan a
             WHERE a.tenant_id = p_tenant_id
               AND a.code = left(s.code, 1)
               AND a.level = 1)
    FROM (VALUES
        ('10','Capital'), ('11','Reservas y resultados'),
        ('12','Resultados'), ('13','Subvenciones y donaciones'),
        ('16','Deudas a largo plazo'), ('17','Deudas a largo plazo con entidades de crédito'),
        ('20','Inmovilizaciones intangibles'), ('21','Inmovilizaciones materiales'),
        ('25','Inversiones financieras a largo plazo'), ('28','Amortización acumulada'),
        ('30','Existencias: mercaderías'), ('32','Otros aprovisionamientos'),
        ('40','Proveedores'),
        ('41','Acreedores varios'), ('43','Clientes'),
        ('46','H.P. acreedora por conceptos fiscales'), ('47','H.P. deudora por conceptos fiscales'),
        ('57','Tesorería'), ('58','Caja'),
        ('60','Compras'), ('62','Servicios exteriores'),
        ('63','Impuestos sobre beneficios'),
        ('64','Gastos de personal'), ('66','Gastos financieros'),
        ('68','Amortización del inmovilizado'),
        ('70','Ventas de mercaderías'), ('75','Otros ingresos de gestión'),
        ('77','Subvenciones, donaciones y legados de explotación'),
        ('79','Excesos y aplicaciones de provisiones y de pérdidas por deterioro')
    ) AS s(code, name);

    INSERT INTO account_plan (tenant_id, code, level, name, parent_id)
    SELECT p_tenant_id, c.code, 3, c.name,
           (SELECT a.id FROM account_plan a
             WHERE a.tenant_id = p_tenant_id
               AND a.code = left(c.code, 2)
               AND a.level = 2)
    FROM (VALUES
        ('100','Capital social'), ('111','Patrimonio neto'),
        ('132','Subvenciones oficiales de capital'), ('160','Deudas a largo plazo'),
        ('210','Terrenos y bienes naturales'), ('250','Inversiones financieras a LP'),
        ('281','Amortización acumulada del inmovilizado material'),
        ('300','Mercaderías'), ('325','Mercaderías en tránsito'),
        ('400','Proveedores'), ('410','Acreedores por prestaciones de servicios'),
        ('430','Clientes'), ('470','H.P. deudora por IVA'),
        ('473','H.P. deudora por Impuesto sobre Sociedades'),
        ('475','H.P. acreedora por conceptos fiscales'),
        ('570','Caja'), ('572','Bancos c/c'), ('600','Compras de mercaderías'),
        ('621','Arrendamientos y cánones'), ('630','Impuesto sobre beneficios'),
        ('640','Sueldos y salarios'),
        ('662','Intereses de deudas'), ('681','Amortización del inmovilizado material'),
        ('700','Venta de mercaderías'), ('790','Reversión del deterioro de existencias')
    ) AS c(code, name);

    INSERT INTO account_plan (tenant_id, code, level, name, parent_id, is_selectable)
    SELECT p_tenant_id, sc.code, 4, sc.name,
           (SELECT a.id FROM account_plan a
             WHERE a.tenant_id = p_tenant_id AND a.code = sc.parent_code AND a.level = 3),
           TRUE
    FROM (VALUES
        ('1110','Patrimonio neto c/p', '111'), ('1320','Subvenciones oficiales de capital c/p', '132'),
        ('2100','Terrenos', '210'), ('2500','Inversiones financieras a LP en capital', '250'),
        ('2810','A.A. inmovilizado material', '281'),
        ('3000','Mercaderías', '300'), ('4000','Proveedores (euros)', '400'),
        ('4100','Acreedores por prestaciones de servicios', '410'),
        ('4300','Clientes (euros)', '430'), ('4700','H.P. deudora por IVA soportado', '470'),
        ('4709','H.P. acreedora por devoluciones', '470'),
        ('4730','H.P. deudora por Impuesto sobre Sociedades', '473'),
        ('4751','H.P. acreedora por retenciones e ingresos a cuenta', '475'),
        ('4752','H.P. acreedora por retenciones e ingresos a cuenta', '475'),
        ('5720','Bancos c/c vista euros', '572'), ('6000','Compras de mercaderías', '600'),
        ('6210','Arrendamientos', '621'),
        ('6300','Impuesto sobre beneficios. Autoliquidacion', '630'),
        ('6400','Sueldos y salarios', '640'),
        ('6810','Amortización del inmovilizado material', '681'),
        ('7000','Venta de mercaderías', '700')
    ) AS sc(code, name, parent_code);

    INSERT INTO audit_log (empresa_id, usuario, operacion, entidad, entidad_id, ip, payload)
    VALUES (p_tenant_id, 'system', 'SEED_PGC', 'account_plan', NULL, NULL,
            jsonb_build_object(
                'groups', 7, 'subgroups', 29, 'accounts', 25, 'subaccounts', 21
            )::text);
END;
$$;

CREATE OR REPLACE FUNCTION trg_companies_seed() RETURNS trigger AS $$
BEGIN
    PERFORM seed_default_pgc(NEW.company_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_companies_seed ON companies;
CREATE TRIGGER trg_companies_seed AFTER INSERT ON companies
    FOR EACH ROW EXECUTE FUNCTION trg_companies_seed();
