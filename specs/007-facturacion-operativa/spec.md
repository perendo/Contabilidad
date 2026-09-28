# Feature Specification: Facturación Operativa

**Feature Branch**: `007-facturacion-operativa`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Facturación operativa (emitir/rectificar facturas, IVA/IRPF, numeración correlativa y vínculo automático al asiento), con retenciones IRPF integradas"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Emitir una factura con su asiento automático (Priority: P1)

El usuario emite una factura de venta con sus líneas, IVA e IRPF (si aplica). El sistema le asigna el número correlativo de la serie y, al confirmar, genera automáticamente el asiento contable balanceado que la soporta.

**Why this priority**: La facturación es el origen principal de la contabilidad; sin vínculo automático al asiento no hay consistencia.

**Independent Test**: Emitiendo una factura se genera el número correlativo y un asiento balanceado enlazado; no se puede emitir sin vínculo al ejercicio correcto.

**Acceptance Scenarios**:

1. **Given** una empresa activa con configuración de IVA/IRPF, **When** el usuario emite una factura con líneas e impuestos, **Then** se asigna el número correlativo y el asiento contable se genera balanceado (Sum Debe == Sum Haber).
2. **Given** una factura emitida, **When** se consulta, **Then** aparece su asiento vinculado y su numeración es correlativa por empresa y ejercicio.

---

### User Story 2 - Rectificar una factura (abono) (Priority: P2)

El usuario emite una factura rectificativa (abono). El sistema genera el asiento de anulación/rectificación invertido sobre la factura original, respetando la inmutabilidad del asiento ya asentado.

**Why this priority**: Las correcciones de facturas son normales y deben respetar la inmutabilidad del diario (constitución II).

**Independent Test**: Rectificando una factura se genera la factura abono con su número correlativo y el asiento invertido, sin alterar el original.

**Acceptance Scenarios**:

1. **Given** una factura emitida, **When** el usuario la rectifica, **Then** se crea la factura rectificativa con sus importes invertidos y su asiento de anulación enlazado.
2. **Given** el asiento original de la factura, **When** se rectifica, **Then** el asiento original permanece intacto (no se modifica ni elimina).

---

### User Story 3 - Gestionar serie, numeración y estados (Priority: P2)

El usuario configura series de facturación por empresa y conoce el estado de cada factura (borrador, emitida, anulada). La numeración es correlativa y sin saltos dentro de cada serie y ejercicio.

**Why this priority**: La correlatividad y trazabilidad del documento fiscal son obligatorias (constitución IV).

**Independent Test**: Emitiendo y anulando facturas en una serie, la numeración avanza correlativamente y los estados quedan registrados.

**Acceptance Scenarios**:

1. **Given** una serie configurada, **When** se emiten varias facturas, **Then** reciben números consecutivos sin duplicados ni saltos.
2. **Given** una factura anulada, **When** se consulta la serie, **Then** el número queda reservado (no se reutiliza) y el estado es anulado.

---

### Edge Cases

- ¿Qué ocurre si la fecha de la factura cae en un ejercicio cerrado? → Se rechaza la emisión (400).
- ¿Qué ocurre si los importes de IVA/IRPF no cuadran con la base? → El sistema recalcula y rechaza si hay discrepancias de precisión.
- ¿Qué ocurre con una factura rectificativa sobre una factura ya rectificada? → Se admite enlazando a la original, sin reutilizar números.
- ¿Qué ocurre si se elimina una factura en borrador? → Se permite su anulación; una vez emitida no se borra (inmutabilidad).
- ¿Qué ocurre con IVA no deducible o exento? → Se configura por empresa/cuenta.
- ¿Qué ocurre con el recargo de equivalencia? → Se calcula y factura como impuesto adicional, con su cuota separada (cuenta 477 recargo / 472), manteniendo la precisión decimal.
- ¿Qué ocurre con el criterio de caja? → La factura se emite con IVA íntegro; el régimen de caja difiere su devengo, dejando el IVA en la cuenta 477/472 con su saldo pendiente de liquidación hasta el cobro/pago (SPEC-012).

## Requisitos (TODOs numerados)

