# Research: Gestión ONG (Subvenciones, Libros Oficiales y Caja) (SPEC-019)

**Branch**: `019-gestion-ong-libros-caja` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

Decisiones de diseño (Phase 0) para la feature 019, incluidas las aclaraciones de la sesión 2026-09-16 (integradas). Cada sección documenta Decisión / Racional / Alternativas. Decisiones marcadas «NEEDS CLARIFICATION» quedan abiertas.

## D1. Subvención como entidad de control de gasto (sin asientos propios)

**Decisión**: `Subvencion` es una entidad de **control** (concedente, programa, importe concedido, ejercicio, estado) que NO genera asientos. La percepción/ingreso de la subvención se asienta con asientos normales del motor (SPEC-002) fuera de la feature (clarificación integrada).

**Racional**: FR-002 y clarificación «la subvención NO se registra contablemente en esta feature; el gasto se controla aquí, la percepción se asienta en el motor». Evita duplicar la generación de asientos y mantiene al motor como único punto de verdad.

**Alternativas consideradas**:
- Asiento automático de concesión al crear la subvención: viola la clarificación y acopla el registro de subvenciones a reglas contables no especificadas.
- Almacenar el asiento de percepción dentro de la subvención: duplicidad de trazabilidad con el diario inmutable.

## D2. Imputación de gasto a nivel de línea de asiento

**Decisión**: El gasto se imputa a la subvención **a nivel de línea de asiento** (`GastoImputado` referencia `JournalEntryLine`), con `importe_asignado` parcial o total, sumas de imputaciones por línea ≤ importe de la línea, y rechazo si el acumulado de la subvención supera el disponible (clarificación integrada).

**Racional**: Clarificación «¿A qué nivel se imputa un gasto? → a nivel de línea de asiento». Permite dividir un mismo apunte entre subvenciones/partidas (Edge Case: double imputación vs. división explícita) y evita la doble imputación del mismo importe (FR-003, Assumption). La línea nunca se modifica: solo se registra una asignación externa al diario (constitución II respetada).

**Alternativas consideradas**:
- Imputación a nivel de asiento completo: no granular; contradice la clarificación.
- Imputación a nivel de documento/factura: sin trazabilidad al apunte concreto solicitado en FR-003.

## D3. PDF de libros oficiales: renderizado server-side bajo demanda

**Decisión**: Los PDF se generan **bajo demanda** desde el backend por renderizado server-side (biblioteca de generación PDF del stack), leyendo el diario/mayor del ejercicio cerrado, y se persisten con `sha256` en `LibroOficial` (BYTEA) para reproducibilidad y legalización.

**Racional**: FR-005 exige PDF con «todos los asientos, numeración y saldos con exactitud decimal». Renderizar desde los datos del diario inmutable garantiza SC-002 (100 % coincidencia con el diario/mayor). Persistir el PDF con su huella permite la re-legalización con huella idéntica (D4).

**Alternativas consideradas**:
- Frontend imprime HTML→PDF: la precisión decimal y el paginado de miles de apuntes no se controlan; además el navegador altera el contenido.
- PDF pre-generado al cerrar el ejercicio (SPEC-004): evento de cierre no garantiza el render; con generación bajo demanda el PDF siempre refleja los últimos asientos del ejercicio cerrado (que son inmutables).

## D4. Legalización y huella: re-emisión solo con huella idéntica

**Decisión**: El fichero de legalización incluye **empresa, ejercicio, rango de asientos (primero/último/nº), fecha y huella SHA-256** del contenido canónico (PDFs + metadatos). La **re-emisión del mismo ejercicio solo se permite si la huella es idéntica** (recalculada y comparada); si la huella difiere, se rechaza 409 (clarificación integrada). Se restringe a ejercicios cerrados (fr-006/FR-007).

**Racional**: Clarificación «re-emisión permitida solo con huella idéntica; si difiere se rechaza». La huella sobre contenido canónico garantiza que el PDF no cambió entre emisiones; como el ejercicio está cerrado, un cambio de huella significa manipulación o defecto del render, que debe bloquearse. Un ejercicio legalizado no admite asientos posteriores de fecha dentro del ejercicio (refuerzo de bloqueo SPEC-004, FR-007).

**Alternativas consideradas**:
- Re-legalización sin comprobación de huella: permitiría legalizar contenido alterado, invalida la finalidad de integridad.
- Firma digital externa: el trámite formal es externo (Assumption); aquí solo huella.

## D5. Caja = subcuenta 570 real dedicada; movimientos como asientos del motor

**Decisión**: Una caja equivale a una **subcuenta 570** de la empresa activa (`Caja.cuenta_570_id` → subcuenta del grupo PGC 570, SPEC-001). Las entradas/salidas se contabilizan como **asientos reales del motor** (SPEC-002) sobre esa 570; el modelo `MovimientoCaja` es una **vista/traza de los asientos** de la 570 (referencias, no duplicación).

**Racional**: Clarificación «los movimientos de caja/caja chica generan su asiento sobre una subcuenta 570 por caja (Opción A)» y FR-008. Como los asientos son inmutables, la traza se deriva de las líneas del diario con esa 570; la reposición del fondo fijo es una operación de tesorería normal (572→570, Assumption).

**Alternativas consideradas**:
- Tabla `movimiento_caja` con importes propios fuera del diario: duplicaría la contabilidad y rompería la relación saldo-libros = saldo-570.
- Caja como entidad sin cuenta: sin saldo contable verificable, invalidaría el arqueo (D6).

