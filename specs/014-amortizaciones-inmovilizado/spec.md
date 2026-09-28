# Feature Specification: Amortizaciones del Inmovilizado

**Feature Branch**: `014-amortizaciones-inmovilizado`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Amortizaciones del inmovilizado: alta de activos, plan de amortización lineal/regresivo y asientos periódicos automáticos"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dar de alta un activo fijo (Priority: P1)

El usuario registra un elemento del inmovilizado (cuenta 21x) con su coste amortizable, vida útil, método (lineal o regresivo/degresivo) y fecha de alta. El sistema calcula el plan de amortización y lo valida.

**Why this priority**: La amortización periódica depende del registro correcto del activo y de su plan.

**Independent Test**: Alta de un activo con método y vida útil correctos genera el plan de amortización con la cuota calculada y validada.

**Acceptance Scenarios**:

1. **Given** los datos del activo (coste, vida útil, método), **When** se da de alta, **Then** se registra y se calcula el plan de amortización del período.
2. **Given** un método regresivo, **When** se genera el plan, **Then** las cuotas decrecen conforme al tipo seleccionado sin superar el coste amortizable.

---

### User Story 2 - Generar los asientos de amortización del período (Priority: P1)

El usuario (o el proceso) genera los asientos de amortización del período para los activos en uso. Cada asiento imputa la cuota a gasto (681) contra amortización acumulada (281) de la cuenta del activo.

**Why this priority**: La dotación periódica debe asentarse en libros con partida doble exacta.

**Independent Test**: Generando la amortización de un período, se crean los asientos balanceados 681/281 y no se duplican para el mismo período.

**Acceptance Scenarios**:

1. **Given** activos con plan vigente, **When** se genera la amortización del período, **Then** se crean sus asientos balanceados sin duplicados para ese período.
2. **Given** un período ya amortizado, **When** se intenta regenerar, **Then** el sistema lo bloquea o ofrece reabrir con trazabilidad.

---

### User Story 3 - Baja de un activo y ajuste (Priority: P2)

El contador registra la baja o venta de un activo. El sistema calcula la amortización hasta la fecha de baja, el valor contable neto y genera el asiento de baja (caja/banco, amortización acumulada y pérdidas/ganancias).

**Why this priority**: La baja ajusta libros, tesorería y resultados de forma coherente.

**Independent Test**: Bajando un activo se registra su amortización hasta la baja y el asiento de baja cuadra con el valor neto contable.

**Acceptance Scenarios**:

1. **Given** un activo en uso, **When** se registra su baja, **Then** se genera el asiento de baja balanceado y el activo queda fuera del plan.
2. **Given** el valor de venta, **When** se cierra el asiento de baja, **Then** la pérdida/ganancia se calcula con precisión exacta.

---

### Edge Cases

- ¿Qué ocurre si el activo se amortizó de más en períodos previos? → El plan acumulado nunca supera el coste amortizable.
- ¿Qué ocurre si la vida útil restante es menor que un período (amortización parcial)? → Se prorratea la cuota según días o períodos definidos.
- ¿Qué ocurre si el ejercicio está cerrado? → La generación de amortización se restringe al ejercicio abierto.
- ¿Qué ocurre si se corrige un activo ya amortizado (revalorización)? → Se recalcula el plan futuro sin retroceder asientos ya posteados.

## Requisitos (TODOs numerados)

1. **T-01** Alta/edición de activos de inmovilizado con cuenta 21x, coste, vida útil y método.
2. **T-02** Cálculo y validación del plan de amortización (lineal/regresivo).
3. **T-03** Generación de asientos periódicos 681/281 balanceados sin duplicados, restringida a ejercicio abierto.
4. **T-04** Baja/venta de activos con amortización hasta la fecha y asiento de baja.
5. **T-05** Control de que el plan acumulado no supere el coste amortizable.
6. **T-06** Pruebas automáticas (pytest) de cuotas, no duplicados y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar los activos de inmovilizado por empresa y ejercer sobre la empresa activa.
- **FR-002**: El sistema MUST registrar activos con cuenta (21x), coste amortizable, vida útil, método (lineal/regresivo) y fechas, calculando el plan de amortización.
- **FR-003**: El sistema MUST generar los asientos periódicos de amortización (681 contra 281) balanceados, sin duplicados por activo y período.
- **FR-004**: El sistema MUST restringir la generación de amortización al ejercicio abierto de la empresa.
- **FR-005**: El sistema MUST registrar la baja de activos con amortización hasta la fecha de baja y asiento de baja balanceado (con resultado por venta si aplica).
- **FR-006**: El sistema MUST garantizar que la amortización acumulada no supere el coste amortizable del activo.
- **FR-007**: Los importes MUST tratarse en precisión decimal exacta en el plan y en los asientos.
- **FR-008**: El flujo MUST cumplir la constitución (partida doble, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Activo de inmovilizado**: Elemento del 21x con su coste, método y plan.
- **Plan de amortización**: Serie de cuotas por período calculadas y almacenadas.
- **Asiento de amortización**: Asiento 681/281 generado por período y activo.
- **Asiento de baja**: Asiento de salida del activo por venta/retirada con resultado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los planes de amortización se calculan y validan; la cuota acumulada nunca excede el coste amortizable.
- **SC-002**: El 100 % de los asientos de amortización son balanceados y sin duplicados por período.
- **SC-003**: El 100 % de las bajas generan el asiento correcto y sacan el activo del plan.
- **SC-004**: El 100 % de las operaciones están aisladas por empresa.
- **SC-005**: Las cuotas y valores se expresan con precisión de 4 decimales.

## Assumptions

- La cuenta de gasto por defecto es 681 y la de acumulada 281 (grupos configurados); se asocian por cuenta de activo.
- La corrección de activos ya amortizados recalcula el plan futuro sin reabrir asientos posteados (constitución II).
- El prorrateo de cuota parcial se define por la configuración de la empresa (mensual o por días).

## Dependencias

- SPEC-001 (plan de cuentas 21x/281/681), SPEC-002 (motor de asientos), SPEC-004 (cierre del ejercicio), SPEC-006 (multilínea).