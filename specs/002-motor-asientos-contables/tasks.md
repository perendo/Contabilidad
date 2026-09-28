# Tasks: Motor de Asientos Contables (SPEC-002)

**Input**: Design documents from `/specs/002-motor-asientos-contables/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (balance estricto + aislamiento multi-tenant + inmutabilidad).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo `journal` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo journal: `backend/src/models/acct/__init__.py` (ampliar), `backend/src/services/journal/__init__.py`, `backend/src/api/journal/__init__.py`
- [X] T002 [P] Configurar router journal: registrar en `backend/src/api/journal/journal.py` bajo `/api/v1/journal` con dependency de sesión autenticada `get_empresa_id()` de `backend/src/api/deps.py`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/asientos/`, `frontend/src/app/asientos/nuevo/`, `frontend/src/app/asientos/diario/`, `frontend/src/app/asientos/[id]/`, `frontend/src/components/journal/`
- [X] T004 [P] Crear utils de precisión decimal: `backend/src/services/journal/money.py` — normalización a 4 decimales con `Decimal` (contexto de alta precisión, `ROUND_HALF_EVEN`), `as_decimal_str()` para payloads de auditoría; prohibido `float`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `JournalEntry` en `backend/src/models/acct/journal_entry.py`: cabecera con empresa_id (PK compuesta `UNIQUE (empresa_id, id)`), numero BIGINT NULL, ejercicio INT, fecha, concepto, estado (DRAFT/POSTED/CANCELLED), tipo (GENERAL/REVERSAL), reversal_of_id FK self compuesta, created_by/created_at/updated_at; `UNIQUE (empresa_id, ejercicio, numero)`
- [X] T006 [P] Crear modelo `JournalEntryLine` en `backend/src/models/acct/journal_entry_line.py`: empresa_id, entry_id FK compuesta → journal_entry, line_no, account_id FK compuesta → account_plan(tenant_id, id), debit/credit NUMERIC(18,4) DEFAULT 0, detail; CHECK solo Debe o solo Haber y no nulos
- [X] T007 [P] Crear migración DDL + triggers en `backend/migrations/003_journal.sql`: tablas `journal_entry`/`journal_entry_line`, FK compuestas multi-tenant, índice `(empresa_id, fecha, numero)`, trigger `chk_journal_entry_balance` (suma Debe == suma Haber en cualquier mutación), triggers de **inmutabilidad** (prohíben UPDATE/DELETE de `POSTED`/`CANCELLED` y sus líneas), trigger `chk_journal_line_account_selectable` (plan raíz §5.d: cuenta de la misma empresa, apuntable y activa)
- [X] T008 [P] Implementar util `next_numero()` en `backend/src/services/journal/sequence.py`: contador por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE` dentro de la transacción del asentado; números no reutilizados tras rollback
- [X] T009 [P] Implementar util de auditoría `audit_escribir()` en `backend/src/services/audit/writer.py`: insertar `audit_log` (empresa_id, actor, action, entity, entity_id, ip, payload JSONB con importes como strings Decimal) en la misma sesión/transacción
- [X] T010 [P] Tests unit de modelos: `backend/tests/unit/test_journal_models.py` — `UNIQUE (empresa_id, ejercicio, numero)`, CHECK de lineas (Debe XOR Haber), FK compuestas
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_journal_tenant_isolation.py` — crear asiento en empresa A, verificar que empresa B no lo ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Registrar un asiento contable (Priority: P1) ?? MVP

**Goal**: Crear y asentar asientos balanceados con líneas sobre cuentas apuntables de la empresa activa; partida doble estricta, atomicidad cabecera+líneas y numeración correlativa.

**Independent Test**: Registrando un asiento balanceado se persiste con número secuencial; un asiento desbalanceado se rechaza sin dejar rastro parcial.

### Tests for User Story 1