## D6. Arqueo: saldo 570 vs efectivo, diferencia aprobada exige asiento de ajuste

**Decisión**: `Arqueo` calcula `diferencia = efectivo_contado - saldo_libros570` (suma de líneas de la 570 del período), registra estado `cuadra | con_diferencia`. Si la diferencia supera 0 en valor absoluto y se **aprueba**, el sistema **exige** y valida un **asiento de ajuste enlazado** (Debe/Haber 570 vs cuenta de diferencias) que cuadre 570 con el efectivo; si solo se **archiva**, la diferencia queda con estado `pendiente` visible (clarificaciones integradas).

**Racional**: Clarificación «arqueo con diferencia aprobada exige asiento de ajuste que cuadre 570 con el efectivo; si solo se archiva, la diferencia queda como pendiente visible» y FR-009. El ajuste es un asiento nuevo del motor (constitución II: el original no se toca); el saldo resultante de 570 tras el ajuste debe igualar el efectivo contado.

**Alternativas consideradas**:
- Aprobación de diferencia sin ajuste: resultaría en un arqueo «aprobado» con libros sin cuadrar — rechazado por la clarificación.
- Ajuste automático silencioso al aprobar: el importe destino debe decidir el usuario; el ajuste debe auditarse como asiento, no generarse a ciegas.

## D7. Disponible de subvención y división de líneas entre subvenciones

**Decisión**: `GastoImputado` valida, en la misma transacción ACID: `importe_asignado > 0`; lo imputado a la línea ≤ importe de la línea; el acumulado de la subvención (incluido el nuevo) ≤ `importe_concedido` de las partidas vigentes. Un mismo gasto puede repartirse entre subvenciones/partidas con importes parciales explícitos (Edge Case), nunca re-imputarse el mismo importe dos veces (FR-003).

**Racional**: FR-003, Edge Cases y Assumption. El control en backend (no UI) evita exceso y doble imputación incluso bajo concurrencia; el `SELECT ... FOR UPDATE` sobre la subvención previene carreras en el disponible (constitución IV por analogía: atomicidad).

**Alternativas consideradas**:
- Comprobación solo en UI y aceptación en escritura sin lock: podría superarse el disponible con concurrencia.
- Imputación por documento completo: contradice D2/clarificación del nivel de línea.

## D8. Estados de subvención y reintegro

**Decisión**: `estado` ENUM(`concedida`, `en_curso`, `justificada`, `reintegrada`). La transición `justificada → reintegrada` exige el asiento rectificativo correspondiente (Edge Case «subvención reintegrable»); el `ajuste` se registra como `ADJUSTMENT`/`REVERSAL` enlazado con su importe.

**Racional**: El Edge Case del spec exige admitir estado `reintegro` y el ajuste correspondiente (asiento rectificativo, constitución II). El estado `justificada` solo se alcanza cuando gastado ≥ concedido (o por decisión del responsable con informe de pendiente).

**Alternativas consideradas**:
- Modelo con solo dos estados: no cubre el Edge Case de reintegro ni el control de justificación.
- Permitir borrar estados: la auditoría exige historial de estados; se guardan en la misma fila + audit log.

## D9. Estado de «ejercicio legalizado» y bloqueo de asientos posteriores

**Decisión**: Tras legalizar un ejercicio, el sistema mantiene `Legalizacion.valido = true` y refuerza el bloqueo de SPEC-004 (no admite asientos posteriores con fecha dentro del ejercicio; a nivel DB/alta en servicios del motor). El bloqueo es anterior a la legalización (solo se legaliza un ejercicio cerrado) y se re-verifica en la emisión de libros.

**Racional**: FR-007 «un ejercicio legalizado no admite asientos posteriores de fecha dentro del ejercicio». REFORZAR lo ya aportado por SPEC-004 sin desacoplar la regla del motor: el motor conoce la fecha del documento y el estado del ejercicio; la legalización añade la marca informativa.

**Alternativas consideradas**:
- Marca solo informativa sin bloqueo: viola FR-007.
- Bloqueo solo a nivel API: la constitución exige refuerzo en DB (asientos = restricción).

## D10. ISR/multi-tenant y permisos (SPEC-015)

**Decisión**: Toda operación de subvenciones, libros, legalización y caja filtra por `empresa_id` de la sesión; permisos por SPEC-015 (contador/admin para legalización y ajustes; responsable/tesorero para gastos, cajas y arqueos según matriz).

**Racional**: FR-001 (aislamiento total) y constitución III. La legalización es una operación sensible → rol contable; el arqueo puede realizarlo el tesorero; cualquier cruce cross-tenant → 404.

**Alternativas consideradas**:
- Un único rol para todo el módulo: no respeta la matriz de permisos del plan raíz.

---

## Decisiones en condicional (NEEDS CLARIFICATION si no se confirman)

- **Biblioteca de PDF**: se propone ReportLab (server-side). Si el repositorio ya fija otra (p. ej., WeasyPrint/FPDF), se ajusta el generador sin cambiar el contrato de `libros-pdf.md`.
- **Cuentas de la subvención en concesión y ajuste de arqueo**: para `concedida`/`reintegrada` no se crean asientos; para el ajuste de arqueo el usuario selecciona la cuenta de diferencias (se asume cuenta 570 vs 657/678 según convenio de la empresa). Pendiente de confirmar con el rol contable.
- **Partidas del programa de subvención**: los importes se controlan de forma agrupada (disponible total) en primera versión; si se exige control por partida individual desde el inicio, NEEDS CLARIFICATION para modelar `Partida` como subtabla.