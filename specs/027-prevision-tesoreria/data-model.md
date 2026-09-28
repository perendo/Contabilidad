# Data Model: Previsión y Flujo de Caja (SPEC-027)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003; alias `tenant_id` del `plan.md` raíz) en PK/índices/filtros; se deriva de la sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría (`audit_log`, WORM) en la misma transacción ACID.
- Los vencimientos (SPEC-011/020) y el diario (SPEC-002) se leen sin modificar (inmutabilidad II).

## PrevisionTesoreria

Cabecera de una proyección de tesorería generada por el usuario.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id) |
| numero_prevision | BIGINT | correlativo por empresa, asignado atómicamente (constitución IV) |
| fecha_generacion | TIMESTAMPTZ | momento de la generación |
| desde_fecha | DATE | inicio de la proyección |
| hasta_fecha | DATE | fin de la proyección |
| granularidad | ENUM | `dia`, `semana`, `mes` |
| saldo_inicial | NUMERIC(18,4) | saldo de tesorería inicial (SPEC-013 si hay cuenta 572, si no, balance de SPEC-002) |
| saldo_final | NUMERIC(18,4) | saldo proyectado resultante |
| estado | ENUM | `borrador`, `generada`, `anulada` |
| creado_por / created_at | | auditoría |

**Validaciones**: `hasta_fecha >= desde_fecha`; solo vencimientos no vencidos no cobrados/pagados entran en la proyección (FR-006); `saldo_inicial`/`saldo_final` en precisión 4 dec.

**Transiciones**: `borrador → generada` (ejecuta proyección y alertas) | `generada → anulada` (trazable; solo si las alertas asociadas están atendidas/ignoradas).

## MovimientoPrevision

Cada vencimiento pendiente o flujo manual colocado en su fecha de proyección.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| prevision_id | UUID FK → PrevisionTesoreria | opcional: un movimiento puede existir del vencimiento sin previsión |
| origen | ENUM | `vencimiento` (SPEC-011), `remesa_cobro` (SPEC-020), `pago_recurrente`, `cobro_estimado` |
| vencimiento_id | UUID NULL FK → SPEC-011 Vencimiento | si origen = vencimiento/remesa |
| numero_recibo | VARCHAR NULL | identificador del recibo de remesa (SPEC-020) |
| tipo | ENUM | `cobro`, `pago` |
| importe | NUMERIC(18,4) | > 0 |
| fecha_prevista | DATE | fecha de proyección (asignada o estimada por el usuario) |
| frecuencia | ENUM | `unico`, `semanal`, `mensual`, `anual` (para recurrentes) |
| concepto | VARCHAR(200) | descripción (p. ej. "Alquiler oficinas") |
| incluido | BOOLEAN | true si entró en la última proyección: false si fue excluido por no estar datado |

**Validaciones**: los vencidos/cobrados/pagados se excluyen de la proyección (FR-006); un movimiento sin `fecha_prevista` solo se incluye si el usuario la asigna; la FK a vencimiento es compuesta `(empresa_id, vencimiento_id)`.

**Transición**: `fecha_prevista` puede reasignarse por la acción `reprogramar_pago` de una alerta (D6 research), siempre con auditoría.

## AlertaLiquidez

Notificación de saldo negativo proyectado en un bucket de una previsión.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| prevision_id | UUID FK → PrevisionTesoreria | |
| fecha | DATE | bucket con saldo negativo |
| saldo_proyectado | NUMERIC(18,4) | saldo negativo en el bucket (check < 0) |
| importe_deficit | NUMERIC(18,4) | valor absoluto del déficit |
| estado | ENUM | `abierta`, `atendida`, `ignorada` |
| accion_sugerida | ENUM | `reprogramar_pago`, `incluir_ingreso` |
| movimiento_origen_id | UUID NULL FK → MovimientoPrevision | movimiento asociado si se reprograma |

**Validaciones**: una alerta por `(empresa_id, prevision_id, fecha)` con saldo < 0; el saldo exactamente cero NO genera alerta (edge case: límite de solvencia).

**Transición**: `abierta → atendida` (acción aplicada) | `abierta → ignorada` (desestimada, trazable).

## InformeEFE

Snapshot del Estado de Flujos de Efectivo consolidado de un ejercicio.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio | INT | año del informe |
| saldo_inicial | NUMERIC(18,4) | tesorería del inicio del ejercicio |
| saldo_final | NUMERIC(18,4) | tesorería al cierre |
| cuadre | BOOLEAN | saldo_inicial + Σ movimientos == saldo_final |
| sin_conciliar | BOOLEAN | true si hay diferencia contra SPEC-013 (permite formular con aviso) |
| estado | ENUM | `borrador`, `formulado` (inmutable) |
| formulado_por / fecha_formulacion | | auditoría |

**Validación**: `cuadre` se calcula con aritmética Decimal; `estado = formulado` es inmutable (no UPDATE/DELETE).

**Transición**: `borrador → formulado` (cuadre verificado; fichero inmutable y trazado).

## LineaEFE

Partida del EFE dentro de un bloque de actividad.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| informe_id | UUID FK → InformeEFE | |
| bloque | ENUM | `operativa`, `inversion`, `financiacion` |
| cuenta_id | UUID FK → account_plan (SPEC-001) | cuenta clasificada |
| importe | NUMERIC(18,4) | importe neto de la cuenta en el bloque (firmado: cobros + / pagos −) |
| override_usuario | BOOLEAN | true si el usuario reclasificó manualmente la cuenta |

**Validaciones**: una cuenta en un único bloque por informe (si hay override, se respeta el del usuario); la suma de `LineaEFE.importe` = variación de tesorería.

## Referencias externas (solo lectura / fuente de datos)

- `Vencimiento` (SPEC-011) y `ReciboRemesa` (SPEC-020): vencimientos pendientes de cobro/pago con su fecha de vencimiento.
- `ConciliacionBancaria` (SPEC-013): saldo según extracto de la cuenta 572 para el `saldo_inicial`/cuadre del EFE.
- `journal_entry_line` / `account_plan` (SPEC-002/001): movimientos y grupos del plan para clasificar por actividad.

## Resumen de relaciones

```
PrevisionTesoreria 1 ── n MovimientoPrevision (proyección)
Vencimiento (SPEC-011)/ReciboRemesa (SPEC-020) 1 ── 0..1 MovimientoPrevision (origen)
PrevisionTesoreria 1 ── n AlertaLiquidez (bucket con saldo < 0)
AlertaLiquidez 0..1 ── 1 MovimientoPrevision (reprogramación)
InformeEFE 1 ── n LineaEFE (bloques del EFE)
account_plan (SPEC-001) 1 ── n LineaEFE (cuenta clasificada)
ConciliacionBancaria (SPEC-013) — lectura → saldo inicial / validation de EFE
```

**Nota de convención**: `empresa_id` == `tenant_id` del `plan.md` raíz; alias documentado en `research.md` D8.