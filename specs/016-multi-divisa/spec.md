# Feature Specification: Multi-Divisa

**Feature Branch**: `016-multi-divisa`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Multi-divisa: moneda funcional por empresa, tipos de cambio por fecha, importes en divisa y contable, y diferencias de cambio"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Asentar operaciones en moneda extranjera (Priority: P1)

El usuario registra un asiento en una divisa distinta de la moneda funcional de su empresa. El sistema almacena el importe en divisa y el equivalente en moneda funcional con el tipo de cambio de la fecha, manteniendo la partida doble balanceada en ambas.

**Why this priority**: La actividad internacional requiere registrar divisas sin romper el cuadre contable.

**Independent Test**: Registrando un asiento en divisa con su tipo de cambio, el asiento cuadra en divisa y en moneda funcional.

**Acceptance Scenarios**:

1. **Given** una empresa con moneda funcional y un tipo de cambio para la fecha, **When** se registra un asiento en divisa, **Then** se guardan importe en divisa y funcional, y cuadran ambas columnas.
2. **Given** la consulta del asiento, **When** se visualiza, **Then** muestran la divisa, el tipo de cambio y el equivalente funcional.

---

### User Story 2 - Valorar saldos en divisa a cierre (diferencias de cambio) (Priority: P2)

Al cierre de un ejercicio o período, el contador valora los saldos en divisa pendientes con el tipo de cambio de cierre. El sistema calcula y genera el asiento de diferencias de cambio (pérdidas o ganancias) de forma balanceada.

**Why this priority**: La valoración a cierre ajusta los saldos vivos a su valor real.

**Independent Test**: Valuando saldos en divisa a cierre, la diferencia de cambio se calcula exacta y se asienta balanceada.

**Acceptance Scenarios**:

1. **Given** saldos en divisa con tipo al cierre, **When** se valorizan, **Then** la diferencia de cambio se calcula con precisión y se genera su asiento.
2. **Given** el asiento de diferencia, **When** se valida, **Then** cuadra en moneda funcional y queda vinculado al cierre.

---

### User Story 3 - Cambios históricos del tipo de cambio (Priority: P2)

El usuario consulta los tipos de cambio aplicados por fecha y divisa, y el sistema bloquea la modificación del tipo usado en asientos ya posteados (inmutabilidad).

**Why this priority**: La trazabilidad del tipo usado es imprescindible para reproducir asientos.

**Independent Test**: Consultando el tipo de cambio de una fecha de un asiento posteado, es el mismo y no se puede alterar.

**Acceptance Scenarios**:

1. **Given** asientos posteados con su tipo, **When** se consulta el histórico, **Then** se muestra el tipo usado por fecha.
2. **Given** un intento de cambiar el tipo de un asiento posteado, **When** se envía, **Then** el sistema lo bloquea.

---

### Edge Cases

- ¿Qué ocurre con el redondeo de las conversiones? → El redondeo sigue la regla del tipo de cambio configurada (half-even u otro acordado) y nunca rompe el balance.
- ¿Qué ocurre si no hay tipo de cambio para una fecha? → Se bloquea el registro o se exige tipo explícito.
- ¿Qué ocurre con una cuenta en divisa vs la empresa funcional? → Cada cuenta se define en la moneda de la empresa; las transacciones en otra divisa se convierten.
- ¿Qué ocurre con un asiento en ejercicio cerrado? → Se bloquea por el cierre (SPEC-002/004).

## Requisitos (TODOs numerados)

1. **T-01** Moneda funcional por empresa y divisas de trabajo.
2. **T-02** Tipos de cambio por divisa y fecha con histórico.
3. **T-03** Registro de asientos con importe en divisa y equivalente funcional balanceado.
4. **T-04** Conversión con regla de redondeo exacta acordada.
5. **T-05** Valoración a cierre y asiento de diferencias de cambio.
6. **T-06** Bloqueo de modificación de tipos de asientos posteados.
7. **T-07** Pruebas automáticas (pytest) de cuadre en doble moneda y redondeo.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST fijar una moneda funcional por empresa y admitir operaciones en otras divisas de trabajo.
- **FR-002**: El sistema MUST gestionar tipos de cambio por divisa y fecha con histórico inmutable una vez usados en asientos posteados.
- **FR-003**: El sistema MUST registrar asientos en divisa almacenando importe en divisa, tipo de cambio e importe en moneda funcional, cuadrado en ambas.
- **FR-004**: El sistema MUST aplicar una regla de conversión y redondeo acordados que nunca desequilibre el asiento.
- **FR-005**: El sistema MUST valorizar saldos en divisa a cierre y generar el asiento de diferencias de cambio.
- **FR-006**: El sistema MUST bloquear la modificación del tipo de cambio usado en asientos posteados (inmutabilidad).
- **FR-007**: El sistema MUST aislar divisas y conversiones por empresa.
- **FR-008**: El flujo MUST cumplir la constitución (precisión decimal, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Moneda**: Divisas del sistema; moneda funcional de la empresa.
- **Tipo de cambio**: Conversión divisa ⇄ funcional fechada e histórica.
- **Asiento en divisa**: Asiento con columnas en divisa y funcional.
- **Diferencia de cambio**: Ajuste de valoración a cierre de los saldos en divisa.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los asientos en divisa cuadran en divisa y en moneda funcional.
- **SC-002**: El 100 % de los tipos de cambio usados en posteados quedan inmutables.
- **SC-003**: El 100 % de las conversiones siguen la regla de redondeo acordada.
- **SC-004**: El 100 % de las diferencias de cambio a cierre se asientan balanceadas.
- **SC-005**: El 100 % de las operaciones están aisladas por empresa.

## Assumptions

- La regla de redondeo de conversión se fija a nivel de empresa y se documenta (half-even por defecto).
- La valorización a cierre genera asientos automáticos revisables, no abre el ejercicio.
- La multi-divisa no sustituye a los arqueos de caja (SPEC-019) ni a la conciliación bancaria en divisa (SPEC-013), que la consumirán.

## Dependencias

- SPEC-001 (cuentas en divisa), SPEC-002 (asientos), SPEC-004 (cierre), SPEC-006 (multilínea).