- [X] T012 [P] [US1] Test balance estricto: `backend/tests/unit/test_balance_estricto.py` — desbalanceado → 422; aceptado solo con sumas exactas (4 decimales); con >4 decimales → normalización canónica y validación sobre canónico; líneas malformadas (Debe==Haber nulos) → 422 (FR-002/FR-006)
- [X] T013 [P] [US1] Test cuentas no apuntables: `backend/tests/unit/test_cuenta_no_apuntable.py` — línea a cuenta de 1-3 dígitos, inactiva, inexistente o de otra empresa → 422/404 (FR-003)
- [X] T014 [P] [US1] Test atomicidad: `backend/tests/integration/test_atomicidad_cabecera_lineas.py` — si una línea falla, no queda cabecera huérfana ni líneas parciales (FR-004)
- [X] T015 [P] [US1] Test correlatividad: `backend/tests/unit/test_correlatividad_asiento.py` — asentar 3 asientos → números 1,2,3 sin saltos; ejercicio distinto → secuencia independiente (FR-005/SC-006)

### Implementation for User Story 1

- [X] T016 [US1] Implementar servicio `crear_borrador()` en `backend/src/services/journal/entry_service.py`: validar fecha→ejercicio (existente, no cerrado), mínimo 2 líneas (Debe y Haber), balance con `Decimal`, cuentas apuntables/activas de la empresa; insertar cabecera DRAFT + líneas y auditoría CREATE en `async with async_session.begin()`
- [X] T017 [US1] Implementar servicio `asentar()` en `backend/src/services/journal/entry_service.py`: re-validar balance/cuentas/ejercicio, `next_numero()` (SELECT FOR UPDATE) en la misma transacción, estado → POSTED, auditoría POSTED
- [X] T018 [US1] Implementar endpoints en `backend/src/api/journal/journal.py`: POST `/api/v1/journal/entries` (201) y POST `/api/v1/journal/entries/{id}/post` (200/409/400/404)
- [X] T019 [US1] Crear página frontend `frontend/src/app/asientos/nuevo/page.tsx`: formulario de asiento con `JournalEntryForm` (fecha, concepto, líneas Debe/Haber con AccountAutocomplete de SPEC-001); balance informativo en UI (nunca autoritativo)
- [X] T020 [US1] Crear componente frontend `frontend/src/components/journal/JournalEntryForm.tsx`: entrada optimizada al teclado (tab/enter/flechas, atajos) con resumen Debe/Haber
- [X] T021 [US1] Tests integración asiento completo: `backend/tests/integration/test_asiento_completo.py` — crear + asentar, verificar número correlativo, balance en DB, entradas de auditoría CREATE/POSTED en la misma transacción
- [X] T022 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_asiento_aislamiento.py` — asiento B no visible/asentable por A (404); líneas con cuenta de B → 403/422

**Checkpoint**: User Story 1 completa — registro de asientos del diario con partida doble garantizada. MVP desplegable.

---

## Phase 4: User Story 2 — Consultar el libro diario (Priority: P1)

**Goal**: Libro diario paginado por rango de fechas de la empresa activa, orden cronológico; solo asientos de la empresa.

**Independent Test**: Consultando el libro diario con fechas y página se obtienen solo los asientos de la empresa activa en el rango, ordenados.

### Tests for User Story 2

- [X] T023 [P] [US2] Test paginación y orden: `backend/tests/unit/test_libro_diario_paginacion.py` — 45 asientos → páginas de 20 sin saltos; orden (fecha, numero) asc (FR-007)
- [X] T024 [P] [US2] Test aislamiento libro diario: `backend/tests/integration/test_libro_diario_aislamiento.py` — asientos de B en el mismo rango no aparecen en A (SC-002)

### Implementation for User Story 2

- [X] T025 [US2] Implementar servicio `consultar_diario()` en `backend/src/services/journal/journal_query.py`: filtro obligatorio `date_from/date_to` + `empresa_id` de sesión, paginación (total + page), solo POSTED/CANCELLED, orden `(fecha, numero)`
- [X] T026 [US2] Implementar endpoint GET `/api/v1/journal/entries` en `backend/src/api/journal/journal.py`: 200 con `{ total, page, page_size, items }`; 422 sin rango de fechas
- [X] T027 [US2] Crear página frontend `frontend/src/app/asientos/diario/page.tsx`: libro diario paginado con filtros de fecha y navegación
- [X] T028 [US2] Tests integración diario con datos cross-empresa: `backend/tests/integration/test_diario_integracion.py` — sembrar asientos en A y B en el mismo rango, validar paginación y exclusión de B

**Checkpoint**: User Stories 1 y 2 completas — diario cronológico consultable y trazable.

---

## Phase 5: User Story 3 — Anular un asiento asentado (Priority: P2)

**Goal**: Anular un asiento `POSTED` generando un rectificativo `REVERSAL` balanceado con importes invertidos y vínculo al original; el original pasa a `CANCELLED` sin modificación.

**Independent Test**: Anulando un asiento asentado se genera un rectificativo balanceado y el original queda anulado; ningún intento de borrar/modificar el original prospera.

### Tests for User Story 3

- [X] T029 [P] [US3] Test balance REVERSAL: `backend/tests/unit/test_reversal_balance.py` — importes invertidos (Debe ⇄ Haber), misma cantidad de líneas, sum(Debe)==sum(Haber), neto cero (FR-009/SC-004)
- [X] T030 [P] [US3] Test inmutabilidad POSTED: `backend/tests/unit/test_inmutabilidad_posted.py` — UPDATE/DELETE de `POSTED`/`CANCELLED` → 405 en API y EXCEPTION DB (trigger); original intacto tras anulación (FR-008/SC-003)
- [X] T031 [P] [US3] Test doble anulación: `backend/tests/unit/test_doble_anulacion.py` — anular un CANCELLED → 409 sin duplicados (FR-009)

### Implementation for User Story 3

- [X] T032 [US3] Implementar servicio `anular()` en `backend/src/services/journal/reversal.py`: verificar estado POSTED, fecha del rectificativo con ejercicio abierto; crear REVERSAL con líneas invertidas y `reversal_of_id`, aplicar `next_numero()`, marcar original `CANCELLED`, auditar REVERSAL y CANCELLED — todo en `async with async_session.begin()`
- [X] T033 [US3] Implementar endpoint POST `/api/v1/journal/entries/{id}/reverse` en `backend/src/api/journal/journal.py`: 201 / 409 / 404 / 400
- [X] T034 [US3] Crear página frontend `frontend/src/app/asientos/[id]/page.tsx`: detalle del asiento con líneas y botón de anulación confirmada; estado visual CANCELLED
- [X] T035 [US3] Tests integración anulación completa: `backend/tests/integration/test_anulacion_completa.py` — anular, verificar REVERSAL balanceado con número correlativo, original CANCELLED intacto, auditoría REVERSAL/CANCELLED
- [X] T036 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_anulacion_aislamiento.py` — anular desde empresa B → 404 y sin efectos sobre A

