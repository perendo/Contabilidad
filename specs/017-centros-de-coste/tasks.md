# Tasks: Centros de Coste (SPEC-017)

**Input**: Design documents from `/specs/017-centros-de-coste/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo `costcenters` en backend y frontend según plan.md; integrar la dimensión de centro en el motor multilínea (SPEC-006).

- [X] T001 [P] Crear estructura del módulo costcenters: `backend/src/models/costcenters/__init__.py`, `backend/src/services/costcenters/__init__.py`, `backend/src/api/costcenters/__init__.py`, `backend/src/api/costcenters/routes.py`
- [X] T002 [P] Configurar router costcenters: registrar prefijo `/api/v1` en `backend/src/api/costcenters/__init__.py` con dependency de sesión autenticada y cabecera de empresa activa
- [X] T003 [P] Crear utils de sesión: `backend/src/api/costcenters/deps.py` con `get_empresa_activa()` que extrae el `empresa_id` de la sesión/cabecera y bloquea acceso cross-tenant
- [X] T004 [P] Crear estructura frontend: `frontend/src/app/centros/`, `frontend/src/app/informes/costes/`, `frontend/src/components/costcenters/`, y cliente HTTP reutilizando `frontend/src/services/client.ts`
- [X] T005 [P] Añadir columna `centro_coste_id` a `JournalEntryLine` en `backend/src/models/acct/journal_detail.py` (SPEC-006): FK compuesta a `centro_coste(empresa_id, id)` nullable, sin tocar Debe/Haber

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T006 [P] Crear modelo `CentroCoste` en `backend/src/models/costcenters/centro_coste.py`: empresa_id (PK compuesta), id, codigo VARCHAR(20), nombre, tipo ENUM(departamento/proyecto/subvencion/delegacion), parent_id FK compuesta nullable, subvencion_id FK nullable a SPEC-019, estado (activo/inactivo), created_at, updated_at; constraint unicidad (empresa_id, codigo) y FK compuesta en parent_id
- [X] T007 [P] Crear modelo `JerarquiaCentro` (closure) en `backend/src/models/costcenters/jerarquia.py`: empresa_id PK, ancestro_id, descendiente_id, profundidad SMALLINT; PK compuesta (empresa_id, ancestro_id, descendiente_id); FK compuestas a centro_coste
- [X] T008 [P] Crear modelo `ImputacionCentro` en `backend/src/models/costcenters/imputacion.py`: empresa_id PK, id, asiento_id, linea_id, centro_coste_id FK compuesta, periodo SMALLINT, created_at; registros inmutables (sin UPDATE/DELETE)
- [X] T009 [P] Migración ALTER para `centro_coste_id` en línea de asiento: `backend/src/db/migrations/20260916_017_centros_linea.py` con FK compuesta (empresa_id, centro_coste_id) y CHECK de que el centro pertenece a la misma empresa de la línea
- [X] T010 [P] Tests de modelos fundacionales: `backend/tests/unit/test_costcenter_models.py` — unicidad (empresa_id, codigo), FK compuesta cross-tenant imposible, closure materializa ancestro/descendiente
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_costcenter_tenant_isolation.py` — crear centro en empresa A, verificar que B no lo ve en ninguna consulta; intento de FK compuesta con empresa B → error

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Definir centros de coste y su jerarquía (Priority: P1) ?? MVP

**Goal**: El contador crea centros de coste organizados en jerarquía, exclusivos de la empresa activa, y los asocia a las subvenciones de SPEC-019 si procede.

**Independent Test**: Crear un centro y su jerarquía funciona para la empresa activa y no es visible para otras.

### Tests for User Story 1

- [X] T012 [P] [US1] Test alta y árbol: `backend/tests/unit/test_centro_arbol.py` — crear centros padre/hijo, verificar closure (ancestro→descendiente con profundidad) y consulta de árbol
- [X] T013 [P] [US1] Test ciclo y duplicados: `backend/tests/unit/test_centro_restricciones.py` — `codigo` duplicado → rechazo; ciclo padre/hijo → rechazo 409; padre de otra empresa → rechazo
- [X] T014 [P] [US1] Test vínculo subvenciones: `backend/tests/unit/test_centro_subvencion.py` — vincular centro a `Subvencion` de la empresa activa OK; subvención de otra empresa → rechazo; vínculo opcional (NULL ok)

### Implementation for User Story 1

