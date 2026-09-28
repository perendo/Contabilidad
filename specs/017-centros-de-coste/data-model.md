# Data Model: Centros de Coste (SPEC-017)

**Branch**: `017-centros-de-coste` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

## Key Entities + FRs

- **CentroCoste**: FR-001, FR-002, FR-004, FR-005, FR-007, FR-008.
- **JerarquiaCentro** (closure table): FR-001, FR-006.
- **ImputacionCentro** (+ columna de línea en `JournalEntryLine`): FR-003, FR-004, FR-007.
- **InformeDeCostes** (agregación, no tabla): FR-006.

## Tablas

### `centro_coste`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa; derivado solo de sesión (constitución III) |
| `id` | BIGINT | PK compuesta; identidad por empresa |
| `codigo` | VARCHAR(20) | Único por empresa; no editable tras crear con imputaciones |
| `nombre` | VARCHAR(120) | Obligatorio |
| `tipo` | ENUM(`departamento`, `proyecto`, `subvencion`, `delegacion`) | Obligatorio |
| `parent_id` | BIGINT NULL | Padre dentro de la misma empresa; NULL = raíz; ciclo prohibido (validación app + CHECK DB) |
| `subvencion_id` | BIGINT NULL | Vínculo opcional a `Subvencion` (SPEC-019) de la misma empresa (FR-002) |
| `estado` | ENUM(`activo`, `inactivo`) | Default `activo`; inactivo bloquea nuevas imputaciones e hijos |
| `es_hoja` | BOOLEAN | Derivado: sin hijos; informativo (la imputación se permite a cualquier nodo activo del árbol, decisión D2) |
| `created_at` / `updated_at` | TIMESTAMPTZ | Auditoría |

Restricciones:
- Unicidad `(empresa_id, codigo)`.
- `parent_id` no puede apuntar a un centro de otra empresa (FK compuesta con `empresa_id`).
- NO se puede borrar físicamente un centro con imputaciones o descendientes (constraint/trigger; solo inactivación — FR-005).
- `subvencion_id` valida pertenencia a la empresa activa (FR-004).

Transiciones de estado:
`activo → inactivo` (por usuario con permiso; bloquea nuevas imputaciones; historial intacto). `inactivo → activo` permitido (reactivación admin). Borrado físico solo si el centro es raíz `activo` sin imputaciones ni hijos (sin historial que proteger); con historial → solo inactivación.

### `jerarquia_centro` (closure table)

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa |
| `ancestro_id` | BIGINT | PK compuesta; FK `centro_coste.id` (misma empresa) |
| `descendiente_id` | BIGINT | PK compuesta; FK `centro_coste.id` (misma empresa) |
| `profundidad` | SMALLINT | 0 = el propio nodo |

Reglas:
- Contrastiene todos los pares ancestro→descendiente de la jerarquía (profundidad ≥ 0).
- Se mantiene en la misma transacción ACID que la alta/reasignación de `centro_coste` (audit log en la misma transacción).
- Permite agregación por ancestro con un solo `JOIN` (decisión D1).

### Columna en `JournalEntryLine` (motor SPEC-006, modelo `acct/`)

| Campo | Tipo | Reglas |
|---|---|---|
| `centro_coste_id` | BIGINT NULL | FK compuesta a `centro_coste(empresa_id, id)` de la empresa de la línea; NULL = apunte sin imputar (válido, Edge Case) |

Reglas:
- La FK compuesta incluye `empresa_id` de la línea → imposibilidad técnica de imputar a un centro cross-tenant (FR-004).
- No altera `importe_debe`/`importe_haber`; el balance del asiento se valida como siempre en backend (constitución I).
- Restricción a nivel DB: líneas de asientos `POSTED` no admiten `UPDATE` ni `DELETE` (inmutabilidad, constitución II / SPEC-002).
- Borradores pueden editarse normalmente (asignar/quitar centro antes de asentar).

### `imputacion_centro` (traza de auditoría / reporting)

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa |
| `id` | BIGINT | PK compuesta |
| `asiento_id` | BIGINT | FK al `JournalEntry` (misma empresa); solo referencia |
| `linea_id` | BIGINT | FK a `JournalEntryLine` (misma empresa) |
| `centro_coste_id` | BIGINT | FK compuesta a `centro_coste` (misma empresa) |
| `periodo` | SMALLINT | Mes del asiento (para informe rápido por período) |
| `created_at` | TIMESTAMPTZ | Momento de la imputación |

Reglas:
- Se inserta en la misma transacción ACID que la creación/rectificación del asiento (constitución audiencia).
- Nunca se modifica ni borra (solo se añaden registros immutables).
- El informe agrega las líneas del diario filtrando por esta traza o por la columna de línea (decisión D5); la traza garantiza reproducir el historial imputado.

Transición de estados (imputación): creada → inmutable. Solo desaparece si el asiento es borrador y se cancela (borrador no es diario).

## Resumen de relaciones

```text
empresa (SPEC-000) 1─N CentroCoste 1─N ImputacionCentro N─1 JournalEntryLine 1─N JournalEntry
                          │  N─1 JerarquiaCentro (ancestro/descendiente, mismo empresa)
                          │  N─1 Subvencion (SPEC-019) [opcional]
centro_coste.parent_id ──► centro_coste.id (misma empresa, árbol)
```

- Un asiento `N` líneas → cada línea puede tener 0..1 centro (imputación opcional).
- Un centro puede estar en varias líneas de distintos asientos.
- La jerarquía es multi-padre? No: `parent_id` simple (árbol); la closure table materializa cualquier profundidad.
- La subvención (SPEC-019) es opcional y 1:1 en esta dirección (centro → subvención); la asignación de gastos real se gobierna en 019.