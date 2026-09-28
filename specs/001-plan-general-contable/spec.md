# Feature Specification: Plan General Contable

**Feature Branch**: `001-plan-general-contable`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Implementa el módulo del Plan General Contable (SPEC-001) siguiendo la arquitectura definida en constitution.md: modelo de cuentas con soporte multi-tenant, árbol de cuentas, búsqueda para autocompletar, alta de subcuentas, edición y protección de cuentas con asientos asociados, con pruebas automáticas de aislamiento entre empresas y de jerarquía."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consultar el árbol de cuentas de la empresa activa (Priority: P1)

El contador de una empresa inicia sesión y visualiza el plan de cuentas completo de su empresa como un árbol estructurado, con hasta 5 niveles de profundidad. Solo ve las cuentas de su propia empresa, nunca las de otras.

**Why this priority**: Sin ver el plan de cuentas no es posible registrar operaciones contables; es la base de todo el módulo.

**Independent Test**: Puede probarse visualizando el árbol de cuentas de una empresa y verificando que las cuentas de otras empresas no aparecen.

**Acceptance Scenarios**:

1. **Given** un usuario autenticado de la Empresa A con cuentas creadas, **When** consulta el plan de cuentas, **Then** ve únicamente las cuentas de la Empresa A organizadas jerárquicamente (nivel 1..5).
2. **Given** un usuario de la Empresa A, **When** intenta consultar una cuenta de la Empresa B (por su identificador), **Then** el sistema rechaza la operación y no expone ningún dato de la Empresa B.

---

### User Story 2 - Buscar cuentas apuntables para registrar asientos (Priority: P1)

Durante la introducción de un asiento, el contador escribe en el campo de cuenta y el sistema autocompleta mostrando rápidamente las cuentas **seleccionables (apuntables)**, buscando por código o por nombre.

**Why this priority**: La búsqueda de cuentas apuntables es el punto de entrada de la partida doble; sin ella no se pueden imputar apuntes.

**Independent Test**: Puede probarse introduciendo un texto (código o nombre) y verificando que solo aparecen cuentas seleccionables de la empresa activa.

**Acceptance Scenarios**:

1. **Given** cuentas con códigos/nombres variados y estado apuntable, **When** el usuario escribe un fragmento de código o nombre, **Then** el sistema sugiere solo las cuentas apuntables (`is_selectable = true`) de la empresa activa.
2. **Given** un texto sin coincidencias, **When** el usuario busca, **Then** el sistema devuelve una lista vacía sin errores.

---

### User Story 3 - Alta de subcuentas (Priority: P2)

El contador crea subcuentas bajo una cuenta padre existente dentro del plan de cuentas de su empresa, con un código único por empresa.

**Why this priority**: La ampliación del plan de cuentas es necesaria para adaptarse al desglose contable de cada negocio.

**Independent Test**: Puede probarse creando una subcuenta y verificando que aparece bajo su padre y que solo las subcuentas de último nivel (hojas) se marcan como apuntables.

**Acceptance Scenarios**:

1. **Given** una cuenta padre existente, **When** el contador crea una subcuenta con código y nombre válidos, **Then** se crea correctamente bajo el padre y se hereda la jerarquía (nivel = nivel padre + 1).
2. **Given** una cuenta con cuentas hijas, **When** se intenta editar o conservar su estado apuntable, **Then** el sistema la marca como NO apuntable (solo son apuntables las cuentas de último nivel/hija).
3. **Given** un intento de crear una subcuenta con un código ya existente dentro de la misma empresa, **When** se envía el alta, **Then** el sistema la rechaza con un mensaje claro.
4. **Given** una cuenta en el nivel máximo (nivel 5), **When** se intenta crear una subcuenta hija, **Then** el sistema lo rechaza.

---

### User Story 4 - Editar nombre y estado de una cuenta (Priority: P2)

El contador renombra una cuenta o la inactiva/activa según corresponda, siempre dentro de su empresa y respetando las reglas de protección.

**Why this priority**: Mantener el plan de cuentas actualizado es una tarea frecuente sin la cual el catálogo se degrada.

**Independent Test**: Puede probarse modificando el nombre de una cuenta y su estado activo/inactivo y verificando que las cuentas usadas en asientos no pueden desactivarse.

**Acceptance Scenarios**:

1. **Given** una cuenta sin asientos asociados, **When** el contador la edita, **Then** los cambios de nombre y estado se guardan correctamente.
2. **Given** una cuenta con asientos contables asociados, **When** el contador intenta desactivarla o eliminarla, **Then** el sistema lo bloquea y explica que la cuenta tiene imputaciones.
3. **Given** una cuenta de otra empresa, **When** se intenta editar, **Then** el sistema lo rechaza (no existe para el usuario).

---

### Edge Cases

