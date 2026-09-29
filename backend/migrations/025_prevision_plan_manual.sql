-- SPEC-027 · Previsión de tesorería: la columna `plan_manual` que faltaba.
--
-- CONTEXTO. Cuando SPEC-027 hizo que el plan manual de una previsión se conservara
-- al regenerarla con otro rango (para que un pago mensual siguiera cubriendo los
-- meses nuevos y una reprogramacion por alerta de liquidez no se perdiera), se
-- anadio `plan_manual` al MODELO. La migracion `018_cashflow.sql` **ya estaba
-- aplicada** para entonces, y nunca se le hizo un `ALTER TABLE`.
--
-- Por eso no se vio: los tests construyen el esquema con `create_all` desde el
-- modelo, y ahi la columna si existe. Contra la base de verdad, cualquier consulta
-- a `prevision_tesoreria` falla:
--
--     UndefinedColumnError: no existe la columna prevision_tesoreria.plan_manual
--
-- Es decir, la superficie de prevision de tesoreria estaba rota en la aplicacion
-- real, en una tabla que si tiene migracion. Y es una clase de defecto que
-- `test_toda_tabla_del_orm_tiene_migracion` NO puede ver: ese guard cruza nombres
-- de tabla, no de columna.
--
-- Lo encontro `db/esquema.py`, que compara los metadatos de los modelos contra la
-- base interrogndola de verdad. Ver AGENTS.md.
--
-- IDEMPOTENCIA. `ADD COLUMN IF NOT EXISTS` es la forma correcta y la mas simple:
-- `db.migrate` reaplica los ficheros ya aplicados, y el fixture `pg_engine` de los
-- tests de PostgreSQL aplica sobre la base de verdad sin borrar el esquema. Los dos
-- escriben encima. Una migracion que noTolere su propia segunda ejecucion tumba
-- todas las siguientes (leccion de AGENTS.md 50).
--
-- TIPO. `JSONB` y no `JSON` porque las ocho columnas JSON de este repositorio son
-- `jsonb` en las seis migraciones que las crean, y el modelo declaraba `JSON` por
-- inercia. Aqui se alinea el modelo con la convencion en vez de al reves.

ALTER TABLE prevision_tesoreria
    ADD COLUMN IF NOT EXISTS plan_manual JSONB;

COMMENT ON COLUMN prevision_tesoreria.plan_manual IS
    'Definiciones manuales del plan (pago recurrente / cobro estimado) declaradas por el '
    'usuario. Es la definicion, no su recorte temporal: al regenerar con otro rango se '
    're-expande desde aqui, de modo que un pago mensual siga cubriendo los meses nuevos '
    'y una reprogramacion por alerta de liquidez se conserve.';
