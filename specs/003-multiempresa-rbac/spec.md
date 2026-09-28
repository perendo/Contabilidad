# Feature Specification: Multiempresa y Control de Acceso por Roles (RBAC)

**Feature Branch**: `003-multiempresa-rbac`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Especifica la arquitectura de gestión Multiempresa y Control de Acceso basado en Roles (RBAC) (SPEC-003) siguiendo constitution.md: entidades de empresa, usuario y relación usuario-empresa-rol; login con lista de empresas y empresa por defecto; conmutación de empresa activa sin cerrar sesión; creación de empresa con rol ADMIN y plantilla base del PGC; contexto de empresa inyectado en backend y frontend; pruebas de acceso no autorizado (403) y aislamiento de datos."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Iniciar sesión y acceder a las empresas autorizadas (Priority: P1)

El usuario introduce sus credenciales y el sistema lo autentica, devolviendo su sesión junto con la lista de empresas a las que tiene acceso y su empresa por defecto. Las operaciones posteriores ocurren siempre dentro de una de esas empresas.

**Why this priority**: Sin autenticación y contexto de empresa no hay forma de garantizar el aislamiento multi-tenant, pilar de la constitución.

**Independent Test**: Autenticando a un usuario se obtienen su sesión, su lista de empresas y su empresa por defecto; sin credenciales válidas no se inicia ninguna sesión.

**Acceptance Scenarios**:

1. **Given** un usuario con credenciales válidas y acceso a una o más empresas, **When** inicia sesión, **Then** se devuelve su sesión con la lista de empresas accesibles y la empresa marcada por defecto.
2. **Given** un intento de inicio de sesión con credenciales incorrectas o usuario inactivo, **When** se envía, **Then** el sistema rechaza la autenticación sin revelar datos de ninguna empresa.

---

### User Story 2 - Cambiar de empresa activa sin cerrar sesión (Priority: P1)

El usuario, desde el selector de empresa del Navbar, cambia de empresa para trabajar sobre otra de sus organizaciones sin volver a introducir sus credenciales. Su sesión se actualiza y todas las operaciones pasan a ejecutarse bajo la nueva empresa.

**Why this priority**: La conmutación fluida de empresa es el mecanismo cotidiano del multi-empresa y el momento de mayor riesgo de filtración de datos.

**Independent Test**: Seleccionando otra empresa con acceso se actualiza la sesión y los listados de cuentas/asientos devuelven exclusivamente los datos de la nueva empresa.

**Acceptance Scenarios**:

1. **Given** un usuario con acceso a dos empresas, **When** cambia la empresa activa desde el selector, **Then** su sesión se actualiza a la nueva empresa y las peticiones posteriores llevan el contexto nuevo sin exigir re-login.
2. **Given** un intento de cambiar a una empresa sin relación activa del usuario, **When** se solicita el cambio, **Then** el sistema lo rechaza (HTTP 403) y la empresa activa permanece sin cambios.

---

### User Story 3 - Trabajar solo dentro de las empresas autorizadas (Priority: P1)

Cualquier operación (consultas y modificaciones de cuentas, asientos, etc.) exige que el usuario tenga una relación activa con la empresa solicitada. Si la empresa indicada no corresponde al usuario, el sistema deniega la operación de inmediato sin exponer información.

**Why this priority**: Es la garantía directa de la norma de multi-tenancy estricto de la constitución: sin filtro de empresa autorizada no hay contacto con los datos.

**Independent Test**: Enviando una petición con una empresa que no pertenece al usuario se obtiene un rechazo y ningún dato de esa empresa.

**Acceptance Scenarios**:

1. **Given** un usuario autenticado con acceso solo a la Empresa A, **When** envía una petición indicando la Empresa B, **Then** el sistema responde HTTP 403 sin exponer información de la Empresa B.
2. **Given** una empresa inactiva o un usuario inactivo, **When** se intenta operar, **Then** la operación se deniega.
3. **Given** el contexto de empresa autorizado, **When** el usuario consulta cuentas o asientos, **Then** solo recibe los datos de esa empresa.

---

### User Story 4 - Crear una nueva empresa (Priority: P2)

El usuario con capacidad de administración crea una nueva empresa proporcionando su identificación fiscal y razón social. El sistema lo registra como administrador (rol ADMIN) de la nueva empresa e inicializa su plantilla base del Plan General Contable.

**Why this priority**: La creación de nuevas empresas es parte del ciclo de vida del negocio y debe quedar aislada desde su primer registro.

**Independent Test**: Creando una empresa, el creador queda con rol ADMIN en ella y aparece en su lista de empresas; sus cuentas parten de la plantilla base.

**Acceptance Scenarios**:

1. **Given** un usuario autenticado, **When** crea una empresa con identificación fiscal y razón social válidas, **Then** la empresa se registra, el usuario queda como ADMIN de la misma y se inicializa su plan de cuentas base.
2. **Given** una empresa recién creada, **When** el usuario la consulta dentro de su lista, **Then** aparece entre sus empresas accesibles y opera sobre ella con sus datos iniciales aislados.

---

### Edge Cases

