# Modelo 115 — Layout del Soporte (SPEC-024)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

El modelo 115 (retenciones e ingresos a cuenta sobre rendimientos procedentes del arrendamiento o subarrendamiento de inmuebles urbanos) se genera como informe/descargable con los siguientes bloques.

## Bloque 1: Datos del Declarante

| Campo | Descripción | Tipo |
|-------|-------------|------|
| nif | NIF del declarante | VARCHAR(9) |
| razon_social | Denominación social | VARCHAR(100) |
| ejercicio | Año fiscal | INT |
| trimestre | Trimestre natural (1-4) | INT |
| periodo | Periodo YYYY-Qn | VARCHAR(7) |

## Bloque 2: Datos del Periodo

| Campo | Descripción | Tipo |
|-------|-------------|------|
| total_arrendadores | Número total de arrendadores | INT |
| total_rendimientos | Rendimientos íntegros totales | NUMERIC(18,4) |
| total_retenciones | Total de retenciones practicadas | NUMERIC(18,4) |

## Bloque 3: Detalle por Arrendador

| Campo | Descripción | Tipo |
|-------|-------------|------|
| nif_arrendador | NIF del arrendador | VARCHAR(9) |
| nombre_arrendador | Nombre o razón social | VARCHAR(100) |
| direccion_inmueble | Direccion del inmueble arrendado | VARCHAR(200) |
| clave_retencion | Clave de retención | VARCHAR(10) |
| base_imponible | Rendimiento íntegro sujeto a retención | NUMERIC(18,4) |
| tipo_retencion | Tipo de retención (%) | NUMERIC(5,2) |
| retencion_practicada | Retención practicada | NUMERIC(18,4) |

## Bloque 4: Totales

| Campo | Descripción | Tipo |
|-------|-------------|------|
| total_retenciones | Suma de retenciones | NUMERIC(18,4) |
| resultado | Cuota a ingresar | NUMERIC(18,4) |

## Validación

1. `total_retenciones = Σ(retencion_practicada por arrendador)` (con tolerancia ±0.01)
2. `retencion_practicada = base_imponible × tipo_retencion / 100` (por arrendador)
3. Todos los NIF no vacíos
4. Solo incluye retenciones de tipo `IRPF_ARRENDAMIENTOS`
