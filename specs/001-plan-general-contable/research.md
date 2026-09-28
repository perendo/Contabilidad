# Research: Plan General Contable (SPEC-001)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan técnico raíz (`H:\ContabilidadV1\plan.md`, autoritativo para SPEC-001).

## D1. Fuente de verdad técnica del modelado del plan de cuentas

- **Decision**: Adoptar el **`plan.md` raíz del repositorio** como fuente autoritativa: tabla `account_plan`, columna `tenant_id`, PK `(tenant_id, id)`, `UNIQUE (tenant_id, code)`, `UNIQUE (tenant_id, name)`, jerarquía por `parent_id` y triggers. Los artefactos de esta feature (`data-model.md`, `contracts/`, `tasks.md`) se alinean 1:1 con él y **no lo reescriben**.
- **Rationale**: El plan raíz ya resuelve las reglas estructurales del PGC (nivel = longitud de código, profundidad ≤ 5, hojas apuntables, prefijo jerárquico, seed y triggers) y mantiene coherencia con `constitution.md` v1.0.0. Reescribirlo en artefactos duplicados arriesgaría divergencias.
- **Alternatives considered**: Modelo propio `cuentas` con `empresa_id` y campos redundantes de nivel (rompe el naming y el diseño ya aprobado); reescribir el DDL en cada artefacto (duplicación de fuente de verdad).

## D2. Jerarquía de 5 niveles por longitud del código

- **Decision**: El **nivel se deriva de la longitud del código**: nivel 1-4 exige `level == length(code)`; el nivel 5 admite códigos de **5 a 8 dígitos** (subcuentas auxiliares). Nunca más de 8 dígitos. El código de una hija hereda el prefijo del padre (`'43000001'` cuelga de `'4300'`).
- **Rationale**: Es el criterio oficial del PGC (grupo/subgrupo/cuenta/subcuenta/subcuenta auxiliar) y permite validar la jerarquía con una única regla aritmética en base de datos.
- **Alternatives considered**: Nivel explícito sin correlación con el código (permite jerarquías inconsistentes); nivel máximo fijo de 5 dígitos (impide auxiliares de 8 dígitos frecuentes en la práctica).

## D3. Regla de apuntabilidad (`is_selectable`)

- **Decision**: `is_selectable = true` **solo en cuentas de último nivel de su rama (sin hijas) y nivel ≥ 4** (subcuentas). Grupos/subgrupos/cuentas de 1-3 dígitos y cualquier cuenta con descendencia son `is_selectable = false`. El mantenimiento es automático por trigger al insertar/actualizar `parent_id`.
- **Rationale**: Concreta FR-005 (hojas apuntables) del plan raíz §1.3: impide asientos sobre cuentas de cargo de 1-3 dígitos (430), habilitando solo imputaciones sobre subcuentas (4300) y auxiliares.
- **Alternatives considered**: Toda hoja apuntable (permitiría apuntes a cuentas de cargo → contabilidad inválida); apuntabilidad por flag manual (viola SC-005).

## D4. Seeding automático por tenant

- **Decision**: Función `seed_default_pgc(p_tenant_id)` que siembra los **7 grupos**, subgrupos/cuentas representativas y subcuentas de 4 dígitos apuntables; **idempotente** (si el tenant ya tiene nivel 1, omite); invocada por **trigger `trg_companies_seed` (AFTER INSERT ON companies)** y, de forma equivalente, desde el **servicio de alta de empresa** dentro del mismo `async with async_session.begin()` (SPEC-003). Registra entrada `SEED_PGC` en `audit_log` con actor `system` en la misma transacción.
- **Rationale**: El plan raíz amplía la spec (seeding automático por tenant como requisito del usuario) manteniendo la atomicidad: si el seed falla, la creación de la empresa se revierte completa.
- **Alternatives considered**: Seed vía CLI independiente (rompe la atomicidad con la creación de empresa); seed perezoso en primera consulta (añade latencia y bloqueos de carrera).

## D5. Validación estructural en el punto de persistencia

- **Decision**: Trigger `chk_account_plan_structure` (BEFORE INSERT/UPDATE) impone a nivel DB: código solo dígitos, `nivel == longitud` (1-4 / 5-8 en nivel 5), padre de la **misma empresa** con `level = nivel hijo - 1` y `is_active = true`, prefijo del padre y presencia obligatoria de padre para nivel > 1.
- **Rationale**: Constitución I ("más cercano a la persistencia") y III (rechazo a nivel de datos, no solo de aplicación).
- **Alternatives considered**: Solo validación en servicio FastAPI (debilita la garantía frente a inserts directos, migraciones o seeds descuidados).

