# Modelo 190 — Layout del Soporte (SPEC-024)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

El modelo 190 (resumen anual de retenciones e ingresos a cuenta sobre rendimientos del trabajo, profesionales, etc., por perceptor) se genera como informe/descargable con los siguientes bloques.

## Bloque 1: Datos del Declarante

| Campo | Descripción | Tipo |
|-------|-------------|------|
| nif | NIF del declarante | VARCHAR(9) |
| razon_social | Denominación social | VARCHAR(100) |
| ejercicio | Año fiscal | INT |
| domicilio_social | Domicilio fiscal | VARCHAR(200) |
| codigo_postal | CP | VARCHAR(5) |
| municipio | Municipio | VARCHAR(100) |
| provincia | Provincia | VARCHAR(50) |

## Bloque 2: Totales del Ejercicio

| Campo | Descripción | Tipo |
|-------|-------------|------|
| total_perceptores | Número total de perceptores del año | INT |
| total_base_retenciones | Base imponible total anual | NUMERIC(18,4) |
| total_retenciones | Total de retenciones anuales | NUMERIC(18,4) |

## Bloque 3: Detalle por Perceptor (obligatorio NIF)

| Campo | Descripción | Tipo |
|-------|-------------|------|
| nif_perceptor | NIF del perceptor (obligatorio) | VARCHAR(9) |
| nombre_perceptor | Nombre o razón social | VARCHAR(100) |
| codigo_postal | CP del perceptor | VARCHAR(5) |
| municipio | Municipio del perceptor | VARCHAR(100) |
| provincia | Provincia del perceptor | VARCHAR(50) |
| clave_retencion | Clave de retención | VARCHAR(10) |
| concepto_renta | Concepto del rendimiento | VARCHAR(50) |
| base_imponible_anual | Base imponible anual acumulada | NUMERIC(18,4) |
| tipo_retencion | Tipo de retención (%) | NUMERIC(5,2) |
| retencion_anual | Retención anual acumulada | NUMERIC(18,4) |
| ejercicios_anteriores | Retenciones de ejercicios anteriores cobradas en el año | NUMERIC(18,4) |

## Bloque 4: Totales

| Campo | Descripción | Tipo |
|-------|-------------|------|
| total_retenciones_anual | Suma de retenciones anuales por perceptor | NUMERIC(18,4) |

## Validación

1. `total_retenciones_anual = Σ(retencion_anual por perceptor)` (con tolerancia ±0.01)
2. `retencion_anual = Σ(retenciones trimestrales del 111 por perceptor)` (cruce con 111)
3. Todos los NIF **obligatoriamente** no vacíos → si algún perceptor no tiene NIF, el sistema rechaza la generación con 422
4. `total_base_retenciones_anual = Σ(base_imponible_anual por perceptor)`
