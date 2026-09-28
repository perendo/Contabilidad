# Data Model: Retenciones IRPF y Modelos 111/115/190 (SPEC-024)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## LiquidacionRetenciones

Registro de la liquidación trimestral de retenciones IRPF.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta; FK → empresa (SPEC-003) |
| ejercicio | INT | año fiscal |
| trimestre | INT | 1-4 (Q1-Q4) |
| periodo | VARCHAR(7) | formato YYYY-Qn (ej: 2025-Q1) |
| total_base_retenciones | NUMERIC(18,4) | suma de bases de retención del trimestre |
| total_retenciones | NUMERIC(18,4) | suma de retenciones del trimestre; = acumulado en 4751 |
| n_perceptores | INT | número de perceptores con retención |
| estado | ENUM | `pendiente`, `liquidado` |
| fecha_liquidacion | DATE NULL | fecha del ingreso/pago |
| asiento_id | UUID FK NULL → SPEC-002 JournalEntry | asiento liquidación (4751 vs 572) |
| modelo_111_id | UUID FK NULL → Modelo111 | modelo 111 generado |
| modelo_115_id | UUID FK NULL → Modelo115 | modelo 115 generado (si hay alquileres) |
| notas | TEXT | |
| creado_por / created_at | | auditoría |

**Validaciones**: `trimestre` entre 1 y 4; `ejercicio + trimestre` único por empresa (solo una liquidación por trimestre); si `estado = liquidado`, `asiento_id` no nulo.

**Transiciones de estado**: `pendiente → liquidado` (al contabilizar liquidación).

**Índices**: `(empresa_id, ejercicio, trimestre)` único; `(empresa_id, estado)` para consultas.

## RetencionPeriodo

Detalle de retenciones de un perceptor en un trimestre (vista materializada o calculada).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| liquidacion_retenciones_id | UUID FK → LiquidacionRetenciones | |
| tercero_id | UUID FK → SPEC-008 Tercero | perceptor de la retención |
| nif | VARCHAR(9) | NIF del perceptor (copiado del tercero) |
| nombre | VARCHAR(100) | nombre del perceptor (copiado) |
| tipo_retencion | ENUM | `IRPF_PROFESIONALES`, `IRPF_ARRENDAMIENTOS`, `IRPF_OBRAS`, `IRPF_OTROS` |
| base_imponible | NUMERIC(18,4) | base sujeta a retención; > 0 |
| tipo_porcentaje | NUMERIC(5,2) | tipo de retención aplicado (%) |
| retencion_practicada | NUMERIC(18,4) | = base × tipo / 100; > 0 |
| facturas | JSONB | lista de facturas asociadas [{factura_id, numero, fecha, importe_base, retencion}] |
| notas | TEXT | |
| creado_por / created_at | | auditoría |

**Validaciones**: `retencion_practicada = base_imponible × tipo_porcentaje / 100` (con tolerancia ±0.01); `base_imponible > 0`; NIF no vacío.

## Modelo111

Soporte del modelo 111 (autoliquidación trimestral de retenciones).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| liquidacion_retenciones_id | UUID FK → LiquidacionRetenciones | |
| ejercicio | INT | |
| trimestre | INT | |
| fecha_generacion | TIMESTAMPTZ | |
| contenido | JSONB | datos del modelo 111 por bloques |
| hash_contenido | CHAR(64) | SHA-256 del contenido |
| creado_por / created_at | | auditoría |

## Modelo115

Soporte del modelo 115 (retenciones por arrendamientos).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| liquidacion_retenciones_id | UUID FK → LiquidacionRetenciones | |
| ejercicio | INT | |
| trimestre | INT | |
| fecha_generacion | TIMESTAMPTZ | |
| contenido | JSONB | datos del modelo 115 por bloques |
| hash_contenido | CHAR(64) | SHA-256 del contenido |
| creado_por / created_at | | auditoría |

## Modelo190

Soporte del modelo 190 (declaración anual de retenciones por perceptor).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio | INT | |
| fecha_generacion | TIMESTAMPTZ | |
| contenido | JSONB | datos del modelo 190 por bloques (perceptores, totales) |
| hash_contenido | CHAR(64) | SHA-256 del contenido |
| n_perceptores | INT | número de perceptores incluidos |
| creado_por / created_at | | auditoría |

**Validación**: todos los perceptores deben tener NIF; las retenciones anuales coinciden con la suma de las trimestrales.

## Resumen de relaciones

```
LiquidacionRetenciones 1 ── n RetencionPeriodo
LiquidacionRetenciones 1 ── 0..1 Modelo111
LiquidacionRetenciones 1 ── 0..1 Modelo115
LiquidacionRetenciones 1 ── 0..1 JournalEntry (asiento_id)
Tercero (SPEC-008) 1 ── n RetencionPeriodo
Factura (SPEC-007) n ── n RetencionPeriodo (via JSONB facturas)
Modelo190 1 ── n RetencionPeriodo (por ejercicio, no por trimestre)
```
