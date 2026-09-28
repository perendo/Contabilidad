# Feature Specification: Cuentas Anuales (Balance de Situación y Pérdidas y Ganancias)

**Feature Branch**: `010-cuentas-anuales`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Balance de Situación y Pérdidas y Ganancias (cuentas anuales) para completar los informes de SPEC-004"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generar el Balance de Situación (Priority: P1)

El contador formula el Balance de Situación del ejercicio de su empresa: activo, pasivo y patrimonio neto, a partir de los saldos de las cuentas del plan. El balance cuadra siempre (Activo == Pasivo + Patrimonio Neto) y conserva la precisión monetaria.

**Why this priority**: Es el informe exigido por la normativa y surge directamente del ciclo contable.

**Independent Test**: Generando el Balance de Situación de un ejercicio, la igualdad Activo == Pasivo + Patrimonio se cumple y solo incluye datos de la empresa activa.

**Acceptance Scenarios**:

1. **Given** un ejercicio con saldos en sus cuentas, **When** se formula el Balance de Situación, **Then** se muestran activo, pasivo y patrimonio neto con precisiones exactas y la igualdad fundamental.
2. **Given** datos de otra empresa, **When** se formula, **Then** no aparecen en el balance (aislamiento).

---

### User Story 2 - Generar la Cuenta de Pérdidas y Ganancias (Priority: P1)

El contador genera la Cuenta de Pérdidas y Ganancias del ejercicio: ingresos y gastos por grupos del plan, con el resultado del ejercicio. La suma de gastos e ingresos cuadra con el resultado.

**Why this priority**: Expresa el resultado contable del ejercicio y alimenta el cierre y la memoria.

**Independent Test**: Generando la PyG de un ejercicio, el resultado coincide con la diferencia Ingresos - Gastos y con el saldo de la cuenta de resultados.

**Acceptance Scenarios**:

1. **Given** asientos de gestión del ejercicio, **When** se genera la PyG, **Then** se agregan ingresos y gastos y el resultado del ejercicio es exacto.
2. **Given** el resultado generado, **When** se compara con el asiento de regularización del cierre (SPEC-004), **Then** coinciden.

---

### User Story 3 - Formular y bloquear las cuentas anuales (Priority: P2)

El contador formula y aprueba las cuentas anuales del ejercicio cerrado; una vez formuladas, las cuentas anuales quedan inmutables y asociadas a su ejercicio.

**Why this priority**: Así se mantiene la integridad del informe frente al ejercicio cerrado.

**Independent Test**: Formulando las cuentas anuales de un ejercicio cerrado, quedan inmutables y con su trazabilidad.

**Acceptance Scenarios**:

1. **Given** un ejercicio cerrado, **When** se formulan las cuentas anuales, **Then** se genera el documento inmutable con fecha y usuario.
2. **Given** unas cuentas anuales formuladas, **When** se intenta reformular sin anular, **Then** el sistema lo impide o registra la reformulación con trazabilidad.

---

### User Story 4 - Formular el Informe de Flujos de Efectivo (EFE) (Priority: P2)

El contador genera el Estado de Flujos de Efectivo del ejercicio (parte de las cuentas anuales): cobros y pagos por actividades operativas, de inversión y de financiación, con el cuadre de saldo inicial, movimientos y saldo final de tesorería.

**Why this priority**: Es un documento obligatorio de las cuentas anuales que permite evaluar la liquidez del ejercicio.

**Independent Test**: Generando el EFE, los saldos de apertura + movimientos coinciden con el saldo final y con la tesorería del ejercicio.

**Acceptance Scenarios**:

1. **Given** los movimientos de tesorería del ejercicio, **When** se formula el EFE, **Then** se desglosan por actividad (operativa, inversión, financiación) y el cuadre final es exacto.
2. **Given** el EFE formulado, **When** se compara con la variación de tesorería del Balance, **Then** coinciden.

---

### Edge Cases

