# Feature Specification: Motor de Asientos Contables

**Feature Branch**: `002-motor-asientos-contables`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Especifica el motor de asientos contables (SPEC-002) siguiendo estrictamente las reglas inmutables de constitution.md: cabecera de asiento con numeración secuencial por empresa/ejercicio, apuntes (Debe/Haber con precisión decimal), partida doble estricta (Sum debe == Sum haber), inmutabilidad de asientos POSTED, anulación por asiento de rectificación, libro diario paginado por fechas, auditoría automática y pruebas de desbalanceo/inmutabilidad/multi-tenant."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar un asiento contable (Priority: P1)

El contador de una empresa registra un asiento indicando fecha, concepto y una o más líneas de apunte (Debe/Haber) sobre cuentas apuntables de su propia empresa. El sistema guarda cabecera y líneas de forma indivisible y solo acepta asientos perfectamente balanceados.

**Why this priority**: La partida doble es el invariante fundamental del dominio; sin el registro de asientos no existe contabilidad.

**Independent Test**: Registrando un asiento balanceado (suma debe == suma haber) se persiste correctamente; un asiento desbalanceado se rechaza con un error claro y no deja rastro parcial.

**Acceptance Scenarios**:

1. **Given** un usuario autenticado de la Empresa A con cuentas apuntables, **When** registra un asiento balanceado con uno o más apuntes, **Then** se guardan cabecera y líneas de forma indivisible, con número secuencial dentro del ejercicio.
2. **Given** un asiento donde la suma del Debe no es exactamente igual a la suma del Haber, **When** se intenta guardar, **Then** el sistema lo rechaza sin persistir nada (error de validación, sin estado parcial).
3. **Given** un apunte que referencia una cuenta NO apuntable o de otra empresa, **When** se intenta guardar el asiento, **Then** el sistema lo rechaza y no persiste el asiento.
4. **Given** un asiento balanceado pero con importes que exigen precisión monetaria, **When** se guarda, **Then** los importes se conservan sin errores de redondeo (nunca coma flotante).

---

### User Story 2 - Consultar el libro diario (Priority: P1)

El contador consulta el libro diario de su empresa, filtrado por rango de fechas y con paginación, de mayor a menor. Solo ve asientos de su empresa.

**Why this priority**: El libro diario es el registro cronológico exigido por la normativa contable; sin él no hay trazabilidad del ejercicio.

**Independent Test**: Consultando el libro diario con fechas y página determinadas se obtienen sólo los asientos de la empresa activa del usuario en ese rango.

**Acceptance Scenarios**:

1. **Given** asientos de la Empresa A y de la Empresa B en el mismo rango de fechas, **When** el usuario de la Empresa A consulta el libro diario, **Then** solo aparecen los asientos de la Empresa A, ordenados cronológicamente.
2. **Given** un rango de fechas y un número de página, **When** se consulta, **Then** se devuelve la página correspondiente con la paginación correcta y sin saltos de registros.

---

### User Story 3 - Anular un asiento asentado (Priority: P2)

Cuando el contador debe corregir un asiento ya asentado (`POSTED`), el sistema no permite modificarlo ni borrarlo, sino que genera un nuevo asiento de rectificación con los importes invertidos (Debe <-> Haber) que deja el balance en cero, y deja constancia del vínculo con el asiento original.

**Why this priority**: La inmutabilidad del diario es una regla constitucional; la corrección solo es válida mediante anulación/rectificativo, garantizando la integridad histórica.

**Independent Test**: Intentando anular un asiento asentado se genera un nuevo asiento rectificativo balanceado y el original queda marcado como anulado; ningún intento de borrar o modificar el asiento original prospera.

**Acceptance Scenarios**:

1. **Given** un asiento en estado asentado (`POSTED`), **When** el usuario solicita su anulación, **Then** el sistema genera un nuevo asiento rectificativo con los importes invertidos, igual número de apuntes, y la suma neta queda en cero.
2. **Given** un asiento asentado, **When** se intenta eliminarlo o modificarlo, **Then** el sistema lo rechaza (operación no permitida) y deja los datos intactos.
3. **Given** un asiento ya anulado, **When** se intenta anular de nuevo, **Then** el sistema lo rechaza con un mensaje claro.

---

### Edge Cases

