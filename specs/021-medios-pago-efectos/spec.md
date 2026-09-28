# Feature Specification: Medios de Pago y Efectos

**Feature Branch**: `021-medios-pago-efectos`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Cheques, pagarés y letras (emisión, vencimiento, cobro/impago y cartera de efectos); cobro por TPV/tarjeta y transferencia directa; distintos medios de cobro con comisión asociada"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Gestionar la cartera de efectos (Priority: P1)

El usuario emite/registra cheques, pagarés y letras de clientes o proveedores, con fecha de vencimiento y estado. Al vencimiento liquida el efecto (cobro o impago) generando el asiento correspondiente.

**Why this priority**: La cartera de efectos es un activo real que debe estar controlado por fecha y estado.

**Independent Test**: Registrando un efecto y liquidándolo al vencimiento se genera el asiento balanceado y el efecto cambia de estado.

**Acceptance Scenarios**:

1. **Given** un efecto (cheque/pagaré/letra) con vencimiento, **When** el usuario lo cobra al vencimiento, **Then** se genera el asiento (572 contra 431) y el efecto queda cobrado.
2. **Given** una letra que vence sin fondos, **When** se registra el impago, **Then** el efecto queda en estado impagado y el vencimiento del tercero se reabre.

---

### User Story 2 - Registrar cobros por TPV/tarjeta y transferencia (Priority: P2)

El usuario registra un cobro/pago por tarjeta (TPV) o transferencia directa contra un vencimiento, incluyendo la comisión bancaria. El sistema genera el asiento neto (importe - comisión) con la cuenta de comisión.

**Why this priority**: Amplía los medios de cobro habituales del comercio (ONG/reventa).

**Independent Test**: Registrando un cobro por tarjeta con comisión se genera el asiento con el neto y la cuenta de gasto de comisión.

**Acceptance Scenarios**:

1. **Given** un vencimiento de cliente, **When** se cobra por TPV con comisión, **Then** se genera el asiento (572 por el neto, 626 por la comisión, 430 por el total).
2. **Given** una transferencia recibida sin comisión, **When** se concilia, **Then** el cobro cuadra con el saldo del banco.

---

### User Story 3 - Conciliar medios y estados en tesorería (Priority: P2)

El usuario consulta la cartera de efectos y los cobros/pagos por medio para controlar la tesorería y detectar efectos pendientes o impagados.

**Why this priority**: Control de tesorería y previsión de impagos.

**Independent Test**: Consultando la cartera, cada efecto muestra su medio, vencimiento y estado correctos.

**Acceptance Scenarios**:

1. **Given** efectos con distintos estados, **When** se consulta la cartera, **Then** se agrupan por medio y estado (emitido, cobrado, impagado).
2. **Given** un combo de medios (TPV, transferencia, cheque), **When** se consulta el detalle de un cobro, **Then** se muestra el medio y la comisión aplicada.

---

### Edge Cases

- ¿Qué ocurre con un cheque posdatado? → Se registra con vencimiento futuro y no se contabiliza hasta su cobro.
- ¿Qué ocurre con una letra impagada con gastos? → El impago reabre el vencimiento y opcionalmente se contabilizan gastos de devolución.
- ¿Qué ocurre si no se informa la comisión? → Se registra con comisión 0 y queda editable solo antes de contabilizar.
- ¿Qué ocurre si el impago afecta a un ejercicio cerrado? → Se rechaza la gestión en el ejercicio cerrado.

## Requisitos (TODOs numerados)

1. **T-01** Modelo de efectos (cheque, pagaré, letra) con medio, fecha, vencimiento, estado y tercero.
2. **T-02** Liquidación de efectos al cobro/impago con asiento automático (432/431 contra 572/570).
3. **T-03** Cartera de efectos: consulta por medio, estado y vencimiento con filtros.
4. **T-04** Cobros/pagos por TPV/tarjeta y transferencia con comisión asociada y asiento neto (626).
5. **T-05** Reapertura de vencimiento en impagos y registros de gastos de devolución.
6. **T-06** Bloqueo de gestión en ejercicios cerrados.
7. **T-07** Pruebas automáticas (pytest) de efectos, comisiones, impagos y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar la cartera de efectos y los cobros/pagos por medio por empresa y ejercer sobre la empresa activa.
- **FR-002**: El sistema MUST registrar efectos (cheques, pagarés, letras) con medio, tercero, vencimiento y estado, liquidándolos al cobro o impago con asiento balanceado y atómico.
- **FR-003**: El sistema MUST registrar cobros/pagos por TPV/tarjeta y transferencia directa contra vencimientos, con comisión bancaria opcional, generando asiento por el neto y la cuenta de gasto de comisión (626).
- **FR-004**: El sistema MUST ofrecer la cartera de efectos con filtros por medio, estado y fecha, mostrando la información completa de cada efecto.
- **FR-005**: El sistema MUST reabrir el vencimiento del tercero ante un impago y permitir registrar gastos de devolución.
- **FR-006**: El sistema MUST rechazar la gestión de efectos o comisiones que afecten a un ejercicio cerrado (SPEC-002/004).
- **FR-007**: El flujo MUST cumplir la constitución (partida doble, precisión Decimal, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Efecto**: Cheque, pagaré o letra con medio, tercero, vencimiento y estado (emitido, cobrado, impagado).
- **Cartera de efectos**: Vista consolidada de efectos por medio y estado.
- **Cobro/Pago por medio**: Operación con TPV/tarjeta, transferencia o cheque con su comisión.
- **Comisión**: Gasto asociado al medio, contabilizado en cuenta 626.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los efectos liquidados generan un asiento balanceado y actualizan el estado.
- **SC-002**: El 100 % de los cobros por TPV/transferencia con comisión cuadran por el neto.
- **SC-003**: El 100 % de los impagos reabren el vencimiento y quedan trazados.
- **SC-004**: El 100 % de la cartera de efectos se muestra agrupada y filtrable por medio y estado.
- **SC-005**: Los importes se tratan con precisión de 4 decimales sin errores de redondeo.

## Assumptions

- Las cuentas de efectos son 431 (clientes, efectos comerciales a cobrar) y 401/400 prox. de pagos; la comisión se contabiliza en 626 (servicios bancarios y similares).
- El cobro/pago se direcciona al banco 572 o caja 570 configurado por empresa; el registro solo existe tras el cobro efectivo (cheque posdatado se contabiliza en su cobro).
- El impago con gastos requiere la información del banco (R19/C19) y queda registrado como tal.

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-008 (terceros), SPEC-010/011 (vencimientos y estados), SPEC-013 (conciliación bancaria), SPEC-020 (domiciliaciones para verificar saldos).