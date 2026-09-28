# Feature Specification: Cierre Intermedio y Reapertura Controlada

**Feature Branch**: `028-cierre-intermedio`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Cierre intermedio/parcial (mensual/trimestral) más allá del cierre anual de SPEC-004; reapertura controlada del ejercicio"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cerrar un periodo intermedio (mes o trimestre) (Priority: P1)

El usuario cierra un periodo intermedio (mensual o trimestral) bloqueando la contabilización en ese periodo. El sistema genera un balance de comprobación del periodo y bloquea la posibilidad de anotar o modificar asientos en esas fechas.

**Why this priority**: Cierres parciales son necesarios para informes periódicos y evitar errores sin cerrar el ejercicio.

**Independent Test**: Cerrando el mes, no se pueden anotar nuevos asientos en ese periodo y el balance cuadra.

**Acceptance Scenarios**:

1. **Given** un mes abierto, **When** el usuario lo cierra, **Then** no se pueden anotar asientos en ese periodo y el balance queda registrado.
2. **Given** un trimestre cerrado, **When** se genera el balance, **Then** el Debe y el Haber cuadran y el periodo aparece como cerrado.

---

### User Story 2 - Cerrar el ejercicio anual completo (Priority: P1)

El usuario cierra el ejercicio completo (cierre total) generando los asientos de regularización y apertura (SPEC-004/SPEC-009). El sistema bloquea la contabilización del ejercicio y genera los informes del cierre.

**Why this priority**: Es el cierre que previene la constitución (partida doble estricta) y alimenta las cuentas anuales (SPEC-010).

**Independent Test**: Cerrando el ejercicio, los asientos de cierre cuadran y el balance queda inmutable.

**Acceptance Scenarios**:

1. **Given** un ejercicio completo con todos los periodos cerrados, **When** se cierra, **Then** se generan los asientos de regularización y apertura, el balance queda cerrado y el ejercicio bloqueado.
2. **Given** el cierre anual completo, **When** se intenta anotar un asiento en el ejercicio cerrado, **Then** el sistema lo rechaza.

---

### User Story 3 - Reapertura de un periodo cerrado de forma controlada (Priority: P2)

En casos excepcionales (error de contabilización, ajuste legal pendiente) el usuario puede reabrir un periodo cerrado. El sistema exige confirmación, genera un asiento de rectificación que mantiene la inmutabilidad del asiento original, registra la reapertura y bloquea de nuevo al completar el ajuste.

**Why this priority**: Rectificar errores sin romper la inmutabilidad es fundamental para la integridad del sistema.

**Independent Test**: Reabriendo un periodo cerrado se genera el asiento de rectificación (REVERSAL/ADJUSTMENT) y el periodo queda bloqueado otra vez tras el ajuste.

**Acceptance Scenarios**:

1. **Given** un periodo cerrado con un error detectado, **When** el usuario solicita la reapertura, **Then** el sistema genera el asiento de rectificación (con la naturaleza REVERSAL o ADJUSTMENT) y reabre el periodo temporalmente.
2. **Given** la reapertura con asiento de rectificación, **When** se completa el ajuste, **Then** el periodo se cierra nuevamente y queda inmutable.

---

### Edge Cases

- ¿Qué ocurre si se intenta reabrir un periodo sin justificar? → Se exige una justificación y un usuario autorizado (SPEC-003/015).
- ¿Qué ocurre si la reapertura afecta a un ejercicio que ya tiene cuentas anuales (SPEC-010)? → Se rechaza la reapertura si el ejercicio está legalizado o formulado.
- ¿Qué ocurre con el IS del periodo (SPEC-023)? → Solo se recalculará si el cierre del IS aún no se ha hecho; si está hecho, la reapertura afecta parcialmente.
- ¿Qué ocurre si un cierre intermedio tiene saldo a cero? → Se permite su cierre normal sin anomalía.
- ¿Qué ocurre si se reabren varios periodos a la vez? → Se debe reabrir uno a la vez y re-cerrarlo antes de pasar al siguiente.

## Requisitos (TODOs numerados)

1. **T-01** Cierre de periodos intermedios (mes/trimestre) con bloqueo de contabilización y balance de comprobación.
2. **T-02** Cierre anual completo con asientos de regularización y apertura (integración con SPEC-009).
3. **T-03** Reapertura controlada de periodos cerrados con asiento de rectificación (REVERSAL/ADJUSTMENT) que preserve la inmutabilidad.
4. **T-04** Bloqueo del ejercicio si tiene cuentas anuales (SPEC-010) o impuestos liquidados (SPEC-023/024).
5. **T-05** Registro de la reapertura con justificación, usuario y fecha.
6. **T-06** Multi-tenancy y aislamiento por empresa.
7. **T-07** Pruebas automáticas (pytest) de cierre, reapertura, rectificaciones y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST permitir cierres de periodos intermedios (mes/trimestre) bloqueando la contabilización en el periodo, ejerciendo sobre la empresa activa.
- **FR-002**: El sistema MUST generar el cierre anual completo con los asientos de regularización (SPEC-004) y apertura (SPEC-009), bloqueando el ejercicio y alimentando las cuentas anuales (SPEC-010).
- **FR-003**: El sistema MUST permitir la reapertura de un periodo cerrado solo si el ejercicio no está legalizado/formulado y el usuario tiene permiso (SPEC-003/015), requiriendo justificación.
- **FR-004**: La reapertura MUST generar un asiento de rectificación (REVERSAL o ADJUSTMENT) que mantenga la inmutabilidad del asiento original (constitución), y re-cerrar el periodo tras el ajuste.
- **FR-005**: El sistema MUST exigir la reapertura y cierre de un solo periodo a la vez, sin abrir varios periodos simultáneamente.
- **FR-006**: El sistema MUST registrar cada reapertura con justificación, usuario y fecha, manteniendo la trazabilidad.
- **FR-007**: El flujo MUST cumplir la constitución (partida doble, precisión Decimal, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Periodo cerrado**: Periodo (mes/trimestre/ejercicio) con estado cerrado y bloqueo de contabilización.
- **Asiento de rectificación**: Asiento REVERSAL o ADJUSTMENT que mantiene la inmutabilidad del original.
- **Solicitud de reapertura**: Registro de la solicitud con justificación, usuario y fecha.
- **Cierre anual**: Proceso que genera asientos de regularización y apertura (SPEC-004/009).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los cierres intermedios bloquean la contabilización del periodo.
- **SC-002**: El 100 % de los cierres anuales generan asientos balanceados y bloquean el ejercicio.
- **SC-003**: El 100 % de las reaperturas generan un asiento de rectificación que preserve la inmutabilidad.
- **SC-004**: El 0 % de reaperturas se permiten en ejercicios legalizados o con cuentas anuales.
- **SC-005**: El 100 % de las reaperturas quedan registradas con justificación y usuario.

## Assumptions

- Los cierres intermedios son informativos y de control; no generan asientos de cierre automáticos (ese es el cierre anual).
- La reapertura no es un flujo habitual; se considera excepcionalidad controlada con permisos específicos.
- El cierre anual completo depende de que todos los periodos intermedios estén cerrados.
- La inmutabilidad de los asientos existentes se mantiene siempre; la corrección se hace con un nuevo asiento (REVERSAL/ADJUSTMENT) que cuadra el Debe/Haber.

## Dependencias

- SPEC-002 (motor de asientos), SPEC-003/015 (multiempresa/permisos), SPEC-004 (informes y cierre), SPEC-009 (apertura de ejercicio), SPEC-010 (cuentas anuales), SPEC-023 (IS), SPEC-024 (retenciones).