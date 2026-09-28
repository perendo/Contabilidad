# Research: Medios de Pago y Efectos (SPEC-021)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Ciclo de vida de los efectos (cheques, pagarés, letras)

- **Decision**: Los efectos pasan por los estados `emitido → cobrado | impagado`. Un efecto se **emite/registra** con fecha de vencimiento; al vencer se **liquida** (cobro → asiento 572 vs 431, o impago → REVERSAL y reapertura del vencimiento). Los estados son mutuamente excluyentes (un efecto no puede ser cobrado e impagado a la vez).
- **Rationale**: La simplificación de estados minimiza la complejidad y cubre los escenarios de SPEC-021. La Liquidación = movimiento de caja/banco, que puede ocurrir en la fecha de vencimiento o antes.
- **Alternatives considered**: Estados intermedios como `en_cartera` o `protestado` (añaden complejidad innecesaria en MVP); integración con el módulo de remesas SPEC-020 (se mantiene como referencia, no se fusiona).

## D2. Cuentas PGC para efectos

- **Decision**: **431** (clientes, efectos comerciales a cobrar) para efectos de clientes; **401** (proveedores, efectos comerciales a pagar) para efectos de proveedores. Cobro → **572** (banco) o **570** (caja). Comisión bancaria → **626** (servicios bancarios). Impago → REVERSAL de 572/570 contra 431, reapertura del vencimiento.
- **Rationale**: Coherente con las cuentas del PGC y las assumptions del spec. La cuenta 431 es estándar para letras y pagarés a cobrar.
- **Alternatives considered**: Usar 430 en lugar de 431 (confunde con la deuda normal del cliente; se usa 431 para distinguir efectos). Se descarta.

## D3. Comisiones por TPV/tarjeta y transferencia

- **Decision**: Las comisiones se registran como parte del asiento de cobro: **Debe 572** (neto cobrado) + **Debe 626** (comisión bancaria) | **Haber 430** (total del vencimiento). La comisión es opcional (DEFAULT 0); se edita solo antes de contabilizar. El neto = importe total - comisión; neto >= 0 siempre.
- **Rationale**: La comisión es un gasto real que reduce el cobro neto; el asiento con 626 es el tratamiento PGC estándar.
- **Alternatives considered**: Asiento separado por comisión (pierde atomicidad del cobro); comisión como porcentaje configurable (en MVP, se permite importe fijo y porcentaje).

## D4. Cobro por TPV/tarjeta vs transferencia

- **Decision**: Ambos se registran como **cobro por medio** con un campo `medio_cobro` (ENUM: `CHEQUE`, `PAGARE`, `LETRA`, `TARJETA`, `TRANSFERENCIA`, `CAJA`). La lógica de asiento es la misma; solo varía si hay comisión (tarjeta siempre puede tener comisión; transferencia puede o no tenerla).
- **Rationale**: Unificar la lógica de cobro simplifica el código; el medio es metadata informativa para la cartera.
- **Alternatives considered**: Servicios separados por medio (duplica lógica de asiento); se descarta.

## D5. Reapertura de vencimiento en impagos

- **Decision**: Al registrar un impago, el vencimiento del tercero (SPEC-011) vuelve a estado `pendiente` y se crea un asiento `REVERSAL` del cobro (inmutabilidad II): **Debe 431** (importe total) | **Haber 572/570** (importe cobrado). Si hay gastos de devolución → Debe 431 + 626 | Haber 572/570. El asiento original del cobro NO se modifica.
- **Rationale**: Cumple la constitución II (inmutabilidad); cualquier impago debe revertirse con un asiento nuevo balanceado y trazable.
- **Alternatives considered**: Modificar el asiento original (viola inmutabilidad); solo informativo sin asiento (deja descuadrado el 431).

## D6. Cartera de efectos (vista consolidada)

- **Decision**: La cartera es una **consulta (read-only)** que agrupa efectos por `medio_pago`, `estado` y `fecha_vencimiento`, con filtros por empresa, tercero, estado y rango de fechas. No genera asientos; solo presenta información consolidada.
- **Rationale**: La cartera es una herramienta de control de tesorería, no una operación contable.
- **Alternatives considered**: Vista materializada (premature optimization en MVP); cartera como tabla separada (duplica datos).

## D7. Cheques posdatados

- **Decision**: Un cheque posdatado se **registra** con `fecha_vencimiento` futura y estado `emitido`; no se contabiliza hasta su **cobro efectivo** en la fecha de vencimiento. Mientras tanto, solo es visible en la cartera como pendiente.
- **Rationale**: Coherente con las assumptions del spec; el efecto solo tiene impacto contable al cobrarse.
- **Alternatives considered**: Contabilizar al registrar (infla el activo antes de tiempo); se descarta.

## D8. Impagos con gastos de devolución

- **Decision**: Los gastos de devolución se contabilizan en la misma transacción que el REVERSAL del impago: **Debe 431** (importe total) + **Debe 626** (gastos devolución) | **Haber 572/570** (importe + gastos). La información del banco (R19/C19) se asocia al efecto si se recibe.
- **Rationale**: Atomicidad del asiento de impago; trazabilidad de gastos.
- **Alternatives considered**: Gastos en asiento separado (pierde atomicidad y dificulta el cuadre).

## D9. Bloqueo de ejercicios cerrados

- **Decision**: Todo método de servicio que cree o modifique efectos, comisiones o asientos de cobro/impago verifica que el ejercicio del `fecha_vencimiento` esté abierto (SPEC-002/004). Si está cerrado → rechazo 409 con mensaje `ejercicio_cerrado`.
- **Rationale**: Cumple FR-006 del spec y la constitución (inmutabilidad del ejercicio cerrado).
- **Alternatives considered**: Permitir con etiqueta de ajuste extraordinario (excesiva complejidad para MVP).

## D10. Multi-tenancy y auditoría

- **Decision**: Cada operación de efectos se persiste con `empresa_id` derivado de la sesión autenticada, en la misma transacción ACID. Se registra audit log (actor, timestamp UTC, IP, acción, payload como strings `Decimal`) en la misma transacción. El `empresa_id` nunca se envía en el body del request.
- **Rationale**: Cumple constituciones III y auditoría inmutable.
- **Alternatives considered**: Audit log en tabla separada con commit independiente (rompe atomicidad).
