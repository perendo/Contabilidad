# Feature Specification: Gestión ONG (Subvenciones, Libros Oficiales y Caja)

**Feature Branch**: `019-gestion-ong-libros-caja`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "gestión de subvenciones y justificación de gastos, impresión PDF y legalización de libros oficiales, así como arqueo de caja / caja chica"

## Clarifications

### Session 2026-09-16

- Q: ¿Cómo se contabilizan los movimientos de caja/caja chica? → A: Apuntes reales del diario: cada entrada/salida genera su asiento sobre una subcuenta 570 por caja; el arqueo contrasta el saldo contable 570 con el efectivo contado (Opción A).
- Q: Si se intenta legalizar dos veces el mismo ejercicio, ¿qué hace el sistema? → A: Re-emisión permitida solo con huella idéntica (contenido sin cambios); si la huella difiere se rechaza (Opción A).
- Q: ¿A qué nivel se imputa un gasto a una subvención? → A: A nivel de línea de asiento (un apunte de gasto concreto, parcial o total); no a asiento completo ni a documento (Opción A).
- Q: ¿La subvención se registra contablemente en esta feature? → A: No: esta feature solo controla el gasto; la percepción/ingreso de la subvención se asienta como asiento normal del motor (SPEC-002) fuera de la feature (Opción A).
- Q: Un arqueo aprobado con diferencia, ¿exige asiento de ajuste? → A: Sí, exigir/validar asiento de ajuste que cuadre 570 con el efectivo; si solo se archiva, la diferencia queda como pendiente visible (Opción A).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Gestionar subvenciones y justificar gastos (Priority: P1)

El responsable de una ONG registra una subvención (entidad concedente, programa, importe concedido, ejercicio) y asigna gastos procedentes de la contabilidad para justificarla. El sistema valida que los gastos imputados no excedan el importe disponible, respeta las partidas del programa y permite generar el informe de justificación (concedido, gastado, pendiente).

**Why this priority**: Sin justificación correcta de fondos la entidad pierde financiación; es el uso principal previsto para ONG.

**Independent Test**: Registrando una subvención y asignándole gastos, el sistema controla el importe disponible y produce el informe de justificación; los gastos de otra empresa no pueden imputarse.

**Acceptance Scenarios**:

1. **Given** una subvención registrada con importe concedido, **When** se asignan gastos de la empresa activa, **Then** la justificación acumula gasto sin superar el disponible y muestra concedido/gastado/pendiente.
2. **Given** un intento de imputar un gasto que excede el importe disponible, **When** se asigna, **Then** el sistema lo rechaza y avisa del exceso.
3. **Given** un gasto perteneciente a otra empresa, **When** se intenta imputar, **Then** el sistema lo rechaza (aislamiento multi-tenant).

---

### User Story 2 - Imprimir y legalizar los libros oficiales (Priority: P2)

El contador genera los libros oficiales (diario, mayor y cuentas anuales) en PDF a partir del ejercicio cerrado, con todos los asientos y su numeración, y obtiene el fichero de legalización que certifica su integridad (empresa, ejercicio, rango de asientos y huella de verificación).

**Why this priority**: Los libros oficiales son obligatorios y deben reflejar exactamente el diario inmutable; la legalización automatizada garantiza coherencia e integridad.

**Independent Test**: Generando los libros de un ejercicio cerrado, el PDF coincide al 100 % con el diario/mayor y el fichero de legalización identifica correctamente empresa y rango.

**Acceptance Scenarios**:

1. **Given** un ejercicio cerrado con asientos asentados, **When** se generan los libros oficiales en PDF, **Then** el documento refleja todos los asientos, numeración y saldos con exactitud decimal.
2. **Given** los libros generados, **When** se emite la legalización, **Then** el fichero incluye empresa, ejercicio, rango de asientos, fecha y huella de integridad de la empresa activa.
3. **Given** un ejercicio abierto, **When** se intenta legalizar, **Then** el sistema exige el cierre previo y no genera el fichero.

---

### User Story 3 - Arqueo de caja y caja chica (Priority: P3)

El tesorero registra los movimientos de una caja o fondo de caja chica (entradas y salidas) y realiza arqueos periódicos: compara el saldo según libro con el efectivo contado y registra la diferencia, que puede aprobarse o requerir ajuste.

