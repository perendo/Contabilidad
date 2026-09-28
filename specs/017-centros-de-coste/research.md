# Research: Centros de Coste (SPEC-017)

**Branch**: `017-centros-de-coste` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

Decisiones de diseño (Phase 0) para la feature 017. Cada sección documenta Decisión / Racional / Alternativas. Decisiones marcadas «NEEDS CLARIFICATION» quedan abiertas.

## D1. Estrategia de jerarquía: closure table

**Decisión**: Modelar la jerarquía con una **closure table** (`jerarquia_centro`) que materializa todos los pares ancestro→descendiente junto al árbol padre/hijo (`parent_id` en `centro_coste`).

**Racional**: El informe FR-006 exige subtotales por jerarquía (inclusión de hijos al consultar un padre). Con `parent_id` solo, el SQL recursivo funciona pero degrada con profundidad y miles de centros; la closure table permite consultas de agregación por ancestro con un simple `JOIN` y un único índice, cumpliendo el objetivo de rendimiento (<1 s en 50.000 líneas). El mantenimiento de la closure se hace en la misma transacción ACID que la alta/reasignación del centro (audit log incluido).

**Alternativas consideradas**:
- **Materialized Path** (`path VARCHAR` "1/5/12/"): compacto pero las agregaciones requieren `LIKE` (no sargable en escala) y la reasignación de un subárbol es frágil.
- **Adjacency list + CTE recursiva**: simplicidad de escritura; rendimiento dependiente de la profundidad y sin índices eficientes para agregados por ancestro.
- **Nested sets**: buena para lectura, costosa y propensa a errores en escritura (reasignaciones).

## D2. La imputación como dimensión de línea del motor SPEC-006

**Decisión**: La imputación es una **columna opcional `centro_coste_id` en `JournalEntryLine`** (modelo de `acct/`, SPEC-006) más una tabla `imputacion_centro` que registra la traza (empresa, línea, centro, asiento, fecha) para auditoría y reporting desacoplado del layout físico histórico.

**Racional**: El spec exige imputación «por apunte (línea)», no por asiento completo (Assumption). Integrarla como campo de línea la hace nativa del motor multilínea (SPEC-006) y garantiza que el balance se valide donde el motor lo valida (persistencia, constitución I). La tabla de traza permite re-generar informes y auditar sin alterar el diario.

**Alternativas consideradas**:
- **Tabla puente separada solo con FK a línea**: evita tocar `JournalEntryLine`, pero complica los servicios del motor y parte del modelo queda fuera del registro atómico del asiento.
- **Asiento por centro (imputación a cabecera)**: rechazada — contradice el spec (un asiento se reparte entre varios centros).

## D3. Almacenamiento del vínculo centro ↔ subvención (SPEC-019)

**Decisión**: Vínculo **opcional y 1:N** `CentroCoste.subvencion_id → Subvencion` (nulo si el centro no corresponde a una subvención), validado contra la empresa activa.

**Racional**: El spec FR-002 exige asociar centros a las subvenciones del módulo 019 «si procede». Un único FK opcional es suficiente porque la subvención en 019 es una entidad de control de gasto, no una dimensión con sub-hijos. El aislargasto-imputado seguirá gobernado por 019; aquí solo se etiqueta el centro.

**Alternativas consideradas**:
- Tabla puente 1:N con historial: sobredimensionada para el estado actual de 019 (una subvención ↔ uno o varios centros analíticos).
- Vínculo M:N: DES Estonia— una línea de gasto de 019 ya se divide entre subvenciones/partidas a nivel de línea; el centro es una etiqueta adicional.

## D4. Ciclo de vida del centro: inactivación, no borrado

**Decisión**: Un centro con imputaciones (o descendientes) es físicamente NO borrable (constraint/trigger en DB). Solo admite estado `activo/inactivo`; la inactivación preserva historial y bloquea nuevas imputaciones.

**Racional**: FR-005 y Edge Case «¿eliminar centro con imputaciones? → se bloquea; solo se inactiva con histórico preservado». La restricción a nivel de DB (no solo API) refuerza la constitución II (auditabilidad del historial).

**Alternativas consideradas**:
- Borrado físico en cascada de imputaciones: violaría el históricocontable (el informe histórico ya no podría reproducirse).
- Borrado lógico con `deleted_at`: admite reutilizar códigos y corrompe la correlatividad semántica del catálogo.

## D5. Informe de costes: agregación por suma de líneas vs. transacciones

**Decisión**: El informe agrega directamente los importes **de las líneas imputadas** (`Debe` cuando la línea es de coste, `Haber` cuando es de ingreso) clasificadas por (centro o ancestro, tipo de importe, período), usando `Decimal`/`SUM(NUMERIC(18,4))` en PostgreSQL.

