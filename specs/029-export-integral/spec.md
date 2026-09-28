# Feature Specification: Export Integral del Tenant (Backup y Portabilidad)

**Feature Branch**: `029-export-integral`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Export integral del tenant (backup/portabilidad) y enlace SII (ya declarado opcional en SPEC-012)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Exportar el tenant completo (Priority: P1)

El usuario genera un archivo descargable con todos los datos de contabilidad de su empresa (plan de cuentas, asientos, terceros, cierres, informes, catálogos, etc.) de forma consistente y verificable.

**Why this priority**: Portabilidad de datos y backup de seguridad cumpliendo con el derecho de portabilidad.

**Independent Test**: Exportando un tenant, el archivo contiene todos los bloques de datos de la empresa activa y su huella (hash) permite verificar la integridad.

**Acceptance Scenarios**:

1. **Given** una empresa activa, **When** solicita la exportación, **Then** se genera el archivo con su inventario de contenido y huella verificable.
2. **Given** el archivo exportado, **When** se valida, **Then** la huella coincide y el inventario refleja todos los bloques.

---

### User Story 2 - Verificar la integridad de la exportación (Priority: P2)

El usuario verifica que la exportación no ha sido alterada y está completa, consultando el manifiesto y la huella del archivo.

**Why this priority**: Garantiza que la copia es fiable.

**Independent Test**: Verificando la exportación, la huella del archivo coincide con la del manifiesto.

**Acceptance Scenarios**:

1. **Given** un archivo de exportación, **When** se verifica la huella, **Then** el manifiesto confirma la integridad.
2. **Given** un archivo manipulado, **When** se verifica, **Then** se detecta la inconsistencia.

---

### User Story 3 - Enlazar con el SII de la AEAT (Priority: P2, opcional)

El usuario puede subir la exportación al SII de la AEAT si tiene autorización, o bien usar el archivo como fuente para preparar el enlace. Esta funcionalidad queda declarada pero su integración telemática es opcional.

**Why this priority**: Cumplimiento de la obligación SII para contribuyentes que la tengan.

**Independent Test**: El archivo exportado contiene los datos necesarios para el SII y puede subirse manualmente.

**Acceptance Scenarios**:

1. **Given** una empresa con obligación SII, **When** genera la exportación, **Then** incluye los datos necesarios para el SII.
2. **Given** la exportación, **When** el usuario la sube al portal SII, **Then** puede completar el proceso.

---

### Edge Cases

- ¿Qué ocurre si la empresa tiene datos de varios ejercicios? → Se exporta todo el tenant completo; el usuario puede filtrar por rango si lo desea.
- ¿Qué ocurre si el tenant tiene datos incompletos? → La exportación se realiza igualmente; el manifiesto refleja lo que contiene.
- ¿Qué ocurre si se intenta importar una exportación de otra empresa? → Se rechaza la importación si el tenant_id no coincide (multi-tenancy).
- ¿Qué ocurre si la exportación pesa mucho? → Se genera en lotes o como archivo comprimido; el usuario es informado del progreso.

## Requisitos (TODOs numerados)

1. **T-01** Generación de la exportación completa del tenant con inventario de bloques de datos.
2. **T-02** Huella verificable (hash) y manifiesto del archivo para garantizar integridad.
3. **T-03** Multi-tenancy: exportación solo de la empresa activa, sin datos de otras.
4. **T-04** Datos incluidos: plan de cuentas (versiones), asientos, terceros, vencimientos, cobros/pagos, cierres, informes, catálogos, IVA fiscal, amortizaciones, etc.
5. **T-05** Opción de rango de ejercicios en la exportación.
6. **T-06** Enlace SII: inclusión de los datos necesarios para el SII (formato AEAT); la presentación telemática es opcional.
7. **T-07** Pruebas automáticas (pytest) de exportación, huella y multi-tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST generar una exportación completa del tenant de la empresa activa, con un inventario de todos los bloques de datos incluidos.
- **FR-002**: El sistema MUST generar una huella verificable (hash) del archivo y un manifiesto que permita validar la integridad.
- **FR-003**: El sistema MUST excluir los datos de otras empresas/tenants, exportando solo la empresa activa.
- **FR-004**: El sistema MUST incluir en la exportación los bloques: plan de cuentas y versiones, asientos, terceros, vencimientos, cobros/pagos, remesas, cierres, informes, libros fiscales, amortizaciones, presupuestos y previsiones.
- **FR-005**: El sistema MUST permitir filtrar por rango de ejercicios antes de generar la exportación.
- **FR-006**: El sistema MUST incluir en la exportación los datos necesarios para el SII de la AEAT (formato compatible), declarando la presentación como opcional.
- **FR-007**: El flujo MUST cumplir la constitución (precisión Decimal, multi-tenancy, pruebas).

### Key Entities *(include if feature involves data)*

- **Exportación**: Archivo descargable con todos los bloques de datos del tenant.
- **Manifiesto**: Inventario de bloques y metadatos de la exportación con la huella.
- **Huella (hash)**: Verificador de integridad del archivo exportado.
- **Datos SII**: Subconjunto de datos preparado para el SII de la AEAT (formato compatible).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las exportaciones incluyen todos los bloques de datos de la empresa activa.
- **SC-002**: El 100 % de las exportaciones generan una huella verificable y un manifiesto consistente.
- **SC-003**: El 0 % de la exportación contiene datos de otros tenants.
- **SC-004**: El 100 % de las exportaciones con filtro de ejercicio incluyen solo los datos del rango seleccionado.
- **SC-005**: Los datos numéricos se exportan con precisión de 4 decimales.

## Assumptions

- La exportación es solo de lectura y descarga; la importación (restore) no se contempla en esta versión (solo portabilidad exportable).
- El SII se declara como funcionalidad opcional; el usuario debe tener la autorización y los datos necesarios del SII configurados.
- El archivo exportado está en formato estándar (JSON o XML) y comprimido (ZIP) para su descarga.
- La huella se calcula sobre el contenido del archivo completo (datos + manifiesto).

## Dependencias

- SPEC-001 (plan de cuentas y versiones), SPEC-002 (motor de asientos), SPEC-003 (multiempresa/tenant), SPEC-007 (facturación), SPEC-008 (terceros), SPEC-010 (cuentas anuales), SPEC-011/020 (cobros/pagos y remesas), SPEC-012 (libros fiscales/SII), SPEC-014 (amortizaciones), SPEC-028 (cierres).