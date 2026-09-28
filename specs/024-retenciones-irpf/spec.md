# Feature Specification: Retenciones IRPF y Modelos 111/115/190

**Feature Branch**: `024-retenciones-irpf`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Modelos de IRPF/retenciones: 111 y 190 (la retención en factura está en SPEC-007 pero falta su autoliquidación trimestral/anual); modelo 115 (arrendamientos)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Acumular retenciones del periodo e ingresar el modelo 111 (Priority: P1)

El usuario consulta las retenciones IRPF generadas en facturas (SPEC-007) y de alquileres (modelo 115). El sistema acumula por trimestre y genera el modelo 111/115 con la cuota a ingresar (sin el 0/pequeño).

**Why this priority**: La autoliquidación trimestral de retenciones es obligatoria y vence en plazos legales.

**Independent Test**: Consultando retenciones del trimestre se genera el 111 con el importe acumulado y la deuda (4751) cuadrada.

**Acceptance Scenarios**:

1. **Given** facturas de proveedores con retención, **When** se cierra el periodo trimestral, **Then** el modelo 111 acumula las retenciones y el 473/4751 cuadra.
2. **Given** un alquiler con retención, **When** se genera el 115, **Then** se acumula la retención del arrendador.

---

### User Story 2 - Contabilizar la liquidación trimestral (Priority: P2)

El usuario realiza el pago/ingreso de la retención. El sistema genera el asiento (4751 contra 572) y deja el periodo liquidado.

**Why this priority**: Cuadre contable de la deuda con Hacienda.

**Independent Test**: Liquidando el trimestre se genera el asiento de pago de retenciones y el 4751 queda a cero.

**Acceptance Scenarios**:

1. **Given** la autoliquidación del trimestre, **When** se realiza el ingreso, **Then** se genera el asiento 4751 contra 572 y el saldo queda a cero.
2. **Given** una retención del propio periodo pendiente de ingreso, **When** se consulta el 4751, **Then** refleja el saldo deudor o acreedor correcto.

---

### User Story 3 - Generar el modelo 190 anual (Priority: P2)

El usuario genera el modelo 190 con el resumen anual de retenciones e ingresos a cuenta por perceptor.

**Why this priority**: Declaración anual obligatoria de retenciones por perceptor.

**Independent Test**: Generando el 190 se listan los perceptores con sus retenciones anuales.

**Acceptance Scenarios**:

1. **Given** retenciones del ejercicio, **When** se genera el 190, **Then** se agrupa y resume por perceptor.
2. **Given** perceptores sin retención en el periodo, **When** se revisa el 190, **Then** solo aparecen los perceptores con retenciones o codificados.

---

### Edge Cases

- ¿Qué ocurre con una retención de ejercicio anterior liquidada en el actual? → Se asocia al periodo de devengo y el informe muestra ambos periodos.
- ¿Qué ocurre si hay saldo deudor (retenciones a compensar)? → Solo se informa; el ingreso externo se registra contra 4751.
- ¿Qué ocurre si la retención está en factura rectificativa? → Se recalcula desde la rectificativa (SPEC-007).
- ¿Qué ocurre si el perceptor no tiene NIF configurado? → Se bloquea la inclusión en el 190 y se pide el NIF.

## Requisitos (TODOs numerados)

1. **T-01** Acumulación de retenciones por empresa, tercero y periodo desde SPEC-007.
2. **T-02** Modelo 111 trimestral: agregación, deuda 4751 y generación del soporte.
3. **T-03** Modelo 115 (arrendamientos): retención por alquiler y soporte.
4. **T-04** Asiento de liquidación/ingreso (4751 contra 572) y cierre del periodo.
5. **T-05** Modelo 190 anual por perceptor con NIF obligatorio.
6. **T-06** Validación de NIF y bloqueo de perceptores incompletos.
7. **T-07** Pruebas automáticas (pytest) de acumulación, modelos y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar retenciones y liquidaciones por empresa y ejercer sobre la empresa activa.
- **FR-002**: El sistema MUST acumular por periodo (trimestre/año) las retenciones IRPF generadas en facturación (SPEC-007) y alquileres (modelo 115).
- **FR-003**: El sistema MUST generar los soportes de los modelos 111 (trimestral) y 115 con los importes acumulados y la deuda (4751) cuadrada.
- **FR-004**: El sistema MUST generar el asiento de liquidación/ingreso (4751 contra 572) balanceado y atómico, dejando el periodo liquidado.
- **FR-005**: El sistema MUST generar el modelo 190 anual agrupando por perceptor, exigiendo su NIF para su inclusión.
- **FR-006**: El sistema MUST recalcular retenciones desde facturas rectificativas (SPEC-007).
- **FR-007**: El flujo MUST cumplir la constitución (partida doble, precisión Decimal, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Retención**: Importe retenido en cada factura/operación (4751 como acreedor por retenciones).
- **Periodo**: Trimestre natural de la autoliquidación 111/115.
- **Perceptor**: Tercero al que se le han practicado retenciones en el año.
- **Modelo 111/115/190**: Soportes oficiales generados con la información acumulada.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las retenciones del periodo se acumulan sin duplicados en el 111/115.
- **SC-002**: El 100 % de las liquidaciones cuadran el 4751 con el ingreso realizado.
- **SC-003**: El 100 % de los perceptores del 190 tienen NIF y sus retenciones anuales coinciden con las trimestrales.
- **SC-004**: El 100 % de las rectificativas recalculan la retención del periodo.
- **SC-005**: Los importes se tratan con precisión de 4 decimales sin errores de redondeo (la retención suele tener 2 decimales, coherentes con la factura).

## Assumptions

- La retención IRPF de proveedores/arrendamientos ya se calcula en SPEC-007; esta feature acumula, liquida y declara.
- Los tipos de retención se configuran por empresa y régimen (general, arrendamiento) con vigencia.
- El caso de la autoliquidación declarada con resultado 0 (contribuyentes sin cuota) se gestiona como configuración por empresa.
- La presentación telemática queda fuera de alcance; se generan soportes estándar descargables.

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-007 (facturación y retenciones), SPEC-008 (terceros/NIF), SPEC-023 (IS para el cruce de saldos con Hacienda).