- ¿Qué ocurre si las cuentas del plan no se agrupan en estructura de balance? → Se usan las agrupaciones/grupos definidos (nivel 1-3) configurados por empresa.
- ¿Qué ocurre si el ejercicio no está cerrado? → Se permite un balance provisional y solo la formulación oficial exige cierre.
- ¿Qué ocurre con diferencias de precisión en la consolidación? → El cuadre se garantiza con aritmética decimal.
- ¿Qué ocurre si hay asientos de regularización/cierre sin generarse? → El resultado puede diferir; se advierte cuando falta el cierre.
- ¿Qué ocurre con movimientos de tesorería no clasificados por actividad? → Se clasifican por defecto según el grupo de la cuenta y se permite reasignar manualmente antes de formular.
- ¿Qué ocurre si el EFE no cuadra con la variación de tesorería? → Se avisa y no se permite formular el EFE hasta resolver la diferencia.

## Requisitos (TODOs numerados)

1. **T-01** Agrupación de saldos por estructura de balance a partir del plan de cuentas.
2. **T-02** Generación del Balance de Situación con cuadre Activo == Pasivo + Patrimonio.
3. **T-03** Generación de la Cuenta de Pérdidas y Ganancias con el resultado exacto.
4. **T-04** Comparativa con el ejercicio anterior (opcional).
5. **T-05** Formulación oficial restringida a ejercicios cerrados, con inmutabilidad y trazabilidad.
6. **T-06** Salida imprimible/intercambiable (se enlaza con libros oficiales de SPEC-019).
7. **T-07** Estado de Flujos de Efectivo (EFE) por actividades, con cuadre de saldo inicial/movimientos/final y variación de tesorería.
8. **T-08** Pruebas automáticas (pytest) de cuadre, resultado y aislamiento multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST formular el Balance de Situación de la empresa activa a partir de los saldos del plan de cuentas, con cuadre Activo == Pasivo + Patrimonio Neto.
- **FR-002**: El sistema MUST formular la Cuenta de Pérdidas y Ganancias con ingresos, gastos y resultado del ejercicio exacto en precisión decimal.
- **FR-003**: El sistema MUST aislar las cuentas anuales por empresa y por ejercicio.
- **FR-004**: El sistema MUST permitir balances provisionales en cualquier ejercicio y la formulación oficial únicamente sobre ejercicios cerrados.
- **FR-005**: El sistema MUST generar las cuentas anuales formuladas como documento inmutable con fecha, usuario y trazabilidad.
- **FR-006**: El resultado de la PyG MUST coincidir con el asiento de regularización/cierre definido en SPEC-004.
- **FR-007**: El flujo MUST cumplir la constitución (precisión, inmutabilidad, multi-tenancy y pruebas obligatorias).
- **FR-008**: El sistema MUST formular el Estado de Flujos de Efectivo (EFE) por actividades (operativa, inversión, financiación), con cuadre de saldo inicial + movimientos = saldo final coherente con la variación de tesorería del ejercicio.

### Key Entities *(include if feature involves data)*

- **Balance de Situación**: Informe de activo, pasivo y patrimonio neto por grupos del plan.
- **Cuenta de Pérdidas y Ganancias**: Informe de ingresos, gastos y resultado del ejercicio.
- **Estado de Flujos de Efectivo (EFE)**: Informe de cobros y pagos del ejercicio desglosado por actividades operativa, de inversión y de financiación.
- **Cuentas anuales formuladas**: Conjunto inmutable y trazable de los informes oficiales del ejercicio.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los balances de situación formulados cuadran (Activo == Pasivo + Patrimonio).
- **SC-002**: El 100 % de las PyG muestran un resultado coincidente con la regularización del cierre.
- **SC-003**: El 100 % de las formulaciones oficiales requieren ejercicio cerrado y quedan inmutables.
- **SC-004**: El 100 % de las cuentas anuales están aisladas por empresa.
- **SC-005**: Los importes se presentan con precisión de 4 decimales sin errores de redondeo.

## Assumptions

- La estructura de balance/PyG se deriva de las agrupaciones del plan de cuentas (SPEC-001) con una configuración por empresa.
- La formulación oficial es única y se reformula con trazabilidad y permiso de administrador.
- Las cuentas anuales imprimibles se integran con los libros oficiales (SPEC-019).
- El EFE se deriva de los movimientos de tesorería (grupo 5) y de la clasificación por actividad; la variación coincide con la del balance. Complementa la previsión de tesorería (SPEC-027) pero es un informe histórico cerrado.

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-004 (cierre), SPEC-006 (multilínea), SPEC-013 (conciliación bancaria para el cuadre de tesorería), SPEC-019 (libros oficiales), SPEC-027 (flujo de caja previsional, complementario).