# Feature Specification: Remesas SEPA y Soporte Magnético

**Feature Branch**: `020-remesas-sepa-cobros`

**Created**: 2026-09-16

**Status**: Implemented - final verification pending

**Input**: User description: "Remesa de recibos SEPA / soporte magnético: generar fichero de domiciliaciones (norma CSB 19.19 y XML SEPA DD) con recibos al vencimiento por fecha, cliente y banco; descuento comercial (por pronto pago); devoluciones de recibos con reclamaciones"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Emitir una remesa de recibos en soporte magnético (Priority: P1)

El usuario selecciona recibos pendientes, vencidos o futuros dentro del rango permitido (por fecha, cliente o banco), los agrupa en una remesa y genera el fichero de domiciliación (CSB 19.19 o XML SEPA DD). Una remesa puede contener varias fechas de cargo; el fichero agrupa las operaciones por fecha. El sistema marca los recibos como remesados sin contabilizarlos aún.

**Why this priority**: La generación del cobro por domiciliación es el flujo principal de tesorería.

**Independent Test**: Creando una remesa se genera el fichero con los datos bancarios correctos y los recibos pasan a estado remesado.

**Acceptance Scenarios**:

1. **Given** recibos pendientes vencidos o futuros elegibles, **When** el usuario crea la remesa con criterios (fecha/cliente/banco), **Then** se genera el fichero agrupado por fecha de cargo y los recibos quedan remesados.
2. **Given** un recibo ya cobrado, **When** se intenta incluir en una remesa, **Then** el sistema lo excluye y lo notifica.

---

### User Story 2 - Liquidar recibos con descuento comercial por pronto pago (Priority: P2)

El usuario liquida un recibo aplicando un descuento por pronto pago condicionado a fecha de pago. El sistema calcula el importe descontado y genera el asiento (432/662 contra 430) sin exceder el vencimiento.

**Why this priority**: Impacta el importe efectivo a cobrar y el cuadre contable.

**Independent Test**: Liquidando con descuento por pronto pago se genera un asiento balanceado con la cuenta de descuento y el recibo se salda por el importe neto.

**Acceptance Scenarios**:

1. **Given** un recibo con descuento por pronto pago configurado, **When** el pago se abona dentro del plazo, **Then** se aplica el descuento y el importe cobrado es el neto.
2. **Given** un pago fuera del plazo de descuento, **When** se liquida, **Then** no se aplica el descuento y se cobra el importe íntegro.

---

### User Story 3 - Gestionar devoluciones de recibos (Priority: P2)

El usuario procesa un rechazo o baja bancaria (norma AEB R19/C19). El sistema reabre el recibo/vencimiento, lo marca como devuelto y permite iniciar una reclamación.

**Why this priority**: La devolución afecta saldos y tesorería y debe dejar trazabilidad.

**Independent Test**: Procesando una devolución el vencimiento vuelve a estado pendiente y queda registrada como devuelto con su reclamación.

**Acceptance Scenarios**:

1. **Given** un recibo remesado y cobrado en banco, **When** llega un R19/C19, **Then** el vencimiento se reabre como pendiente y se registra la devolución con su código bancario y asiento REVERSAL.
2. **Given** una devolución registrada, **When** se crea la reclamación, **Then** queda trazada la fecha y estado de la reclamación.

---

### Edge Cases

- ¿Qué ocurre si un recibo sin IBAN se incluye en la remesa? → Se excluye y se informa al usuario (el tercero debe tener IBAN válido).
- ¿Qué ocurre si el descuento supera el importe del recibo? → Se rechaza; el neto no puede ser negativo.
- ¿Qué ocurre con recibos de un ejercicio cerrado? → Se rechaza su gestión/remesa (SPEC-002/004).
- ¿Qué ocurre si se genera dos veces la misma remesa? → Cada remesa tiene número correlativo único y estado; no se permiten duplicados pendientes de cobro.
- ¿Qué ocurre si la fecha de cargo no cumple el plazo de presentación SEPA? → La remesa se bloquea y se informa de la fecha mínima de presentación según el tipo de adeudo.

## Requisitos (TODOs numerados)