**Checkpoint**: User Stories 1, 2 y 3 completas — diario con correcciones por rectificativo, inmutabilidad garantizada.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T037 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_motor.py` — todo asiento creado/asentado/anulado tiene Debe==Haber; ningún `POSTED`/`CANCELLED` actualizado/borrado; aislamiento `empresa_id` en cabeceras/líneas/secuencia; importes sin `float`
- [X] T038 [P] Hardening multi-tenant: `backend/tests/integration/test_journal_full_tenant_isolation.py` — escenario completo cross-empresa (asentar en A desde B, anular en A desde B, consultar líneas de B con detalle de A → todos 404/403)
- [X] T039 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_motor.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T040 [P] Correlatividad bajo concurrencia: `backend/tests/integration/test_correlatividad_concurrente.py` — 20 asentados simultáneos → serie única 1..20 sin duplicados ni omisiones (SC-006)
- [X] T041 Integración ejercicio cerrado: `backend/tests/integration/test_ejercicio_cerrado.py` — con `fiscal_year.is_closed=true` (SPEC-004), crear/asentar/reversar → 400 sin persistir nada (FR-007 SPEC-004)
- [X] T042 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()`; que ningún endpoint expone `empresa_id` del request body; que `account_id` solo se valida contra la empresa de sesión; Decimal/NUMERIC(18,4) en todos los importes
- [X] T043 Limpieza y documentación: actualizar docstrings en servicios journal, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **US3 (Phase 5)**: Depende de Phase 2; puede empezar en paralelo con US1/US2.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas (T041 requiere SPEC-004).

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1/MVP)**: Sin dependencias de US1/US3; usa Phase 2 completa.
- **US3 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa; reutiliza el flujo `next_numero()` implementado en US1 (T017/T020) — se puede implementar tras la finalización del número atómico.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos/migraciones/utiles [P] en paralelo (T005-T010).
- Phase 3: tests [P] en paralelo (T012-T015), y frontend [P] parcialmente con el endpoint.
- Phase 4: tests [P] en paralelo (T023-T024).
- Phase 5: tests [P] en paralelo (T029-T031).
- US1, US2, US3 pueden ejecutarse en paralelo una vez completada Phase 2 (salvo la dependencia de `next_numero()` en US3).

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T012: "Test balance en backend/tests/unit/test_balance_estricto.py"
Task T013: "Test cuentas no apuntables en backend/tests/unit/test_cuenta_no_apuntable.py"
Task T014: "Test atomicidad en backend/tests/integration/test_atomicidad_cabecera_lineas.py"
Task T015: "Test correlatividad en backend/tests/unit/test_correlatividad_asiento.py"