- [X] T015 [US1] Implementar CRUD de centros (servicio) en `backend/src/services/costcenters/centros.py`: crear/editar/inactivar/reactivar con validación de `codigo` único, ciclo (recorrido de ancestros), pertenencia de `parent_id` y `subvencion_id` a la empresa activa; inactivación solo si no hay operaciones en curso; transacción ACID con audit log
- [X] T016 [US1] Mantener closure table en `backend/src/services/costcenters/centros.py`: tras crear/reasignar un centro, actualizar `jerarquia_centro` (nuevos pares ancestro→descendiente) en la misma transacción ACID
- [X] T017 [US1] Implementar servicios de inactivación en `backend/src/services/costcenters/centros.py`: `inactivar_centro` y `reactivar_centro` con bloqueo de nuevas imputaciones en inactivos; DB (constraint/trigger) impide borrado físico con imputaciones o descendientes (FR-005)
- [X] T018 [US1] Implementar endpoints en `backend/src/api/costcenters/centros.py`: POST crear (201), GET listar (paginado + filtros), GET arbol, GET detalle, PATCH editar, POST inactivar, POST reactivar (ver contracts/api-contracts.md)
- [X] T019 [US1] Crear página frontend `frontend/src/app/centros/page.tsx`: árbol de centros con alta/edición/inactivación, selector de tipo y de subvención (SPEC-019), alertas de confirmación en inactivación
- [X] T020 [US1] Crear página frontend `frontend/src/app/centros/nuevo/page.tsx`: formulario de alta con `parent_id` opcional (selector de jerarquía) y `subvencion_id` opcional (SPEC-019)
- [X] T021 [US1] Tests integración alta + jerarquía: `backend/tests/integration/test_centro_arbol_integration.py` — crear jerarquía de 3 niveles, verificar closure y subtotal de agregación posterior, verificar reactivación
- [X] T022 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_centro_tenant.py` — empresa A crea centro y jerarquía, empresa B no los ve en listado/árbol/detalle; introspección de otro `id` → 404

**Checkpoint**: User Story 1 completa — catálogo de centros jerárquico funcional y aislado. MVP parcial (sin imputación aún), base para US2.

---

## Phase 4: User Story 2 — Imputar apuntes a un centro de coste (Priority: P1)

**Goal**: Registrar o editar un asiento imputando determinadas líneas a un centro de la empresa activa; la imputación queda ligada al apunte sin romper el balance y respeta la inmutabilidad.

**Independent Test**: Imputando un apunte a un centro, la línea conserva el vínculo y el asiento sigue balanceado.

### Tests for User Story 2

- [X] T023 [P] [US2] Test balance tras imputar: `backend/tests/unit/test_imputacion_balance.py` — imputar líneas (Debe/Haber) en un asiento multilínea y verificar Debe==Haber tras persistir; la imputación no altera importes
- [X] T024 [P] [US2] Test validación de centro: `backend/tests/unit/test_imputacion_centro_valido.py` — imputar a centro inexistente → 404; a centro de otra empresa → 404; a centro inactivo → 422
- [X] T025 [P] [US2] Test inmutabilidad posteado: `backend/tests/unit/test_imputacion_inmutable.py` — quitar/reasignar imputación en línea `POSTED` → rechazo 409; en línea borrador → OK; la reasignación posteada exige `ADJUSTMENT`

### Implementation for User Story 2

- [X] T026 [US2] Implementar servicio de imputación en `backend/src/services/costcenters/imputacion.py`: `imputar_linea(asiento_id, linea_id, centro_coste_id)` validando asiento/línea de la empresa activa, centro activo y de la misma empresa, líneas posteadas inmutables; insertar `ImputacionCentro` en la misma transacción ACID del asiento; audit log
- [X] T027 [US2] Implementar servicio `quitar_imputacion` en `backend/src/services/costcenters/imputacion.py`: solo líneas de asiento borrador; líneas posteadas → rechazo 409
- [X] T028 [US2] Integrar imputación en creación/edición de asientos del motor: `backend/src/services/acct/journal_engine.py` (SPEC-002/006) — aceptar `centro_coste_id` por línea al registrar comoiento y persistirlo junto al borrador; validación de balance sin cambios
- [X] T029 [US2] Reasignación de imputación posteada vía rectificación: `backend/src/services/costcenters/imputacion.py` — endpoint o servicio que valida el `ADJUSTMENT`/`REVERSAL` del motor y registra la nueva imputación en el asiento rectificativo (nunca editar el original)
- [X] T030 [US2] Implementar endpoints en `backend/src/api/costcenters/imputaciones.py`: POST `{asiento_id}/lineas/{linea_id}/imputar`, DELETE (borrador), GET imputaciones por asiento/centro (ver contracts/api-contracts.md)
- [X] T031 [US2] Adaptar página de asientos para selector de centro: `frontend/src/app/asientos/` — input de imputación por línea con autocompletado de centros activos de la empresa (SPEC-002/006)
- [X] T032 [US2] Tests integración imputación completa: `backend/tests/integration/test_imputacion_completa.py` — crear asiento multilínea con imputaciones mixtas (algunas líneas sin centro), verificar persistencia del vínculo, balance, y traza en `imputacion_centro`
- [X] T033 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_imputacion_tenant.py` — empresa A imputa a su centro; empresa B intenta imputar la línea de A o usar el centro de A → 404; B no ve imputaciones de A

