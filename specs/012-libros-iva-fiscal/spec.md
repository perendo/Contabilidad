# Feature Specification: Libros de IVA y Modelos Fiscales

**Feature Branch**: `012-libros-iva-fiscal`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Libros de registro de IVA (emitidas/recibidas), cuadre de modelos (303, 347, 349) y exportación para presentación; SII como opción futura"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generar los libros de IVA automáticamente (Priority: P1)

El usuario consulta los libros de registro de IVA de su empresa: emitidas, recibidas y, si aplica, intracomunitarias. Se construyen automáticamente desde las facturas y sus asientos, sin entrada manual.

**Why this priority**: Los libros de IVA son exigidos y deben proceder del registro contable, no de datos duplicados.

**Independent Test**: Efectuando facturas e IVA, los libros de IVA reflejan exactamente esas operaciones sin entradas manuales.

**Acceptance Scenarios**:

1. **Given** facturas emitidas y recibidas con IVA, **When** se consultan los libros, **Then** aparecen agrupadas por tipo con bases y cuotas exactas.
2. **Given** una empresa, **When** se consultan los libros, **Then** solo se ven sus propias operaciones.

---

### User Story 2 - Calcular el modelo 303 (IVA trimestral) (Priority: P2)

El usuario calcula el modelo 303 del período: IVA devengado (emitidas), deducible (recibidas) y resultado a ingresar/compensar, cuadrando con los libros.

**Why this priority**: La autoliquidación trimestral se apoya en los libros y debe cuadrar exactamente.

**Independent Test**: Calculando el 303 de un trimestre, el resultado coincide con la diferencia devengado - deducible de los libros del período.

**Acceptance Scenarios**:

1. **Given** un trimestre con IVA devengado y deducible, **When** se calcula el 303, **Then** el resultado (a ingresar/compensar) cuadra con las cuotas de los libros.
2. **Given** hechos imponibles intracomunitarios, **When** se calcula, **Then** se reflejan en el modelo (349 preparado).

---

### User Story 3 - Exportar modelos e informe de operaciones con terceros (Priority: P2)

El usuario exporta el modelo 303/349 y el resumen anual del 347 (operaciones con terceros) en formato legible para su presentación, con trazabilidad del período.

**Why this priority**: Reduce errores de transcripción y facilita la presentación.

**Independent Test**: Exportando los modelos de un período, el fichero incluye el período correcto y agrega las operaciones por tercero.

**Acceptance Scenarios**:

1. **Given** un período con operaciones, **When** se exporta el 303, **Then** el fichero contiene los totales del trimestre.
2. **Given** operaciones de un ejercicio, **When** se prepara el 347, **Then** se agregan por tercero y clave operacional.

---

### User Story 4 - Gestionar recargo de equivalencia e IVA de criterio de caja (Priority: P2)

El usuario liquida el IVA incorporando el recargo de equivalencia (cuotas separadas) y el régimen especial de criterio de caja (IVA devengado solo al cobro/pago). El sistema cuadra las cuotas en los libros y en el 303.

**Why this priority**: Son regímenes especiales que alteran el devengo y el cuadre del IVA.

**Independent Test**: Un período con operaciones de recargo y de caja cuadra sus cuotas en libros y 303 sin mezclar importes.

**Acceptance Scenarios**:

1. **Given** facturas con recargo de equivalencia, **When** se calcula el 303, **Then** las cuotas de recargo aparecen separadas de las del IVA general.
2. **Given** facturas bajo criterio de caja aún no cobradas/pagadas, **When** se calcula el 303, **Then** el IVA diferido no se incluye hasta el cobro/pago y queda trazado.

---

### Edge Cases

- ¿Qué ocurre si una factura no tiene asiento vinculado? → No entra en los libros hasta que su asiento exista.
- ¿Qué ocurre con IVA no deducible (ONG) vs deducible? → Depende de la configuración de cuenta; el 303 refleja la operación según configuración.
- ¿Qué ocurre si la fecha de una factura cae en un período ya exportado? → Se exporta el período y se permite regenerar con advertencia.
- ¿Qué ocurre con operaciones en otras divisas (SPEC-016 futuro)? → Los libros se expresan en moneda de la empresa según configuración.
- ¿Qué ocurre con el recargo de equivalencia? → Se registra como cuota separada del IVA general en los libros y en el 303, con su propia cuenta.
- ¿Qué ocurre con el IVA de criterio de caja aún no cobrado/pagado? → Permanece diferido y trazado hasta el cobro/pago, momento en que entra en la liquidación del período.
- ¿Qué ocurre con el SII si la empresa aún no está obligada? → El enlace SII se mantiene como opción habilitable por empresa.

