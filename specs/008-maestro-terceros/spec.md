# Feature Specification: Maestro de Terceros (Clientes y Proveedores)

**Feature Branch**: `008-maestro-terceros`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Maestro de terceros (clientes/proveedores, NIF/CIF, direcciones), base de las subcuentas 430/410"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Alta y gestión de terceros (Priority: P1)

El usuario da de alta clientes y proveedores con identificación fiscal, razón social, direcciones, teléfono y correo. Cada tercero se asocia automáticamente a sus subcuentas contables de cobro y pago.

**Why this priority**: Las subcuentas 430/410 y la facturación dependen del maestro; sin terceros no hay gestión comercial.

**Independent Test**: Alta de un tercero crea su ficha y sus subcuentas asociadas por empresa; el NIF se valida contra duplicados.

**Acceptance Scenarios**:

1. **Given** una empresa activa, **When** se da de alta un tercero (cliente o proveedor) con NIF y datos, **Then** su ficha se guarda y se asignan sus subcuentas contables por empresa.
2. **Given** un intento de alta con un NIF ya existente en la misma empresa, **When** se envía, **Then** se rechaza o se devuelve el tercero existente (sin duplicados).

---

### User Story 2 - Consultar el histórico y saldo de un tercero (Priority: P2)

El usuario consulta la ficha de un tercero con su histórico de facturas, cobros/pagos y saldo pendiente. La información es exclusiva de la empresa activa.

**Why this priority**: La trazabilidad del saldo por tercero sustenta vencimientos y conciliaciones.

**Independent Test**: Consultando un tercero se obtienen sus movimientos y saldo de la empresa activa, nunca los de otra empresa.

**Acceptance Scenarios**:

1. **Given** un tercero con movimientos, **When** se consulta su ficha, **Then** se muestra su histórico y saldo pendiente de la empresa activa.
2. **Given** un tercero existente en otra empresa, **When** se intenta consultar, **Then** el sistema lo niega (aislamiento).

---

### User Story 3 - Baja y retirada de terceros (Priority: P2)

El usuario retira un tercero sin movimientos; si el tercero tiene asientos, facturas o vencimientos, la retirada se bloquea y solo se permite su inactivación.

**Why this priority**: Evitar que datos con implicación contable se pierdan o alteren.

**Independent Test**: Retirando un tercero sin movimientos, se inactiva; con movimientos, se bloquea la baja definitiva.

**Acceptance Scenarios**:

1. **Given** un tercero sin movimientos, **When** se retira, **Then** se inactiva sin borrar su histórico.
2. **Given** un tercero con asientos o facturas, **When** se intenta dar de baja, **Then** el sistema bloquea la baja y sugiere inactivar.

---

### Edge Cases

- ¿Qué ocurre con un NIF mal formado? → Se valida el formato antes de guardar.
- ¿Qué ocurre si un tercero es a la vez cliente y proveedor? → Se admite una ficha única con ambos roles.
- ¿Qué ocurre si dos empresas comparten tercero? → Cada empresa mantiene su propia ficha aislada (el maestro es por empresa).
- ¿Qué ocurre si se cambia el NIF de un tercero con movimientos? → Se permite solo con trazabilidad del cambio (auditoría).
- ¿Qué ocurre si el NIF coincide con la empresa (autofactura)? → Se asocia como tercero propio con validación específica (supuesto de diseño).
- ¿Qué ocurre si un tercero no tiene IBAN? → Puede operar en facturación/cobros manuales, pero se excluye de las remesas SEPA (SPEC-020).

## Requisitos (TODOs numerados)

1. **T-01** Entomodelo de terceros (clientes/proveedores) con datos fiscales y de contacto.
2. **T-02** Validación de NIF/CIF y unicidad por empresa.
3. **T-03** Asignación automática de subcuentas contables (430/410 y correlativas).
4. **T-04** Ficha de tercero con histórico de movimientos y saldo pendiente.
5. **T-05** Retirada/inactivación con protección de terceros con movimientos.
6. **T-06** Auditoría de cambios del maestro.
7. **T-07** Pruebas automáticas (pytest) de unicidad, protección de baja y aislamiento multi-tenant.
8. **T-08** Datos bancarios del tercero (IBAN/banco, validación de formato) y condiciones de pronto pago (plazo y %) por tercero.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar el maestro de terceros por empresa: consultas y altas operan sobre la empresa activa.
- **FR-002**: El sistema MUST registrar terceros con roles de cliente y/o proveedor, NIF/CIF, razón social, direcciones y contactos.
- **FR-003**: El sistema MUST validar el formato del NIF/CIF y la unicidad dentro de la misma empresa (sin duplicados).
- **FR-004**: El sistema MUST asignar automáticamente las subcuentas contables de cobro/pago del tercero dentro del plan de cuentas de la empresa.
- **FR-005**: El sistema MUST exponer la ficha del tercero con histórico de facturas, cobros/pagos y saldo pendiente de la empresa activa.
- **FR-006**: El sistema MUST impedir la baja definitiva de terceros con movimientos (asientos, facturas o vencimientos), permitiendo solo inactivar.
- **FR-007**: El sistema MUST registrar en auditoría los cambios del maestro (usuario, fecha, acción).
- **FR-008**: El flujo completo MUST cumplir las reglas inmutables de la constitución (multi-tenancy y pruebas obligatorias).
- **FR-009**: El sistema MUST registrar los datos bancarios (IBAN/banco) y las condiciones de pronto pago (plazo y %) del tercero, validando el IBAN y quedando este obligatorio para la inclusión en remesas (SPEC-020).

### Key Entities *(include if feature involves data)*

- **Tercero**: Cliente y/o proveedor con datos fiscales, de contacto y bancarios (IBAN/banco), única ficha por empresa.
- **Condición de pago**: Plazo y porcentaje de pronto pago configurados por tercero.
- **Subcuenta de cobro/pago**: Cuentas del plan (SPEC-001) asignadas por empresa al tercero.
- **Movimiento de tercero**: Facturas, asientos y vencimientos que componen su histórico y saldo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las altas de terceros crean sus subcuentas asociadas y no se producen NIF duplicados por empresa.
- **SC-002**: El 100 % de las bajas de terceros con movimientos quedan bloqueadas.
- **SC-003**: El 100 % de las consultas de terceros no filtran datos de otra empresa.
- **SC-004**: El 100 % de los cambios del maestro quedan auditados.

## Assumptions

- El maestro es por empresa (no global); cada empresa mantiene sus propios terceros.
- La asignación de subcuentas sigue una convención configurable (p. ej., subcuenta por NIF bajo la cuenta 430/431).
- El cambio de NIF con movimientos requiere permiso de administrador y queda auditado.
- La baja definitiva (borrado físico) requiere vaciar histórico; por defecto solo se inactiva.

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (asientos), SPEC-007 (facturación), SPEC-011 (vencimientos/cobros-pagos) y SPEC-020 (remesas SEPA que consumen IBAN y condiciones de pronto pago).