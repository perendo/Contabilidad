# Feature Specification: Impuesto sobre Sociedades (Modelo 200)

**Feature Branch**: `023-impuesto-sociedades`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Impuesto de Sociedades (modelo 200) y las cuentas 473/630"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Calcular la base y la cuota del IS (Priority: P1)

El usuario prepara el Impuesto sobre Sociedades del ejercicio. El sistema toma el resultado contable, permite aplicar ajustes extracontables y deducciones, calcula la base imponible y la cuota con el tipo configurado, considerando los pagos a cuenta (473) ya registrados.

**Why this priority**: Determinar la deuda fiscal anual del ejercicio es obligatorio para cualquier sociedad y afecta al cierre.

**Independent Test**: Calculando el IS con ajustes y pagos a cuenta se obtiene la cuota diferencial correcta.

**Acceptance Scenarios**:

1. **Given** el resultado contable del ejercicio y los ajustes extracontables, **When** se calcula, **Then** se obtiene la base y el impuesto a pagar o devolver.
2. **Given** pagos a cuenta registrados en 473, **When** se calcula la cuota diferencial, **Then** se descuentan y aparece el importe resultante.

---

### User Story 2 - Contabilizar el gasto por impuesto (Priority: P1)

El usuario contabiliza el impuesto del ejercicio. El sistema genera el asiento (630 contra 473 y 4752/4757 u 6301) de forma balanceada y atómica.

**Why this priority**: El gasto por impuesto forma parte de la cuenta de pérdidas y ganancias y del cierre.

**Independent Test**: Contabilizando el IS se genera el asiento 630/473/4752 balanceado.

**Acceptance Scenarios**:

1. **Given** la cuota calculada, **When** se contabiliza el IS, **Then** se genera el asiento con la cuenta 630 contra 473/4752.
2. **Given** un IS a devolver, **When** se contabiliza, **Then** se genera el saldo a favor con la cuenta correspondiente.

---

### User Story 3 - Obtener el modelo 200 y su presentación (Priority: P2)

El usuario genera el soporte del modelo 200 con los datos calculados para su presentación.

**Why this priority**: Presentación obligatoria anual ante la AEAT.

**Independent Test**: Generando el modelo 200 se obtienen todos los bloques con importes consistentes.

**Acceptance Scenarios**:

1. **Given** el IS calculado, **When** se exporta el modelo 200, **Then** se generan los datos en el formato establecido.
2. **Given** el modelo exportado, **When** se valida, **Then** no hay inconsistencias entre bloques.

---

### Edge Cases

- ¿Qué ocurre si hay cuota diferencial negativa (a devolver)? → Se registra como saldo a favor (4709/473) y queda en el modelo como a compensar/devolver.
- ¿Qué ocurre si el ejercicio aún no está cerrado? → El cálculo se permite como provisional para cierre intermedio (SPEC-028) pero no bloquea.
- ¿Qué ocurre si el tipo impositivo cambia a mitad de ejercicio? → Se usa el tipo vigente configurado por empresa el último día del ejercicio.
- ¿Qué ocurre si no hay pagos a cuenta? → La cuota diferencial coincide con la cuota íntegra menos deducciones, sin descuento de 473.

## Requisitos (TODOs numerados)

1. **T-01** Modelo del resultado contable del ejercicio desde el motor de asientos (SPEC-002/004).
2. **T-02** Ajustes extracontables (positivos/negativos) y deducciones/bonificaciones con trazabilidad.
3. **T-03** Cálculo de base imponible, cuota íntegra y cuota diferencial con tipo configurable por empresa.
4. **T-04** Integración de pagos a cuenta (473) y generación del asiento (630 contra 473/4752/4757).
5. **T-05** Export del modelo 200 en el formato establecido y validación de bloques.
6. **T-06** Cálculo provisional para cierres intermedios sin bloquear el ejercicio.
7. **T-07** Pruebas automáticas (pytest) del cálculo, asiento, modelo y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar el cálculo y la contabilización del IS por empresa y ejercicio y ejercer sobre la empresa activa.
- **FR-002**: El sistema MUST calcular la base imponible a partir del resultado contable aplicando los ajustes extracontables registrados.
- **FR-003**: El sistema MUST calcular la cuota aplicando el tipo impositivo configurado por empresa y las deducciones/bonificaciones registradas.
- **FR-004**: El sistema MUST descontar los pagos a cuenta (473) registrados y determinar cuota diferencial (a pagar o a devolver).
- **FR-005**: El sistema MUST generar el asiento del impuesto (630 contra 473/4752/4757) balanceado y atómico dentro del proceso de cierre.
- **FR-006**: El sistema MUST exportar el modelo 200 con los datos del cálculo y validar la consistencia entre bloques.
- **FR-007**: El sistema MUST permitir un cálculo provisional en cierres intermedios sin cerrar el ejercicio.
- **FR-008**: El flujo MUST cumplir la constitución (partida doble, precisión Decimal, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Resultado contable**: Suma de ingresos y gastos del ejercicio según el motor de asientos.
- **Ajuste extracontable**: Importe que corrige el resultado contable para obtener la base fiscal.
- **Base imponible / Cuota**: Resultado del cálculo fiscal con tipo y deducciones.
- **Pago a cuenta (473)**: Retención o pagos fraccionados ya contabilizados.
- **Modelo 200**: Soporte oficial con el detalle del cálculo para su presentación.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los cálculos producen base y cuota reproducibles a partir de los datos del ejercicio.
- **SC-002**: El 100 % de las contabilizaciones del IS generan un asiento balanceado y atómico.
- **SC-003**: El 100 % de los exportes del modelo 200 pasan la validación de consistencia entre bloques.
- **SC-004**: El 100 % de los cierres intermedios permiten un cálculo provisional sin bloquear el ejercicio.
- **SC-005**: Los importes se tratan con precisión de 4 decimales sin errores de redondeo.

## Assumptions

- El tipo impositivo (por defecto 25 % general para sociedades) es configurable por empresa y vigencia.
- Los ajustes extracontables y deducciones se introducen manualmente con su descripción y referencia normativa.
- El asiento de cierre usa las cuentas 630 (impuesto sobre beneficios) contra 473/4752 (Hacienda deudora/acreedora por IS) y 6301 si hay diferencia de activo/pasivo diferido.
- El modelo 200 se genera como informe/soporte estándar descargable; la presentación telemática queda fuera de alcance (integración AEAT no incluida).

## Dependencias

- SPEC-002 (motor de asientos), SPEC-004 (informes y cierre), SPEC-010 (cuentas anuales), SPEC-028 (cierre intermedio), SPEC-024 (retenciones del periodo para saldos a favor).