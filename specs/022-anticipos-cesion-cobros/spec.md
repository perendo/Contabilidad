# Feature Specification: Anticipos, Fondos a Cuenta y Cesión de Cobros

**Feature Branch**: `022-anticipos-cesion-cobros`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Anticipos y fondos a cuenta: cobros/pagos por anticipado con liquidación posterior contra factura (cuentas 438/407); confirming/factoring/cesión de cobros a terceros con notificación"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar un anticipo de cliente y liquidarlo (Priority: P1)

El usuario cobra por anticipado a un cliente (fondo a cuenta). El sistema registra el cobro en la cuenta de anticipos de clientes y al emitir la factura lo liquida contra la deuda.

**Why this priority**: Los anticipos son habituales en la ONG (cursos, subvenciones a justificar) y afectan el cuadre de deuda.

**Independent Test**: Cobrando un anticipo y emitiendo luego la factura, el anticipo se aplica como pago parcial de la deuda.

**Acceptance Scenarios**:

1. **Given** un anticipo de cliente, **When** se cobra, **Then** se registra en la cuenta 438 (anticipos de clientes) con su asiento.
2. **Given** una factura posterior, **When** se aplica el anticipo, **Then** la deuda residual es la diferencia y queda trazada la liquidación.

---

### User Story 2 - Registrar un anticipo a proveedor y liquidarlo (Priority: P1)

El usuario paga por anticipado a un proveedor (fondos a cuenta). El sistema lo registra en 407/408 y lo liquida contra las facturas de compra posteriores.

**Why this priority**: Los proveedores con pre-pagos necesitan cuadre exacto contra las facturas recibidas.

**Independent Test**: Pagando un anticipo y recibiendo la factura de compra, el anticipo reduce la deuda y el resto se paga.

**Acceptance Scenarios**:

1. **Given** un anticipo a proveedor, **When** se paga, **Then** se registra en 407/408 con su asiento.
2. **Given** la factura de compra posterior, **When** se aplica el anticipo, **Then** el saldo pendiente es la diferencia.

---

### User Story 3 - Ceder cobros (confirming/factoring) con notificación (Priority: P2)

El usuario cede cobros de clientes a una entidad (factoring/confirming). El sistema registra la cesión, la notificación al cliente y la comisión de la operación.

**Why this priority**: Financiación externa sobre cuentas a cobrar.

**Independent Test**: Cediendo un cobro con notificación se registra la cesión y el cliente queda notificado.

**Acceptance Scenarios**:

1. **Given** un vencimiento elegible, **When** se cede a factoring con comisión, **Then** se registra la cesión y la notificación al cliente.
2. **Given** la cesión registrada, **When** la entidad cobra al cliente, **Then** el vencimiento original se salda sin doble cobro.

---

### Edge Cases

- ¿Qué ocurre si el anticipo supera la factura? → El exceso queda como saldo a favor del cliente/proveedor (nosotros/ellos).
- ¿Qué ocurre si se factura antes de cobrar el anticipo? → Podría quedar deuda negativa; se permite solo como excepcionalidad controlada y se documenta.
- ¿Qué ocurre si el anticipo es de ejercicio cerrado? → Se rechaza su gestión en el ejercicio cerrado.
- ¿Qué ocurre con una cesión de un vencimiento ya saldado? → Se rechaza; solo se ceden vencimientos pendientes.

## Requisitos (TODOs numerados)

1. **T-01** Registro de anticipos de clientes (438) y proveedores (407/408) con asiento automático (SPEC-002).
2. **T-02** Liquidación de anticipos contra facturas con trazabilidad de aplicación.
3. **T-03** Control de excesos: saldo a favor residual tras liquidar la factura.
4. **T-04** Cesión de cobros (factoring/confirming): registro, comisión y notificación al cliente.
5. **T-05** Saldo único de vencimientos cedidos para evitar doble cobro.
6. **T-06** Bloqueo de gestión en ejercicios cerrados.
7. **T-07** Pruebas automáticas (pytest) de anticipos, cesiones y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar anticipos, cesiones y sus aplicaciones por empresa y ejercer sobre la empresa activa.
- **FR-002**: El sistema MUST registrar anticipos de clientes (438) y proveedores (407/408) generando su asiento balanceado y atómico, y aplicarlos contra las facturas posteriores con trazabilidad.
- **FR-003**: El sistema MUST permitir el exceso residual cuando el anticipo supera la factura, mostrándolo como saldo a favor del tercero.
- **FR-004**: El sistema MUST registrar cesiones de cobro (factoring/confirming) solo sobre vencimientos pendientes, con su comisión y la notificación al cliente.
- **FR-005**: El sistema MUST impedir el doble cobro de un vencimiento cedido, saldándolo cuando la entidad cobra al cliente.
- **FR-006**: El sistema MUST rechazar la gestión de anticipos o cesiones que afecten a un ejercicio cerrado (SPEC-002/004).
- **FR-007**: El flujo MUST cumplir la constitución (partida doble, precisión Decimal, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Anticipo**: Cobro/pago por anticipado frente a futuras facturas (438 / 407-408).
- **Liquidación**: Aplicación de un anticipo contra una o varias facturas.
- **Cesión**: Transferencia del derecho de cobro a una entidad con comisión y notificación.
- **Notificación**: Comunicación registrada al cliente de que su deuda ha sido cedida.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los anticipos generan su asiento y se aplican contra las facturas correctas.
- **SC-002**: El 100 % de los excesos quedan identificados como saldo a favor del tercero.
- **SC-003**: El 100 % de las cesiones solo aceptan vencimientos pendientes y evitan el doble cobro.
- **SC-004**: El 100 % de las cesiones registran su comisión y notificación.
- **SC-005**: Los importes se tratan con precisión de 4 decimales sin errores de redondeo.

## Assumptions

- Las cuentas de anticipos son 438 (anticipos de clientes), 407 (anticipos a proveedores) y 408 (acreedores por operaciones pendientes de facturar).
- La liquidación de anticipos se hace explícita por el usuario contra una factura (o se detecta automáticamente si coincide el importe).
- La cesión de cobros es informativa y de financiación; el riesgo de insolvencia y la contabilización de la comisión (intereses 6622/669) siguen las cuentas estándar del plan.

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-007 (facturación), SPEC-008 (terceros), SPEC-011 (vencimientos y cobros), SPEC-021 (medios de pago para el desembolso inicial).