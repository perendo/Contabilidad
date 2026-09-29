# Feature Specification: Conciliación Bancaria

**Feature Branch**: `013-conciliacion-bancaria`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Conciliación bancaria: importar extractos, cruce automático/manual con los apuntes de banco (572) y control del saldo"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Importar un extracto bancario (Priority: P1)

El usuario importa el extracto de una cuenta bancaria de su empresa (en formato interoperable tipo norma 43/19). El sistema agrupa los movimientos del extracto con su fecha e importe y detecta posibles correspondencias con los apuntes contables de la cuenta 572.

**Why this priority**: Sin extractos no existe conciliación fiable, y su cuadre sustenta el cierre.

**Independent Test**: Importando un extracto de una cuenta 572, los movimientos se cargan y se marcan posibles cruces con apuntes del mismo concepto/importe.

**Acceptance Scenarios**:

1. **Given** un fichero de extracto válido de la cuenta bancaria de la empresa, **When** se importa, **Then** los movimientos se registran y el saldo de extracto se muestra.
2. **Given** un extracto de una cuenta de otra empresa, **When** se importa, **Then** el sistema lo rechaza por aislamiento.

---

### User Story 2 - Conciliar apuntes con movimientos (manualmente y propuestas) (Priority: P1)

El usuario cruza los apuntes contables (572) con los movimientos del extracto, aceptando propuestas automáticas o realizando el cruce manual. Cada cruce concilia el apunte y el movimiento de forma trazable.

**Why this priority**: La conciliación verifica la coherencia entre libros y banco y detecta errores u omisiones.

**Independent Test**: Conciliando apuntes y movimientos, los cruces quedan registrados y el saldo conciliado coincide con la diferencia entre saldos.

**Acceptance Scenarios**:

1. **Given** apuntes y movimientos con coincidencia de importe, **When** se acepta el cruce propuesto, **Then** quedan conciliados con fecha de cruce.
2. **Given** un apunte o movimiento sin correspondencia, **When** se concluye la conciliación, **Then** queda marcado como pendiente visible en el informe.

---

### User Story 3 - Calcular la diferencia de saldos y cerrar la conciliación (Priority: P2)

El contador conoce en todo momento: saldo según banco, saldo según libros y diferencia por conciliar. Al cerrar el período de conciliación, si la diferencia es cero se archiva; si no, se informa de los elementos pendientes.

**Why this priority**: El control del saldo permite cerrar cuadre la tesorería del período.

**Independent Test**: Con todos los movimientos conciliados, la diferencia es cero y el período conciliado queda archivado.

**Acceptance Scenarios**:

1. **Given** todos los apuntes y movimientos cruzan, **When** se cierra el período, **Then** la diferencia es cero y se archiva la conciliación.
2. **Given** elementos sin cruzar, **When** se intenta cerrar, **Then** el sistema advierte y lista los pendientes sin archivar.

---

### Edge Cases

- ¿Qué ocurre si un importe coincide pero el concepto no? → La propuesta se marca como candidata y el usuario decide.
- ¿Qué ocurre con los asientos de la 572 sin extracto (cheques, débitos)? → Quedan pendientes y se detectan en el informe.
- ¿Qué ocurre si se importa el mismo extracto dos veces? → Se detecta el duplicado y se evita la doble carga.
- ¿Qué ocurre si hay divisas (SPEC-016 futuro)? → La conciliación se expresa en la moneda de la cuenta; el cruce usa el importe contable.

## Requisitos (TODOs numerados)

1. **T-01** Importación de extractos bancarios de la cuenta 572 (formato interoperable: 43/19, CSV normalizado o XLSX de banco).
2. **T-02** Detección de duplicados de extracto.
3. **T-03** Propuesta automática y cruce manual de apuntes con movimientos.
4. **T-04** Informe de conciliación: saldo banco, saldo libros, pendientes y diferencia.
5. **T-05** Cierre/archivo del período conciliado con validación de diferencia cero.
6. **T-06** Pruebas automáticas (pytest) de cruces, duplicados y aislamiento multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST importar extractos bancarios de las cuentas 572 de la empresa activa en formato interoperable, con detección de duplicados. Se admiten **tres** formatos: **norma 43/19** (ancho fijo), **CSV normalizado** y **XLSX de banco** (el que descarga el área de clientes de la banca electrónica). Un formato no soportado MUST rechazarse diciendo cuáles sí valen, sin intentar leerlo con el parser de otro formato.
- **FR-002**: El sistema MUST aislar los extractos y la conciliación por empresa.
- **FR-003**: El sistema MUST proponer cruces automáticos (importe y orientación deudora/acreedora) y permitir el cruce manual de apuntes con movimientos.
- **FR-004**: El sistema MUST mantener para cada cuenta el saldo según extracto, saldo según libros, y la lista de elementos pendientes con su diferencia.
- **FR-005**: El sistema MUST archivar el período conciliado solo cuando la diferencia es cero, advirtiendo de los pendientes en caso contrario.
- **FR-006**: Los importes MUST tratarse en precisión decimal exacta y la diferencia se expresa en la cuenta de la empresa.
- **FR-007**: El flujo MUST cumplir la constitución (precisión, trazabilidad, multi-tenancy y pruebas obligatorias).

### Key Entities *(include if feature involves data)*

- **Extracto bancario**: Movimientos de la cuenta 572 del banco en un período.
- **Apunte contable**: Movimiento de la cuenta 572 en nuestros libros procedente de asientos (SPEC-002).
- **Conciliación**: Cruce entre apuntes y movimientos con estado conciliado/pendiente y diferencia.
- **Período conciliado**: Rango archivado con diferencia cero.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los extractos importados se cargan sin duplicados.
- **SC-002**: El 100 % de los cruces quedan trazados (quién y cuándo).
- **SC-003**: El 100 % de los períodos con diferencia cero se archivan; los demás advierten de pendientes.
- **SC-004**: El 100 % de las conciliaciones están aisladas por empresa.
- **SC-005**: Los saldos y diferencias se expresan con precisión de 4 decimales.

## Assumptions

- El formato de extracto es interoperable sin conexión directa a la banca electrónica. **Actualizado 2026-09-29**: se admiten norma 43/19, CSV normalizado y XLSX de banco. El XLSX era el unico formato que la banca entrega en la practica, y la decisión original de este research lo había desestimado; ver `research.md` D1 y D1-bis.
- El extracto en XLSX **no trae código de cuenta**: trae el IBAN. La cuenta 572 a la que corresponde la indica el usuario, porque un IBAN no es un código del plan de cuentas y no existe (ni debe existir) un maestro IBAN → cuenta: eso sería un maestro de bancos que no está en ninguna spec.
- La conciliación cubre cuentas 572 en moneda de la empresa; las cuentas 570 (caja) se concilian con arqueos (SPEC-019).
- Una operación bancaria sin apunte contable genera una alerta, no un asiento automático.

## Dependencias

- SPEC-001 (plan de cuentas 572), SPEC-002 (asientos), SPEC-011 (tesorería), SPEC-012 (fiscal).