**Why this priority**: Control de efectivo físico vs. libros; típico en entidades pequeñas con gastos en metálico.

**Independent Test**: Registrando movimientos de caja y haciendo un arqueo, el sistema calcula el saldo, compara con el efectivo anotado y reporta diferencias.

**Acceptance Scenarios**:

1. **Given** una caja con movimientos registrados, **When** se realiza un arqueo con el efectivo contado, **Then** el sistema calcula la diferencia frente al saldo en libros y la registra.
2. **Given** un arqueo con diferencia, **When** el responsable decide, **Then** la diferencia aprobada exige el asiento de ajuste enlazado que cuadre 570 con el efectivo; si solo se archiva, la diferencia queda marcada como pendiente visible.

---

### Edge Cases

- ¿Qué ocurre si un mismo gasto se quiere imputar a dos subvenciones? → Se divide a nivel de línea de asiento en importes parciales explícitos entre subvenciones/partidas; el sistema evita que la suma de imputaciones de una línea supere su importe total.
- ¿Qué ocurre al imprimir un ejercicio mientras se asientan operaciones? → Los libros solo se generan sobre períodos cerrados para garantizar integridad.
- ¿Qué ocurre si el arqueo no cuadra? → Se registra la diferencia y su estado pasa a "con diferencia"; la aprobación exige el asiento de ajuste enlazado que cuadre 570 con el efectivo, y si solo se archiva la diferencia queda como pendiente visible.
- ¿Qué ocurre con gastos de subvención con IVA no deducible (típico ONG)? → Se imputan por su importe total, conforme a la configuración contable de la empresa.
- ¿Qué ocurre si la subvención es reintegrable tras auditoría? → Se admite el estado reintegro y el ajuste correspondiente (asiento rectificativo).
- ¿Qué ocurre si se intenta legalizar dos veces el mismo ejercicio? → Se permite la re-emisión únicamente si el contenido no cambió (misma huella); si la huella difiere se rechaza (el ejercicio está cerrado e inmutable).

## Requisitos (TODOs numerados)

1. **T-01** Registro de subvenciones (entidad concedente, programa, importe, ejercicio, estado).
2. **T-02** Asignación y control de gastos a subvenciones con límite de disponible y partidas.
3. **T-03** Informe de justificación por subvención (concedido, gastado, pendiente) y exportación.
4. **T-04** Generación de PDF de libros oficiales (diario, mayor, cuentas anuales) con precisión decimal.
5. **T-05** Fichero de legalización con integridad (empresa, ejercicio, rango, huella) restringido a ejercicios cerrados.
6. **T-06** Cajas y caja chica: alta de cajas/fondos y registro de movimientos.
7. **T-07** Arqueo de caja con cálculo de diferencias, aprobación o ajuste.
8. **T-08** Pruebas automáticas (pytest) de límites de subvención, integridad de PDF/legalización, arqueos y aislamiento multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar por completo subvenciones, libros y cajas por empresa: toda operación opera sobre la empresa activa del usuario autenticado.
- **FR-002**: El sistema MUST permitir registrar subvenciones con entidad concedente, programa, importe concedido, ejercicio y estado, como entidad de control del gasto sin generar asientos propios.
- **FR-003**: El sistema MUST permitir asignar gastos contabilizados (de la empresa activa) a una subvención a nivel de línea de asiento (apunte de gasto concreto), validando que el acumulado no exceda el importe disponible y evitando la doble imputación del mismo importe.
- **FR-004**: El sistema MUST generar el informe de justificación por subvención con las cifras de concedido, gastado y pendiente, expresadas con precisión monetaria exacta.
- **FR-005**: El sistema MUST generar los libros oficiales en formato imprimible (PDF) del diario y el mayor, y de las cuentas anuales si están definidas, reflejando fielmente los asientos y saldos en precisión exacta.
- **FR-006**: El sistema MUST generar el fichero de legalización únicamente para ejercicios cerrados, incluyendo empresa, ejercicio, rango de asientos, fecha y huella de integridad. Una re-emisión del mismo ejercicio solo se permite si la huella es idéntica; una huella distinta se rechaza.
- **FR-007**: El sistema MUST garantizar que un ejercicio legalizado no admite asientos posteriores de fecha dentro del ejercicio (refuerzo de bloqueo de SPEC-004).
- **FR-008**: El sistema MUST permitir gestionar cajas/caja chica (fondos fijos) cuyo movimiento de entradas y salidas se registra mediante asientos reales sobre una subcuenta 570 dedicada por caja (una caja = una subcuenta 570 de la empresa activa).
- **FR-009**: El sistema MUST realizar arqueos comparando el saldo en libros con el efectivo contado, calculando la diferencia y registrando su estado; una diferencia aprobada exige el asiento de ajuste enlazado que cuadre la subcuenta 570 con el efectivo, y si solo se archiva la diferencia queda marcada como pendiente visible.
- **FR-010**: Todos los importes del dominio MUST tratarse en precisión decimal canónica; queda prohibida la precisión flotante.
- **FR-011**: El flujo completo MUST cumplir las reglas inmutables de la constitución (partida doble, multi-tenancy, inmutabilidad del diario y pruebas obligatorias).