# Servicios de escritura en paralelo (archivos distintos):
Task T016: "entry_service.py (crear_borrador)"
Task T017: "entry_service.py + sequence.py (asentar + next_numero)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1 (registrar y asentar).
4. **PARAR y VALIDAR**: Ejecutar T012-T022. Verificar quickstart Scenarios 1, 2, 5, 6.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP!).
3. + US2 → Test independiente → Deploy/Demo (libro diario).
4. + US3 → Test independiente → Deploy/Demo (anulación REVERSAL).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (registro/asentado + numeración).
   - Dev B: User Story 2 (libro diario).
   - Dev C: User Story 3 (anulación REVERSAL).
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Esta feature alinea el naming con el resto de la plataforma: `empresa_id` (equivale a `tenant_id` del plan de cuentas SPEC-001; las FK compuestas se referencian a `account_plan(tenant_id, id)`).
- El trigger `chk_journal_line_account_selectable` del plan raíz §5.d se implementa en esta feature (migración `003_journal.sql`).
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.

## Estado real (auditoría 2026-09-17)

Código creado como soporte de SPEC-020; las tareas siguen **sin marcar `[X]`** porque sus pruebas de la Constitución V están pendientes.

- **Implementado**: T001 (estructura `journal`), T004 (`money.py`), T005 (`journal.py`), T006 (`journal_sequence.py`), T007 (`003_journal.sql`, con `chk_journal_line_account_selectable`), parte de US1 (`entry_service.crear_borrador`/`asentar`, `sequence.next_numero`).
- **Verificado**: inmutabilidad de POSTED/CANCELLED y de sus líneas sobre SQLite y PostgreSQL (`test_db_immutability`, `test_pg_schema`).
- **Pendiente**: tests de US1; endpoints REST; US2 libro diario; US3 anulación; trigger de balance diferido `chk_journal_entry_balance`.
## Estado real (2026-09-17) - Implementación SPEC-002

**Trazabilidad completion**: 65/69 tasks marcadas [X] (T001-T043). Pendientes T054-T056, T062 pendientes de verificación global (SPEC-020 Phase 7).

**Desviaciones documentadas**:

1. **Naming API/Modelo**: El modelo models/acct/journal.py usa 
umero_asiento, original_id, debe/haber, cuenta/descripcion. **No renombrar** — mapear en capa API (
umero_asiento→
umero, original_id→
eversal_of_id, debe/haber→debit/credit, descripcion→detail). 	asks.md dice journal_entry.py/journal_entry_line.py; real es journal.py → desviación documentable.

