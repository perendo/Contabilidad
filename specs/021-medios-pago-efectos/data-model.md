# Data Model: Medios de Pago y Efectos (SPEC-021)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## Efecto

Registro de un cheque, pagaré o letra con su ciclo de vida completo.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta; FK → empresa (SPEC-003) |
| tercero_id | UUID FK → SPEC-008 Tercero | cliente o proveedor |
| tipo_efecto | ENUM | `CHEQUE`, `PAGARE`, `LETRA` |
| numero_documento | VARCHAR(50) | número/identificador del efecto (único por empresa+tercero+tipo) |
| fecha_emision | DATE | día de emisión/registro del efecto |
| fecha_vencimiento | DATE | fecha límite de cobro; indexada para cartera |
| importe | NUMERIC(18,4) | importe nominal del efecto; > 0 |
| moneda | VARCHAR(3) DEFAULT 'EUR' | ISO 4217 |
| estado | ENUM | `emitido`, `cobrado`, `impagado` |
| asiento_cobro_id | UUID FK NULL → SPEC-002 JournalEntry | asiento al cobrar (431 vs 572/570) |
| asiento_impago_id | UUID FK NULL → SPEC-002 JournalEntry | asiento REVERSAL al impago |
| notas | TEXT | observaciones |
| creado_por / created_at | | auditoría |

**Validaciones**: `numero_documento` único por (empresa_id, tercero_id, tipo_efecto, numero_documento); `fecha_vencimiento >= fecha_emision`; `estado` solo transiciona según reglas below.

**Transiciones de estado**: `emitido → cobrado` (al liquidar, genera asiento_cobro) | `emitido → impagado` (al registrar impago, genera asiento_impago REVERSAL y reapertura del vencimiento). Los estados `cobrado` e `impagado` son finales (inmutables).

**Índices**: `(empresa_id, estado, fecha_vencimiento)` para cartera; `(empresa_id, tercero_id)` para consultas por tercero.

## CobroMedio

Operación de cobro/pago por un medio específico (TPV, tarjeta, transferencia, cheque) contra un vencimiento de SPEC-011.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| vencimiento_id | UUID FK → SPEC-011 Vencimiento | vencimiento liquidado |
| medio_cobro | ENUM | `CHEQUE`, `PAGARE`, `LETRA`, `TARJETA`, `TRANSFERENCIA`, `CAJA` |
| fecha_cobro | DATE | fecha del cobro efectivo |
| importe_total | NUMERIC(18,4) | importe total del vencimiento |
| importe_comision | NUMERIC(18,4) DEFAULT 0 | comisión bancaria; >= 0; <= importe_total |
| importe_neto | NUMERIC(18,4) | = importe_total - importe_comision; calculado |
| cuenta_banco | VARCHAR(12) | cuenta bancaria/caja destino (572/570) |
| asiento_cobro_id | UUID FK → SPEC-002 JournalEntry | asiento balanceado generado |
| creado_por / created_at | | auditoría |

**Validaciones**: `importe_neto = importe_total - importe_comision`; `importe_comision >= 0`; `importe_neto >= 0`; el vencimiento debe estar `pendiente` antes de cobrar; el asiento cuadra: Debe 572 (neto) + 626 (comisión) | Haber 430 (total).

**Índices**: `(empresa_id, fecha_cobro)` para consultas por periodo; `(empresa_id, medio_cobro)` para cartera.

## ComisionBancaria (opcional, para tracking detallado)

Registro desglosado de comisiones bancarias asociadas a cobros.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| cobro_medio_id | UUID FK → CobroMedio | |
| banco_codigo | VARCHAR(12) | código de la entidad bancaria |
| tipo_comision | VARCHAR(50) | tipo de comisión (TPV, transferencia, etc.) |
| importe | NUMERIC(18,4) | importe de la comisión |
| porcentaje | NUMERIC(5,2) NULL | porcentaje aplicado (si aplica) |
| cuenta_contable | VARCHAR(12) DEFAULT '626' | cuenta de gasto de comisión |
| creado_por / created_at | | auditoría |

**Validación**: `importe >= 0`; coherente con `CobroMedio.importe_comision`.

## Resumen de relaciones

```
Tercero (SPEC-008) 1 ── n Efecto
Efecto 0..1 ── 1 JournalEntry (asiento_cobro_id)
Efecto 0..1 ── 1 JournalEntry (asiento_impago_id)
Vencimiento (SPEC-011) 1 ── 0..1 CobroMedio
CobroMedio 1 ── 1 JournalEntry (asiento_cobro_id)
CobroMedio 1 ── 0..n ComisionBancaria
```

**Nota**: El efecto es independiente del vencimiento (es un registro propio con su propio ciclo de vida). El `CobroMedio` sí referencia directamente al vencimiento de SPEC-011 para liquidaciones por TPV/transferencia.
