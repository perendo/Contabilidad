# Data Model: Plantillas de Asientos (SPEC-018)

**Branch**: `018-plantillas-asientos` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

## Key Entities + FRs

- **PlantillaAsiento**: FR-001, FR-002, FR-006, FR-007.
- **LineaPlantilla**: FR-002, FR-004, FR-005.
- **VariablePlantilla**: FR-002, FR-005.
- **AsientoGenerado**: FR-003, FR-005, FR-006 (trazabilidad).

## Tablas

### `plantilla_asiento`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa; derivado solo de sesión (constitución III) |
| `id` | BIGINT | PK compuesta; identidad por empresa |
| `nombre` | VARCHAR(120) | Obligatorio; único por empresa |
| `descripcion` | TEXT NULL | Opcional (decisión D10) |
| `categoria` | VARCHAR(50) NULL | Agrupamiento opcional |
| `version_actual` | INT | Incrementa en cada edición que cambia líneas/variables (D5) |
| `estado` | ENUM(`activa`, `inactiva`) | Default `activa`; `inactiva` bloquea la generación (Edge Case) |
| `created_at` / `updated_at` | TIMESTAMPTZ | Auditoría |

Restricciones:
- Unicidad `(empresa_id, nombre)`.
- No se borra físicamente una plantilla con `AsientoGenerado` (FK + trazabilidad; solo se inactiva — D6).

Transiciones de estado: `activa → inactiva` (bloquea generación; asientos generados intactos). `inactiva → activa` permitida.

### `variable_plantilla`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa |
| `id` | BIGINT | PK compuesta |
| `plantilla_id` | BIGINT | FK compuesta a `plantilla_asiento` (misma empresa) |
| `nombre` | VARCHAR(60) | Único por plantilla; mostrado al generar |
| `tipo` | ENUM(`importe`) | Solo importes numéricos (sin fórmulas — Assumption) |
| `es_requerida` | BOOLEAN | Default true; si false y vacía, la línea se omite |

### `linea_plantilla`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa |
| `id` | BIGINT | PK compuesta |
| `plantilla_id` | BIGINT | FK compuesta (misma empresa) |
| `orden` | SMALLINT | Orden de los apuntes en el asiento |
| `cuenta_id` | BIGINT | Cuenta del plan de la empresa (SPEC-001) |
| `posicion` | ENUM(`debe`, `haber`) | Posición en el asiento |
| `importe_fijo` | NUMERIC(18,4) NULL | Excluyente con `variable_id` (CHECK) |
| `variable_id` | BIGINT NULL | A `variable_plantilla` (misma empresa y misma plantilla); excluyente con fijo |

Restricciones:
- CHECK: `(importe_fijo IS NULL) OR (variable_id IS NULL)` — una línea es fija o variable (D1).
- `cuenta_id` verificada contra el plan de la empresa (FR-004).
- El balance de la plantilla completa puede ser no nulo con variables; se resuelve en generación.

### `asiento_generado`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK; FK empresa |
| `asiento_id` | BIGINT | PK; FK al `JournalEntry` (misma empresa) — el asiento generado |
| `plantilla_id` | BIGINT | FK a `plantilla_asiento` (misma empresa); trazabilidad (D8) |
| `version_plantilla` | INT | Version al generar (snapshot semántico, D5) |
| `variables_aportadas` | JSONB | Mapa `variable_id → importe` como `Decimal` string (constitución: nunca float) |
| `fecha_generacion` | TIMESTAMPTZ | Momento de generación |
| `usuario_generador` | BIGINT | Actor de la generación |

Restricciones:
- Registro inmutable (sin UPDATE/DELETE) — el asiento `POSTED` es inmutable (constitución II).
- Se escribe en la misma transacción ACID que la creación del asiento (D8).

## Transición de estados del asiento generado

El asiento sigue exactamente el ciclo del motor SPEC-002 (borrador → posteado → inmutable). La plantilla solo produce el borrador inicial; la legalidad (número correlativo, balance, ejercicio abierto) la gobierna el motor.

## Resumen de relaciones

```text
empresa (SPEC-000) 1─N plantilla_asiento 1─N variable_plantilla
                          │ 1─N linea_plantilla N─1 cuenta (SPEC-001, misma empresa)
                          │ 1─N asiento_generado N─1 journal_entry (SPEC-002/006, misma empresa)
```

- Una plantilla tiene 1..N líneas y 0..N variables.
- Una línea fija → `importe_fijo`; una línea variable → `variable_id`.
- Un asiento generado referencia la plantilla y contiene sus líneas reales (diario inmutable); editar la plantilla no afecta al asiento (FR-006).