# Research: Anticipos, Fondos a Cuenta y Cesión de Cobros (SPEC-022)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Cuentas PGC para anticipos

- **Decision**: **438** (anticipos de clientes) para cobros por anticipado; **407** (anticipos a proveedores) para pagos por anticipado; **408** (acreedores por operaciones pendientes de facturar) cuando el anticipo no tiene factura asociada. El asiento de anticipo de cliente: Debe 572 (cobro) | Haber 438 (anticipo). El asiento de anticipo a proveedor: Debe 407/408 (anticipo) | Haber 572 (pago).
- **Rationale**: Coherente con las assumptions del spec y el PGC español.
- **Alternatives considered**: Usar 430 en lugar de 438 (confunde con la deuda normal; se necesita separar el anticipo para control de saldos). Se descarta.

## D2. Liquidación de anticipos contra facturas

- **Decision**: La liquidación es **explícita** por el usuario: selecciona un anticipo y una factura, y el sistema crea el asiento de aplicación. Asiento: Debe 430 (factura) | Haber 438 (anticipo) por el importe aplicado. Si el anticipo supera la factura, el exceso queda como saldo en 438 (o 407). La liquidación se registra en `LiquidacionAnticipo` con trazabilidad del anticipo, factura e importe aplicado.
- **Rationale**: La liquidación explícita da control total al usuario; la trazabilidad permite auditar cada aplicación. Cumple FR-002 y FR-003.
- **Alternatives considered**: Liquidación automática al emitir factura (pierde control; dificulta escenarios parciales).

## D3. Control de excesos (anticipo > factura)

- **Decision**: Si el anticipo supera la factura, el exceso queda como **saldo a favor** del tercero en la cuenta 438 (cliente) o 407 (proveedor). La liquidación registra el importe aplicado y el saldo residual. El usuario puede consultar el saldo de anticipos no aplicados.
- **Rationale**: Cumple FR-003; el saldo residual es un activo/pasivo real que debe reflejarse.
- **Alternatives considered**: Rechazar la liquidación si hay exceso (poco práctico); crear asiento de devolución automática (excesiva complejidad).

## D4. Cesión de cobros (factoring/confirming)

- **Decision**: La cesión registra la transferencia del derecho de cobro a una entidad financiera. Asiento de cesión: Debe 572 (importe cobrado por la entidad) + 662/6622 (comisión de factoring) | Haber 430 (vencimiento cedido). El vencimiento pasa a estado `cedido` y no puede cobrarse de nuevo (evita doble cobro). Cuando la entidad cobra al cliente, se salda el vencimiento con la notificación.
- **Rationale**: La comisión de factoring se contabiliza como gasto financiero (662/6622 según PGC); la cesión genera un efecto real sobre la deuda.
- **Alternatives considered**: Cesión solo informativa sin asiento (no refleja la realidad económica); cesión como descuento comercial (confunde con pronto pago).

## D5. Notificación al cliente

- **Decision**: La notificación es un **registro** en `NotificacionCesion` con fecha, medio (email/correo/registro) y estado (pendiente/enviada). No genera asiento; es informativa para trazabilidad. La notificación es opcional en MVP pero se registra siempre.
- **Rationale**: La notificación es un requisito legal del factoring; su registro permite auditoría.
- **Alternatives considered**: Generación automática de email (excesiva complejidad para MVP); sin registro (pierde trazabilidad).

## D6. Impedir doble cobro de vencimiento cedido

- **Decision**: Un vencimiento en estado `cedido` no puede cobrarse ni cederse de nuevo. El estado se actualiza en la misma transacción que la cesión. Si la entidad cobra al cliente, se crea un `CobroEntidad` que salda el vencimiento y genera el asiento correspondiente.
- **Rationale**: Cumple FR-005; el doble cobro es un riesgo financiero crítico.
- **Alternatives considered**: Marca booleana `cedido` en el vencimiento (menos expresivo que un estado propio); se descarta.

## D7. Cesión solo sobre vencimientos pendientes

- **Decision**: El endpoint de cesión valida que todos los vencimientos seleccionados estén en estado `pendiente` y pertenezcan a la empresa activa. Si alguno no es elegible, la operación falla atómicamente (no se cede ninguno).
- **Rationale**: Cumple FR-004; la cesión parcial exitosa con rechazos parciales es un escenario de error complejo; se simplifica a operación atómica.
- **Alternatives considered**: Cesión parcial con lista de rechazos (añade complejidad; se difiere a evolución).

## D8. Comisión de cesión (intereses y gastos)

- **Decision**: La comisión se registra como parte del asiento de cesión en la cuenta **662** (descuentos concedidos) o **6622** (intereses de descuentos). El importe de comisión es configurable por operación (importe fijo o porcentaje del vencimiento). El neto recibido = importe del vencimiento - comisión.
- **Rationale**: La comisión de factoring es un gasto financiero estándar del PGC.
- **Alternatives considered**: Cuenta separada 669 (gastos financieros diversos); se mantiene como alternativa si la empresa lo configura.

## D9. Liquidación de anticipos a proveedores

- **Decision**: El flujo es simétrico al de clientes: Debe 407 (anticipo) | Haber 572 (pago) al registrar el anticipo; al aplicar contra factura: Debe 410 (factura proveedor) | Haber 407 (anticipo). Si el anticipo es mayor que la factura, el exceso queda en 407 como saldo acreedor.
- **Rationale**: Simetría con el flujo de clientes; cuentas 407/408 son estándar del PGC.
- **Alternatives considered**: Servicios separados para clientes y proveedores (duplica lógica); se unifica con parámetro tipo.

## D10. Bloqueo de ejercicios cerrados

- **Decision**: Todo método de servicio que cree o modifique anticipos, liquidaciones o cesiones verifica que el ejercicio del documento esté abierto (SPEC-002/004). Si está cerrado → rechazo 409 con mensaje `ejercicio_cerrado`.
- **Rationale**: Cumple FR-006 del spec y la constitución (inmutabilidad del ejercicio cerrado).
- **Alternatives considered**: Permitir con etiqueta de ajuste extraordinario (excesiva complejidad para MVP).