## D6. Mantenimiento automático de `is_selectable`

- **Decision**: Trigger `sync_account_plan_selectable` (AFTER INSERT/UPDATE OF parent_id): al insertar una hija, la madre pierde su condición de hoja (`is_selectable = false`); la cuenta nueva es apuntable si `level >= 4`. Todo en la misma transacción ACID.
- **Rationale**: La apuntabilidad es un invariante derivado de la estructura; mantenerla por trigger evita estados inconsistentes (SC-005) y no depende de disciplina de aplicación.
- **Alternatives considered**: Recalcular `is_selectable` en cada consulta (coste O(n) e inconsistencia entre peticiones); servicio que actualice en cascada (depende de que el servicio sea llamado siempre).

## D7. Protección de cuentas con asientos asociados

- **Decision**: Trigger `chk_account_plan_protected` (BEFORE UPDATE/DELETE): impide borrar cualquier cuenta con imputaciones (`journal_entry_line`) **o con hijas**, e impide desactivar (`is_active true → false`) cuentas con asientos asociados. La API **no expone DELETE**; la restricción es defensiva a nivel de datos.
- **Rationale**: Constitución II (inmutabilidad de lo imputado) aplicada al catálogo; SC-004 exige bloqueo del 100 % de los intentos.
- **Alternatives considered**: Soft-delete con flag `deleted_at` (complica correlatos e historia); bloqueo solo en API (no protege la base).

## D8. Autocompletar por código o nombre (< 1 s, SC-002)

- **Decision**: Índice **`pg_trgm` GIN sobre `name`** (búsqueda por fragmento) + consulta que también matchea **prefijo de `code`**, siempre filtrando `tenant_id` activo, `is_selectable = true` y `is_active = true`, con `LIMIT` razonable. El endpoint `suggest` es el único camino de autocompletar.
- **Rationale**: `ILIKE '%fragmento%'` sobre decenas de miles de cuentas sin índice rompe el SLA de 1 s; `pg_trgm` da coincidencias por subcadena con coste indexado.
- **Alternatives considered**: Índice B-tree clásico solo por prefijo (no cubre fragmentos intermedios); búsqueda en frontend tras descargar todo el árbol (rompe aislamiento de datos y escala).

## D9. Recuperación del árbol en una sola consulta

- **Decision**: Endpoint `GET /api/v1/accounts/tree` obtiene **todos los nodos de la empresa activa en una única consulta** (filtro `tenant_id`, orden por `code`) y construye el árbol anidado en Python (máximo 5 niveles). Sin N+1.
- **Rationale**: Un plan de cuentas por empresa es un dataset acotado (centenares a millares de nodos); el N+1 por nodo degradaría el rendimiento y el `LIMIT` no es aplicable a un árbol.
- **Alternatives considered**: Recursive CTE en PostgreSQL (se guarda como alternativa equivalente cuando el árbol supere ~10k nodos); consulta recursiva por nivel (N consultas, peor latencia).

## D10. Auditoría y serialización con precisión decimal

- **Decision**: Cada escritura del plan (seed, alta, edición, desactivación) inserta su fila en `audit_log` **dentro de la misma transacción ACID** con actor, `TIMESTAMPTZ` UTC, IP y `payload` JSONB. El `payload` serializa cualquier importe como **cadena Decimal** (`Decimal → str`), nunca `float`.
- **Rationale**: Constitución (auditoría inmutable en la misma transacción; prohibido `float`); el plan de cuentas no contiene importes, pero el patrón se hereda a SPEC-002.
- **Alternatives considered**: Auditoría asíncrona fuera de la transacción (pierde la atomicidad exigida); payload con números flotantes (prohibido).

## D11. Stack e integración

- **Decision**: Backend **FastAPI async + SQLAlchemy 2.x async + asyncpg** en `services/acct`; frontend Next.js (App Router) con árbol y combobox teclado consumiendo los endpoints; la empresa activa viaja en la cabecera de sesión y el backend la deriva exclusivamente del contexto autenticado (nunca de los datos del cliente).
- **Rationale**: Coherencia con la constitución y el plan raíz; la validación de apuntabilidad en UI es solo informativa.
- **Alternatives considered**: Lógica de negocio en frontend (excluye validaciones obligatorias de backend/DB); modelo ORM sin DDL gestionado (pierde triggers de integridad).