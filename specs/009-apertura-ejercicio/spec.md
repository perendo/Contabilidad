# Feature Specification: Apertura del Ejercicio

**Feature Branch**: `009-apertura-ejercicio`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Apertura del ejercicio (asiento de apertura) para el ejercicio siguiente al cierre definido en SPEC-004"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Abrir el ejercicio siguiente con el asiento de apertura (Priority: P1)

Al finalizar un ejercicio cerrado, el contador abre el ejercicio siguiente: el sistema genera automáticamente el asiento de apertura con los saldos iniciales de las cuentas patrimoniales procedentes del cierre anterior, reiniciando la numeración del nuevo ejercicio.

**Why this priority**: Sin apertura no puede asentarse el ejercicio nuevo; es la continuidad del ciclo contable.

**Independent Test**: Abriendo un ejercicio tras un cierre, el asiento de apertura se genera con los saldos correctos y el nuevo ejercicio queda numerado desde 1.

**Acceptance Scenarios**:

1. **Given** un ejercicio cerrado con saldos, **When** se abre el ejercicio siguiente, **Then** se genera el asiento de apertura balanceado con los saldos iniciales de cuentas patrimoniales.
2. **Given** el nuevo ejercicio abierto, **When** se registra el primer asiento, **Then** la numeración comienza correlativamente (número 1 y siguientes) por empresa y ejercicio.

---

### User Story 2 - Controlar y corregir una apertura errónea (Priority: P2)

Si la apertura se genera incorrectamente (p. ej., por un cierre mal cerrado), el contador puede anularla y regenerarla sin afectar a los datos del ejercicio anterior.

**Why this priority**: La apertura es reversible con trazabilidad, respetando la inmutabilidad de los asientos ya asentados.

**Independent Test**: Anulando una apertura se genera el asiento rectificativo y se permite regenerarla; el ejercicio anterior permanece intacto.

**Acceptance Scenarios**:

1. **Given** una apertura generada, **When** el contador la detecta errónea y la anula, **Then** se crea el asiento de anulación y se permite regenerar la apertura.
2. **Given** la anulación realizada, **When** se verifica el ejercicio anterior, **Then** permanece cerrado e inmutable.

---

### User Story 3 - Evitar aperturas duplicadas o incompletas (Priority: P1)

El sistema impide abrir un ejercicio si ya existe, si no hay cierre del ejercicio anterior, o si el nuevo ejercicio no tiene definido su rango de fechas.

**Why this priority**: Evita dobles aperturas y estados inconsistentes del ciclo contable.

**Independent Test**: Intentando una doble apertura o una apertura sin cierre previo, el sistema la rechaza con mensajes claros.

**Acceptance Scenarios**:

1. **Given** un ejercicio ya abierto, **When** se intenta abrir de nuevo, **Then** el sistema lo rechaza sin duplicar el asiento de apertura.
2. **Given** un ejercicio sin cierre previo, **When** se intenta abrir el siguiente, **Then** el sistema lo rechaza indicando que falta el cierre.

---

### Edge Cases

- ¿Qué ocurre si el cierre del ejercicio anterior aún no existe? → Se bloquea la apertura.
- ¿Qué ocurre si el rango del nuevo ejercicio se solapa con el anterior? → Se valida la correlación de fechas antes de abrir.
- ¿Qué ocurre si la apertura no cuadra (diferencia entre cargos y abonos)? → Se bloquea: la partida doble es estricta.
- ¿Qué ocurre si hay saldos en moneda extranjera (SPEC-016 futuro)? → Se abren en la moneda de cada cuenta o en funcional, según configuración.

## Requisitos (TODOs numerados)

1. **T-01** Validación de requisitos previos (ejercicio sin abrir, cierre previo existente, rango definido).
2. **T-02** Generación del asiento de apertura con saldos patrimoniales del cierre anterior.
3. **T-03** Verificación de balance estricto de la apertura.
4. **T-04** Anciones/anulación y regeneración de la apertura (rectificativo enlazado).
5. **T-05** Reinicio de la numeración por ejercicio y empresa.
6. **T-06** Pruebas automáticas (pytest) de generación, bloqueos y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar la apertura por empresa y generar el asiento de apertura únicamente para el ejercicio activo y empresa activa.
- **FR-002**: El sistema MUST exigir el cierre del ejercicio anterior, un ejercicio siguiente sin abrir y un rango de fechas definido antes de abrir.
- **FR-003**: El sistema MUST generar el asiento de apertura con los saldos iniciales de las cuentas patrimoniales del cierre anterior, balanceado y en precisión decimal exacta.
- **FR-004**: El sistema MUST impedir una segunda apertura para el mismo ejercicio y empresa.
- **FR-005**: El sistema MUST iniciar la numeración del nuevo ejercicio en 1 y mantenerla correlativa.
- **FR-006**: El sistema MUST permitir anular y regenerar la apertura mediante asiento rectificativo sin alterar el ejercicio anterior (inmutabilidad).
- **FR-007**: El flujo MUST cumplir las reglas de la constitución (partida doble, numeración correlativa, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Asiento de apertura**: Asiento inicial del ejercicio con los saldos patrimoniales de entrada.
- **Ejercicio contable**: Período que se abre; hereda los saldos del cierre anterior.
- **Asiento de anulación de apertura**: Rectificativo generado si se corrige la apertura.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las aperturas generan un asiento balanceado con los saldos correctos del cierre anterior.
- **SC-002**: El 100 % de las aperturas dobles o sin cierre previo son rechazadas.
- **SC-003**: El 100 % de las correcciones de apertura se producen con rectificativo sin tocar el ejercicio anterior.
- **SC-004**: El 100 % de las aperturas quedan aisladas por empresa.
- **SC-005**: La numeración del ejercicio abierto es correlativa desde el 1 en el 100 % de los casos.

## Assumptions

- La apertura es un proceso de contabilidad general disponible para todos los usuarios con rol contable según la matriz de permisos (SPEC-015).
- La reapertura de un ejercicio cerrado queda fuera del alcance; solo se permite anular la apertura del ejercicio en curso.
- Los saldos se heredan de las cuentas patrimoniales del cierre; las cuentas de resultados no se abren.

## Dependencias

- SPEC-002 (motor de asientos), SPEC-004 (cierre de ejercicio) y SPEC-010 (cuentas anuales).