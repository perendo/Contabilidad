# Feature Specification: Importación y Exportación Masiva de Asientos Contables

**Feature Branch**: `005-import-export-asientos`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Especifica el módulo de Importación y Exportación Masiva de Asientos Contables en CSV/Excel (SPEC-005) siguiendo constitution.md: previsualización sin escritura (dry-run) con validación de cuentas apuntables, partida doble estricta con Decimal y ejercicios no cerrados; importación definitiva con transacciones atómicas por asiento, numeración secuencial y auditoría; exportación en CSV/XLSX con precisión de 4 decimales; interfaz drag-and-drop con vista previa de errores; pruebas de desbalanceo, aislamiento multi-tenant e integridad decimal."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Previsualizar la importación de asientos (Priority: P1)

El contador sube un archivo CSV o Excel con asientos contables y, antes de que se escriba nada en los libros, el sistema realiza una pre-validación (prueba en seco) y le muestra un resumen: total de asientos detectados, asientos válidos, asientos con error y, por cada error, la fila, la cuenta implicada y el motivo.

**Why this priority**: Detectar errores antes de tocar el diario evita asientos inválidos en los libros y respeta la partida doble estricta desde la entrada masiva.

**Independent Test**: Subiendo un archivo con asientos válidos y otros con errores, el resumen distingue válidos/erróneos y no se escribe ningún dato en el sistema.

**Acceptance Scenarios**:

1. **Given** un archivo CSV/XLSX con asientos de la empresa activa, **When** se solicita la pre-visualización, **Then** el sistema devuelve el total de asientos, los válidos, los con error y el detalle (fila, cuenta, motivo) sin escribir nada.
2. **Given** un asiento cuyo Debe no es exactamente igual a su Haber, **When** se pre-visualiza, **Then** se marca con error de desbalanceo y no pasa a la importación.
3. **Given** un asiento que referencia una cuenta inexistente en la empresa activa o no apuntable, **When** se pre-visualiza, **Then** se marca con error (cuenta no encontrada / no apuntable).

---

### User Story 2 - Confirmar y ejecutar la importación definitiva (Priority: P1)

Una vez revisados los errores en la vista previa, el contador confirma la importación. El sistema insiste en validar, importa únicamente los asientos válidos con transacciones atómicas por asiento, asigna la numeración secuencial correcta por empresa y ejercicio, y deja constancia de la operación en el registro de auditoría.

**Why this priority**: La importación definitiva debe incorporar asientos íntegros (cabecera + apuntes) sin contaminar la secuencia ni el diario, garantizando atomicidad y trazabilidad.

**Independent Test**: Confirmando la importación de un archivo mixto, solo los asientos válidos se registran, con numeración correlativa, y la operación queda auditada.

**Acceptance Scenarios**:

1. **Given** una pre-visualización con asientos válidos, **When** el usuario confirma la importación, **Then** los asientos válidos se guardan con cabecera y apuntes indivisibles y se les asigna numeración secuencial continua por empresa y ejercicio.
2. **Given** una importación confirmada, **When** finaliza, **Then** queda un registro de auditoría de la operación con empresa, usuario, acción y fecha-hora.
3. **Given** un asiento que falla durante la ejecución, **When** se procesa el lote, **Then** ese asiento se omite sin afectar a los demás y sin dejar estado parcial.

---

### User Story 3 - Exportar el libro diario (Priority: P2)

El contador exporta el libro diario de su empresa a CSV o Excel para el rango de fechas deseado. El archivo refleja fielmente los montos con precisión de 4 decimales y solo incluye los asientos de la empresa activa.

**Why this priority**: La exportación fiel del diario es necesaria para presentaciones, conciliaciones y procesos externos, y debe conservar la precisión contable.

**Independent Test**: Exportando el diario por rango de fechas se obtiene un archivo descargable con los asientos de la empresa activa y montos de Debe/Haber exactos.

**Acceptance Scenarios**:

1. **Given** asientos asentados de la empresa activa en el rango, **When** se exporta a CSV o Excel, **Then** el archivo descargable incluye dichos asientos con importes de Debe y Haber exactos a 4 decimales.
2. **Given** una solicitud de exportación, **When** se ejecuta, **Then** solo se incluyen asientos de la empresa activa y el rango de fechas indicado.

---

### Edge Cases

