# Tasks: Plantillas de Asientos (SPEC-018)

**Input**: Design documents from `/specs/018-plantillas-asientos/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Trazabilidad FR ↔ User Story

| Requisito | Descripción breve | User Story |
|---|---|---|
| FR-001 | Crear plantillas por empresa con apuntes predefinidos | US1 |
| FR-002 | Admitir importes fijos y variables en líneas | US1 |
| FR-003 | Generar asiento balanceado y dentro del ejercicio | US2 |
| FR-004 | Validar cuentas contra plan antes de generar | US2 |
| FR-005 | Impedir generación si no cuadra o faltan variables | US2 |
| FR-006 | Conservar asientos generados inmutables ante cambios | US3 |
| FR-007 | Aislar plantillas por empresa y respetar permisos | US1 |
| FR-008 | Cumplir constitución en flujo completo | US2 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo `templates` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo templates: `backend/src/models/templates/__init__.py`, `backend/src/services/templates/__init__.py`, `backend/src/api/templates/__init__.py`
- [X] T002 [P] Configurar router templates: registrar prefijo `/api/v1` en `backend/src/api/templates/__init__.py` con dependency de sesión autenticada y cabecera de empresa activa
- [X] T003 [P] Crear utils de sesión: `backend/src/api/templates/deps.py` con `get_empresa_activa()` que extrae el `empresa_id` de la sesión y bloquea acceso cross-tenant
- [X] T004 [P] Crear estructura frontend: `frontend/src/app/plantillas/`, `frontend/src/components/templates/`, y cliente HTTP reutilizando `frontend/src/services/client.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `PlantillaAsiento` en `backend/src/models/templates/plantilla.py`: empresa_id (PK compuesta), id, nombre único por empresa, descripcion NULL, categoria NULL, version_actual INT, estado ENUM(activa/inactiva), created_at, updated_at; constraint unicidad (empresa_id, nombre)
- [X] T006 [P] Crear modelo `VariablePlantilla` en `backend/src/models/templates/variable.py`: empresa_id PK compuesta, id, plantilla_id FK compuesta, nombre, tipo ENUM(importe), es_requerida BOOLEAN; nombre único por plantilla
- [X] T007 [P] Crear modelo `LineaPlantilla` en `backend/src/models/templates/linea.py`: empresa_id PK compuesta, id, plantilla_id FK, orden SMALLINT, cuenta_id FK a plan (misma empresa), posicion ENUM(debe/haber), importe_fijo NUMERIC(18,4) NULL, variable_id FK NULL; CHECK excluyente fijo/variable (decisión D1)
- [X] T008 [P] Crear modelo `AsientoGenerado` en `backend/src/models/templates/asiento_generado.py`: empresa_id PK, asiento_id PK, plantilla_id FK, version_plantilla INT, variables_aportadas JSONB (Decimal como string), fecha_generacion, usuario_generador; inmutable (sin UPDATE/DELETE)
- [X] T009 [P] Tests de modelos fundacionales: `backend/tests/unit/test_template_models.py` — unicidad (empresa_id, nombre), CHECK fijo/variable excluyente, FK compuesta cross-tenant imposible
- [X] T010 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_template_tenant_isolation.py` — crear plantilla en empresa A, verificar que B no la ve; FK compuesta con empresa B → error

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Crear una plantilla reutilizable (Priority: P1) ?? MVP — cubre FR-001, FR-002, FR-007

**Goal**: El contador crea una plantilla de asiento con apuntes predefinidos, con importes fijos y variables listos para la generación.

**Independent Test**: Creando una plantilla con importes fijos y variables, queda guardada para la empresa activa y lista para generar asientos.

### Tests for User Story 1

- [X] T011 [P] [US1] Test alta con fijos/variables: `backend/tests/unit/test_plantilla_alta.py` — crear plantilla con línea fija y línea variable; verificar persistencia y `version_actual=1`
- [X] T012 [P] [US1] Test restricciones de línea: `backend/tests/unit/test_plantilla_lineas.py` — línea con fijo y variable a la vez → 422; variable no declarada → 422; cuenta inexistente en el plan → 422; nombre duplicado → 409

### Implementation for User Story 1

- [X] T013 [US1] Implementar CRUD de plantillas en `backend/src/services/templates/plantillas.py`: crear (con líneas y variables en la misma transacción ACID), listar (paginado + filtros), detalle, editar (incrementando `version_actual`), activar/inactivar; validación de líneas (D1) y cuentas contra el plan (SPEC-001); audit log
- [X] T014 [US1] Implementar activación/inactivación en `backend/src/services/templates/plantillas.py`: `activar`/`inactivar` con transición de estado; la `inactiva` bloquea la generación (D6); sin borrado físico con `AsientoGenerado`
- [X] T015 [US1] Implementar endpoints en `backend/src/api/templates/plantillas.py`: POST crear (201), GET listar (paginado), GET detalle, PATCH editar, POST activar, POST inactivar (ver contracts/api-contracts.md)
- [X] T016 [US1] Crear página frontend `frontend/src/app/plantillas/page.tsx`: listado de plantillas con filtros y enlaces a detalle/creación
- [X] T017 [US1] Crear página frontend `frontend/src/app/plantillas/nueva/page.tsx`: editor de líneas (cuenta autocompletada del plan, posición, importe fijo o variable) y definición de variables
- [X] T018 [US1] Tests integración alta completa: `backend/tests/integration/test_plantilla_alta_integration.py` — crear plantilla completa, verificar líneas/variables persistidas, detalle consultable, edición con `version_actual=2`
- [X] T019 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_plantilla_tenant.py` — empresa A crea plantilla, B no la ve en listado/detalle; intento de editar desde B → 404

