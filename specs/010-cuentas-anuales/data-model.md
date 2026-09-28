# Data Model: Cuentas Anuales (SPEC-010)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## ConfiguracionInforme

Configuración de agrupación del plan de cuentas por empresa (nivel de masa patrimonial para balance/PyG/EFE).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio | INT | |
| informe_tipo | ENUM | `BALANCE`, `PYG`, `EFE` |
| agrupacion_id | UUID FK → SPEC-001 Agrupacion | nivel 1-3 definido en el plan |
| cuenta_ini | VARCHAR(20) | rango de cuentas (desde) |
| cuenta_fin | VARCHAR(20) NULL | rango (hasta); NULL = autoclave prefijo |
| actividad_efe | ENUM NULL | `operativa`/`inversion`/`financiacion` (solo EFE) |
| creado_por | | auditoría |

**Validaciones**: una cuenta no puede asignarse a dos agrupaciones del mismo informe en el mismo ejercicio; si no hay configuración, la cuenta queda en "Otros" con advertencia.

## Balance de Situación (informe calculado)

No se persiste como registro (se calcula bajo demanda), salvo en la formulación oficial donde se congela dentro de `FormulacionCuentasAnuales`.

| Campo (JSON del cálculo) | Tipo | Reglas |
|-------|------|--------|
| empresa_id | BIGINT | |
| ejercicio | INT | |
| total_activo | NUMERIC(18,4) | = suma activo (corriente + no corriente) |
| total_pasivo | NUMERIC(18,4) | = suma pasivo |
| total_patrimonio | NUMERIC(18,4) | = patrimonio neto (grupo 1) + resultado |
| masas[] | JSONB | estructura de masas y partidas con importes `Decimal` |
| cuadre | BOOLEAN | `total_activo == total_pasivo + total_patrimonio` calculado en backend |
| comparativo_anterior | JSONB NULL | importes del ejercicio previo |

**Validación**: `cuadre` must ser `true`; si no, 422 `balance_descuadrado`.

## Cuenta de Pérdidas y Ganancias (informe calculado)

| Campo (JSON del cálculo) | Tipo | Reglas |
|-------|------|--------|
| empresa_id | BIGINT | |
| ejercicio | INT | |
| total_ingresos | NUMERIC(18,4) | suma grupo 7 |
| total_gastos | NUMERIC(18,4) | suma grupo 6 |
| resultado_ejercicio | NUMERIC(18,4) | Ingresos - Gastos |
| resultado_cierre | NUMERIC(18,4) | saldo asiento de regularización (SPEC-004) |
| coincide_cierre | BOOLEAN | `resultado_ejercicio == resultado_cierre` |

**Validación**: `coincide_cierre` false → advertencia `descuadre_cierre`; formulación oficial bloqueada hasta coincidir.

## EFE (informe calculado)

| Campo | Tipo | Reglas |
|-------|------|--------|
| empresa_id | BIGINT | |
| ejercicio | INT | |
| saldo_inicial_tesoreria | NUMERIC(18,4) | grupo 5 al inicio |
| cobros_pagos_operativa | NUMERIC(18,4) | |
| cobros_pagos_inversion | NUMERIC(18,4) | |
| cobros_pagos_financiacion | NUMERIC(18,4) | |
| saldo_final_tesoreria | NUMERIC(18,4) | = saldo_inicial + movimientos |
| variacion_balance | NUMERIC(18,4) | diferencia tesorería del Balance |
| cuadre | BOOLEAN | `saldo_final == saldo_inicial + movimientos` y `variacion == variacion_balance` |

**Validación**: `cuadre` false → no se permite formular el EFE hasta resolver la diferencia (edge case del spec).

## FormulacionCuentasAnuales

Documento inmutable de la formulación oficial de las cuentas anuales del ejercicio.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio | INT | ejercicio cerrado obligatorio |
| numero_formulacion | BIGINT | correlativo por (empresa_id, ejercicio), asignado atómicamente |
| fecha_formulacion | TIMESTAMPTZ | UTC |
| usuario_id | UUID FK → SPEC-003 | |
| contenido_hash | CHAR(64) | sha256 del JSON sellado de los informes |
| estado | ENUM | `formulada`, `anulada` |
| motivo_anulacion | VARCHAR(255) NULL | si se anula |
| anulada_por / anulada_en | | auditoría |
| created_at | TIMESTAMPTZ | |

**Validaciones**: único registro `formulada` por (empresa_id, ejercicio); anulación requiere permiso de administrador y motivo; los asientos del ejercicio no se modifican.

**Transiciones de estado**: `formulada → anulada` (reformulación con trazabilidad) | nueva `formulada` (tras anulación).

## Resumen de relaciones

```
Empresa (SPEC-003) 1 ── n ConfiguracionInforme
Agrupacion (SPEC-001) 1 ── n ConfiguracionInforme
EjercicioContable 1 ── 0..1 FormulacionCuentasAnuales (estado formulada)
FormulacionCuentasAnuales 1 ── 1 Cloud snapshot de Balance/PyG/EFE (blob sellado con hash)
Balance/PyG/EFE ── derivados de JournalEntry/JournalEntryLine (SPEC-002) y Account (SPEC-001)
```