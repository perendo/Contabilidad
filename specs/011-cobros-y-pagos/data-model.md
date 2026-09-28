# Data Model: Vencimientos, Cobros y Pagos (SPEC-011)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitucion):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` en PK/indices y filtros; se deriva de sesion.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoria en la misma transaccion ACID.
- Numeracion correlativa por (empresa_id, ejercicio) asignada atomicamente.

## Vencimiento

Fecha e importe de cobro/pago de una factura (SPEC-007) o compra, con su estado.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta |
| numero_vencimiento | BIGINT | correlativo por (empresa_id, ejercicio) |
| ejercicio | INT | ejercicio fiscal de la fecha de vencimiento |
| factura_id | UUID FK → SPEC-007 Factura | factura de origen |
| tercero_id | UUID FK → SPEC-008 Tercero | cliente o proveedor |
| tipo | ENUM | `cobro` / `pago` |
| fecha_vencimiento | DATE | |
| importe | NUMERIC(18,4) | > 0 |
| acumulado | NUMERIC(18,4) DEFAULT 0 | suma de cobros/pagos registrados |
| estado | ENUM | `pendiente`, `parcial`, `cobrado`, `remesado` |
| remesa_id | UUID FK NULL → Remesa | si esta remesado |
| saldo_pendiente | NUMERIC(18,4) | `importe - acumulado` (generado o calculado) |

**Validaciones**: `importe > 0`; `acumulado <= importe` (check DB); estado coherente con acumulado (si acumulado==importe -> cobrado; si 0<acumulado<importe -> parcial); un vencimiento solo se remesa si esta `pendiente` o `parcial`; el ejercicio de la fecha no puede ser cerrado.

**Transiciones de estado**: `pendiente → parcial` (primer parcial sin completar) | `pendiente/parcial → cobrado` (acumulado == importe) | `pendiente/parcial → remesado` (incluido en remesa emitida; el cobro se confirma mas tarde) | `remesado → cobrado` (marcado por SPEC-020).

## CobroPago

Operacion registrada (total o parcial) que genera su asiento contra tesoreria.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| numero_operacion | BIGINT | correlativo por (empresa_id, ejercicio) |
| vencimiento_id | UUID FK → Vencimiento | |
| fecha | DATE | dentro del ejercicio abierto |
| tipo | ENUM | `cobro` / `pago` |
| importe | NUMERIC(18,4) | > 0; el acumulado del vencimiento no debe superar el importe |
| cuenta_tesoreria | VARCHAR(20) | cuenta 572/570 configurada por empresa (default 572 banco, 570 caja) |
| journal_entry_id | UUID FK → SPEC-002 JournalEntry | asiento del cobro/pago (POSTED) |
| created_at / created_by / ip | | auditoria inmutable |

**Validaciones**: suma(importe <= vencimiento.importe - vencimiento.acumulado) en tuplas anteriores; journal_entry_id no nulo y el asiento esta `POSTED`; no se permite UPDATE/DELETE tras crear (inmutabilidad asiento).

## Remesa (agrupacion)

Agrupacion de vencimientos para cobro o pago con estado y trazabilidad. La generacion de ficheros SEPA/CSB 19.19 pertenece a SPEC-020.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| numero_remesa | BIGINT | correlativo por (empresa_id, ejercicio); asignado atomicamente |
| ejercicio | INT | |
| tipo | ENUM | `cobro` / `pago` |
| fecha_creacion | DATE | |
| fecha_cargo_prevista | DATE NULL | fecha de cargo estimada (la valida SPEC-020) |
| estado | ENUM | `borrador`, `emitida` |
| n_vencimientos | INT | contador de vencimientos miembro |
| importe_total | NUMERIC(18,4) | suma de saldos pendientes de los vencimientos incluidos |
| creado_por / created_at | | auditoria |

**Validaciones**: un vencimiento solo pertenece a una remesa no emitida o a una remesa ya emitida sin cobrar (el alta en remesa emitida queda fuera de 011); importe_total > 0.

**Transiciones de estado**: `borrador → emitida` (pasa estado de vencimientos a `remesado`) | la confirmacion de cobro de una remesa emitida se gestiona en SPEC-020.

## Informe de Antiguedad de Saldos (informe calculado)

No se persiste; se calcula bajo demanda. Para cada tercero con saldo pendiente:

| Campo | Tipo | Reglas |
|-------|------|--------|
| tercero_id | UUID FK → SPEC-008 | |
| saldo_total_pendiente | NUMERIC(18,4) | suma de saldos de vencimientos no saldados |
| rango_30 | NUMERIC(18,4) | saldo de vencimientos con 0-29 dias desde fecha_vencimiento |
| rango_60 | NUMERIC(18,4) | 30-59 dias |
| rango_90 | NUMERIC(18,4) | 60-89 dias |
| rango_90mas | NUMERIC(18,4) | 90+ dias |
| vencimientos[] | JSONB | detalle de vencimientos del tercero |

**Validacion**: suma de rangos == saldo_total_pendiente (verificado en backend con Decimal); solo empresa activa.

## Resumen de relaciones

```
Factura (SPEC-007) 1 ── n Vencimiento (por linea/fecha de pago)
Tercero (SPEC-008) 1 ── n Vencimiento
Tercero (SPEC-008) 1 ── n Saldos antiguedad (informe)
Vencimiento 1 ── n CobroPago
Remesa 1 ── n Vencimiento (remesa_id)
Vencimiento 1 ── n CobroPago → JournalEntry (SPEC-002)
Exportacion especifica (vencimientos): Vencimiento (SPEC-011) 1 ── 0..1 ReciboRemesa (SPEC-020)
```