**Checkpoint**: User Stories 1 y 2 completas — imputación por apunte funcional y balanceada.

---

## Phase 5: User Story 3 — Informes de costes por centro (Priority: P2)

**Goal**: El usuario genera informes de gastos e ingresos por centro y período, con subtotales por jerarquía y precisión monetaria exacta.

**Independent Test**: Generando el informe de un centro y período, los importes agregan exactamente los apuntes imputados.

### Tests for User Story 3

- [X] T034 [P] [US3] Test agregación exacta: `backend/tests/unit/test_informe_agregacion.py` — líneas imputadas en dos centros, SUM con `Decimal`, compara contra suma manual en 4 decimales sin errores de redondeo
- [X] T035 [P] [US3] Test subtotales por jerarquía: `backend/tests/unit/test_informe_subtotales.py` — consultar un centro padre y verificar que `subtotal` incluye a los hijos (closure), sin duplicar
- [X] T036 [P] [US3] Test período y ejercicio: `backend/tests/unit/test_informe_periodo.py` — filtrar por fecha_desde/hasta y ejercicio; asientos fuera del rango excluidos; ejercicio cerrado únicamente informa del cerrado

### Implementation for User Story 3

- [X] T037 [US3] Implementar servicio de informe en `backend/src/services/costcenters/informes.py`: agregar líneas de la empresa activa con `centro_coste_id` y período, `SUM` de `NUMERIC(18,4)` en `Debe` (coste) / `Haber` (ingreso), clasificación por tipo con grupo PGC (SPEC-001); total por ancestro vía closure `jerarquia_centro`
- [X] T038 [US3] Implementar exportación en `backend/src/services/costcenters/informes.py`: CSV (delimitador `;`) y JSON con importes `Decimal` en 4 decimales (contracts: `/informes/costes/exportar`)
- [X] T039 [US3] Implementar endpoints en `backend/src/api/costcenters/informes.py`: GET informe (query ejercicio/fechas/centro/tipo), GET exportar (format csv|json) — respuestas con precision canónica
- [X] T040 [US3] Crear página frontend `frontend/src/app/informes/costes/page.tsx`: selección de centro (árbol), período, tabla con subtotales por jerarquía y botón exportar
- [X] T041 [US3] Tests integración informe completo: `backend/tests/integration/test_informe_completo.py` — datos reales (asientos + imputaciones), informe de ejercicio completo vs ventana parcial, exportación CSV parseable
- [X] T042 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_informe_tenant.py` — empresa B solicita informe de centro de A o período con imputaciones de A → vacío; agregado de B no incluye líneas de A

**Checkpoint**: User Stories 1, 2 y 3 completas — análisis de costes funcional y aislado.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T043 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_costcenters.py` — todo asiento con imputación tiene Debe==Haber; ninguna línea `POSTED` se edita; `empresa_id` presente en PK/índices de todas las tablas costcenters
- [X] T044 [P] Hardening multi-tenant: `backend/tests/integration/test_costcenters_full_tenant_isolation.py` — escenario completo cross-empresa (árbol A, imputación B, informe A desde B → vacío/404) con dos roles (SPEC-015)
- [X] T045 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_costcenters.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T046 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()`; que ningún endpoint expone `empresa_id` en ruta/body; que los importes de informe son `Decimal`/`NUMERIC`
- [X] T047 Validar inmutabilidad a nivel DB: test que intente `UPDATE`/`DELETE` de `imputacion_centro` o de línea `POSTED` directamente por SQL → rechazo por trigger/constraint
- [X] T048 Limpieza y documentación: docstrings en servicios costcenters, type hints completos, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2 y de US1 (se imputa a centros existentes); puede empezar en paralelo con la parte final de US1 si los modelos de centro están listos.
- **US3 (Phase 5)**: Depende de Phase 4 (necesita imputaciones) para tests de integración completos; el servicio de informe puede esqueleto equivalente tras US1.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1)**: Depende de US1 (los centros existen para imputar) + del motor SPEC-002/006 y de la columna T005.
- **US3 (P2)**: Depende de US2 (datos imputados) para su prueba independiente completa.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T005).
- Phase 2: todos los modelos [P] en paralelo (T006-T010).
- Phase 3: tests [P] en paralelo (T012-T014).
- Phase 4: tests [P] en paralelo (T023-T025).
- Phase 5: tests [P] en paralelo (T034-T036).

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T012: "Test alta y árbol en backend/tests/unit/test_centro_arbol.py"
Task T013: "Test ciclo y duplicados en backend/tests/unit/test_centro_restricciones.py"
Task T014: "Test vínculo subvenciones en backend/tests/unit/test_centro_subvencion.py"

# Servicio CRUD + frontend en paralelo:
Task T015: "CRUD de centros en backend/src/services/costcenters/centros.py"
Task T019: "Árbol de centros en frontend/src/app/centros/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T012-T022. Verificar quickstart Escenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (catálogo jerárquico).
3. + US2 → Test independiente → Deploy/Demo (imputación por apunte).
4. + US3 → Test independiente → Deploy/Demo (informes de costes).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (catálogo y jerarquía).
   - Dev B: User Story 3 (informes) una vez US1 estable — la imputación (US2) depende del motor SPEC-002/006 que puede estar en desarrollo.
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.
- La imputación es dimensión (metadatos) de la línea: nunca modifica Debe/Haber; el balance lo garantiza el motor SPEC-002 en persistencia.

---

## Estado real (implementación 2026-09-22)

SPEC-017 **completa**: 48/48 tareas marcadas y puertas en verde.

### Rutas reales vs. plan (desviaciones documentadas)

- **T005**: `centro_coste_id` se añadió a `JournalEntryLine` en `backend/src/models/acct/journal.py`
  (no existe `models/acct/journal_detail.py`).
- **T009**: migración SQL `backend/migrations/009_costcenters.sql` (no `db/migrations/20260916_017_centros_linea.py`);
  incluye los triggers de inmutabilidad de `imputacion_centro` y de borrado protegido de `centro_coste`.
- **T028**: la dimensión de centro se integra en `backend/src/services/journal/motor.py`
  (`crear_asiento_multilinea`), `validador_multilinea.py` y `entry_service._normalizar_linea`
  (no existe `services/acct/journal_engine.py`).
- **T031**: selector de centro en `frontend/src/components/journal/line-editor.tsx` y
  `frontend/src/app/contabilidad/asientos/nuevo/page.tsx` (y `asientos/nuevo`).
- **T046**: `async_session.begin()` no se usa en servicios; el boundary ACID es `get_db` + `flush()`
  (patrón del proyecto). Ningún endpoint expone `empresa_id` en ruta/body (guard `get_empresa_id`).
- Los tests T043/T047 se apoyan en `sqlalchemy.exc.IntegrityError` (no `Exception`) para los triggers
  SQLite, y el test de inmutabilidad UPDATE/DELETE se dividió en dos tests independientes porque el
  `rollback()` intermedio revierte toda la transacción del `db_session`.

### Otras decisiones

- `subvencion_id` es un UUID libre sin FK ni validación cross-empresa: SPEC-019 no está implementada
  (validación diferida).
- `informes.py`: los `totales` del informe suman importes **directos** (cada apunte una sola vez);
  el `subtotal` por fila sí agrega la jerarquía vía closure. Evita doble conteo de padres.
- SPEC-017 añade el módulo `centros` al catálogo RBAC (SPEC-015): 10→11 módulos y +13 concesiones
  (ADMIN 8 + ACCOUNTANT 4 + READ_ONLY 1); actualizadas las aserciones de recuento en
  `test_matriz_evaluacion.py`, `test_rbac_tenant_models.py` y `test_quickstart_rbac.py`.

### Verificación (puertas)

- pytest: **1055 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky bajo carga, verde aislado).
- `ruff check src tests`: All checks passed.
- `mypy` (`-p api -p models -p services -p database -p base -p db -p main -p config`): limpio (251 fuentes).
- `tsc --noEmit`, `eslint src`: limpios.
- `next build`: **57 rutas** (incluye `/centros`, `/centros/nuevo`, `/informes/costes`).