### Key Entities *(include if feature involves data)*

- **Subvención**: Fondo recibido o concedido a la entidad (concedente, programa, importe y estado) usada como control del gasto; la percepción del ingreso se asienta con asientos normales del motor fuera de esta feature.
- **Gasto imputado / justificación**: Vinculación de una línea de asiento (apunte de gasto concreto) con una subvención y una partida del programa, con importe asignado (parcial o total) y control de doble imputación.
- **Libro oficial**: Representación imprimible (PDF) del diario y el mayor de un ejercicio, y de las cuentas anuales si aplican.
- **Legalización**: Fichero de integridad que certifica los libros de un ejercicio cerrado (empresa, ejercicio, rango y huella).
- **Caja / caja chica**: Fondo de efectivo de la empresa soportado por una subcuenta 570 dedicada; sus movimientos son asientos reales del motor (SPEC-002); **arqueo**: contraste entre el saldo contable de la subcuenta 570 y el efectivo físico contado, con registro de diferencias. Reposición/fondo fijo se rige por transferencia 572→570 u operación equivalente.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los gastos imputados a subvenciones se validan contra el importe disponible y ningún gasto de otra empresa puede imputarse.
- **SC-002**: El 100 % de los PDF de libros oficiales coinciden con el diario/mayor del ejercicio (sin diferencias de asientos ni importes) y conservan la precisión de 4 decimales.
- **SC-003**: El 100 % de los ficheros de legalización se generan solo para ejercicios cerrados e incluyen empresa, ejercicio, rango y huella correctos.
- **SC-004**: El 100 % de los arqueos comparan saldo y efectivo y registran la diferencia (cero o no) sin pérdidas de movimientos.
- **SC-005**: El 100 % de las operaciones de subvenciones, libros y cajas quedan aisladas por empresa (verificado por pruebas automáticas).

## Assumptions

- La gestión de subvenciones se apoya en las cuentas del PGC (SPEC-001) y en los asientos del motor (SPEC-002); el vínculo con proyectos/centros de coste (SPEC-017, futuro) queda opcional.
- El proceso de legalización formal ante entidades/registro es externo; esta feature genera el fichero y los PDF con la integridad necesaria (huella), no sustituye trámites presenciales.
- La caja chica gestiona un único fondo por caja (subcuenta 570) en moneda funcional; la multi-divisa (SPEC-016, futuro) se resuelve fuera de esta feature. La reposición del fondo fijo se contabiliza como operación de tesorería (p. ej., 572→570) y no como movimiento paralelo.
- El tratamiento del IVA de las ONG (no deducible, desgravado) se resuelve con cuentas configuradas por la empresa; esta feature no impone tipos impositivos.
- Un gasto solo se imputa a una subvención salvo división en importes parciales a nivel de línea de asiento explícitamente registrada por el usuario; el sistema evita exceder el disponible y que la suma de imputaciones supere el importe de la línea.

## Dependencias

- SPEC-001 (subcuentas 570), SPEC-002 (motor de asientos), SPEC-004 (informes y cierre), SPEC-015 (permisos por rol), SPEC-016 (multi-divisa), SPEC-017 (centros de coste).