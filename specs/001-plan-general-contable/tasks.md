# Tasks: Plan General Contable (SPEC-001)

**Input**: Design documents from `/specs/001-plan-general-contable/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Fuente técnica**: plan.md raíz del repositorio (tabla `account_plan`, triggers, seed, `audit_log`). No reescribir su DDL; alinear nombres (`tenant_id`), tabla y triggers con él.

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble indirecta vía apuntabilidad + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. This feature no maneja importes; el patrón Decimal se hereda para audit (`payload` como cadenas Decimal).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3, US4)
- Incluir ruta exacta del archivo en la descripción

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo `acct` en backend y frontend según plan.md raíz.

- [X] T001 [P] Crear estructura del módulo acct: `backend/src/models/acct/__init__.py`, `backend/src/services/acct/__init__.py`, `backend/src/api/acct/__init__.py`
- [X] T002 [P] Configurar router de cuentas: registrar en `backend/src/api/acct/accounts.py` bajo `/api/v1/accounts` con dependency de sesión y `get_empresa_id()` de `backend/src/api/deps.py`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/cuentas/page.tsx`, `frontend/src/app/cuentas/nueva/page.tsx`, `frontend/src/components/acct/`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/deps.py` con `get_empresa_id()` que extrae la empresa activa del contexto autenticado y bloquea consultas sin ella (403)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelo, DDL y triggers constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `AccountPlan` en `backend/src/models/acct/account_plan.py`: campos id, tenant_id (PK compuesta no explícita: `UNIQUE (tenant_id, id)`), code (VARCHAR(8)), name (VARCHAR(200)), parent_id, level (SMALLINT CHECK 1..5), is_selectable, is_active, created_at/updated_at TIMESTAMPTZ; constraints `UNIQUE (tenant_id, code)` y `UNIQUE (tenant_id, name)`, FK `tenant_id → companies.company_id`
- [X] T006 [P] Crear migración DDL + triggers en `backend/migrations/001_account_plan.sql`: tabla `account_plan` según plan raíz §2, índices multi-tenant `(tenant_id, parent_id)`, `(tenant_id, level, is_selectable)`, `(tenant_id, code)`, `ix_account_plan_name_trgm` GIN (pg_trgm); triggers `chk_account_plan_structure` (§5.a) y `sync_account_plan_selectable` (§5.b)
- [X] T007 [P] Crear migración `audit_log` en `backend/migrations/000_audit_log.sql`: tabla WORM del plan raíz §5.e con índice multi-tenant y trigger de inmutabilidad (UPDATE/DELETE denegados)
- [X] T008 [P] Crear migración de seed en `backend/migrations/002_seed_pgc.sql`: función idempotente `seed_default_pgc(p_tenant_id)` (7 grupos, subgrupos/cuentas/subcuentas de nivel 4 apuntables, entrada `SEED_PGC` en audit_log) y trigger `trg_companies_seed` AFTER INSERT ON companies
- [X] T009 [P] Tests unit de modelo: `backend/tests/unit/test_account_plan_model.py` — unicidad (tenant_id, code) y (tenant_id, name), constrains de level, FKs
- [X] T010 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_pgc_tenant_isolation.py` — crear empresa A y B (seed), verificar que el árbol de A nunca devuelve nodos de B y que el acceso por ID cruzado no filtra datos

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Consultar el árbol de cuentas (Priority: P1) ?? MVP

**Goal**: El contador visualiza el plan de cuentas de su empresa como árbol de hasta 5 niveles; nunca ve cuentas de otras empresas.

**Independent Test**: Visualizando el árbol de la Empresa A se ven solo las cuentas de A jerárquicas; una consulta por ID de cuenta de B es rechazada sin exponer datos.

### Tests for User Story 1

- [X] T011 [P] [US1] Test jerarquía del árbol: `backend/tests/unit/test_arbol_jerarquia.py` — profunda hasta 5 niveles, `level == length(code)`, orden por code, `is_selectable` solo en hojas nivel ≥ 4, cuentas inactivas distinguibles (FR-010)
- [X] T012 [P] [US1] Test aislamiento del árbol: `backend/tests/integration/test_arbol_aislamiento.py` — cargar 2 empresas con cuentas, el árbol y el GET por ID de A no devuelven nunca datos de B (SC-001)

### Implementation for User Story 1