- ¿Qué ocurre cuando la petición no incluye ningún contexto de empresa (cabecera o token sin empresa)? → No se puede operar: la operación se deniega; no existe operación "sin empresa".
- ¿Qué ocurre cuando el contexto de empresa incluye un identificador mal formado o inexistente? → Se deniega sin distinguir entre "no existe" y "sin permiso" (sin revelar información).
- ¿Qué ocurre cuando la empresa existe pero el usuario no tiene relación activa? → HTTP 403 inmediato, sin filtrar datos.
- ¿Qué ocurre al cambiar de empresa a mitad de una introducción de asiento? → La sesión se actualiza; el trabajo pendiente debe revalidarse bajo el nuevo contexto o descartarse (regla de frontend).
- ¿Qué ocurre si el usuario solo tiene una empresa? → El selector muestra una única opción y no permite vaciar el contexto.
- ¿Qué ocurre cuando dos usos comparten el mismo correo? → El alta de usuario garantiza correos únicos; asumido en el registro existente de la plataforma.
- ¿Qué ocurre si una empresa se crea con identificación fiscal duplicada? → Se acepta como nueva empresa en esta feature; la unicidad fiscal queda diferida a validación de negocio (supuesto documentado).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST autenticar a los usuarios por credenciales y devolver, en el inicio de sesión, la empresa por defecto y la relación de empresas accesibles del usuario.
- **FR-002**: El sistema MUST derivar el contexto de empresa activo exclusivamente de la sesión autenticada (cabecera o token de sesión), nunca de datos no confiables del cliente, y denegar cualquier operación sin contexto de empresa.
- **FR-003**: El sistema MUST validar, antes de cada operación que toque datos de una empresa, que el usuario autenticado tiene una relación activa en esa empresa; si no, responder HTTP 403 sin exponer información.
- **FR-004**: El sistema MUST permitir al usuario conmutar su empresa activa sin volver a autenticarse, validando el acceso a la nueva empresa y actualizando su sesión.
- **FR-005**: El sistema MUST listar únicamente las empresas a las que el usuario tiene acceso activo.
- **FR-006**: El sistema MUST mantener, por cada par (usuario, empresa), un único rol entre ADMIN, ACCOUNTANT y READ_ONLY; las capacidades de escritura se restringen según el rol (mínimo: READ_ONLY no puede escribir).
- **FR-007**: El sistema MUST asignar automáticamente el rol ADMIN al usuario que crea una nueva empresa e inicializar la plantilla base del plan de cuentas de la nueva empresa.
- **FR-008**: El sistema MUST considerar una relación (usuario, empresa) como activa únicamente cuando tanto el usuario como la empresa están activos.
- **FR-009**: El aislamiento de datos de cuentas y asientos MUST mantenerse sin fisuras al cambiar la empresa activa: cada conmutación altera exclusivamente el contexto, nunca expone datos de otra empresa.
- **FR-010**: El flujo completo de esta feature MUST cumplir las reglas inmutables de la constitución del proyecto (multi-tenancy estricto, pruebas obligatorias de aislamiento y acceso).

### Key Entities *(include if feature involves data)*

- **Empresa (Tenant)**: Entidad que representa una razón social independiente del sistema; identificación fiscal, razón social, estado activo y fecha de creación. Agrupa y aísla todos sus datos.
- **Usuario**: Entidad global de la plataforma; correo único, credenciales cifradas, nombre completo y estado activo. Un usuario puede pertenecer a varias empresas.
- **Relación usuario-empresa-rol**: Entidad intermedia que determina las empresas a las que accede un usuario y el rol que desempeña en cada una (ADMIN, ACCOUNTANT, READ_ONLY), incluida la empresa por defecto.
- **Sesión de usuario**: Estado autenticado del usuario que transporta la empresa activa actual; su renovación permite la conmutación de empresa sin re-login.
- **Plan de cuentas base**: Conjunto inicial de cuentas que se crea para cada nueva empresa (depende del módulo de Plan General Contable, SPEC-001).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las peticiones con contexto de empresa no perteneciente al usuario responden HTTP 403 y no filtran ningún dato (verificado por pruebas automáticas).
- **SC-002**: Al conmutar la empresa activa, el 100 % de las consultas de cuentas y asientos devuelven exclusivamente los datos de la nueva empresa.
- **SC-003**: El 100 % de las peticiones salientes del frontend incluyen el contexto de empresa activa; ninguna petición de datos se emite sin contexto.
- **SC-004**: Un cambio de empresa se refleja en la sesión y en la interfaz en menos de 1 segundo y sin exigir volver a iniciar sesión.
- **SC-005**: El 100 % de las empresas creadas quedan con su creador como ADMIN y con su plan de cuentas base inicializado.

## Assumptions

- El alta de usuarios (registro) y la gestión de contraseñas quedan fuera del alcance de esta feature; el inicio de sesión asume usuarios ya existentes y activos.
- La matriz detallada de permisos por rol (qué endpoint requiere qué rol) se define durante el diseño técnico; esta feature exige como mínimo el bloqueo de escritura para el rol READ_ONLY.
- La unicidad de la identificación fiscal entre empresas queda diferida a validación de negocio; no se fuerza en esta feature.
- Una relación (usuario, empresa) se considera activa cuando el usuario y la empresa están activos (el modelo de relación cuenta con empresa por defecto e is_default).
- La plantilla base del plan de cuentas para nuevas empresas se obtiene del módulo de Plan General Contable (SPEC-001); esta feature la invoca al crear una empresa.
- El marco de autenticación se basa en tokens de sesión (JWT); el detalle del algoritmo y expiración se decide en el diseño técnico.

## Dependencias

- SPEC-001 (plan de cuentas como módulo base protegido). Base de la tenancy y RBAC, sin dependencias funcionales previas.