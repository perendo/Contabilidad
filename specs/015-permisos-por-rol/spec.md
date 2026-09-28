# Feature Specification: Matriz de Permisos por Rol

**Feature Branch**: `015-permisos-por-rol`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Matriz de permisos por rol y módulo (operación), con denegación por defecto y verificación en cada operación (diferida de SPEC-003) y el requisito de multiempresa"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Definir la matriz de permisos por rol (Priority: P1)

El administrador define, por cada módulo y operación (ver, crear, editar, aprobar, importar/exportar, configurar), qué roles pueden ejecutarla. La matriz se configura por empresa y se aplica de forma central en el sistema.

**Why this priority**: Sin la matriz, el acceso a los módulos operativos no es controlable ni auditable.

**Independent Test**: Configurando una operación para un rol, solo los usuarios con ese rol pueden ejecutarla; el resto lo tiene denegado.

**Acceptance Scenarios**:

1. **Given** la matriz configurada, **When** un usuario de un rol sin permiso intenta la operación, **Then** se deniega en el sistema.
2. **Given** la matriz de la empresa activa, **When** se accede, **Then** solo se muestran módulos y operaciones permitidas para el rol del usuario.

---

### User Story 2 - Denegación por defecto y restricción multiempresa (Priority: P1)

Toda operación queda denegada por defecto salvo que la matriz la conceda, y aplica por empresa: el usuario no supera el mínimo de la empresa, su rol y el permiso de la operación.

**Why this priority**: Garantiza seguridad por defecto y aislamiento estricto entre empresas (constitución III).

**Independent Test**: Sin matriz explícita para una operación, cualquier intento es denegado; aun con rol global, la falta de acceso de la empresa deniega.

**Acceptance Scenarios**:

1. **Given** una operación sin entrada en la matriz, **When** un usuario la intenta, **Then** se deniega.
2. **Given** un rol con permiso en la empresa A pero no en la B, **When** el usuario actúa sobre la B, **Then** se deniega.

---

### User Story 3 - Auditar las comprobaciones de permiso (Priority: P2)

El sistema registra en el log de auditoría cada intento denegado y cada permiso concedido que afecte a datos contables, con usuario, empresa y operación.

**Why this priority**: La trazabilidad de los accesos sustenta el cumplimiento y la revisión.

**Independent Test**: Denegando una operación o concediéndola, el evento queda registrado con actor, empresa y operación.

**Acceptance Scenarios**:

1. **Given** un intento denegado, **When** se audita, **Then** aparece en el log con usuario y empresa.
2. **Given** una operación concedida sobre asientos, **When** se audita, **Then** queda registrada la operación.

---

### Edge Cases

- ¿Qué ocurre si un rol no existe? → La denegación por defecto evita el acceso.
- ¿Qué ocurre si el usuario es administrador? → Hereda denegaciones por defecto fuera de la matriz, salvo la configuración de la empresa.
- ¿Qué ocurre si se solicita un permiso inexistente? → Se deniega y se registra.
- ¿Qué ocurre con las operaciones de configuración? → Solo las concede la matriz de configuración por empresa.

## Requisitos (TODOs numerados)

1. **T-01** Modelo de matriz (módulo, operación, rol, empresa) con denegación por defecto.
2. **T-02** Endpoint/regla de autorización central verificada en cada operación.
3. **T-03** Restricción multiempresa obligatoria en la comprobación.
4. **T-04** Configuración de la matriz por empresa (administrador).
5. **T-05** Auditoría de intentos denegados y permisos concedidos.
6. **T-06** Pruebas automáticas (pytest) de denegación por defecto y aislamiento de empresas.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aplicar una matriz de permisos por módulo, operación y rol, configurable por empresa.
- **FR-002**: El sistema MUST denegar por defecto toda operación no concedida explícitamente.
- **FR-003**: El sistema MUST verificar la autorización en cada operación del sistema (mínimo entre la empresa, el rol y el permiso), sin bypass posible.
- **FR-004**: El sistema MUST comprobar la empresa activa y su matriz antes de ejecutar cualquier operación de módulos con datos.
- **FR-005**: El sistema MUST registrar en auditoría cada intento denegado y cada permiso concedido con usuario, empresa y operación.
- **FR-006**: Las operaciones de configuración de la matriz MUST estar restringidas a la matriz de configuración de la empresa.
- **FR-007**: El flujo MUST cumplir la constitución (multi-tenancy, seguridad y pruebas obligatorias).

### Key Entities *(include if feature involves data)*

- **Matriz de permisos**: Tabla de módulo × operación × rol × empresa que define los accesos.
- **Rol**: Perfil del usuario (por defecto ADMIN, ACCOUNTANT, READ_ONLY) con accesos según matriz.
- **Evento de auditoría de acceso**: Registro del intento denegado o permiso concedido.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las operaciones sin permiso explícito se deniegan.
- **SC-002**: El 100 % de las operaciones respetan el mínimo empresa × rol × operación.
- **SC-003**: El 100 % de los intentos denegados y permisos concedidos quedan auditados.
- **SC-004**: El 100 % de las operaciones del sistema verifican la autorización sin bypass.
- **SC-005**: Ningún usuario accede a datos de otra empresa aun con rol global.

## Assumptions

- Los roles base (ADMIN, ACCOUNTANT, READ_ONLY) se siembran en la creación de la empresa y se pueblan con la matriz inicial.
- El administrador no excede la matriz de su empresa; no existe un "superusuario" global por defecto.
- La matriz se evalúa en cada petición (no se cachea en exceso para evitar permisos caducados).

## Dependencias

- SPEC-003 (RBAC/determinación de empresa activa), SPEC-001/002 (módulos base) y el resto de features que deberán respetar la matriz.