- ¿Qué ocurre cuando el código de cuenta enviado ya existe dentro de la misma empresa? → Se rechaza el alta (unicidad por empresa).
- ¿Qué ocurre cuando se intenta enlazar un apunte a una cuenta no apuntable o de otro nivel? → Se rechaza la vinculación.
- ¿Qué ocurre cuando se intenta crear una subcuenta bajo un padre inexistente o de otra empresa? → Se rechaza la operación.
- ¿Qué ocurre cuando el plan de cuentas está vacío? → Se muestra el árbol vacío sin errores; las cuentas de nivel 1 se crean sin padre.
- ¿Qué ocurre con códigos que se solapan (p. ej., "430" vs "4300")? → Se gestionan como entidades distintas y únicas; la búsqueda los distingue por coincidencia exacta/prefijo.
- ¿Qué ocurre si una cuenta tiene hijos y se intenta desactivar? → Se evalúa la regla: solo se requiere protección si la cuenta (o sus dependientes) tiene asientos asociados.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar por completo las cuentas de cada empresa (multi-tenant): toda consulta, búsqueda, alta, edición o desactivación opera exclusivamente sobre las cuentas de la empresa activa del usuario autenticado.
- **FR-002**: El sistema MUST exponer el plan de cuentas de la empresa activa como un árbol estructurado con hasta 5 niveles de profundidad.
- **FR-003**: El sistema MUST permitir buscar cuentas por fragmentos del código o del nombre (autocompletar), retornando únicamente cuentas apuntables de la empresa activa.
- **FR-004**: El sistema MUST permitir dar de alta cuentas con código, nombre, empresa y, opcionalmente, cuenta padre, rechazando códigos duplicados dentro de la misma empresa.
- **FR-005**: El sistema MUST marcar como apuntable únicamente las cuentas de último nivel (hojas) dentro de su rama; las cuentas con hijos NO son apuntables.
- **FR-006**: El sistema MUST limitar la profundidad del plan de cuentas a 5 niveles y rechazar altas que la superen.
- **FR-007**: El sistema MUST permitir editar el nombre y el estado activo/inactivo de una cuenta de la empresa activa.
- **FR-008**: El sistema MUST impedir la eliminación o desactivación de una cuenta que tenga asientos contables asociados, tanto a nivel de interfaz/API como de base de datos.
- **FR-009**: El sistema MUST registrar la fecha de creación y de última modificación de cada cuenta en formato de hora universal (UTC).
- **FR-010**: El usuario MUST poder distinguir visualmente en el árbol cuándo una cuenta está inactiva y cuándo es apuntable.

### Key Entities *(include if feature involves data)*

- **Cuenta contable**: Representa un nodo del plan de cuentas de una empresa. Atributos: identificador, empresa a la que pertenece (aislamiento), código, nombre, cuenta padre (relación jerárquica consigo misma), nivel (1..5), apuntable (sí/no), activo (sí/no) y marcas temporales UTC.
- **Empresa / Tenant**: Entidad existente de la plataforma que agrupa y aísla los datos de cada cliente; el módulo opera siempre dentro de una empresa activa del usuario.
- **Asiento contable**: Entidad del dominio contable (definida en la constitución) cuyos apuntes se vinculan a cuentas; su existencia protege las cuentas frente a eliminación/desactivación.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los intentos de una empresa por consultar, buscar, modificar o desactivar cuentas de otra empresa son rechazados y no filtran ningún dato (verificado por pruebas automáticas).
- **SC-002**: En una búsqueda de autocompletar, el usuario ve las sugerencias en menos de 1 segundo en condiciones normales de red.
- **SC-003**: Una subcuenta dada de alta aparece bajo su padre dentro de su rama jerárquica de forma inmediata; el 100 % de los altas con código duplicado son rechazadas.
- **SC-004**: El 100 % de los intentos de eliminar o desactivar cuentas con asientos asociados son bloqueados con un mensaje comprensible para el usuario.
- **SC-005**: Solo las cuentas de último nivel (hojas) son apuntables; el 100 % de las cuentas con descendencia se mantienen NO apuntables.

## Assumptions

- El módulo de autenticación/sesión (JWT/sesión) ya existe y provee la identidad del usuario y su **empresa activa**; el plan de cuentas no implementa autenticación propia.
- El plan de cuentas parte vacío (o con el catálogo existente en la base de datos); el catálogo estándar (seed) se incorpora por el seeding automático por tenant definido en el plan (plan.md raíz: seed_default_pgc al crear empresa); esta feature cubre la gestión manual y las versiones normativas se tratan en SPEC-025.
- No se expone un borrado físico definitivo de cuentas (`DELETE` no forma parte de la API); la protección de cuentas con asientos aplica a la desactivación y a cualquier intento de borrado defensivo a nivel de datos.
- La gestión de cuentas es exclusiva de usuarios con rol contable; el control de permisos por rol se asume cubierto por la plataforma.
- Las reglas de arquitectura e inmutabilidad definidas en la constitución del proyecto (multitenancy estricto, partida doble, precisión decimal en importes, pruebas obligatorias) MUST respetarse en el flujo completo de esta feature.

## Dependencias

- SPEC-003 (multiempresa: tabla companies para la tenancy).