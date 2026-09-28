# Feature Specification: Versionado del Plan de Cuentas (Vigencias Normativas)

**Feature Branch**: `025-catalogo-versionado`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Actualización normativa del catálogo: versionado del plan contable (vigencia por ejercicio) para cambios de PGC"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar una nueva versión del plan de cuentas (Priority: P1)

El administrador incorpora una nueva versión del catálogo (p. ej., por actualización normativa del PGC) indicando su vigencia (fecha/ejercicio de inicio). El sistema conserva las versiones anteriores intactas.

**Why this priority**: Permite convivir ejercicios con catálogos distintos sin romper la inmutabilidad de los asientos.

**Independent Test**: Creando una nueva versión del catálogo, los asientos antiguos siguen usando su versión original.

**Acceptance Scenarios**:

1. **Given** un catálogo vigente, **When** se registra una nueva versión con vigencia, **Then** quedan dos versiones con sus ámbitos de vigencia y ningún asiento se migra retroactivamente.
2. **Given** una cuenta eliminada en la nueva versión, **When** se consulta un asiento antiguo, **Then** la cuenta sigue disponible en su contexto histórico.

---

### User Story 2 - Importar el catálogo de una nueva normativa (Priority: P2)

El usuario importa una actualización normativa del catálogo (nuevas cuentas, renombradas o suprimidas) definiendo el mapeo de cuentas afectadas entre versiones.

**Why this priority**: Facilita la adaptación a cambios de norma con trazabilidad del mapeo.

**Independent Test**: Importando una actualización con mapeo, las cuentas nuevas se incorporan y las renombradas se enlazan.

**Acceptance Scenarios**:

1. **Given** una actualización normativa, **When** se importa, **Then** se crean las cuentas nuevas y el mapeo de las renombradas/suprimidas.
2. **Given** una cuenta suprimida sin mapeo, **When** se valida, **Then** el sistema avisa antes de cerrar la migración.

---

### User Story 3 - Reclasificar saldos al cambiar de versión (Priority: P2)

Al abrir un nuevo ejercicio con una versión distinta, el usuario revisa y confirma la reclasificación de saldos (o los movimientos) según el mapeo antes de generar la apertura.

**Why this priority**: Garantiza que el balance de apertura encaja con el nuevo catálogo.

**Independent Test**: Reclasificando los saldos de apertura con el mapeo se generan los movimientos en las cuentas nuevas y el balance cuadra.

**Acceptance Scenarios**:

1. **Given** un cambio de versión para el nuevo ejercicio, **When** se confirma la reclasificación, **Then** los saldos se trasladan a las cuentas nuevas conforme al mapeo.
2. **Given** saldos reclasificados, **When** se abre el ejercicio (SPEC-009), **Then** el balance de apertura cuadra con el nuevo catálogo.

---

### Edge Cases

- ¿Qué ocurre con una cuenta histórica usada en asientos del ejercicio anterior? → Seguirá visible en su contexto; la nueva versión solo afecta a partir de su vigencia.
- ¿Qué ocurre si el mapeo deja una cuenta sin destino? → Se bloquea la activación de la nueva versión hasta resolver el mapeo.
- ¿Qué ocurre si dos versiones comparten vigencia? → Se rechaza el solape de vigencia por empresa.
- ¿Qué ocurre si se suprime una cuenta con saldo distinto de cero? → Se requiere mapeo explícito o cero saldo para activar la versión.

## Requisitos (TODOs numerados)

1. **T-01** Modelo de versiones del catálogo con vigencia (fecha inicio/fin) por empresa y tenant.
2. **T-02** Importación de catálogos normativos con alta/baja/cambio de cuentas.
3. **T-03** Mapeo de cuentas entre versiones (renombradas, suprimidas, nuevas).
4. **T-04** Consulta histórica: los asientos usan la versión vigente en su fecha.
5. **T-05** Reclasificación de saldos para apertura (SPEC-009) y validación de balance.
6. **T-06** Validación de solape y mapeos incompletos antes de activar.
7. **T-07** Pruebas automáticas (pytest) de vigencias, mapeos y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST versionar el plan de cuentas por empresa con vigencia sin solapes, ejercer sobre la empresa activa y conservar las versiones anteriores intactas.
- **FR-002**: El sistema MUST permitir importar actualizaciones normativas del catálogo (altas, bajas y renombrados) definiendo un mapeo entre versiones.
- **FR-003**: El sistema MUST resolver cada asiento con la versión del catálogo vigente en la fecha del asiento, garantizando la consulta histórica.
- **FR-004**: El sistema MUST validar que toda cuenta suprimida con saldo distinto de cero tenga mapeo explícito antes de activar la nueva versión.
- **FR-005**: El sistema MUST reclasificar los saldos conforme al mapeo para la apertura del ejercicio (SPEC-009), cuadrando el balance de apertura.
- **FR-006**: El sistema MUST rechazar el solape de vigencias y los mapeos incompletos.
- **FR-007**: El flujo MUST cumplir la constitución (precisión Decimal, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **CatalogoVersion**: Versión del plan de cuentas con vigencia por empresa.
- **MapeoCuenta**: Relación entre una cuenta de la versión anterior y su(s) equivalente(s) en la nueva.
- **Reclasificación**: Traslado de saldos de apertura a las cuentas de la nueva versión.
- **Vigencia**: Rango de fechas/ejercicios en que una versión es aplicable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los asientos se resuelven con la versión vigente en su fecha.
- **SC-002**: El 100 % de las cuentas suprimidas con saldo tienen mapeo o bloqueo detectable.
- **SC-003**: El 100 % de las aperturas reclasificadas cuadran el balance según SPEC-009.
- **SC-004**: El 0 % de vigencias solapadas se activan por empresa.
- **SC-005**: Los saldos reclasificados conservan la precisión de 4 decimales.

## Assumptions

- La versión del plan de cuentas es un dato multi-tenant (catálogo por empresa), compatible con SPEC-001 y el `plan.md` de PGC.
- La importación de normativa se hace con un formato estructurado (CSV/JSON) con el mapeo; la vigencia suele coincidir con el ejercicio económico.
- Los asientos ya contabilizados no se reescriben (inmutabilidad); solo los saldos de apertura se reclasifican explícitamente.
- La activación de una nueva versión se confirma antes de la apertura del ejercicio (SPEC-009).

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-003 (multiempresa/tenant), SPEC-009 (apertura de ejercicio), SPEC-002 (motor de asientos para recuperar vigencias).