- [X] T013 [US1] Implementar servicio `build_tree()` en `backend/src/services/acct/plan_tree.py`: una sola consulta filtrada por `tenant_id` de sesión ordenada por `code`, construcción del árbol anidado en Python (máx. 5 niveles, sin N+1)
- [X] T014 [US1] Implementar endpoint GET `/api/v1/accounts/tree` en `backend/src/api/acct/accounts.py`: response `{ "nodos": [...] }`; plan vacío → lista vacía sin error; auditoría de lectura no requerida
- [X] T015 [US1] Crear página frontend `frontend/src/app/cuentas/page.tsx`: render del árbol con indicadores visuales de inactiva y apuntable (FR-010), llamada a `frontend/src/services/acct/api.ts`
- [X] T016 [US1] Crear componente frontend `frontend/src/components/acct/PlanTree.tsx`: árbol recursivo con estado abierto/cerrado por nodo y navegación por teclado

**Checkpoint**: User Story 1 completa — público el plan de cuentas de la empresa activa. MVP parcial desplegable.

---

## Phase 4: User Story 2 — Buscar cuentas apuntables (Priority: P1)

**Goal**: Autocompletar por código o nombre mostrando solo cuentas `is_selectable=true` e `is_active=true` de la empresa activa, en < 1 s.

**Independent Test**: Escribiendo un fragmento de código o nombre solo aparecen cuentas seleccionables de la empresa activa; sin coincidencias → lista vacía sin error.

### Tests for User Story 2

- [X] T017 [P] [US2] Test suggest solo apuntables: `backend/tests/unit/test_suggest_apuntables.py` — grupos/subgrupos/cuentas de 1-3 dígitos y cuentas con hijas NUNCA aparecen; hojas nivel ≥ 4 activas sí (FR-003/FR-005)
- [X] T018 [P] [US2] Test suggest sin coincidencias y aislamiento: `backend/tests/integration/test_suggest_aislamiento.py` — texto sin coincidencias → 200 vacío; empresas B con datos coincidentes no se filtran hacia A

### Implementation for User Story 2

- [X] T019 [US2] Implementar servicio `suggest()` en `backend/src/services/acct/account_service.py`: `code` por prefijo (indexado) y `name` por fragmento con pg_trgm; filtro `tenant_id + is_selectable + is_active`, `LIMIT` (máx 50)
- [X] T020 [US2] Implementar endpoint GET `/api/v1/accounts/suggest?q=&limit=` en `backend/src/api/acct/accounts.py` (SC-002 < 1 s)
- [X] T021 [US2] Crear componente frontend `frontend/src/components/acct/AccountAutocomplete.tsx`: combobox de teclado (flechas, tab, enter) que consume suggest con debounce (250 ms en `cuentas/nueva`)
- [X] T022 [US2] Integrar AccountAutocomplete como campo reutilizable para el formulario de asientos (`frontend/src/components/journal/JournalEntryForm.tsx`, consumido por SPEC-002)

**Checkpoint**: User Stories 1 y 2 completas — plan visible y apuntes imputables mediante autocompletar.

---

## Phase 5: User Story 3 — Alta de subcuentas (Priority: P2)

**Goal**: El contador crea subcuentas bajo cuentas existentes con código único por empresa, heredando jerarquía (nivel = padre + 1) y actualizando la apuntabilidad por trigger.

**Independent Test**: Dada de alta una subcuenta aparece bajo su padre y es apuntable (si hoja nivel ≥ 4); las subcuentas de último nivel son las únicas apuntables; duplicados rechazados.

### Tests for User Story 3

- [X] T023 [P] [US3] Test alta correcta: `backend/tests/unit/test_alta_subcuenta.py` — level = padre + 1, prefijo del padre, apuntabilidad de la nueva hoja, madre deja de ser apuntable (SC-005)
- [X] T024 [P] [US3] Test duplicado/estructura: `backend/tests/unit/test_alta_rechazos.py` — código duplicado → 409; nivel 5 con hija → 422; código no numérico / nivel-longitud inconsistente → 422 (FR-004/FR-006)
- [X] T025 [P] [US3] Test aislamiento alta: `backend/tests/integration/test_alta_aislamiento.py` — padre inexistente o de otra empresa → 404/403; el alta nunca referencia datos de otro tenant

### Implementation for User Story 3

