# Modelo 111 — Layout del Soporte (SPEC-024)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

El modelo 111 (autoliquidación trimestral de retenciones e ingresos a cuenta sobre rendimientos del trabajo, profesionales, etc.) se genera como informe/descargable con los siguientes bloques.

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
| total_perceptores | Número total de perceptores | INT |
| total_base_retenciones | Base imponible total sujeta a retención | NUMERIC(18,4) |
| total_retenciones_practicadas | Total de retenciones practicadas | NUMERIC(18,4) |

## Bloque 3: Detalle por Perceptor

| Campo | Descripción | Tipo |
|-------|-------------|------|
| nif_perceptor | NIF del perceptor | VARCHAR(9) |
| nombre_perceptor | Nombre o razón social | VARCHAR(100) |
| tipo_renta | Tipo de rendimiento (trabajo, profesional, etc.) | VARCHAR(50) |
| clave_retencion | Clave de la retención | VARCHAR(10) |
| base_imponible | Base sujeta a retención | NUMERIC(18,4) |
| tipo_retencion | Tipo de retención (%) | NUMERIC(5,2) |
| retencion_practicada | Retención practicada | NUMERIC(18,4) |

## Bloque 4: Totales

| Campo | Descripción | Tipo |
|-------|-------------|------|
| total_retenciones | Suma de retenciones | NUMERIC(18,4) |
| resultado | Cuota a ingresar (siempre positiva en 111) | NUMERIC(18,4) |

## Validación

1. `total_retenciones = Σ(retencion_practicada por perceptor)` (con tolerancia ±0.01)
2. `retencion_practicada = base_imponible × tipo_retencion / 100` (por perceptor)
3. Todos los NIF no vacíos
