# Feature Specification: Centros de Coste

**Feature Branch**: `017-centros-de-coste`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Centros de coste / departamentos / proyectos: imputación por apunte y análisis de costes"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Definir centros de coste y su jerarquía (Priority: P1)

El contador crea centros de coste (departamentos, proyectos, subvenciones, delegaciones) organizados en jerarquía, exclusivos de la empresa activa, y los asocia a las subvenciones del módulo 019 si procede.

**Why this priority**: Sin centros definidos no existe imputación ni análisis por tipo de gasto.

**Independent Test**: Crear un centro y su jerarquía funciona para la empresa activa y no es visible para otras.

**Acceptance Scenarios**:

1. **Given** una empresa activa, **When** se crean centros y una jerarquía, **Then** se guardan y el árbol se consulta.
2. **Given** la consulta desde otra empresa, **When** se lista, **Then** no se muestran dichos centros.

---

### User Story 2 - Imputar apuntes a un centro de coste (Priority: P1)

Al registrar o editar un asiento, el usuario imputa determinados apuntes (líneas) a un centro de coste. La imputación queda ligada al apunte y la mantiene el asiento sin romper su balance.

**Why this priority**: La imputación por apunte permite el análisis granular sin modificar la legalidad del asiento.

**Independent Test**: Imputando un apunte a un centro, la línea conserva el vínculo y el asiento sigue balanceado.

**Acceptance Scenarios**:

1. **Given** un asiento con apuntes, **When** se imputa una línea a un centro, **Then** la línea queda vinculada y el asiento permanece balanceado.
2. **Given** un centro inexistente o de otra empresa, **When** se imputa, **Then** se rechaza.

---

### User Story 3 - Informes de costes por centro (Priority: P2)

El usuario genera informes de gastos e ingresos por centro y período, con subtotales por jerarquía y con precisión monetaria exacta.

**Why this priority**: La información por centro es un insumo clave para justificaciones de subvenciones y dirección.

**Independent Test**: Generando el informe de un centro y período, los importes agregan exactamente los apuntes imputados.

**Acceptance Scenarios**:

1. **Given** apuntes imputados a centros, **When** se genera el informe por centro y período, **Then** suman exactamente los importes imputados.
2. **Given** una jerarquía, **When** se consulta un centro padre, **Then** los subtotales incluyen a sus hijos.

---

### Edge Cases

- ¿Qué ocurre si se imputa a un centro un apunte de otra empresa? → Se rechaza.
- ¿Qué ocurre si se elimina un centro con imputaciones? → Se bloquea; solo se inactiva con histórico preservado.
- ¿Qué ocurre con un apunte sin centro? → Es válido; el informe no lo incluye en centros, pero la imputación es opcional.
- ¿Qué ocurre si se reasigna la imputación de un asiento posteado? → Solo con asiento de rectificación; nunca se edita el apunte posteado.

## Requisitos (TODOs numerados)

1. **T-01** Alta de centros de coste con jerarquía por empresa.
2. **T-02** Vínculo opcional de centros con subvenciones (SPEC-019).
3. **T-03** Imputación de apuntes (líneas) a centros al crear/editar asientos (esquema multilínea SPEC-006).
4. **T-04** Validación de centro válido de la empresa activa.
5. **T-05** Informes de costes por centro con subtotales por jerarquía.
6. **T-06** Protección de centros con imputaciones (inactivación, no borrado).
7. **T-07** Pruebas automáticas (pytest) de imputación, informes y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar los centros de coste por empresa y permitir jerarquías.
- **FR-002**: El sistema MUST vincular opcionalmente centros con subvenciones de la empresa activa (SPEC-019).
- **FR-003**: El sistema MUST imputar apuntes (líneas de asiento) a centros al registrar o rectificar asientos, sin romper el balance del asiento.
- **FR-004**: El sistema MUST rechazar la imputación a centros inexistentes o de otra empresa.
- **FR-005**: El sistema MUST impedir el borrado de centros con imputaciones, permitiendo solo la inactivación.
- **FR-006**: El sistema MUST generar informes de costes por centro y período con totales por jerarquía y precisión exacta.
- **FR-007**: La imputación de asientos posteados MUST conservar la inmutabilidad (solo rectificación).
- **FR-008**: El flujo MUST cumplir la constitución (precisión, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Centro de coste**: Departamentos, proyectos, subvenciones, agrupados en jerarquía por empresa.
- **Imputación**: Vínculo de un apunte (línea de asiento) con un centro.
- **Informe de costes**: Agregación de los importes imputados por centro y período.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las imputaciones se asocian a centros de la empresa activa.
- **SC-002**: El 100 % de los asientos imputados permanecen balanceados.
- **SC-003**: El 100 % de los informes de centro agregan los importes imputados con precisión.
- **SC-004**: El 100 % de los centros con imputaciones no se borran físicamente.
- **SC-005**: El 100 % de los datos de centros están aislados por empresa.

## Assumptions

- La imputación es por apunte (línea), no por asiento completo; un asiento puede repartirse entre varios centros.
- Los centros de coste sirven de base para el análisis de gastos de subvenciones del módulo 019.
- La reasignación de imputaciones en asientos posteados requiere rectificación; nunca una edición directa.

## Dependencias

- SPEC-002 (asientos), SPEC-006 (multilínea), SPEC-019 (subvenciones), SPEC-015 (permisos).