## Requisitos (TODOs numerados)

1. **T-01** Libros de IVA emitidas/recibidas/intracomunitarias derivados de las facturas y asientos.
2. **T-02** Resumen periódico (trimestral/mensual) de cuotas por tipo.
3. **T-03** Cálculo del modelo 303 con cuadre con libros.
4. **T-04** Preparación del modelo 347 (operaciones con terceros por clave) y 349 (intracomunitarias).
5. **T-05** Exportación de modelos en fichero para presentación.
6. **T-06** Trazabilidad del período exportado y regeneración controlada.
7. **T-07** SII: definición de interfaz opcional habilitable por empresa.
8. **T-08** Recargo de equivalencia (cuotas separadas) e IVA de criterio de caja (diferido al cobro/pago) en libros y 303.
9. **T-09** Pruebas automáticas (pytest) de cuadre 303 y aislamiento multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST generar los libros de registro de IVA (emitidas, recibidas e intracomunitarias) automáticamente a partir de las facturas y los asientos, sin entrada manual.
- **FR-002**: El sistema MUST calcular el modelo 303 por período con resultado que cuadre con las cuotas de los libros de la empresa activa.
- **FR-003**: El sistema MUST preparar el resumen anual de operaciones con terceros (347) agregado por NIF y clave, y las operaciones intracomunitarias (349).
- **FR-004**: El sistema MUST exportar los modelos en formato legible para presentación con identificación del período y de la empresa.
- **FR-005**: El sistema MUST aislar los libros y modelos por empresa.
- **FR-006**: El sistema MUST registrar la exportación de un período con trazabilidad (cuándo y quién).
- **FR-007**: El sistema MUST soportar la habilitación opcional del SII por empresa (interfaz declarada, sin envío ejecutado en esta feature).
- **FR-008**: Los importes MUST tratarse en precisión decimal exacta y las cuotas de los modelos MUST cuadrar con las operaciones.
- **FR-009**: El sistema MUST tratar el recargo de equivalencia como cuota separada del IVA general, registrándola en libros y en el 303 con su cuenta diferenciada.
- **FR-010**: El sistema MUST aplicar el régimen especial de criterio de caja, difiriendo el IVA devengado/deducible hasta el cobro/pago y trazando los importes diferidos hasta su liquidación.
- **FR-011**: El sistema MUST preparar el enlace SII de forma opcional por empresa (interfaz declarada) e integrarse con la exportación (SPEC-029).
- **FR-012**: El flujo MUST cumplir la constitución (partida doble, precisión Decimal, multi-tenancy y pruebas obligatorias).

### Key Entities *(include if feature involves data)*

- **Libro de IVA**: Registro de operaciones por tipo (emitidas, recibidas, intracomunitarias) derivado del registro contable.
- **Modelo 303**: Autoliquidación trimestral/mensual del IVA.
- **Modelo 347/349**: Resumen anual de operaciones con terceros / intracomunitarias.
- **Recargo de equivalencia**: Cuota adicional al IVA para comerciantes minoristas, con cuenta y registro separados.
- **IVA de criterio de caja**: IVA devengado/deducible diferido hasta el cobro/pago efectivo.
- **Período fiscal**: Trimestre o mes y ejercicio al que se refiere cada modelo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los libros de IVA se generan desde las facturas/asientos sin entradas manuales.
- **SC-002**: El 100 % de los modelos 303 cuadran con los libros del período.
- **SC-003**: El 100 % de las exportaciones identifican período y empresa y quedan trazadas.
- **SC-004**: El 100 % de los libros y modelos están aislados por empresa.
- **SC-005**: Las cuotas se expresan con precisión de 4 decimales sin errores de redondeo.

## Assumptions

- La configuración de cuentas de IVA (472/477, no deducible ONG) define cómo se tratan los impuestos de cada empresa.
- Los modelos solo calculan y exportan; la presentación telemática es externa o se añade por SII en fase posterior.
- La facturación (SPEC-007) es la única fuente de hechos de IVA de venta; las compras se introducen por factura recibida.
- El recargo de equivalencia y el criterio de caja son regímenes optativos por empresa; el vínculo entre el IVA diferido y el cobro/pago se apoya en los vencimientos (SPEC-011).
- El SII queda declarado como interfaz opcional habilitable por empresa; su presentación ejecutada se integra con SPEC-029 (export integral).

## Dependencias

- SPEC-001 (cuentas de IVA), SPEC-007 (facturación operativa, recargo y criterio de caja), SPEC-008 (terceros/347), SPEC-011 (cobros/pagos para el IVA de caja), SPEC-029 (export integral/SII).