# Feature Specification: Plantillas de Asientos

**Feature Branch**: `018-plantillas-asientos`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Plantillas de asientos reutilizables: creación por la empresa, variables y generación de asientos balanceados"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Crear una plantilla reutilizable (Priority: P1)

El contador crea una plantilla de asiento con un conjunto de apuntes predefinidos (cuenta, debe/haber), donde algunos importes son fijos y otros variables que se solicitan en la generación.

**Why this priority**: Agiliza la operación repetitiva y reduce errores de transcripción.

**Independent Test**: Creando una plantilla con importes fijos y variables, queda guardada para la empresa activa y lista para generar asientos.

**Acceptance Scenarios**:

1. **Given** los apuntes de la plantilla, **When** se crea, **Then** queda guardada con sus importes fijos y variables definidos.
2. **Given** una plantilla guardada, **When** se consulta desde otra empresa, **Then** no es visible.

---

### User Story 2 - Generar un asiento desde la plantilla (Priority: P2)

El usuario elige plantilla, completa las variables y fecha, y el sistema genera el asiento de la empresa activa dentro de las reglas del motor (SPEC-002): balance estricto, ejercicio válido y multiplicidad de líneas.

**Why this priority**: La generación desde plantilla debe producir asientos legales sin violar el motor.

**Independent Test**: Generando un asiento con la plantilla, el resultado es balanceado, en la empresa activa y en el ejercicio correcto.

**Acceptance Scenarios**:

1. **Given** una plantilla y las variables, **When** se genera el asiento, **Then** queda balanceado con todas las líneas resueltas.
2. **Given** un ejercicio cerrado o una empresa incorrecta, **When** se intenta generar, **Then** el sistema lo bloquea.

---

### User Story 3 - Gestionar plantillas (editado, activado, versiones) (Priority: P2)

El contador edita, activa o desactiva plantillas. Los asientos generados conservan la fecha de generación y no cambian retroactivamente si la plantilla se edita.

**Why this priority**: Las plantillas evolucionan sin alterar asientos ya generados.

**Independent Test**: Editando una plantilla, los asientos generados antes conservan sus datos originales.

**Acceptance Scenarios**:

1. **Given** una plantilla editada, **When** se consulta un asiento generado con la versión anterior, **Then** conserva sus líneas originales.
2. **Given** una plantilla desactivada, **When** se intenta generar, **Then** se bloquea.

---

### Edge Cases

- ¿Qué ocurre si la plantilla no cuadra (Sum Debe != Sum Haber) con las variables? → Se impide generar; el motor exige balance.
- ¿Qué ocurre si un importe variable no se completa? → Se bloquea la generación con mensaje de faltante.
- ¿Qué ocurre si la cuenta no existe en el plan de la empresa? → Se valida contra el plan antes de generar.
- ¿Qué ocurre con fórmulas (p. ej., neto con IVA)? → Solo se admiten importes fijos y variables numéricos en esta feature.

## Requisitos (TODOs numerados)

1. **T-01** Entidad de plantillas con apuntes predefinidos por empresa.
2. **T-02** Soporte de importes fijos y variables.
3. **T-03** Generación de asientos desde plantilla validando el motor (SPEC-002/006).
4. **T-04** Validación de cuentas contra el plan y balance estricto.
5. **T-05** Gestión de versiones/activación sin alterar asientos generados.
6. **T-06** Pruebas automáticas (pytest) de generación, balance y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST permitir crear plantillas de asientos por empresa con apuntes predefinidos.
- **FR-002**: El sistema MUST admitir en las líneas importes fijos y variables que se completan al generar.
- **FR-003**: El sistema MUST generar desde plantilla un asiento de la empresa activa balanceado y dentro del ejercicio abierto (motor SPEC-002).
- **FR-004**: El sistema MUST validar las cuentas de la plantilla contra el plan de cuentas de la empresa antes de generar.
- **FR-005**: El sistema MUST impedir la generación si el asiento resultante no cuadra o faltan variables.
- **FR-006**: El sistema MUST conservar los asientos generados inmutables aunque la plantilla se edite o desactive.
- **FR-007**: El sistema MUST aislar las plantillas por empresa y respetar la matriz de permisos (SPEC-015).
- **FR-008**: El flujo MUST cumplir la constitución (partida doble, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Plantilla de asiento**: Conjunto de líneas con importes fijos/variables por empresa.
- **Variable**: Importe a completar en la generación del asiento.
- **Asiento generado**: Asiento resultante, inmutable, ligado a su plantilla y herramienta de trazabilidad.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los asientos generados desde plantilla son balanceados.
- **SC-002**: El 100 % de las generaciones validan las cuentas contra el plan de la empresa.
- **SC-003**: El 100 % de los asientos generados permanecen inmutables a ediciones posteriores de la plantilla.
- **SC-004**: El 100 % de las plantillas están aisladas por empresa.
- **SC-005**: El 100 % de las generaciones respetan el ejercicio abierto.

## Assumptions

- Los importes son fijos o variables; no se soportan fórmulas complejas (p. ej., cálculo de IVA) en esta feature.
- La herramienta de registro (asiento y auditoría) la provee el motor (SPEC-002/005).
- Las plantillas se comparten dentro de la empresa (no entre empresas), y el acceso sigue la matriz de permisos.

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-006 (multilínea), SPEC-015 (permisos).