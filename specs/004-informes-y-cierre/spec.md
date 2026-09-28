# Feature Specification: Contabilidad Habitual, Informes y Cierre de Ejercicio

**Feature Branch**: `004-informes-y-cierre`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Especifica las funcionalidades contables habituales y el motor de informes (SPEC-004) siguiendo constitution.md: facturas emitidas y recibidas (precisión decimal), ejercicios contables con bloqueo (is_closed), Balance de Sumas y Saldos, Libro Mayor por subcuenta, cierre de ejercicio atómico (regularización + cierre + bloqueo), validación de ejercicios cerrados al crear asientos, y pruebas de cuadre, bloqueo de periodos y multi-tenant."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consultar el Balance de Sumas y Saldos (Priority: P1)

El contador genera el Balance de Sumas y Saldos de su empresa para un rango de fechas y un nivel de profundidad del plan de cuentas. El informe agrega los movimientos del Debe y del Haber por cuenta y siempre cuadra (suma total del Debe == suma total del Haber).

**Why this priority**: El balance de sumas y saldos es la verificación formal de la partida doble a nivel de ejercicio; es el informe de control por excelencia.

**Independent Test**: Generando el informe para varios rangos y niveles de cuentas, la suma del Debe es siempre idéntica a la del Haber y solo incluye asientos de la empresa activa.

**Acceptance Scenarios**:

1. **Given** asientos asentados en el rango solicitado, **When** se genera el Balance de Sumas y Saldos de la empresa activa, **Then** se agregan por cuenta (en el nivel de profundidad indicado) los movimientos y saldos, con Sum(Debe) == Sum(Haber) exactamente.
2. **Given** asientos de otra empresa en el mismo rango, **When** se genera el balance, **Then** no se incluye ningún movimiento de la otra empresa.

---

### User Story 2 - Consultar el Libro Mayor de una subcuenta (Priority: P1)

El contador consulta el extracto del Libro Mayor de una subcuenta concreta, obteniendo el detalle cronológico de los apuntes (debe, haber y saldo acumulado) de su empresa.

**Why this priority**: El Libro Mayor es el informe de trazabilidad por cuenta y sustenta conciliaciones y auditoría.

**Independent Test**: Consultando el mayor de una subcuenta se obtienen solo los apuntes de esa subcuenta de la empresa activa, ordenados cronológicamente, con saldo acumulado correcto.

**Acceptance Scenarios**:

1. **Given** apuntes sobre una subcuenta de la empresa activa, **When** se consulta su Libro Mayor, **Then** se devuelven los movimientos cronológicos con Debe, Haber y saldo acumulado exactos.
2. **Given** la subcuenta pertenece a otra empresa, **When** se intenta consultar su mayor, **Then** el sistema niega la operación sin exponer datos.

---

### User Story 3 - Cerrar el ejercicio contable (Priority: P2)

Al finalizar el ejercicio, el contador ejecuta el cierre: el sistema genera de forma atómica el asiento de regularización (cuentas de resultados, grupos 6 y 7), el asiento de cierre del ejercicio y bloquea definitivamente el periodo (is_closed = True). Si algo falla en el proceso, no queda ningún cambio parcial.

**Why this priority**: El cierre inmoviliza el ejercicio cumpliendo la inmutabilidad del diario; la atomicidad garantiza que el bloqueo nunca se aplica sin los asientos de cierre o viceversa.

**Independent Test**: Ejecutando el cierre, aparecen los asientos de regularización y cierre y el ejercicio queda bloqueado; si el proceso falla a mitad, el ejercicio permanece abierto.

**Acceptance Scenarios**:

1. **Given** un ejercicio abierto con asientos asentados, **When** se ejecuta el cierre, **Then** se generan el asiento de regularización y el asiento de cierre, y el ejercicio queda marcado como cerrado.
2. **Given** un ejercicio ya cerrado, **When** se intenta cerrar de nuevo, **Then** el sistema lo rechaza sin generar asientos duplicados.
3. **Given** un fallo durante el cierre, **When** el proceso se interrumpe, **Then** no queda ninguna huella parcial (regularización, cierre y bloqueo se aplican juntos o ninguno).

---

### User Story 4 - Registrar y conservar facturas (Priority: P2)

El sistema conserva las facturas emitidas y recibidas de cada empresa, con sus importes monetarios de precisión exacta (base imponible, IVA y total) y vinculadas al asiento contable que las soporta.

**Why this priority**: Las facturas son el documento soporte de la contabilidad; su persistencia con precisión exacta evita desajustes frente a otros módulos.

**Independent Test**: Almacenando facturas de distintos tipos (emitida/recibida) se conservan sus importes sin errores de redondeo y se respeta la numeración correlativa por empresa.

**Acceptance Scenarios**:

1. **Given** una factura emitida y una recibida de la misma empresa, **When** se consultan sus datos, **Then** sus importes (base, IVA, total) se conservan con precisión monetaria exacta y su numeración es correlativa dentro de la empresa.
2. **Given** una factura de otra empresa, **When** se intenta acceder, **Then** el sistema niega la operación (aislamiento).

---

### Edge Cases

