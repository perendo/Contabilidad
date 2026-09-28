# Data Model: Impuesto sobre Sociedades (Modelo 200) (SPEC-023)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## CalculoIS

Cálculo del Impuesto sobre Sociedades para un ejercicio dado.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta; FK → empresa (SPEC-003) |
| ejercicio | INT | año fiscal del cálculo |
| resultado_contable | NUMERIC(18,4) | suma de ingresos-gastos del ejercicio (consultado del cierre SPEC-004) |
| ajustes_positivos | NUMERIC(18,4) | suma de ajustes extracontables positivos; >= 0 |
| ajustes_negativos | NUMERIC(18,4) | suma de ajustes extracontables negativos; >= 0 |
| base_imponible | NUMERIC(18,4) | = resultado_contable + ajustes_positivos - ajustes_negativos |
| tipo_impositivo | NUMERIC(5,2) | porcentaje; default 25.00 |
| cuota_integra | NUMERIC(18,4) | = base_imponible × tipo_impositivo / 100 |
| deducciones | NUMERIC(18,4) | suma de deducciones/bonificaciones; >= 0 |
| cuota_liquida | NUMERIC(18,4) | = cuota_integra - deducciones |
| pagos_a_cuenta | NUMERIC(18,4) | consulta del submayor 473 del ejercicio; >= 0 |
| cuota_diferencial | NUMERIC(18,4) | = cuota_liquida - pagos_a_cuenta; positiva = a pagar, negativa = a devolver |
| provisional | BOOLEAN DEFAULT true | true = cálculo provisional; false = definitivo |
| estado | ENUM | `borrador`, `calculado`, `contabilizado` |
| asiento_id | UUID FK NULL → SPEC-002 JournalEntry | asiento del IS (630 vs 473/4752) |
| notas | TEXT | |
| creado_por / created_at | | auditoría |

**Validaciones**: `base_imponible = resultado_contable + ajustes_positivos - ajustes_negativos`; `cuota_integra = base_imponible × tipo_impositivo / 100`; `cuota_liquida = cuota_integra - deducciones`; `cuota_diferencial = cuota_liquida - pagos_a_cuenta`; `tipo_impositivo > 0`; `ejercicio` único por empresa (solo un cálculo definitivo).

**Transiciones de estado**: `borrador → calculado` (al ejecutar cálculo) | `calculado → contabilizado` (al generar asiento). Un cálculo `provisional` puede recalcularse libremente; uno definitivo (`provisional=false`) solo se crea al cerrar el ejercicio.

**Índices**: `(empresa_id, ejercicio)` único; `(empresa_id, estado)` para consultas.

## AjusteExtracontable

Detalle de ajustes, deducciones y bonificaciones aplicados al cálculo.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| calculo_is_id | UUID FK → CalculoIS | |
| tipo | ENUM | `AJUSTE_POSITIVO`, `AJUSTE_NEGATIVO`, `DEDUCCION`, `BONIFICACION` |
| descripcion | VARCHAR(500) | descripción del ajuste/deducción |
| referencia_normativa | VARCHAR(255) | referencia legal (opcional) |
| importe | NUMERIC(18,4) | importe del ajuste; > 0 siempre (el signo lo da el tipo) |

**Validaciones**: `importe > 0`; todos los ajustes pertenecen al mismo ejercicio que el cálculo.

## Modelo200

Soporte/export del modelo 200 generado a partir del cálculo.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| calculo_is_id | UUID FK → CalculoIS | cálculo del que se genera |
| fecha_generacion | TIMESTAMPTZ | fecha de generación del modelo |
| contenido | JSONB | datos del modelo 200 por bloques |
| hash_contenido | CHAR(64) | SHA-256 del contenido para integridad |
| creado_por / created_at | | auditoría |

**Validación**: el contenido debe pasar la validación de consistencia antes de generarse.

## Resumen de relaciones

```
CalculoIS 1 ── n AjusteExtracontable
CalculoIS 1 ── 0..1 JournalEntry (asiento_id)
CalculoIS 1 ── 0..1 Modelo200
Cierre (SPEC-004) 1 ── 1 CalculoIS (por ejercicio)
```