- ¿Qué ocurre con un archivo en un formato no soportado o con columnas faltantes? → Se rechaza el archivo con un error claro antes de cualquier validación.
- ¿Qué ocurre si un asiento referencia una cuenta de otra empresa? → La cuenta se reporta como no encontrada (sin revelar su existencia).
- ¿Qué ocurre si una fecha corresponde a un ejercicio cerrado? → Se marca error en la pre-visualización y se bloquea en la ejecución.
- ¿Qué ocurre con valores numéricos en notación imprecisa (flotante) o con más de 4 decimales? → Se interpretan con precisión decimal canónica y se valida el balance sobre esa precisión.
- ¿Qué ocurre si el archivo no contiene ningún asiento válido? → La importación no se puede confirmar y el sistema lo informa.
- ¿Qué ocurre si se exporta un rango sin asientos? → Se devuelve un archivo con las cabeceras y sin filas.
- ¿Qué ocurre si el archivo mezcla asientos válidos y con error en la confirmación? → Solo se importan los válidos; los erróneos se listan de nuevo.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aislar por completo la importación y exportación por empresa: pre-visualización, ejecución y exportación operan exclusivamente sobre la empresa activa del usuario autenticado.
- **FR-002**: El sistema MUST realizar la pre-visualización (dry-run) sin efectuar ninguna escritura en la base de datos.
- **FR-003**: La pre-visualización MUST validar, por asiento: (a) existencia y apuntabilidad de todas las cuentas en el plan de la empresa activa, (b) partida doble estricta (Sum Debe == Sum Haber) con precisión decimal, y (c) fecha no perteneciente a un ejercicio cerrado.
- **FR-004**: La pre-visualización MUST devolver un resumen con total de asientos, asientos válidos, asientos con error y el detalle de cada error (fila, cuenta y motivo).
- **FR-005**: El sistema MUST confirmar la importación con re-validación y persistir cada asiento válido en una transacción atómica (cabecera y apuntes indivisibles).
- **FR-006**: El sistema MUST asignar la numeración de asientos de forma secuencial y sin saltos, por empresa y ejercicio, durante la importación definitiva.
- **FR-007**: El sistema MUST registrar en auditoría cada operación de importación definitiva (empresa, usuario, acción, identificador y fecha-hora).
- **FR-008**: El sistema MUST exportar el libro diario a CSV o Excel filtrado por rango de fechas y empresa activa, conservando los importes con precisión monetaria exacta de 4 decimales.
- **FR-009**: El sistema MUST procesar todos los importes del dominio como valores decimales exactos; queda prohibido el uso de precisión flotante en importaciones y exportaciones.
- **FR-010**: El usuario MUST poder ver el resultado de la pre-visualización resaltando las filas con error y su motivo, y confirmar la importación una vez corregidos o aceptados los asientos válidos.
- **FR-011**: El flujo completo de esta feature MUST cumplir las reglas inmutables de la constitución (partida doble, multi-tenancy, numeración correlativa, precisión decimal, auditoría y pruebas obligatorias).

### Key Entities *(include if feature involves data)*

- **Archivo de importación**: CSV o Excel que el usuario sube; se interpreta en asientos con sus apuntes y se valida sin escritura.
- **Asiento contable (Cabecera + Apuntes)**: Entidades del módulo de asientos (SPEC-002) que la importación crea; su persistencia es indivisible por asiento.
- **Cuenta contable**: Entidad del plan de cuentas (SPEC-001) usada para validar existencia y apuntabilidad dentro de la empresa activa.
- **Ejercicio contable**: Entidad de SPEC-004; determina si la fecha de un asiento está bloqueada (cerrada) o admite escritura.
- **Resultado de importación**: Resumen (totales) y detalle de errores (fila, cuenta, motivo) devuelto por la pre-visualización.
- **Registro de auditoría**: Entidad de plataforma donde se deja constancia de la importación definitiva.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los archivos con asientos desbalanceados marcan el error en la pre-visualización y ningún asiento desbalanceado llega al diario.
- **SC-002**: El 100 % de las cuentas pertenecientes a otra empresa se reportan como no encontradas, sin filtrar información de esa empresa.
- **SC-003**: El 100 % de los importes importados y exportados conservan la precisión de 4 decimales (ronda completa sin errores por conversión flotante).
- **SC-004**: El 100 % de las importaciones con fecha en ejercicio cerrado son rechazadas antes de escribir nada.
- **SC-005**: El 100 % de las importaciones confirmadas quedan registradas en auditoría y mantienen numeración secuencial sin duplicados ni saltos.
- **SC-006**: El usuario ve el resultado de la pre-visualización y confirma la importación en menos de 2 minutos tras la subida para los tamaños de archivo definidos.

## Assumptions

- El esquema exacto de columnas del archivo de importación (fecha, concepto, cuenta, debe, haber, detalle) se fija en la plantilla estándar que acompañará a esta feature; la spec asume un esquema mínimo con esos campos.
- La exportación del libro diario incluye únicamente asientos asentados (POSTED), coherente con la modalidad de diario del módulo de asientos (SPEC-002).
- La importación definitiva es selectiva: solo se persisten los asientos válidos; los asientos con error se reportan y no se reintentan automáticamente.
- Se definirá (en diseño técnico) un tamaño máximo razonable de archivo y número de asientos por lote; el procesamiento será secuencial por asiento.
- La re-validación al ejecutar protege contra cambios de estado entre la pre-visualización y la confirmación (p. ej., ejercicio cerrado en ese lapso).
- La autenticación y el contexto de empresa provienen del módulo de multiempresa/RBAC (SPEC-003).

## Dependencias

- SPEC-001 (plan de cuentas), SPEC-002 (motor de asientos), SPEC-003 (multiempresa).