1. **T-01** Selección de recibos por fecha/cliente/banco y agrupación en remesa con número correlativo.
2. **T-02** Generación del soporte de domiciliación en formato CSB 19.19 y XML SEPA DD (CORE predeterminado, B2B opcional) con los datos bancarios de los terceros.
3. **T-03** Estados de recibo/remesa (pendiente, remesado, cobrado, devuelto) y exclusión de cobrados.
4. **T-04** Descuento comercial por pronto pago: configuración, cálculo condicionado a fecha y asiento (432/662 contra 430).
5. **T-05** Procesado de devoluciones (R19/C19): asiento de reversión del cobro (REVERSAL) con gastos opcionales, reapertura de vencimiento, registro de devolución y reclamación.
6. **T-06** Bloqueo de remesas/devoluciones en ejercicios cerrados.
7. **T-07** Pruebas automáticas (pytest) de ficheros, descuentos, devoluciones y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar remesas, recibos y devoluciones por empresa y ejercer sobre la empresa activa.
- **FR-002**: El sistema MUST permitir seleccionar recibos pendientes por rango de fecha, cliente o banco y agruparlos en una remesa con número correlativo único.
- **FR-003**: El sistema MUST generar el fichero de domiciliación en ambos formatos estándar (XML SEPA DD CORE como predeterminado y CSB 19.19), admitiendo adeudos B2B de forma opcional, con los datos bancarios de los terceros, excluyendo recibos ya cobrados o sin IBAN válido.
- **FR-004**: El sistema MUST usar la fecha de vencimiento de cada recibo como fecha de cargo, permitir varias fechas en una remesa y agruparlas en el fichero por `ReqdColltnDt`; debe validar los plazos SEPA diferenciando primera/recurrente CORE y B2B.
- **FR-005**: El sistema MUST aplicar el descuento por pronto pago configurado por condiciones del tercero (plazo y % en SPEC-008) o su override por factura, solo cuando el pago ocurre dentro del plazo, calculando el neto con precisión de 4 decimales y generando el asiento (432/662 contra 430) de forma balanceada y atómica.
- **FR-006**: El sistema MUST gestionar devoluciones R19/C19 generando un asiento de reversión del cobro (REVERSAL, con gastos de devolución opcionales) que reabre el vencimiento a pendiente sin modificar el asiento original, registrando la devolución y permitiendo una reclamación trazable.
- **FR-007**: El sistema MUST confirmar el cobro de un recibo remesado mediante marcado manual o mediante un movimiento conciliado por SPEC-013. Ambos caminos deben ser idempotentes, no duplicar el asiento y rechazar conflictos de estado.
- **FR-008**: El sistema MUST rechazar remesas o devoluciones que afecten a un ejercicio cerrado (SPEC-002/004).
- **FR-009**: El flujo MUST cumplir la constitución (partida doble, precisión Decimal, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Remesa**: Agrupación de recibos con número correlativo, fecha de emisión, formato y estado.
- **Recibo**: Vencimiento agrupado para domiciliación, con datos bancarios y estado.
- **Fichero de domiciliación**: Soporte CSB 19.19 / SEPA DD (CORE por defecto, B2B opcional) generado para enviar al banco.
- **Devolución (R19/C19)**: Rechazo o baja bancaria que revierte el cobro (asiento REVERSAL) y reabre el recibo.
- **Reclamación**: Seguimiento posterior a la devolución con fecha y estado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las remesas generan un fichero válido en el formato solicitado (CSB 19.19 o SEPA DD).
- **SC-002**: El 100 % de los recibos remesados pasan a estado remesado sin duplicados pendientes.
- **SC-003**: El 100 % de los descuentos por pronto pago aplicados generan asiento balanceado y neto no negativo.
- **SC-004**: El 100 % de las devoluciones reabren el vencimiento y quedan trazadas con su reclamación.
- **SC-005**: Los importes se tratan con precisión de 4 decimales sin errores de redondeo.
- **SC-006**: El 100 % de los cobros de recibos remesados se confirman por marcado manual o conciliación bancaria (SPEC-013), sin duplicar el asiento aunque ambos eventos lleguen para el mismo recibo.
- **SC-007**: El 100 % de las remesas generadas pasan la validación de plazos de presentación SEPA según fecha de cargo y tipo de adeudo.

## Assumptions

- Los recibos se generan desde los vencimientos de facturación (SPEC-007/SPEC-011); esta feature los agrupa y domicilia, admitiendo vencimientos pasados o futuros mientras sigan pendientes y el ejercicio esté abierto.
- El IBAN es obligatorio en terceros para poder incluirse en remesas (SPEC-008).
- El descuento por pronto pago usa las cuentas 432 (clientes, descuentos sobre ventas por pronto pago) y 662 (descuentos sobre ventas por pronto pago) contra 430; se configura por condiciones del tercero (SPEC-008) con opción de override por factura y aplica según la fecha de pago.
- El soporte bancario se genera en formato estándar como salida descargable; el envío al banco queda fuera de alcance hasta la integración bancaria (SPEC-013).
- El cobro de los recibos se confirma manualmente y/o por un evento de conciliación bancaria de SPEC-013; no se integra la descarga automática de confirmaciones bancarias en esta feature.

## Clarifications

### Session 2026-09-16

- Q: ¿Qué formato(s) debe generar la remesa de recibos y cuál debe ser el predeterminado? → A: Ambos (SEPA DD CORE + CSB 19.19), predeterminado SEPA DD CORE; B2B opcional si el tercero lo requiere.
- Q: ¿Cómo se confirma que un recibo remesado ha sido efectivamente cobrado? → A: Marcado manual y/o evento de conciliación bancaria de SPEC-013; ambos caminos son idempotentes y no duplican el asiento, sin descarga automática desde el banco en esta feature.
- Q: Al procesar una devolución R19/C19 de un recibo ya cobrado, ¿se registra contablemente la reversión o solo se reabre el vencimiento? → A: Asiento automático de devolución (REVERSAL del cobro) que reabre el vencimiento, con gastos opcionales, respetando la inmutabilidad del asiento original.
- Q: ¿Dónde se configura el descuento por pronto pago? → A: Por condiciones del tercero (plazo y % en SPEC-008), con opción de override por factura.
- Q: ¿Qué regla aplica a la fecha de cargo de los adeudos SEPA? → A: Fecha de cargo = fecha de vencimiento del recibo, validando los plazos de presentación según tipo de adeudo (CORE: D-2 hábiles, primera domiciliación; B2B: D-1 con mandato previo).

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-007 (facturación), SPEC-008 (terceros/IBAN), SPEC-011 (vencimientos y cobros), SPEC-013 (conciliación bancaria), SPEC-021 (medios de pago para el abono en cuentas 572/570).