**Racional**: FR-006 exige que «los importes agregan exactamente los apuntes imputados» (SC-003). Agregar las líneas del diario inmutable es la única garantía de exactitud; no se mantienen saldos materializados que pudieran desincronizarse. El tipo de importe (coste/ingreso) se deriva de la posición Debe/Haber y del grupo del plan (SPEC-001).

**Alternativas consideradas**:
- Saldos materializados por centro (`tabla resumen_costo`): rendimiento en lectura, pero riesgo de desincronización con el diario inmutable y complejidad de reconciliación.
- Líneas solo de `Debe` como importe de coste: pierde ingresos imputados a proyectos/subvenciones, que el spec exige distinguir.

## D6. Reasignación de imputaciones sobre asientos posteados

**Decisión**: Prohibida la edición directa de `centro_coste_id` en líneas posteadas (constraint a nivel de aplicación y DB vía trigger del motor SPEC-002). La reasignación exige un asiento de rectificación (`ADJUSTMENT`/`REVERSAL`) enlazado, tal como el motor lo define.

**Racional**: AS-4 y Edge Case «¿reasignar la imputación de un posteado? → solo con rectificación». Es una consecuencia directa de la constitución II; la traza `imputacion_centro` permite ver el historial imputado antes/después.

**Alternativas consideradas**:
- `UPDATE` permitido en borrador y bloqueado tras `POSTED`: el diseño del motor separa borradores de asentados; la regla del spec se aplica a ambos por homogeneidad y porque un borrador re-asignado es simplemente una edición del borrador, no una reasignación histórica.

## D7. Multi-tenancy estricto en imputaciones e informes

**Decisión**: `empresa_id` en PK de `centro_coste` y en índices de `imputacion_centro` y de la columna de línea; toda consulta (incluida la agregación del informe) filtra por `empresa_id` derivado de sesión; la validación del centro en la imputación verifica pertenencia a la empresa activa (FR-004).

**Racional**: Constitución III «NINGUNA consulta sin filtro explícito». Los informes agregan exclusivamente líneas de la empresa activa; el intento de cruzar empresa devuelve 404 (no 403) para no revelar existencia.

**Alternativas consideradas**:
- Empresa en nombre de esquema (schema-per-tenant): descartada por el stack común multi-tenant del plan raíz (tablas compartidas con `empresa_id`).

## D8. Permisos y matriz SPEC-015

**Decisión**: Toda operación de centros verifica la matriz de permisos (SPEC-015): lectura/informes para roles analistas; alta/edición/inactivación solo para roles contable/administrador según matriz.

**Racional**: Dependencia declarada «SPEC-015 (permisos)» en el spec. La integración se realiza mediante el dependency del RBAC existente; los tests de integración de aislamiento se ejecutan con dos empresas y dos roles.

**Alternativas consideradas**:
- Permisos ad-hoc dentro de la feature (sin SPEC-015): crearía una matriz paralela contradictoria con el plan raíz.

## D9. Formato del informe: períodos flexibles y exportación

**Decisión**: El informe acepta `ejercicio` y rango de fechas opcional por línea, resultados por centro/hijo con subtotales por ancestro, y exportación JSON/CSV (4 decimales).

**Racional**: FR-006 pide «por centro y período». Mantener el informe como agregación parametrizada cubre ejercicios completos y ventanas parciales sin duplicar lógica; la exportación cubre usos de justificación (SPEC-019) y dirección sin PDF obligatorio (el PDF pertenece a 019).

**Alternativas consideradas**:
- Exportación PDF propia: duplica la funcionalidad de los libros de 019 (que ya genera PDF con saldos exactos); se delega PDF a 019 y aquí CSV/JSON.

## D10. Prelación de implementación y contexto raíz

**Decisión**: US1 (definición/jerarquía) → US2 (imputación) → US3 (informes). La imputación depende de que existan centros (US1); los informes agregan datos de la imputación (US2).

**Racional**: AS-order natural del spec y de las dependencias entre stories. Cada US conserva su test independiente; el bloqueo de borrado y la closure table se construyen en US1 (base fundacional) ya que US2/US3 dependen de su existencia.

**Alternativas consideradas**:
- Construir informes antes de la imputación: inviable, no hay datos que agregar.
- US2 antes que US1: se necesitan centros para imputar (validación FR-004).

---

## Decisiones en condicional (NEEDS CLARIFICATION si no se confirman)

- **Ruta alternativa de cierre**: si el repositorio ya dispone de la closure table del SPEC-019 (no planificada), se reutiliza en lugar de crear una nueva. Pendiente de confirmar con el plan raíz.
- **Nombrado de módulo**: `costcenters` es el directorio propuesto (aliases: `centros_de_coste`, `cost_centers`). Se confirma con la convención del plan raíz.
- **Tipo de importe en informe**: se asume derivado de Debe/Haber + grupo PGC (SPEC-001); si el plan de cuentas no agrupa cuentas de gasto/ingreso, NEEDS CLARIFICATION para la regla exacta de clasificación.