- [X] T026 [US3] Implementar servicio `crear_cuenta()` en `backend/src/services/acct/account_service.py`: validar padre (misma empresa, nivel padre < 5), derivar nivel de `length(code)`, insertar dentro de `async with async_session.begin()` y escribir auditoría (CREATE) en la misma transacción
- [X] T027 [US3] Implementar endpoint POST `/api/v1/accounts` en `backend/src/api/acct/accounts.py`: 201 / 409 (duplicado) / 422 (nivel máximo, formato) / 404 (padre) / 403 (padre de otra empresa)
- [X] T028 [US3] Crear página frontend `frontend/src/app/cuentas/nueva/page.tsx`: formulario código + nombre + selector de padre (con AccountAutocomplete restringido a cuentas no-hoja del tenant), aviso de nivel 5 no ampliable
- [X] T029 [US3] Tests de integración de triggers: `backend/tests/integration/test_alta_triggers.py` — insertar una subcuenta por SQL y verificar `is_selectable` de la madre a false (trigger DB, no solo servicio)

**Checkpoint**: User Stories 1, 2 y 3 completas — plan de cuentas ampliable por la empresa.

---

## Phase 6: User Story 4 — Editar nombre y estado de una cuenta (Priority: P2)

**Goal**: Renombrar y activar/desactivar cuentas de la empresa activa respetando la protección de cuentas con asientos asociados.

**Independent Test**: Modificando nombre y estado de una cuenta sin asientos se guardan; desactivar/eliminar una cuenta con imputaciones se bloquea; editar una cuenta de otra empresa se rechaza.

### Tests for User Story 4

- [X] T030 [P] [US4] Test edición correcta: `backend/tests/unit/test_editar_cuenta.py` — renombrar y activar/desactivar una cuenta sin movimientos persiste (FR-007); nombre duplicado → 409
- [X] T031 [P] [US4] Test protección: `backend/tests/unit/test_proteccion_cuenta_movimiento.py` — desactivar cuenta con imputaciones → 409 y EXCEPTION DB (trigger `chk_account_plan_protected`); borrado de cuenta con hijas → rechazado (FR-008/SC-004)
- [X] T032 [P] [US4] Test aislamiento edición: `backend/tests/integration/test_editar_aislamiento.py` — PATCH sobre cuenta de otra empresa → 404 sin exponer datos

### Implementation for User Story 4

- [X] T033 [US4] Implementar servicio `actualizar_cuenta()` en `backend/src/services/acct/account_service.py`: validar pertenencia al tenant, aplicar PATCH (name/is_active) dentro de `async with async_session.begin()`, escribir auditoría (UPDATE) en la misma transacción; propagar los EXCEPTION de protección del trigger como 409 amigable
- [X] T034 [US4] Implementar endpoint PATCH `/api/v1/accounts/{id}` en `backend/src/api/acct/accounts.py`: 200 / 404 / 409 (protección, nombre duplicado)
- [X] T035 [US4] Crear componente frontend `frontend/src/components/acct/AccountEdit.tsx`: modal/inline de edición con aviso de protección y estado visual
- [X] T036 [US4] Tests de integración de protección: `backend/tests/integration/test_proteccion_integracion.py` — insertar `journal_entry_line` (SPEC-002) y verificar que el PATCH de desactivación falla con 409 y el estado queda intacto

**Checkpoint**: User Stories 1, 2, 3 y 4 completas — gestión completa del plan de cuentas.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez (constitución V).

