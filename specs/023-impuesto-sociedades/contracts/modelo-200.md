# Modelo 200 — Layout del Soporte (SPEC-023)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

El modelo 200 se genera como un informe/descargable (JSON estructurado y PDF) con los siguientes bloques de datos. La presentación telemática está fuera de alcance.

## Bloque 1: Datos del Declarante

| Campo | Descripción | Tipo |
|-------|-------------|------|
| nif | NIF de la entidad | VARCHAR(9) |
| razon_social | Denominación social | VARCHAR(100) |
| ejercicio | Año fiscal | INT |
| tipo_entidad | Tipo de entidad (sociedad, etc.) | VARCHAR(50) |
| domicilio_social | Domicilio fiscal | VARCHAR(200) |
| codigo_postal | CP | VARCHAR(5) |
| municipio | Municipio | VARCHAR(100) |
| provincia | Provincia | VARCHAR(50) |
| comunidad_autonoma | CCAA | VARCHAR(50) |

## Bloque 2: Resultado Contable

| Campo | Descripción | Tipo |
|-------|-------------|------|
| resultado_neto | Resultado neto del ejercicio (ingresos - gastos) | NUMERIC(18,4) |
| ajustes_positivos | Suma de ajustes extracontables positivos | NUMERIC(18,4) |
| ajustes_negativos | Suma de ajustes extracontables negativos | NUMERIC(18,4) |
| resultado_ajustado | = resultado_neto + ajustes_positivos - ajustes_negativos | NUMERIC(18,4) |

## Bloque 3: Base Imponible y Cuota

| Campo | Descripción | Tipo |
|-------|-------------|------|
| base_imponible | Base imponible del IS | NUMERIC(18,4) |
| tipo_impositivo | Tipo aplicado (%) | NUMERIC(5,2) |
| cuota_integra | = base × tipo / 100 | NUMERIC(18,4) |
| bonificaciones | Suma de bonificaciones | NUMERIC(18,4) |
| deducciones | Suma de deducciones | NUMERIC(18,4) |
| cuota_liquida | = cuota_integra - bonificaciones - deducciones | NUMERIC(18,4) |

## Bloque 4: Pagos a Cuenta y Cuota Diferencial

| Campo | Descripción | Tipo |
|-------|-------------|------|
| pagos_a_cuenta | Pagos a cuenta (retenciones, fraccionados) | NUMERIC(18,4) |
| cuota_diferencial | = cuota_liquida - pagos_a_cuenta | NUMERIC(18,4) |
| resultado | "a_pagar" si > 0, "a_devolver" si < 0, "cero" si = 0 | ENUM |

## Bloque 5: Datos de la Liquidación (complementario)

| Campo | Descripción | Tipo |
|-------|-------------|------|
| fecha_primera_mutex | Fecha primera mutualidad (si aplica) | DATE NULL |
| cuota_liquidacion_anterior | Cuota de la liquidación anterior | NUMERIC(18,4) NULL |
| complementaria | Si es complementaria de otra liquidación | BOOLEAN |

## Validación de Consistencia

El sistema valida antes de exportar:
1. `base_imponible = resultado_neto + ajustes_positivos - ajustes_negativos`
2. `cuota_integra = base_imponible × tipo_impositivo / 100` (con tolerancia de ±0.01)
3. `cuota_liquida = cuota_integra - bonificaciones - deducciones`
4. `cuota_diferencial = cuota_liquida - pagos_a_cuenta`
5. Todos los importes >= 0 cuando corresponda (ajustes positivos/negativos siempre >= 0)
6. `tipo_impositivo > 0`

Si alguna validación falla → 422 con detalle del error y campo con inconsistencia.