- ¿Qué ocurre con un asiento sin líneas o con una sola línea? → Se rechaza: la partida doble exige al menos un apunte en Debe y uno en Haber, o igual suma.
- ¿Qué ocurre cuando la suma Debe == Haber pero alguna línea referencia una cuenta inexistente o de otro tenant? → Se rechaza sin persistir nada.
- ¿Qué ocurre al superponer fechas de distintos ejercicios fiscales? → La numeración se calcula por empresa y ejercicio; cada ejercicio reinicia su secuencia.
- ¿Qué ocurre cuando dos usuarios registran asientos a la vez? → La asignación del número secuencial es atómica: sin duplicados ni omisiones.
- ¿Qué ocurre al anular un asiento cuya fecha es de un ejercicio cerrado? → Regla de negocio a definir en cierres; supuesto: anulación permitida, el rectificativo toma la fecha actual o la indicada por el usuario.
- ¿Qué ocurre si el asiento balanceado usa importes con más de 4 decimales? → El sistema aplica la precisión monetaria definida (4 decimales) y la validación de balance opera sobre la precisión canónica.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar por completo los asientos y apuntes de cada empresa: toda creación, consulta, anulación o numeración opera exclusivamente sobre la empresa activa del usuario autenticado.
- **FR-002**: El sistema MUST aplicar la partida doble estricta: un asiento solo se acepta si la suma del Debe es exactamente igual a la suma del Haber; si no cuadra, el alta se aborta sin persistir nada.
- **FR-003**: El sistema MUST validar que todas las cuentas referenciadas por los apuntes son apuntables (`is_selectable`) y pertenecen a la misma empresa del asiento.
- **FR-004**: El sistema MUST persistir cabecera y líneas del asiento de forma indivisible (transacción atómica): si alguna validación falla, no queda ningún rastro parcial.
- **FR-005**: El sistema MUST asignar el número de asiento de forma secuencial y sin saltos, por empresa y por ejercicio contable, de manera atómica incluso bajo concurrencia.
- **FR-006**: El sistema MUST tratar los importes con precisión monetaria exacta (4 decimales) en todo el flujo; queda prohibido el uso de precisión flotante para importes contables.
- **FR-007**: El sistema MUST mantener un libro diario consultable por empresa, con filtro obligatorio de fecha (rango) y paginación, ordenado cronológicamente.
- **FR-008**: El sistema MUST tratar los asientos asentados (`POSTED`) como inmutables: queda prohibido su modificación o eliminación; toda corrección usa un asiento de anulación/rectificativo.
- **FR-009**: El sistema MUST generar, al anular un asiento, un nuevo asiento rectificativo balanceado con los importes invertidos (Debe <-> Haber) y el vínculo al asiento original; el original pasa a estado anulado (`CANCELLED`).
- **FR-010**: El sistema MUST registrar automáticamente en el registro de auditoría cada creación y anulación de asiento, incluyendo empresa, usuario, acción, identificador de la entidad, fecha-hora universal (UTC) y dirección IP.
- **FR-011**: El sistema MUST exponer los estados de asiento previstos (borrador, asentado, anulado) y controlar las transiciones permitidas (borrador → asentado; asentado → anulado mediante rectificativo).
- **FR-012**: El flujo completo de esta feature MUST cumplir las reglas inmutables de la constitución del proyecto (partida doble, inmutabilidad del diario, multi-tenancy estricto, numeración correlativa, pruebas obligatorias).

### Key Entities *(include if feature involves data)*

- **Asiento contable (Cabecera)**: Entidad que agrupa los apuntes de una operación contable. Atributos: identificador, empresa (aislamiento), número de asiento, ejercicio fiscal, fecha del asiento, concepto, estado (borrador/asentado/anulado), fecha de creación y usuario que lo creó.
- **Apunte contable (Línea)**: Entidad detallada del asiento. Atributos: identificador, empresa, asiento al que pertenece, cuenta contable imputada, importes de Debe y de Haber (precisión monetaria exacta) y detalle del concepto.
- **Ejercicio contable**: Período derivado de la fecha del asiento que agrupa y numera la secuencia; definido por la plataforma (asignación/cambio de ejercicio queda fuera de esta feature).
- **Cuenta contable**: Entidad existente del módulo de Plan General Contable (SPEC-001); los apuntes se vinculan a cuentas apuntables de la misma empresa.
- **Registro de auditoría**: Entidad existente de la plataforma donde se registran obligatoriamente las operaciones de escritura con su trazabilidad completa.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los intentos de registrar asientos desbalanceados (suma Debe != suma Haber) son rechazados sin dejar ningún dato parcial en el sistema.
- **SC-002**: El 100 % de los intentos de una empresa de consultar, modificar o anular asientos de otra empresa son rechazados y no filtran información.
- **SC-003**: El 100 % de los intentos de modificar o eliminar asientos ya asentados son bloqueados y los datos permanecen intactos.
- **SC-004**: El 100 % de las anulaciones producen un asiento rectificativo balanceado (importes invertidos) con suma neta cero y marcan el original como anulado.
- **SC-005**: El 100 % de las creaciones y anulaciones generan su correspondiente registro de auditoría con los campos de trazabilidad completos.
- **SC-006**: La numeración de asientos es secuencial y sin saltos por empresa y ejercicio; se detecta y rechaza automáticamente cualquier duplicado.

## Assumptions

- El módulo de autenticación/sesión provee la identidad del usuario y su empresa activa; la empresa siempre se deriva del contexto autenticado, nunca de datos del cliente.
- El **ejercicio fiscal** (`fiscal_year`) se deriva de la fecha del asiento (campo de la cabecera), no se introduce manualmente; el alta/cambio de ejercicio contable queda fuera del alcance de esta feature.
- El registro de auditoría (`audit_logs`) ya existe como infraestructura de plataforma (norma de la constitución) y esta feature lo invoca asegurando que el evento se persiste en la misma transacción que la operación auditada.
- La numeración secuencial sin saltos se garantiza por asignación atómica dentro de la transacción de persistencia; ante un fallo, los números no emitidos no se reutilizan (regla de correlatividad de la constitución).
- La anulación de un asiento genera un asiento rectificativo con la fecha indicada por el usuario (por defecto, la fecha actual); el bloqueo por ejercicio cerrado no forma parte de esta feature.
- El rol de contador es el habilitado para estas operaciones; el control fino de permisos por rol se asume cubierto por la plataforma.

## Dependencias

- SPEC-001 (plan general contable), SPEC-003 (multiempresa).