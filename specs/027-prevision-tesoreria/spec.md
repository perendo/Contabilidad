# Feature Specification: Previsión y Flujo de Caja

**Feature Branch**: `027-prevision-tesoreria`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Previsión/flujo de caja a partir de vencimientos no vencidos (usa SPEC-011 y SPEC-013); informe de flujos de efectivo (EFE, parte de la memoria de SPEC-010)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generar la previsión de tesorería (Priority: P1)

El usuario genera una previsión de tesorería a partir de vencimientos pendientes (cobros esperados y pagos previstos). El sistema proyecta los flujos por día, semana o mes, mostrando el saldo disponible y los movimientos esperados.

**Why this priority**: Control de tesorería y capacidad de pago.

**Independent Test**: Generando una previsión, los cobros y pagos esperados cuadran con los vencimientos pendientes por fecha de vencimiento.

**Acceptance Scenarios**:

1. **Given** vencimientos pendientes de cobro y pago con fechas, **When** se genera la previsión, **Then** el saldo proyectado muestra día a día los flujos esperados.
2. **Given** pagos recurrentes (alquileres, nóminas no vencidas), **When** se incluyen en la previsión, **Then** aparecen en el flujo.

---

### User Story 2 - Visualizar el flujo de efectivo consolidado (Priority: P2)

El usuario visualiza un informe consolidado de flujos de efectivo (EFE) del ejercicio, desglosado por tipo de operación (actividades operativas, inversión, financiación).

**Why this priority**: Forma parte de la memoria de cuentas anuales (SPEC-010) y de la gestión interna.

**Independent Test**: Generando el EFE, los saldos de apertura, movimientos y cierre cuadran entre sí.

**Acceptance Scenarios**:

1. **Given** los movimientos del ejercicio, **When** se genera el EFE, **Then** aparecen los tres bloques (operativa, inversión, financiación) y el saldo final.
2. **Given** movimientos de apertura del banco (SPEC-013), **When** se cruzan con el EFE, **Then** coinciden el saldo final bancario y el saldo de caja del EFE.

---

### User Story 3 - Alertar sobre necesidades de tesorería (Priority: P2)

El sistema detecta días/meses con saldo negativo proyectado y notifica al usuario, permitiendo planificar pagos o buscar financiación.

**Why this priority**: Prevención de problemas de liquidez.

**Independent Test**: Si la previsión muestra saldo negativo en algún periodo, el sistema lo notifica.

**Acceptance Scenarios**:

1. **Given** una previsión con día de saldo negativo, **When** se genera, **Then** el sistema lo resalta.
2. **Given** una alerta generada, **When** se consultan las opciones, **Then** el usuario puede reprogramar pagos o incluir ingresos previstos.

---

### Edge Cases

- ¿Qué ocurre con pagos no datados? → Solo se incluyen si tienen fecha prevista estimada; sin fecha quedan fuera de la proyección.
- ¿Qué ocurre con cobros inciertos (sin fecha de cobro real)? → Se excluirán de la previsión salvo que el usuario indique una fecha estimada.
- ¿Qué ocurre si la previsión incluye movimientos de un ejercicio cerrado? → Solo muestra los no vencidos para proyectar; los vencidos y cobrados se excluyen.
- ¿Qué ocurre si el saldo proyectado es exactamente cero? → Se muestra como límite de solvencia, sin alerta negativa.

## Requisitos (TODOs numerados)

1. **T-01** Recuperación de vencimientos pendientes (cobro y pago) de SPEC-011/020 con fecha de vencimiento.
2. **T-02** Proyección del flujo de tesorería por día, semana o mes (saldo + movimientos).
3. **T-03** Alertas de saldo negativo en la proyección por día.
4. **T-04** Informe EFE (flujo de efectivo) desglosado por actividad (operativa, inversión, financiación) y cuadre con apertura/cierre.
5. **T-05** Integración de movimientos bancarios (SPEC-013) para validar saldos.
6. **T-06** Multi-tenancy y aislamiento por empresa.
7. **T-07** Pruebas automáticas (pytest) de proyección, EFE y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST generar la previsión de tesorería a partir de vencimientos pendientes (cobros y pagos) con su fecha de vencimiento, ejerciendo sobre la empresa activa.
- **FR-002**: El sistema MUST proyectar el saldo y los movimientos por día, semana o mes según elección del usuario.
- **FR-003**: El sistema MUST generar alertas cuando el saldo proyectado sea negativo en algún periodo.
- **FR-004**: El sistema MUST generar el informe EFE (flujo de efectivo) desglosado por tipo de actividad, con cuadre del saldo de apertura + movimientos = saldo de cierre.
- **FR-005**: El sistema MUST cruzar el saldo del EFE con el saldo de conciliación bancaria (SPEC-013) para validación.
- **FR-006**: El sistema MUST excluir vencimientos vencidos y ya cobrados/pagados de la proyección futura.
- **FR-007**: El flujo MUST cumplir la constitución (precisión Decimal, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Previsión de tesorería**: Proyección de saldos y movimientos por periodo futuro.
- **Flujo de efectivo (EFE)**: Informe consolidado por tipo de actividad (operativa, inversión, financiación).
- **Movimiento proyectado**: Cada vencimiento pendiente colocado en su fecha de proyección.
- **Alerta de liquidez**: Notificación de saldo negativo en la proyección.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los vencimientos pendientes se proyectan en la fecha correcta de vencimiento.
- **SC-002**: El 100 % de las proyecciones muestran el saldo acumulado sin errores.
- **SC-003**: El 100 % de los EFE cuadran (apertura + movimientos = cierre).
- **SC-004**: El 100 % de los días con saldo negativo generan una alerta visible.
- **SC-005**: Los importes se tratan con precisión de 4 decimales.

## Assumptions

- La previsión usa los vencimientos de SPEC-011 y SPEC-020 pendientes; pagos recurrentes no vencidos se insertan manualmente como pagos previstos.
- El EFE se genera a partir de los movimientos del motor de asientos y la conciliación bancaria; la clasificación por actividad se hace por el usuario o se infiere de las cuentas del grupo 6/7 y tesorería.
- La previsión no bloquea la contabilización; es una herramienta de gestión.
- El cuadre del EFE se refuerza con el saldo de conciliación bancaria (SPEC-013) pero no se exige 100 % de coincidencia (puede haber movimientos no conciliados).

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-011 (vencimientos), SPEC-012 (libros fiscales para impuestos previstos), SPEC-013 (conciliación bancaria), SPEC-020 (remesas SEPA para cobros proyectados), SPEC-010 (memoria cuentas anuales para el EFE).