- ¿Qué ocurre si la fecha de un asiento pertenece a un ejercicio cerrado? → Se rechaza la operación de registro (HTTP 400); ninguna escritura entra en el periodo bloqueado.
- ¿Qué ocurre si la fecha de un asiento no pertenece a ningún ejercicio definido? → Se rechaza (HTTP 400); no se crean ejercicios automáticamente.
- ¿Qué ocurre si el Balance de Sumas y Saldos se pide a un nivel de profundidad mayor que el plan existente? → Se agrega al mayor nivel disponible sin error.
- ¿Qué ocurre si el ejercicio a cerrar tiene asientos en borrador (DRAFT)? → El cierre solo consolida asientos asentados; los borradores deben asentarse o anularse antes del cierre.
- ¿Qué ocurre si el cierre se ejecuta con concurrencia (dos peticiones a la vez)? → Solo un cierre prospera; el otro se rechaza (protección atómica del bloqueo).
- ¿Qué ocurre si una subcuenta no tiene movimientos? → Su Libro Mayor se devuelve vacío sin error.
- ¿Qué ocurre con los importes con más de 4 decimales? → Se aplica la precisión monetaria canónica (4 decimales) en consolidaciones y saldos.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar por completo facturas, ejercicios e informes por empresa: todo acceso, cálculo, cierre o consulta opera exclusivamente sobre la empresa activa del usuario autenticado.
- **FR-002**: El sistema MUST generar el Balance de Sumas y Saldos de la empresa activa, filtrado por rango de fechas y nivel de profundidad del plan de cuentas, agregando Debe, Haber y saldo por cuenta.
- **FR-003**: El Balance de Sumas y Saldos MUST cuadrar siempre: la suma total del Debe es exactamente igual a la suma total del Haber en el informe consolidado.
- **FR-004**: El sistema MUST generar el extracto del Libro Mayor de una subcuenta de la empresa activa, con movimientos cronológicos y saldo acumulado exacto.
- **FR-005**: El sistema MUST conservar las facturas emitidas y recibidas de cada empresa con sus importes (base imponible, IVA y total) en precisión monetaria exacta (nunca coma flotante) y su vínculo con el asiento contable.
- **FR-006**: El sistema MUST aplicar la numeración correlativa de facturas por empresa según la constitución (secuencia sin saltos ni duplicados).
- **FR-007**: El sistema MUST impedir la creación de asientos cuya fecha pertenezca a un ejercicio cerrado (`is_closed`), respondiendo HTTP 400 sin persistir nada.
- **FR-008**: El sistema MUST ejecutar el cierre de ejercicio de forma atómica: asiento de regularización (grupos 6 y 7), asiento de cierre y marcado de `is_closed` se aplican juntos o ninguno.
- **FR-009**: El sistema MUST rechazar el cierre de un ejercicio ya cerrado o la petición de cierre de una empresa no autorizada, sin generar asientos duplicados.
- **FR-010**: El cierre y los asientos generados MUST respetar la partida doble estricta y la inmutabilidad del diario: los asientos de regularización y cierre se registran como asentados y no modificables.
- **FR-011**: El flujo completo de esta feature MUST cumplir las reglas inmutables de la constitución (precisión decimal, inmutabilidad, multi-tenancy, pruebas obligatorias de cuadre, bloqueo y aislamiento).

### Key Entities *(include if feature involves data)*

- **Factura**: Documento soporte de la contabilidad, emitida o recibida; incluye numeración por empresa, fecha, identificación fiscal del tercero, base imponible, IVA y total (precisión monetaria exacta) y el asiento contable vinculado.
- **Ejercicio contable**: Período definido por empresa con fecha de inicio y fin; su estado cerrado/abierto determina si se admiten escrituras en dicho rango.
- **Balance de Sumas y Saldos**: Informe agregado por cuenta (Debe, Haber y saldo) en el rango y nivel solicitados; debe cuadrar siempre.
- **Libro Mayor**: Informe de detalle de una subcuenta con movimientos cronológicos y saldo acumulado.
- **Asiento de regularización / cierre**: Asientos generados por el cierre que saldan las cuentas de gestión (grupos 6 y 7) y trasladan el resultado; quedan inmutables al asentarse.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El Balance de Sumas y Saldos cuadra en el 100 % de las generaciones verificadas (Sum(Debe) == Sum(Haber)) para cualquier rango, nivel de profundidad y empresa.
- **SC-002**: El 100 % de los intentos de registrar asientos en ejercicios cerrados son rechazados con HTTP 400 y no dejan ningún cambio.
- **SC-003**: El 100 % de los informes de una empresa excluyen asientos, facturas y saldos de cualquier otra empresa (verificado por pruebas automáticas).
- **SC-004**: El cierre de ejercicio es atómico en el 100 % de las ejecuciones: regularización, cierre y bloqueo se completan juntos o no se aplica ninguno.
- **SC-005**: El 100 % de los importes monetarios de facturas e informes se presentan con precisión exacta (4 decimales) sin errores de redondeo.

## Assumptions

- La gestión y creación de ejercicios contables (alta de `fiscal_years`) queda fuera del alcance de esta feature: los ejercicios se asumen provisionados y esta feature solo los consulta y los bloquea al cerrar.
- La API de gestión de facturas (alta/listado) queda fuera del alcance de esta feature: solo se define y persiste la entidad factura con sus reglas de precisión y numeración; los endpoints vendrán en una feature posterior.
- El cierre solo considera asientos asentados (POSTED); los asientos en borrador deben asentarse o anularse antes de ejecutar el cierre.
- La reapertura de un ejercicio cerrado queda fuera del alcance (require un proceso formal futuro); en esta feature un ejercicio cerrado permanece bloqueado.
- La fecha de un asiento debe pertenecer a un ejercicio definido; si no, se rechaza el registro (sin creación automática de ejercicios).
- La identificación fiscal única de terceros en facturas es responsabilidad del módulo de terceros (futuro); esta feature no la valida.
- Roles: la generación de informes está disponible para los roles contables (ADMIN, ACCOUNTANT, READ_ONLY en modo solo lectura) y el cierre exige rol de gestión (ADMIN/ACCOUNTANT) según la matriz de permisos definida en SPEC-003.

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-003 (multiempresa).