**Checkpoint**: User Story 1 completa — catálogo de plantillas funcional y aislado.

---

## Phase 4: User Story 2 — Generar un asiento desde la plantilla (Priority: P2) — cubre FR-003, FR-004, FR-005, FR-008

**Goal**: El usuario elige plantilla, completa variables y fecha, y el sistema genera el asiento de la empresa activa dentro de las reglas del motor (SPEC-002): balance estricto, ejercicio válido y multiplicidad de líneas.

**Independent Test**: Generando un asiento con la plantilla, el resultado es balanceado, en la empresa activa y en el ejercicio correcto.

### Tests for User Story 2

- [X] T020 [P] [US2] Test balance de generación: `backend/tests/unit/test_generacion_balance.py` — resolver plantilla con variables y verificar Debe==Haber con precisión `Decimal`; plantilla que no cuadra → rechazo 409 del motor
- [X] T021 [P] [US2] Test variables: `backend/tests/unit/test_generacion_variables.py` — variable faltante → 422 con listado; valor no numérico → 422; variable `es_requerida=false` vacía → línea omitida
- [X] T022 [P] [US2] Test cuentas y ejercicio: `backend/tests/unit/test_generacion_cuenta_plan.py` — cuenta inexistente/inactiva en el plan → 422; `fecha_asiento` en ejercicio cerrado → 409 (SPEC-004); fecha fuera del rango → 422

### Implementation for User Story 2

- [X] T023 [US2] Implementar servicio de generación en `backend/src/services/templates/generacion.py`: `generar_asiento(plantilla_id, fecha, variables)` — validar plantilla `activa`, resolver cada línea (fija/usar variable), validar cuentas contra el plan, comprobar variables requeridas; construir el borrador del asiento multilínea
- [X] T024 [US2] Integrar con motor SPEC-002/006 en `backend/src/services/templates/generacion.py`: entregar el borrador al `crear_asiento_multilinea`, que persiste asiento+lineas, asigna número correlativo, valida balance y auditoría
- [X] T025 [US2] Persistir `AsientoGenerado` en `backend/src/services/templates/generacion.py`: registrar plantilla_id, version_plantilla, variables_aportadas (Decimal string) en la misma transacción ACID del asiento (D8)
- [X] T026 [US2] Implementar endpoints en `backend/src/api/templates/plantillas.py`: POST `{id}/generar` (201 con asiento generado), GET `{id}/generados` (paginado, con version y fecha)
- [X] T027 [US2] Crear página frontend `frontend/src/app/plantillas/[id]/generar/page.tsx`: formulario con fecha y campos por variable (numéricos, atajo de teclado), vista previa de líneas resueltas, confirmación antes de generar (UX optimizada por teclado, constitución)
- [X] T028 [US2] Tests integración generación completa: `backend/tests/integration/test_generacion_completa.py` — crear plantilla mixta, generar, verificar asiento `POSTED` balanceado con todas las líneas, número correlativo correcto, `AsientoGenerado` con version y variables; intentos de 409/422
- [X] T029 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_generacion_tenant.py` — empresa A genera; empresa B intenta generar desde la plantilla de A o ver su `AsientoGenerado` → 404; numeración de B no se ve afectada

**Checkpoint**: User Stories 1 y 2 completas — generación de asientos balanceados desde plantilla.

---

## Phase 5: User Story 3 — Gestionar plantillas (edición, activación, versiones) (Priority: P2) — cubre FR-006

**Goal**: El contador edita, activa o desactiva plantillas. Los asientos generados conservan la fecha de generación y no cambian retroactivamente si la plantilla se edita.

**Independent Test**: Editando una plantilla, los asientos generados antes conservan sus datos originales.

### Tests for User Story 3

- [X] T030 [P] [US3] Test inmutabilidad frente a edición: `backend/tests/unit/test_plantilla_edicion_inmutable.py` — editar plantilla (cambiar importe fijo), verificar que el asiento generado anterior conserva sus líneas originales y `version_plantilla` antigua
- [X] T031 [P] [US3] Test activación/desactivación: `backend/tests/unit/test_plantilla_estado.py` — inactivar bloquea generación 409; reactivar permite; borrado físico de plantilla con `AsientoGenerado` → error de integridad (D6)

### Implementation for User Story 3

- [X] T032 [US3] Consolidar gestión de versiones en `backend/src/services/templates/plantillas.py`: `editar_plantilla` incrementa `version_actual` y mantiene `AsientoGenerado` intacto (sin tocar diario); listado `generados` con `version_plantilla` y `fecha_generacion`
- [X] T033 [US3] Asegurar protección de borrado en `backend/src/models/templates/` + migración: FK `asiento_generado.plantilla_id` sin cascada; prueba de DB que impide `DELETE` de plantilla con generados (constraint)
- [X] T034 [US3] Mejorar página frontend `frontend/src/app/plantillas/[id]/page.tsx`: sección de detalle con asientos generados (versión y fecha), botones activar/inactivar e indicador de versiones
- [X] T035 [US3] Tests integración gestión completa: `backend/tests/integration/test_plantilla_gestion_integration.py` — editar entre dos generaciones, verificar versiones distintas y asientos inmutables; inactivar/reactivar y re-generar; intento de DELETE → rechazo
- [X] T036 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_plantilla_gestion_tenant.py` — empresa B intenta editar/activar/inactivar plantilla de A → 404; lista de generados de B no contiene los de A

