-- El default que le falta a una columna. Una linea, y su propia migracion.
--
-- `manifiesto_exportacion.n_bloques` la crea 020_export.sql (SPEC-029) **sin** valor por
-- defecto, y `models/export/manifiesto.py:64` la declara con `default=0`.
--
-- No rompe nada: SQLAlchemy aplica el valor en el cliente, asi que toda inserccion que
-- haga la aplicacion lleva el 0 y la tabla nunca se queda sin el. Pero modelo y esquema
-- no coinciden, y un `INSERT` escrito a mano contra la tabla fallaria con
-- `null value in column "n_bloques"`.
--
-- No se ha editado 020 para arreglarlo, y esa es la parte importante: **020 ya esta
-- aplicada**, y editarla no la deshace. `db.migrate` la reaplicaria y el
-- `ADD CONSTRAINT` / el `CREATE` reventarian, o la base quedaria en un estado que nadie
-- sabe reconstruir. Una correccion al esquema de algo ya aplicado va en una migracion
-- nueva, por pequena que sea. (Leccion de la seccion 50 de AGENTS.md.)
--
-- Idempotente: `SET DEFAULT` no tiene efecto si ya esta puesto.

ALTER TABLE manifiesto_exportacion
    ALTER COLUMN n_bloques SET DEFAULT 0;