- [X] T037 [P] Validar constitución V en los flujos del plan: `backend/tests/unit/test_constitucion_pgc.py` — verificar apuntabilidad (solo hojas nivel ≥ 4) y aislamiento `tenant_id` en tree/suggest/alta/edición; verificar que ninguna operación dependa de datos del body para el tenant
- [X] T038 [P] Hardening multi-tenant: `backend/tests/integration/test_pgc_cross_tenant_full.py` — escenario completo cross-empresa (A consulta/sugiere/crea/edita sobre IDs de B → todos 404/403)
- [X] T039 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_pgc.py` — reproducir los 5 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T040 [P] Performance suggest: `backend/tests/integration/test_suggest_perf.py` — con ~10k cuentas sembradas, `suggest?q=…` responde < 1 s p95 (SC-002); el árbol < 500 ms
- [X] T041 [P] Code review: verificar que `crear_cuenta`/`actualizar_cuenta` usan `async with async_session.begin()`; que ningún endpoint acepta `tenant_id` en path/body; que el `payload` de auditoría serializa importes como cadenas Decimal (si aparecieran); que `deps.py` extrae la empresa solo de la sesión
- [X] T042 Limpieza y documentación: actualizar docstrings en servicios acct, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1 (usa `AccountPlan` de Phase 2).
- **US3 (Phase 5)**: Depende de Phase 2; puede empezar en paralelo con US1/US2.
- **US4 (Phase 6)**: Depende de Phase 2 y de la existencia de `journal_entry_line` (SPEC-002) para la prueba de protección; se puede empezar en paralelo salvo T036.
- **Polish (Phase 7)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US3 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa.
- **US4 (P2)**: Sin dependencias de US1-US3; la prueba de integración T036 requiere que exista `journal_entry_line` (SPEC-002) con sus triggers.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos/migraciones [P] en paralelo (T005-T009).
- Phase 3: tests [P] en paralelo (T011-T012), y frontend [P] parcialmente con el endpoint.
- Phase 4: tests [P] en paralelo (T017-T018).
- Phase 5: tests [P] en paralelo (T023-T025).
- Phase 6: tests [P] en paralelo (T030-T032).
- US1, US2, US3, US4 pueden iniciarse en paralelo una vez completada Phase 2 (salvo T036).

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T011: "Test jerarquía en backend/tests/unit/test_arbol_jerarquia.py"
Task T012: "Test aislamiento en backend/tests/integration/test_arbol_aislamiento.py"

# Servicio y endpoint en paralelo (archivos distintos):
Task T013: "plan_tree.py' (servicio build_tree)"
Task T014: "accounts.py (endpoint GET tree)"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo; incluye seed y triggers).
3. Completar Phase 3: User Story 1 (árbol).
4. Completar Phase 4: User Story 2 (suggest).
5. **PARAR y VALIDAR**: Ejecutar T011-T022. Verificar quickstart Scenarios 1 y 2.
6. Desplegar/demo si listo (plan visible + autocompletar para futuros asientos).

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (árbol).
3. + US2 → Test independiente → Deploy/Demo (autocompletar; requisito de SPEC-002).
4. + US3 → Test independiente → Deploy/Demo (alta de subcuentas).
5. + US4 → Test independiente → Deploy/Demo (edición/protección).
6. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (árbol) y User Story 2 (suggest).
   - Dev B: User Story 3 (alta de subcuentas).
   - Dev C: User Story 4 (edición/protección).
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Los artefactos de esta feature se alinean con el plan raíz: tabla `account_plan`, `tenant_id`, triggers (§5) y seed (§4); NO reescribir el DDL.
- El modelo usa `tenant_id` (naming del plan raíz); en SPEC-002-004 se usa `empresa_id` (equivalente).
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de aislamiento multi-tenant (+ jerarquía/apuntabilidad en esta feature).

## Estado real (auditoría 2026-09-18)

Código creado como soporte de SPEC-020; las tareas siguen **sin marcar `[X]`** porque sus pruebas de la Constitución V están pendientes.

- **Implementado**: T001 (estructura `acct`), T002 (router `/api/v1/accounts` con `get_empresa_id`), T004 (`api/deps.py`), T005 (modelo `AccountPlan`), T006 (`001_account_plan.sql`), T007 (`000_audit_log.sql`), T008 (`002_seed_pgc.sql`), T013 (`build_tree`), T014 (`GET /accounts/tree`).
- **Desviación**: se omite `UNIQUE (tenant_id, name)` (los nombres del PGC se repiten entre niveles: `Proveedores` 40/400, `Clientes` 43/430, `Caja` 58/570).
- **Verificado**: migraciones aplicadas sobre PostgreSQL 16.4; seed 7/28/22/16 sin huérfanos; triggers de estructura/apuntabilidad/protección; `test_db_immutability`, `test_migrations`, `test_pg_schema`.
- **Completado (2026-09-18)**: T009 (`test_account_plan_model.py` - 10 tests), T010 (`test_pgc_tenant_isolation.py` - 8 tests), T011 (`test_arbol_jerarquia.py` - 8 tests), T012 (`test_arbol_aislamiento.py` - 8 tests), T017 (`test_suggest_apuntables.py` - 5 tests), T018 (`test_suggest_aislamiento.py` - 10 tests), T023 (`test_alta_subcuenta.py` - 7 tests), T024 (`test_alta_rechazos.py` - 10 tests), T025 (`test_alta_aislamiento.py` - 7 tests), T029 (`test_alta_triggers.py` - 6 tests), T030 (`test_editar_cuenta.py` - 7 tests), T031 (`test_proteccion_cuenta_movimiento.py` - 6 tests), T032 (`test_editar_aislamiento.py` - 6 tests) — todos pasan, validan unicidad, FKs, constraints, jerarquía, selectable, inactivas, suggest, alta, edición (renombrar, activar/desactivar, protección, rechazo duplicados), triggers DB (selectable, protección), aislamiento multi-tenant completo.
- **Completado frontend (2026-09-18)**: T003 (estructura `app/cuentas/page.tsx`, `app/cuentas/nueva/page.tsx`, `components/acct/`), T015 (`cuentas/page.tsx` con indicadores inactiva/apuntable FR-010 vía `services/acct/api.ts`), T016 (`PlanTree.tsx` recursivo con abierto/cerrado por nodo y teclado Enter/Espacio/Flechas; fix setState-en-render → `useEffect`, `aria-selected`, tipos `CuentaSugerida` en `nueva/page.tsx`), T035 (`AccountEdit.tsx` inline con nombre/activa, badge de estado, aviso de protección 409, errores 404/409 y callbacks `onGuardado`/`onCancelar` vía `actualizarCuenta`). Puertas: `tsc --noEmit` limpio, `eslint src` 0 errores, `next build` 10 rutas (incluye `/cuentas`, `/cuentas/nueva`).
- **Desviación doc**: T015 cita `services/client.ts`; se usa `services/acct/api.ts` (resuelve parcial G4 para `acct`; el cliente de tesorería sigue en `components/treasury/api.ts`).
- **Completado Phase 7 (2026-09-18)**: T037 (`test_constitucion_pgc.py` - 7 tests: apuntabilidad en tree/suggest/alta, edición sin `is_selectable`, `tenant_id` explícito en servicios, schemas sin tenant en body, aislamiento en flujos), T038 (`test_pgc_cross_tenant_full.py` - 2 tests: flujo consulta/detalle/suggest/alta/edición A→B y B→A, todo 404), T039 (`test_quickstart_pgc.py` - 5 tests: seed+árbol, suggest, alta, edición+protección, aislamiento). Suite total: 280 passed, 3 skipped; ruff + mypy limpios; frontend `tsc`/`eslint` limpios, `next build` 10 rutas.
- **Barrido de marcas (2026-09-18)**: verificados fichero a fichero y marcados `[X]` T001, T002, T004, T005, T006, T007, T008, T013, T014, T019, T020, T021 (debounce 250 ms añadido en `cuentas/nueva`), T026, T027, T028, T033, T034. Desviaciones doc: T019 cita `services/acct/suggest.py`, el servicio vive en `services/acct/account_service.py`; T015 cita `services/client.ts`, se usa `services/acct/api.ts`.
- **Completado cierre (2026-09-18)**: T041 (code review con desviación documentada: sin `async with begin()` en servicios; el boundary ACID es `get_db` commit-al-final/rollback-ante-excepción — equivalente sancionado en AGENTS.md §3; servicios hacen `flush()` + auditoría en la misma sesión/transacción. Verificado: 5/5 endpoints con empresa solo vía `Depends(get_empresa_id)`; schemas sin tenant; `registrar_auditoria` con `json.dumps(default=str)` → Decimal como cadena, nunca float; `get_empresa_id` deriva de cabecera + valida contra `user_companies`, nunca del body). T042 (docstrings + type hints de `services/acct` verificados sin cambios necesarios; puertas: pytest 280+3, ruff + mypy limpios, `tsc`/`eslint` limpios).
- **Pendiente**: T022 `JournalEntryForm` (pertenece a SPEC-002); T036 integración protección (requiere SPEC-002 `journal_entry_line`); T040 perf (~10k cuentas).

## Estado real (implementación 2026-09-19, 42/42)

- T022: creado `frontend/src/components/journal/JournalEntryForm.tsx` (líneas Debe/Haber con `AccountAutocomplete`, balance informativo, teclado); consumible por las páginas de SPEC-002.
- T036: `test_proteccion_integracion.py` — asiento POSTED vía HTTP + PATCH desactivar → 409, cuenta intacta.
- T040: `test_suggest_perf.py` — ~10k cuentas (1.111 niveles 1-4 + 9.000 nivel 5); suggest p95 < 1 s, árbol < 500 ms.
- Puertas: suite global verde, ruff + mypy limpios, `next build` 16 rutas (incl. `/informes/*`, `/cierre`).