**Checkpoint**: User Stories 1, 2 y 3 completas — ciclo de vida de plantillas funcional y seguro.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T037 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_templates.py` — todo asiento generado tiene Debe==Haber (backend); ningún `AsientoGenerado`/línea `POSTED` se edita; `empresa_id` presente en PK/índices de todas las tablas templates
- [X] T038 [P] Hardening multi-tenant: `backend/tests/integration/test_templates_full_tenant_isolation.py` — escenario completo cross-empresa (plantilla A, generación B, edición A desde B → 404)
- [X] T039 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_templates.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T040 [P] Code review: verificar `async with async_session.begin()` en todos los servicios; que ningún endpoint expone `empresa_id` en ruta/body; que `variables_aportadas` y asientos usan `Decimal`; que la generación delega en `journal_engine`
- [X] T041 Validar número correlativo del generado: `backend/tests/integration/test_correlatividad_plantillas.py` — generar 3 asientos en el mismo ejercicio desde plantillas, verificar correlatividad sin saltos; ejercicio distinto → secuencia independiente
- [X] T042 Limpieza y documentación: docstrings en servicios templates, type hints completos, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 3 (necesita plantillas para generar) y del motor SPEC-002/006 operativo.
- **US3 (Phase 5)**: Depende de Phase 3; las pruebas de inmutabilidad frente a edición requieren Phase 4 (generaciones hechas).
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Depende de US1 (la plantilla existe) y del motor de asientos (SPEC-002/006).
- **US3 (P2)**: Depende de US1 para gestión; de US2 para verificar la inmutabilidad de lo generado.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T009).
- Phase 3: tests [P] en paralelo (T011-T012), y T013/T016 (service + frontend).
- Phase 4: tests [P] en paralelo (T020-T022), y T023/T027 (service + frontend).
- Phase 5: tests [P] en paralelo (T030-T031).

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T011: "Test alta con fijos/variables en backend/tests/unit/test_plantilla_alta.py"
Task T012: "Test restricciones de línea en backend/tests/unit/test_plantilla_lineas.py"

# Servicio CRUD y editor frontend en paralelo:
Task T013: "CRUD de plantillas en backend/src/services/templates/plantillas.py"
Task T017: "Editor de líneas en frontend/src/app/plantillas/nueva/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T011-T019. Verificar quickstart Escenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (creación de plantillas).
3. + US2 → Test independiente → Deploy/Demo (generación de asientos balanceados).
4. + US3 → Test independiente → Deploy/Demo (gestión y versiones).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (CRUD de plantillas + editor).
   - Dev B: User Story 2 (generación) en cuanto el motor SPEC-002/006 esté disponible.
3. Cada story se integra y prueba independientemente.
4. Polish al final.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.
- La generación delega en el motor (SPEC-002/006): balance, ejercicios, numeración y auditoría son del motor; el servicio de plantillas solo resuelve variables y valida cuentas (decisiones D2/D3).
---

## Estado real (implementación 2026-09-22)

SPEC-018 cerrada (42/42). Total del proyecto: 900/1.384 (19 specs).

- **Modelos** `models/templates/`: `plantilla.py` (`PlantillaAsiento`, UNIQUE
  `(empresa_id, id)` y `(empresa_id, nombre)`, estado `activa|inactiva`,
  `version_actual`), `variable.py` (`VariablePlantilla`, tipo `importe`),
  `linea.py` (`LineaPlantilla`, CHECK fijo/variable excluyente, FK compuesta a
  cuenta del plan) y `asiento_generado.py` (traza inmutable, PK
  `(empresa_id, asiento_id)`, `variables_aportadas` JSON).
- **Servicios** `services/templates/`: `errores.py` (`TemplateError` con
  `code`/`message`/`status_code`), `plantillas.py` (`crear_plantilla`,
  `actualizar_plantilla` con incremento de version, `cambiar_estado`,
  `detalle_plantilla`, `listar_plantillas`; valida D1 y contra el plan
  SPEC-001) y `generacion.py` (`generar_asiento` resuelve variables por id o
  nombre, omite variables opcionales vacias y delega en el motor
  `crear_asiento_multilinea` de SPEC-002/006; `listar_generados`).
- **API** `api/templates/` (`plantillas.py` + `deps.py` + `__init__.py`):
  `POST/GET /api/v1/plantillas`, `GET/PATCH /api/v1/plantillas/{id}`,
  `POST .../{id}/activar|inactivar|generar`, `GET .../{id}/generados`.
  `empresa_id` siempre via `Depends(get_empresa_id)`; guards
  `require_permission` del modulo `treasury`.
- **Migracion** `backend/migrations/010_templates.sql` (registrada en
  `ORDEN_PREFERENTE` y en `test_migrations.ESPERADAS`): tablas + enums +
  triggers `asiento_generado` append-only y `plantilla_asiento` sin borrado con
  generados. Triggers SQLite equivalentes en `db/triggers.py`.
- **Frontend**: `components/templates/{api.ts,TemplateEditor.tsx}`,
  `app/plantillas/{page,nueva,[id],[id]/generar}`.
- **Tests (54, 51 nuevos)**: unit (`test_template_models`, `test_plantilla_alta`,
  `test_plantilla_lineas`, `test_generacion_balance`, `test_generacion_variables`,
  `test_generacion_cuenta_plan`, `test_plantilla_edicion_inmutable`,
  `test_plantilla_estado`, `test_constitucion_templates`) e integracion
  (`test_template_tenant_isolation`, `test_plantilla_alta_integration`,
  `test_plantilla_tenant`, `test_generacion_completa`, `test_generacion_tenant`,
  `test_plantilla_gestion_integration`, `test_plantilla_gestion_tenant`,
  `test_templates_full_tenant_isolation`, `test_quickstart_templates`,
  `test_correlatividad_plantillas`). Fixture `templates_client` en
  `tests/conftest.py`.
- **Lecciones reutilizables**:
  - En `actualizar_plantilla` hay que `flush()` tras reinsertar las variables y
    antes de insertar las lineas; si no, la FK compuesta de `linea_plantilla`
    falla en SQLite.
  - `obtener_asiento` y los binds de columnas `Uuid` exigen `uuid.UUID(...)` (un
    `str` revienta con `'str' object has no attribute 'hex'`).
  - Las paginas dinamicas Next.js 15 deben leer `params` con
    `useParams<{ id: string }>()`; la firma `{ params }` como objeto rompe
    `next build` (`PageProps` espera una Promise).
  - Borrar una plantilla sin generados obliga a borrar antes lineas y variables
    (FK), y a desactivar el borrado fisico cuando hay `AsientoGenerado`.
- **Desviaciones**: los guards usan el modulo `treasury` del catalogo (no se
  anadio un modulo `templates`); la generacion delega en
  `crear_asiento_multilinea` (SPEC-006) en vez de `journal_engine` nominal; el
  frontend de creacion cubre editor de lineas/variables y el de generacion
  incluye vista previa y confirmacion.
- **Verificacion**: pytest **1109 passed / 5 skipped** en SQLite
  (`test_suggest_perf` flaky bajo carga, verde aislado), ruff + mypy limpios
  (263 fuentes), `tsc` + `eslint` + `next build` **61 rutas**. Migracion 010
  aplicada sobre PostgreSQL 16.4 real y 5 tests opt-in en verde.