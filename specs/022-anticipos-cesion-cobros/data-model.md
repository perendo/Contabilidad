# Data Model: Anticipos, Fondos a Cuenta y Cesión de Cobros (SPEC-022)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## Anticipo

Cobro o pago por anticipado frente a futuras facturas (438 / 407-408).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta; FK → empresa (SPEC-003) |
| tercero_id | UUID FK → SPEC-008 Tercero | cliente o proveedor |
| tipo | ENUM | `CLIENTE` (anticipo recibido) / `PROVEEDOR` (anticipo pagado) |
| cuenta_contable | VARCHAR(12) | 438 (cliente) o 407/408 (proveedor) según tipo |
| fecha | DATE | fecha del anticipo |
| importe | NUMERIC(18,4) | importe del anticipo; > 0 |
| concepto | VARCHAR(255) | descripción del anticipo |
| estado | ENUM | `pendiente`, `parcialmente_aplicado`, `totalmente_aplicado` |
| saldo_pendiente | NUMERIC(18,4) | = importe - suma(liquidaciones); calculado, >= 0 |
| asiento_id | UUID FK → SPEC-002 JournalEntry | asiento de registro del anticipo |
| notas | TEXT | |
| creado_por / created_at | | auditoría |

**Validaciones**: `saldo_pendiente >= 0` siempre; `saldo_pendiente = importe - SUM(LiquidacionAnticipo.importe_aplicado)`; ejercicio abierto en `fecha`.

**Transiciones de estado**: `pendiente → parcialmente_aplicado` (al aplicar parcialmente) | `parcialmente_aplicado → totalmente_aplicado` (al agotar saldo) | `pendiente → totalmente_aplicado` (al aplicar de golpe).

**Índices**: `(empresa_id, tercero_id, tipo)` para consultas por tercero; `(empresa_id, estado)` para saldos pendientes.

## LiquidacionAnticipo

Aplicación de un anticipo contra una o varias facturas con trazabilidad.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| anticipo_id | UUID FK → Anticipo | anticipo aplicado |
| factura_id | UUID FK → SPEC-007 Factura | factura contra la que se aplica |
| fecha_aplicacion | DATE | fecha de la liquidación |
| importe_aplicado | NUMERIC(18,4) | importe del anticipo aplicado a esta factura; > 0; <= saldo pendiente del anticipo |
| asiento_id | UUID FK → SPEC-002 JournalEntry | asiento de liquidación (Debe 430/410 | Haber 438/407) |
| notas | TEXT | |
| creado_por / created_at | | auditoría |

**Validaciones**: `importe_aplicado > 0`; `importe_aplicado <= Anticipo.saldo_pendiente`; ejercicio abierto; la suma de liquidaciones de un anticipo <= importe del anticipo.

## CesionCobro

Transferencia del derecho de cobro a una entidad financiera (factoring/confirming).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| entidad_financiera | VARCHAR(100) | nombre de la entidad de factoring |
| fecha_cesion | DATE | fecha de la cesión |
| comision | NUMERIC(18,4) DEFAULT 0 | comisión de la operación; >= 0 |
| tipo_comision | ENUM | `IMPORTE_FIJO`, `PORCENTAJE` |
| importe_total_cedido | NUMERIC(18,4) | suma de vencimientos cedidos |
| importe_neto_recibido | NUMERIC(18,4) | = importe_total_cedido - comision; calculado |
| estado | ENUM | `activa`, `saldada`, `cancelada` |
| asiento_id | UUID FK → SPEC-002 JournalEntry | asiento de cesión (Debe 572+662 | Haber 430) |
| notas | TEXT | |
| creado_por / created_at | | auditoría |

**Validaciones**: `comision >= 0`; `importe_neto_recibido = importe_total_cedido - comision`; al menos un vencimiento asociado; todos los vencimientos en estado `pendiente`.

## CesionCobroDetalle

Vencimientos incluidos en una cesión (relación N:N entre cesión y vencimiento).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| cesion_id | UUID FK → CesionCobro | |
| vencimiento_id | UUID FK → SPEC-011 Vencimiento | único por cesión; vencimiento debe estar `pendiente` |
| importe | NUMERIC(18,4) | importe del vencimiento cedido |

**Validaciones**: un vencimiento solo puede estar en una cesión activa (constraint de unicidad parcial).

## NotificacionCesion

Registro de la notificación al cliente sobre la cesión.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| cesion_id | UUID FK → CesionCobro | |
| cliente_id | UUID FK → SPEC-008 Tercero | cliente notificado |
| fecha_notificacion | DATE | fecha de envío/registro |
| medio | ENUM | `EMAIL`, `CORREO`, `REGISTRO` |
| estado | ENUM | `pendiente`, `enviada` |
| notas | TEXT | |
| creado_por / created_at | | auditoría |

## Resumen de relaciones

```
Tercero (SPEC-008) 1 ── n Anticipo
Anticipo 1 ── n LiquidacionAnticipo
Factura (SPEC-007) 1 ── n LiquidacionAnticipo
Anticipo 1 ── 1 JournalEntry (asiento_id)
LiquidacionAnticipo 1 ── 1 JournalEntry (asiento_id)
CesionCobro 1 ── n CesionCobroDetalle
Vencimiento (SPEC-011) 1 ── n CesionCobroDetalle
CesionCobro 1 ── 1 JournalEntry (asiento_id)
CesionCobro 1 ── n NotificacionCesion
```
