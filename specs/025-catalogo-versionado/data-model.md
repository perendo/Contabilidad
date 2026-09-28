# Data Model: Catálogo Versionado del Plan de Cuentas (SPEC-025)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003; alias `tenant_id` del `plan.md` raíz SPEC-001) en PK/índices/filtros; se deriva exclusivamente de la sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría (`audit_log`, WORM) en la misma transacción ACID.
- `account_plan` (SPEC-001) NO se modifica: el versionado es aditivo vía las tablas de `catalog/`.

## CatalogoVersion

Cabecera de versión del plan de cuentas con vigencia por empresa, sin solapes.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id) |
| numero_version | BIGINT | correlativo por empresa, asignado atómicamente (constitución IV) |
| codigo | VARCHAR(20) | identificador normativo (p. ej. `PGC-2007`, `PGC-2021`) |
| fecha_inicio | DATE | inicio de vigencia (suele coincidir con el ejercicio) |
| fecha_fin | DATE NULL | fin de vigencia; NULL = vigente sin fin |
| estado | ENUM | `borrador`, `vigente`, `anulada` |
| es_migracion | BOOLEAN | marca importación normativa vs alta manual |
| creado_por / created_at | | auditoría |

**Validaciones** (trigger `trg_catalogo_version_vigencia` + servicio): rechazo de solape de rangos por `empresa_id` (FR-006/SC-004); `numero_version` único por empresa; solo puede haber una versión `vigente` respecto de una fecha (resolución determinista).

**Transiciones de estado**: `borrador → vigente` (activación; valida mapeos completos) | `vigente/borrador → anulada` (trazable; solo si no se han generado reclasificaciones pendientes de apertura).

## CatalogoCuenta

Proyección de membresía y estado de cada cuenta del catálogo canónico en una versión.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| version_id | UUID FK → CatalogoVersion | |
| account_id | UUID FK → account_plan (SPEC-001) | FK compuesta (empresa_id, account_id) |
| codigo_version | VARCHAR(8) | código vigente en esta versión (puede diferir del canónico por renombrado) |
| nombre_version | VARCHAR(200) | nombre vigente en esta versión |
| estado | ENUM | `igual`, `nueva`, `renombrada`, `suprimida` |
| parent_version_id | UUID NULL | padre en el árbol de la versión (FK compuesta a CatalogoCuenta) |

**Validaciones**: único `(empresa_id, version_id, account_id)` y `(empresa_id, version_id, codigo_version)`; toda cuenta usada en asientos históricos permanece en la proyección de su versión (no se purga).

**Transición**: al activar una versión con mapeos completos, las cuentas `nueva`/`renombrada` quedan `igual` en la nueva versión; las `suprimida` sin mapeo bloquean la activación.

## MapeoCuenta

Relación entre una cuenta de la versión anterior y su(s) equivalente(s) en la nueva (renombradas, suprimidas, nuevas).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| version_origen_id | UUID FK → CatalogoVersion | |
| version_destino_id | UUID FK → CatalogoVersion | |
| cuenta_origen_id | UUID NULL FK → CatalogoCuenta | nulo si el origen ya no existe como proyección |
| cuenta_destino_id | UUID NULL FK → CatalogoCuenta | nulo = cuenta sin destino (bloquea activación) |
| tipo_movimiento | ENUM | `igual`, `renombrada`, `suprimida`, `nueva` |
| requiere_reclasificacion | BOOLEAN | true para cuentas con saldo que se trasladan |
| origen | ENUM | `manifiesto`, `autogenerado` |

**Validación**: un `(empresa_id, version_origen_id, version_destino_id, cuenta_origen_id)` único; una cuenta `suprimida`/`renombrada` con saldo ≠ 0 debe tener `cuenta_destino_id` y `requiere_reclasificacion = true` para activar la versión (FR-004).

## ReclasificacionSaldo

Traslado de saldos de apertura a las cuentas de la nueva versión, materializado como asientos del motor (SPEC-002).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| version_destino_id | UUID FK → CatalogoVersion | |
| mapeo_id | UUID FK → MapeoCuenta | |
| cuenta_origen_id | UUID FK → account_plan | cuenta histórica con saldo |
| cuenta_destino_id | UUID FK → CatalogoCuenta | cuenta destino en la nueva versión |
| importe | NUMERIC(18,4) | saldo trasladado, precisión 4 dec.; check ≥ 0 |
| asiento_id | UUID FK NULL → SPEC-002 JournalEntry | asiento `ADJUSTMENT` que materializa el traslado |
| estado | ENUM | `borrador`, `contabilizado`, `cuadrado` |

**Validaciones**: la suma de importes de saldos origen por código de cuenta == suma destino (cuadre de apertura, FR-005/SC-003); cada `asiento_id` generado cumple Debe==Haber (constitución I) y no modifica los asientos históricos.

**Transición**: `borrador → contabilizado` (asiento ADJUSTMENT creado) → `cuadrado` (cuadre verificado y vinculado a la apertura de SPEC-009).

## Referencias externas (no modificadas)

- `account_plan` (SPEC-001): catálogo canónico multi-tenant (`tenant_id`, código único por empresa, niveles 1-5, `is_selectable`, triggers de estructura/protección).
- `journal_entry` / `journal_entry_line` (SPEC-002): asientos y apuntes; origen de saldos para reclasificación; destino de los asientos `ADJUSTMENT`.
- `ejercicio` (SPEC-009/SPEC-004): apertura del ejercicio que consume la reclasificación.

## Resumen de relaciones

```
CatalogoVersion 1 ── n CatalogoCuenta (proyección de la versión)
account_plan (SPEC-001) 1 ── 0..1 CatalogoCuenta (por versión; FK compuesta empresa_id)
CatalogoVersion (origen) 1 ── n MapeoCuenta ── n 1 CatalogoVersion (destino)
MapeoCuenta 1 ── n ReclasificacionSaldo
JournalEntry (SPEC-002) 1 ── 0..1 ReclasificacionSaldo.asiento_id (ADJUSTMENT)
ReclasificacionSaldo ──> Apertura de ejercicio (SPEC-009, cuadre)
```

**Nota de convención**: `empresa_id` == `tenant_id` del `plan.md` raíz; el alias queda documentado aquí y en `research.md` D8.