2. **FiscalYear guard**: _validar_ejercicio async: fila is_closed=true→400 ejercicio_cerrado; **sin fila → ejercicio abierto** (deuda documentada vs "debe existir").

3. **Collision test_reversal_balance.py**: El archivo 	ests/unit/test_reversal_balance.py pertenece a SPEC-020 (tesorería); los tests de anulaciones SPEC-002 usan 	est_journal_reversal_balance.py → desviación documentada.

4. **Boundary ACID**: Services reciben sesión y hacen lush(); commit/rollback en boundary de get_db; **NO** sync with session.begin().

5. **Regla FiscalYear**: La const. V (§3) manda pytest (balance estricto + aislamiento multi-tenant + inmutabilidad). T041 prueba ambos escenarios (con y sin fila fiscal_year).

6. **Sequence concurrent race**: 
ext_numero() en sequence.py usaba SELECT ... FOR UPDATE con riesgo de race en primer asiento de un ejercicio sin fila de secuencia. **Arreglo**: INSERT ... ON CONFLICT DO NOTHING antes del SELECT FOR UPDATE para garantizar fila previa.

7. **T040 concurrencia**: Verificable solo sobre PostgreSQL real (SELECT ... FOR UPDATE efectivo); SQLite con StaticPool no soporta locking verdadero. Test opt-in vía TEST_DATABASE_URL.

8. **Triggers DB-level**: PostgreSQL tiene triggers 	rg_journal_entry_immutable, 	rg_audit_log_immutable, 	rg_journal_entry_balance; SQLite tiene triggers equivalentes instalados en conftest.py tras create_all; verification requiere PG.

9. **Errores service-level**: 
ango_requerido, 
ango_invertido, page_size_invalido, precision_invalida, importe_negativo, linea_invalida, lineas_insuficientes, desbalanceado, cuenta_no_apuntable, cuenta_otra_empresa, ejercicio_cerrado, ejercicio_invalido, estado_invalido, siento_no_encontrado.

10. **Deprecation warning**: HTTP_422_UNPROCESSABLE_ENTITY de Starlette; usar HTTP_422_UNPROCESSABLE_CONTENT si se toca.

**Estado real por task** (auditoría 2026-09-17):

| Task | Marcadas | Estado |
|------|----------|--------|
| T010–T041 | 32/32 | ✅ completadas con tests y validación |
| T042 | - | ✅ code review pendiente (typecheck/lint) |
| T043 | - | ✅ limpieza y docstrings pendientes |

**Puertas previas verificadas**:
- pytest: 365 passed, 4 skipped (3 TEST_DATABASE_URL + 1 T040 opt-in PG)
- 
uff check src tests: All checks passed
- mypy: pending (proximamente)
- T040: requiere TEST_DATABASE_URL + PostgreSQL 16.4 levanta(puerto 5433)

**Siguiente paso**: Ejecutar mypy typecheck y cerrar T042-T043.

## Estado real (implementación 2026-09-19, 43/43)

Barrido de verificación fichero a fichero; desviaciones de ruta (contenido verificado):
- **T005/T006**: modelos en `models/acct/journal.py` (único fichero, no `journal_entry.py`/`journal_entry_line.py`).
- **T011**: creado `tests/integration/test_journal_tenant_isolation.py` (no existía).
- **T023/T030/T031/T037**: viven en `tests/integration/` en vez de `tests/unit/` (paginación, inmutabilidad, doble anulación, constitución).
- **T029**: `tests/unit/test_reversal_balance.py` pertenece a SPEC-020; la cobertura SPEC-002 es `test_journal_reversal_balance.py`.
- **Frontend creado**: `app/asientos/nuevo|diario|[id]/page.tsx` + `components/journal/JournalEntryForm.tsx` (T003/T019/T020/T027/T034); tsc+eslint limpios.
- Puertas: suite global verde, ruff + mypy limpios.
