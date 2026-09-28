# Feature Specification: Vencimientos, Cobros y Pagos

**Feature Branch**: `011-cobros-y-pagos`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Gestión de vencimientos de facturas, cobros y pagos (incluidos parciales), remesas e informe de antigüedad de saldos"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cobrar el vencimiento de una factura (Priority: P1)

El usuario cobra el vencimiento de una factura de cliente. El sistema registra el vencimiento cobrado, genera el asiento de pago (banco/caja contra deuda del tercero) y actualiza el saldo pendiente.

**Why this priority**: Sin cobros/pagos no existe la gestión de tesorería y el cierre quedaría incompleto.

**Independent Test**: Cobrando un vencimiento se genera el asiento de pago balanceado y el saldo pendiente del cliente baja.

**Acceptance Scenarios**:

1. **Given** una factura emitida con vencimiento, **When** el usuario cobra el vencimiento, **Then** se genera el asiento de pago y el vencimiento queda cobrado.
2. **Given** un vencimiento cobrado al 100 %, **When** se consulta la factura, **Then** el saldo pendiente es cero y no puede volver a cobrarse.

---

### User Story 2 - Registrar cobros y pagos parciales (Priority: P1)

El usuario registra cobros/pagos parciales de un vencimiento. El sistema acumula los parciales sin exceder el importe del vencimiento y cierra el vencimiento cuando el acumulado lo iguala.

**Why this priority**: Los pagos a plazos son habituales y deben cuadrar con precisión.

**Independent Test**: Registrando parciales de un vencimiento, el acumulado nunca supera el importe y al igualarlo el vencimiento queda saldado.

**Acceptance Scenarios**:

1. **Given** un vencimiento de importe X, **When** se registran parciales que suman X, **Then** el vencimiento queda saldado sin exceder el importe.
2. **Given** un intento de cobrar más que el saldo pendiente, **When** se envía, **Then** el sistema rechaza el exceso.

---

### User Story 3 - Emitir remesas e informes de antigüedad (Priority: P2)

El usuario agrupa vencimientos en remesas de cobro/pago con estado y trazabilidad (la generación de ficheros de domiciliación SEPA/CSB 19.19 la cubre SPEC-020) y consulta el informe de antigüedad de saldos por tercero (a 30/60/90+ días).

**Why this priority**: Gestión de tesorería y control de morosidad.

**Independent Test**: Emitiendo una remesa y consultando la antigüedad, los vencimientos se agrupan correctamente y el informe clasifica los saldos por rango.

**Acceptance Scenarios**:

1. **Given** varios vencimientos pendientes, **When** el usuario crea una remesa, **Then** se agrupan y marcan en remesa con su estado.
2. **Given** saldos con fechas distintas, **When** se consulta la antigüedad, **Then** se clasifican en los rangos correctos.

---

### Edge Cases

- ¿Qué ocurre si el medio es caja en vez de banco? → Se direcciona el asiento a la cuenta de caja correspondiente.
- ¿Qué ocurre si un parcial deja decimales por redondeo? → Se exige precisión exacta y el cierre del vencimiento solo al igualar.
- ¿Qué ocurre si un vencimiento pertenece a ejercicio cerrado? → Se rechaza la gestión en el ejercicio cerrado.
- ¿Qué ocurre con las rectificativas que ajustan vencimientos? → Los vencimientos se recalculan desde la factura rectificativa (SPEC-007).

## Requisitos (TODOs numerados)

1. **T-01** Modelo de vencimientos por factura/tercero con estados (pendiente, parcial, cobrado, remesado).
2. **T-02** Registro de cobros/pagos con asiento automático (SPEC-002) contra deuda de tercero.
3. **T-03** Soportar parciales acumulados sin exceder el vencimiento.
4. **T-04** Remesas de cobro y pago con estado y trazabilidad (los ficheros de domiciliación se generan en SPEC-020).
5. **T-05** Informe de antigüedad de saldos por tercero y rango.
6. **T-06** Bloqueo de gestión en ejercicios cerrados.
7. **T-07** Pruebas automáticas (pytest) de parciales, asientos y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar vencimientos, cobros y pagos por empresa y ejercer sobre la empresa activa.
- **FR-002**: El sistema MUST generar los vencimientos de cada factura y gestionar sus estados (pendiente, parcial, cobrado, remesado).
- **FR-003**: El sistema MUST registrar cobros y pagos generando el asiento contable vinculado de forma balanceada y atómica.
- **FR-004**: El sistema MUST acumular cobros/pagos parciales sin exceder el importe del vencimiento, saldándolo al igualarlo.
- **FR-005**: El sistema MUST agrupar vencimientos en remesas de cobro o pago con estado trazable (la generación de ficheros de domiciliación la cubre SPEC-020).
- **FR-006**: El sistema MUST calcular el informe de antigüedad de saldos por tercero y rango de antigüedad.
- **FR-007**: El sistema MUST rechazar la gestión de vencimientos cuyo asiento afecte a un ejercicio cerrado (SPEC-002/004).
- **FR-008**: El flujo MUST cumplir la constitución (partida doble, precisión, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Vencimiento**: Fecha e importe de cobro/pago de una factura con su estado.
- **Cobro/Pago**: Operación registrada que genera su asiento contra la cuenta de tesorería (572/570).
- **Remesa**: Agrupación de vencimientos emitidos para cobro o pago.
- **Antigüedad de saldos**: Informe que clasifica el saldo pendiente de cada tercero por rango de fechas.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los cobros/pagos generan un asiento balanceado y actualizan el saldo pendiente.
- **SC-002**: El 100 % de los parciales no superan el importe del vencimiento.
- **SC-003**: El 100 % de las operaciones de tesorería se realizan solo en ejercicios abiertos.
- **SC-004**: El 100 % de las remesas y antigüedades se calculan correctamente por empresa.
- **SC-005**: Los importes se tratan con precisión de 4 decimales sin errores de redondeo.

## Assumptions

- Los vencimientos se generan en la facturación (SPEC-007) y en la compra; esta feature gestiona su cobro/pago.
- La cuenta de tesorería por defecto es 572 (banco) o 570 (caja), configurable por empresa.
- Esta feature agrupa vencimientos en remesas de cobro/pago; los ficheros SEPA/CSB 19.19 y su validación de plazos los cubre SPEC-020.

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-007 (facturación), SPEC-008 (terceros), SPEC-013 (conciliación bancaria).