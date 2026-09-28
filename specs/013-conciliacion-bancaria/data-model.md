# Data Model: Conciliación Bancaria (SPEC-013)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.
- Los apuntes `POSTED` de la 572 (SPEC-002) nunca se modifican; el cruce es una relación externa.

## ExtractoBancario

Cabecera del fichero importado para una cuenta 572.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id) |
| cuenta_id | UUID FK → SPEC-001 Cuenta (572) | cuenta de la empresa activa; rechazo si es de otra empresa |
| fecha_inicio | DATE | rango declarado en el fichero |
| fecha_fin | DATE | rango declarado en el fichero |
| saldo_inicial | NUMERIC(18,4) | saldo al inicio del período (fi fichero) |
| saldo_final | NUMERIC(18,4) | saldo al cierre del fichero |
| nombre_fichero | VARCHAR(255) | nombre original subido |
| sha256 | CHAR(64) | huella del contenido; único por empresa |
| estado | ENUM | `importado`, `duplicado` |
| n_movimientos | INT | total de líneas registradas |
| fecha_importacion | TIMESTAMPTZ | |
| creado_por | | actor (auditoría de sesión) |

**Validaciones**: `saldo_final == saldo_inicial + Σ importes` cuando el fichero declara el desglose; rechazo de fichero ya importado (sha256) o solapado por (cuenta, rango, saldos, nº movimientos) → estado `duplicado` y API 409.

## MovimientoBancario

Línea del extracto (operación bancaria de la cuenta).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| extracto_id | UUID FK → ExtractoBancario | |
| orden | INT | correlativo del fichero; único por (empresa_id, extracto_id, orden) |
| fecha_operacion | DATE | fecha de la operación |
| fecha_valor | DATE | fecha de valor si el fichero la declara |
| concepto | VARCHAR(255) | texto del movimiento |
| importe | NUMERIC(18,4) | valor absoluto > 0 |
| signo | ENUM | `D` (débito) / `H` (crédito) — orientación deudora/acreedora |
| referencia | VARCHAR(80) NULL | referencia operativa del banco |
| estado | ENUM | `pendiente`, `conciliado`, `alertado` |

**Validaciones**: `importe > 0` y dirección codificada en `signo` (evita firmas ambiguas); un movimiento solo puede tener un cruce activo.

**Transición de estado**: `pendiente → conciliado` (cruce confirmado) | `pendiente → alertado` (resolución de alerta de movimiento sin apunte).

## Conciliacion

Sesión de conciliación de una cuenta dentro de un período.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| cuenta_id | UUID FK → SPEC-001 Cuenta (572) | |
| ejercicio | INT | |
| fecha_inicio | DATE | inicio del rango conciliado |
| fecha_fin | DATE | fin del rango conciliado |
| extracto_id | UUID FK → ExtractoBancario | extracto fuente del rango |
| saldo_banco | NUMERIC(18,4) | = extracto.saldo_final |
| saldo_libros | NUMERIC(18,4) | Σ (Haber − Debe) de apuntes 572 del rango |
| diferencia | NUMERIC(18,4) | = saldo_banco − saldo_libros (recalculada con cada cruce) |
| estado | ENUM | `abierta`, `cerrada` |
| periodo_conciliado_id | UUID NULL → PeriodoConciliado | asignado al archivar |

**Transiciones**: `abierta → cerrada` (archivo con diferencia cero, constitución IV) | la conciliación perteneciente a un ejercicio cerrado no se puede abrir (409).

## CruceConciliacion

Relación trazable entre un movimiento del extracto y un apunte de la 572.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| conciliacion_id | UUID FK → Conciliacion | |
| movimiento_id | UUID FK → MovimientoBancario | único por empresa (un movimiento se concilia una vez) |
| apunte_id | UUID FK → SPEC-002 JournalEntryLine | única por empresa para cruces confirmados |
| importe | NUMERIC(18,4) | importe del movimiento (snapshot del cruce) |
| signo | ENUM | D/H (orientación del movimiento) |
| origen | ENUM | `auto` (propuesta) / `manual` |
| prioridad | ENUM | `propuesto` (importe+concepto) / `candidato` (solo importe) |
| estado | ENUM | `pendiente_confirmar`, `confirmado` |
| fecha_cruce | DATE NULL | fecha en que se confirma |
| usuario_id | | actor del cruce |
| confirmado_por_remesa | BOOLEAN | cierto si la confirmación activó el cobro de SPEC-020 |

**Validaciones**: importe del movimiento == importe del apunte (comparación `Decimal` exacta); confirma solo cruces de la empresa activa; en período archivado el cruce es inmutable.

**Transiciones**: `pendiente_confirmar → confirmado` (aceptación, fecha_cruce y actor) | `confirmado → pendiente_confirmar` (deshacer, solo antes del archivo).

## PeriodoConciliado

Período archivado con diferencia cero (inmutable).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| conciliacion_id | UUID FK → Conciliacion | |
| ejercicio | INT | |
| numero_periodo | BIGINT | correlativo por (empresa_id, ejercicio), asignado atómicamente |
| fecha_inicio | DATE | |
| fecha_fin | DATE | |
| saldo_banco | NUMERIC(18,4) | |
| saldo_libros | NUMERIC(18,4) | |
| diferencia | NUMERIC(18,4) | `Decimal("0.0000")` — check `diferencia = 0` |
| fecha_cierre | TIMESTAMPTZ | |
| usuario_id | | actor del cierre |

**Validaciones**: `diferencia == Decimal("0.0000")` obligatoria; `numero_periodo` único por (empresa_id, ejercicio); sin UPDATE/DELETE una vez creado (constitución II, enforced en base de datos).

## AlertaConciliacion

Aviso de operaciones sin correspondencia (no genera asiento).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| conciliacion_id | UUID FK → Conciliacion | |
| tipo | ENUM | `movimiento_sin_apunte`, `apunte_sin_extracto`, `importe_concepto_dudoso` |
| movimiento_id | UUID FK NULL → MovimientoBancario | si aplica |
| descripcion | VARCHAR(255) | detalle del aviso |
| estado | ENUM | `abierta`, `resuelta` |

**Validación**: una alerta por combinación (conciliación, tipo, movimiento) mientras esté `abierta`.

## Resumen de relaciones

```
Cuenta (SPEC-001, 572) 1 ── n ExtractoBancario
ExtractoBancario 1 ── n MovimientoBancario
Conciliacion 1 ── n CruceConciliacion
MovimientoBancario 1 ── 0..1 CruceConciliacion (confirmado)
JournalEntryLine (SPEC-002) 1 ── 0..1 CruceConciliacion (confirmado)
Conciliacion 1 ── 0..1 PeriodoConciliado
Conciliacion 1 ── n AlertaConciliacion
ReciboRemesa (SPEC-020) 1 ── 0..1 (confirmado vía CruceConciliacion.confirmado_por_remesa)
```