1. **T-01** Alta de facturas con líneas, IVA, IRPF y series configuradas por empresa.
2. **T-02** Numeración correlativa por serie y ejercicio (reserva de números anulados).
3. **T-03** Generación automática del asiento vinculado (motor SPEC-002) balanceado.
4. **T-04** Factura rectificativa/abono con asiento de anulación enlazado.
5. **T-05** Estados de factura (borrador, emitida, anulada) y bloqueo de ejercicios cerrados.
6. **T-06** Integración con maestro de terceros (SPEC-008) para cliente/proveedor.
7. **T-07** Recargo de equivalencia y régimen de criterio de caja en la emisión de facturas (cuentas separadas y criterio diferido).
8. **T-08** Pruebas automáticas (pytest) de cuadre del asiento, correlatividad y aislamiento multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar las facturas por empresa: toda emisión, consulta o rectificación opera sobre la empresa activa.
- **FR-002**: El sistema MUST emitir facturas con líneas, base imponible, IVA e IRPF, con precisiones monetarias exactas (Decimal/NUMERIC 18,4).
- **FR-003**: El sistema MUST asignar la numeración correlativa por serie, empresa y ejercicio, sin reutilizar números anulados y sin saltos.
- **FR-004**: Al confirmar una factura, el sistema MUST generar el asiento contable vinculado de forma balanceada y atómica (cabecera+apuntes).
- **FR-005**: El sistema MUST rectificar facturas mediante factura rectificativa con asiento de anulación, sin modificar ni eliminar el asiento original.
- **FR-006**: El sistema MUST rechazar la emisión cuyo fecha corresponda a un ejercicio cerrado (refuerzo de SPEC-004).
- **FR-007**: El sistema MUST sostener los estados de factura (borrador/emitida/anulada) y prohibir el borrado de facturas emitidas.
- **FR-008**: Los importes de facturas y asientos MUST tratarse en precisión decimal exacta en todo el flujo.
- **FR-009**: El flujo completo MUST cumplir las reglas inmutables de la constitución (partida doble, inmutabilidad, correlatividad, multi-tenancy, pruebas).
- **FR-010**: El sistema MUST calcular y facturar el recargo de equivalencia cuando se aplique, con su cuota separada y su cuenta contable, manteniendo la precisión decimal exacta.
- **FR-011**: El sistema MUST soportar la emisión de facturas bajo el régimen de criterio de caja, registrando el IVA devengado e identificando su diferimiento para que SPEC-012 gestione la liquidación al cobro/pago.

### Key Entities *(include if feature involves data)*

- **Factura**: Documento emitido o rectificativo con líneas, base, IVA, IRPF, número correlativo, fecha y su asiento vinculado.
- **Serie de facturación**: Agrupación por empresa que gobierna la numeración correlativa.
- **Asiento vinculado**: Asiento del motor SPEC-002 generado a partir de la factura.
- **Tercero**: Cliente/proveedor del maestro (SPEC-008) asociado a la factura.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las facturas emitidas generan un asiento balanceado vinculado y su número correlativo correcto.
- **SC-002**: El 100 % de las rectificativas generan el asiento de anulación sin alterar el original.
- **SC-003**: El 100 % de los intentos de emisión en ejercicio cerrado son rechazados.
- **SC-004**: El 100 % de los importes de factura y asiento coinciden sin errores de redondeo (precisión 4 decimales).
- **SC-005**: El 100 % de las facturas de una empresa quedan aisladas de las demás (verificado por pruebas automáticas).

## Assumptions

- La configuración de IVA/IRPF (tipos, cuentas 477/472/475/473) se define por empresa/cuenta en una etapa de configuración previa; esta feature la consume.
- El módulo se habilita por empresa (opt-in): una ONG puede operar sin facturación operativa.
- Las rectificativas usan numeración propia correlativa enlazada a la factura original.
- El enlace factura-asiento usa el patrón integrado (misma transacción) definido en la revisión de integración.
- El recargo de equivalencia se calcula sobre la base según los tipos configurados por empresa; su cuota se contabiliza en cuenta separada del IVA (477/472 recargo).
- El criterio de caja es un régimen de IVA optativo por empresa; la factura se emite con IVA íntegro y SPEC-012 aplica el diferimiento de la liquidación.

## Dependencias

- SPEC-002 (motor de asientos), SPEC-004 (rechazo en ejercicios cerrados), SPEC-008 (maestro de terceros), SPEC-012 (libros de IVA).