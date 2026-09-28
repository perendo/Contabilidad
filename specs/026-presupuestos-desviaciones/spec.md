# Feature Specification: Presupuestos y Desviaciones

**Feature Branch**: `026-presupuestos-desviaciones`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Presupuesto anual y desviaciones por cuenta/centro de coste (complementa SPEC-017)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Definir el presupuesto anual por cuenta y centro (Priority: P1)

El usuario define el presupuesto anual desglosado por cuenta y centro de coste (si se usa SPEC-017). El sistema almacena los importes por cada combinación cuenta-centro y ejercicio.

**Why this priority**: El control presupuestario es básico para la gestión de la ONG (proveedores, proyectos, donaciones).

**Independent Test**: Registrando un presupuesto anual por cuenta y centro, el sistema lo almacena y lo consulta por ejercicio.

**Acceptance Scenarios**:

1. **Given** ejercicios y centros de coste definidos, **When** el usuario establece el presupuesto, **Then** el importe queda registrado por cuenta, centro y ejercicio.
2. **Given** un presupuesto duplicado para la misma combinación, **When** se intenta guardar, **Then** el sistema rechaza el duplicado.

---

### User Story 2 - Seguimiento y comparación presupuesto vs real (Priority: P2)

El usuario compara el gasto/ingreso real del ejercicio con el presupuestado, por cuenta y centro. El sistema calcula la desviación (absoluta y relativa) y la muestra en un informe.

**Why this priority**: Permite controlar el gasto real y tomar decisiones sobre desviaciones.

**Independent Test**: Consultando la desviación por cuenta/centro, los valores cuadran con el real menos el presupuesto.

**Acceptance Scenarios**:

1. **Given** presupuesto y asientos reales, **When** se solicita la desviación, **Then** se muestra la diferencia absoluta y relativa por cuenta/centro.
2. **Given** cuentas sin presupuesto, **When** se calcula, **Then** aparecen con desviación igual al gasto real.

---

### User Story 3 - Informes y cierres de seguimiento (Priority: P2)

El usuario genera informes de desviación acumulada por centro y cuenta, y cierra el seguimiento de un periodo.

**Why this priority**: Información gerencial y cierre de control.

**Independent Test**: Generando un informe de desviación, se listan todas las cuentas/centros con sus valores.

**Acceptance Scenarios**:

1. **Given** el seguimiento del periodo, **When** se genera el informe, **Then** las desviaciones se listan por centro y cuenta.
2. **Given** un periodo cerrado, **When** se genera la consolidación, **Then** la desviación final queda registrada como trazable.

---

### Edge Cases

- ¿Qué ocurre si se modifica el presupuesto después del cierre? → Se rechaza si el periodo de seguimiento está cerrado; se permite solo si está abierto con trazabilidad de cambios.
- ¿Qué ocurre si una cuenta no tiene centro de coste? → El seguimiento se hace solo por cuenta (centro vacío).
- ¿Qué ocurre si se genera el informe sin datos reales? → Se muestra todo con real cero y desviación = -presupuesto.
- ¿Qué ocurre con saldos parciales de medio ejercicio? → Se permiten balances acumulados parciales.

## Requisitos (TODOs numerados)

1. **T-01** Modelo de presupuesto por cuenta/centro/ejercicio con importes y vigencia.
2. **T-02** Cálculo de desviación (absoluta y relativa) cuenta-centro comparando presupuesto vs real (motor de asientos SPEC-002).
3. **T-03** Informes de desviación por centro, cuenta y ejercicio.
4. **T-04** Cierre de seguimiento del periodo con trazabilidad.
5. **T-05** Rechazo de modificación en presupuestos ya cerrados.
6. **T-06** Multi-tenancy y aislamiento por empresa.
7. **T-07** Pruebas automáticas (pytest) de cálculo, informes y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST permitir definir el presupuesto por cuenta, centro de coste (si activo) y ejercicio con importes, ejerciendo sobre la empresa activa.
- **FR-002**: El sistema MUST calcular la desviación absoluta y relativa entre el presupuesto y el gasto/ingreso real del motor de asientos (SPEC-002/007).
- **FR-003**: El sistema MUST generar informes de desviación por centro y cuenta con la acumulación del periodo.
- **FR-004**: El sistema MUST cerrar el seguimiento de un periodo, bloqueando la modificación de presupuestos cerrados.
- **FR-005**: El sistema MUST rechazar duplicidades en la combinación cuenta-centro-ejercicio.
- **FR-006**: El sistema MUST permitir cuentas sin centro de coste, calculando la desviación solo por cuenta.
- **FR-007**: El flujo MUST cumplir la constitución (precisión Decimal, inmutabilidad, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Presupuesto**: Importe anual previsto para una combinación cuenta-centro-ejercicio.
- **Desviación**: Diferencia absoluta y relativa entre presupuestado y real.
- **Centro de coste** (opcional): Dimensión analítica (SPEC-017).
- **Periodo de seguimiento**: Rango de fechas para el cotejo y cierre del seguimiento.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las combinaciones cuenta-centro-ejercicio tienen su presupuesto registrado sin duplicados.
- **SC-002**: El 100 % de las desviaciones calculadas cuadran con la resta (real - presupuesto).
- **SC-003**: El 100 % de los periodos cerrados bloquean la modificación de presupuestos.
- **SC-004**: El 100 % de las cuentas sin centro muestran la desviación por cuenta.
- **SC-005**: Los importes se tratan con precisión de 4 decimales.

## Assumptions

- El presupuesto es un dato por empresa y ejercicio, no por asiento; su consolidación se calcula comparando los saldos del motor de asientos (SPEC-002) o los informes (SPEC-004).
- Los centros de coste se usan solo si están activos (SPEC-017); si no, se calcula por cuenta.
- El informe puede ser parcial (a mes cerrado) o acumulado anual.
- La desviación se muestra como valor informativo; no bloquea la contabilización.

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-010 (informes), SPEC-017 (centros de coste).