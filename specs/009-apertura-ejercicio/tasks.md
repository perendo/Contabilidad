# Tasks: Apertura del Ejercicio (SPEC-009)

**Input**: Design documents from `/specs/009-apertura-ejercicio/`

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
| FR-001 | Aislar apertura por empresa y generar para empresa activa | US1 |
| FR-002 | Exigir cierre previo, ejercicio siguiente y rango definido | US3 |
| FR-003 | Generar asiento con saldos patrimoniales balanceado | US1 |
| FR-004 | Impedir segunda apertura para mismo ejercicio y empresa | US3 |
| FR-005 | Iniciar numeración del nuevo ejercicio en 1 correlativa | US1 |
| FR-006 | Permitir anular y regenerar apertura con rectificativo | US2 |
| FR-007 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo de ciclo contable (apertura) en backend y frontend.

- [X] T001 [P] Crear estructura del módulo: `backend/src/services/cycle/__init__.py`, `backend/src/services/cycle/apertura.py`, `backend/src/services/cycle/validacion_previa.py`, `backend/src/api/ciclo/__init__.py`, `backend/src/api/ciclo/routes.py`
- [X] T002 [P] Configurar router ciclo: registrar prefijo `/api/v1/ciclo` en `backend/src/api/ciclo/routes.py` con dependency de sesión autenticada `empresa_id`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/apertura/`, `frontend/src/components/cycle/`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/ciclo/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelo de ejercicio y extensiones de asiento que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `EjercicioContable` en `backend/src/models/fiscal/ejercicio.py`: campos empresa_id (PK compuesta), ejercicio INT, fecha_inicio DATE, fecha_fin DATE, estado ENUM (abierto/cerrado/con_apertura), created_at/created_by; constraint unicidad (empresa_id, ejercicio); constraint fecha_inicio < fecha_fin
- [X] T006 [P] Extender el modelo `JournalEntry` existente con campos `tipo` ENUM (OPENING/OPENING_REVERSAL/REGULAR/CLOSING/ADJUSTMENT) y `referencia_cierre_id` UUID FK NULL en `backend/src/models/acct/journal_entry.py`
- [X] T007 [P] Crear migración de esquema para `EjercicioContable` y extensión de `JournalEntry` en `backend/src/models/migrations/`
- [X] T008 [P] Tests de modelos fundacionales: `backend/tests/unit/test_cycle_models.py` — verificar unicidad (empresa_id, ejercicio), constraint fecha, constraint estado
- [X] T009 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_cycle_tenant_isolation.py` — crear ejercicio en empresa A, verificar que empresa B no lo ve

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Abrir el ejercicio siguiente con el asiento de apertura (Priority: P1) — MVP — cubre FR-001, FR-003, FR-005, FR-007

**Goal**: El sistema genera automáticamente el asiento de apertura balanceado con los saldos patrimoniales del cierre anterior y reinicia la numeración del nuevo ejercicio.

**Independent Test**: Abriendo un ejercicio tras un cierre, el asiento de apertura se genera con los saldos correctos y el nuevo ejercicio queda numerado desde 1.

### Tests for User Story 1

- [X] T010 [P] [US1] Test balance apertura: `backend/tests/unit/test_apertura_balance.py` — generar asiento de apertura con saldos conocidos, verificar Debe==Haber con `Decimal` exacto; verificar que solo aparecen cuentas de grupo 1-3; verificar que cuentas de grupo 6-7 no se abren
- [X] T011 [P] [US1] Test correlatividad: `backend/tests/unit/test_apertura_numeracion.py` — generar asiento en ejercicio nuevo, verificar numero_asiento=1; si ya existe asiento manual antes de apertura, verificar que la apertura toma el siguiente número

### Implementation for User Story 1

- [X] T012 [US1] Implementar `validar_previa_apertura` en `backend/src/services/cycle/validacion_previa.py`: verificar (a) ejercicio anterior existe y está `cerrado`, (b) ejercicio destino existe con rango de fechas, (c) no existe asiento `OPENING` para el destino, (d) no hay solapamiento de rangos; devolver errores 409 específicos
- [X] T013 [US1] Implementar `calcular_saldos_patrimoniales` en `backend/src/services/cycle/apertura.py`: consultar saldos del plan de cuentas (SPEC-001) para el ejercicio anterior, filtrar cuentas grupo 1-3, calcular `debito - credito` por cuenta; devolver lista de (account_id, debit/credit) en `Decimal`
- [X] T014 [US1] Implementar `generar_asiento_apertura` en `backend/src/services/cycle/apertura.py`: crear `JournalEntry` tipo `OPENING` + `JournalEntryLine[]` en una sola transacción ACID (`async with async_session.begin()`); asignar numero_asiento por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE`; validar Debe==Haber antes de commit; registrar audit log
- [X] T015 [US1] Implementar endpoints en `backend/src/api/ciclo/routes.py`: POST `/api/v1/ciclo/apertura` (201), GET `/api/v1/ciclo/apertura/estado` (200)
- [X] T016 [US1] Tests integración apertura completa: `backend/tests/integration/test_apertura_completa.py` — crear empresa con plan de cuentas, generar cierre previo, ejecutar apertura, verificar asiento balanceado, verificar numeración desde 1, verificar que solo se abren cuentas patrimoniales
- [X] T017 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_apertura_tenant.py` — empresa A crea apertura, empresa B no la ve en consulta de estado ni en listado de asientos; intento de apertura para empresa B desde contexto A → 409 o sin efecto

**Checkpoint**: User Story 1 completa — apertura funcional con asiento balanceado. MVP desplegable.

---

## Phase 4: User Story 2 — Controlar y corregir una apertura errónea (Priority: P2) — cubre FR-006

**Goal**: El contador puede anular y regenerar una apertura errónea sin afectar al ejercicio anterior, generando un asiento REVERSAL trazable.

**Independent Test**: Anulando una apertura se genera el asiento rectificativo y se permite regenerarla; el ejercicio anterior permanece intacto.

### Tests for User Story 2

- [X] T018 [P] [US2] Test balance REVERSAL: `backend/tests/unit/test_apertura_reversal_balance.py` — generar REVERSAL del asiento de apertura, verificar Debe==Haber invertido; verificar que el asiento original OPENING no fue modificado (inmutabilidad)
- [X] T019 [P] [US2] Test regeneración: `backend/tests/unit/test_apertura_regeneracion.py` — tras anulación, generar nuevo OPENING; verificar que tiene numero_asiento correlativo y saldo correcto; verificar que el REVERSAL sigue enlazado al original

### Implementation for User Story 2

- [X] T020 [US2] Implementar `anular_apertura` en `backend/src/services/cycle/apertura.py`: buscar asiento `OPENING` activo del ejercicio, crear `JournalEntry` tipo `OPENING_REVERSAL` con líneas invertidas enlazado al original; todo en transacción ACID; verificar que el ejercicio destino sigue `abierto`; audit log; el asiento original NO se modifica
- [X] T021 [US2] Implementar `regenerar_apertura` en `backend/src/services/cycle/apertura.py`: validar que existe un `OPENING_REVERSAL` previo o el `OPENING` fue anulado; llamar a `generar_asiento_apertura` para crear un nuevo `OPENING` con saldos recalculados
- [X] T022 [US2] Implementar endpoints en `backend/src/api/ciclo/routes.py`: POST `/api/v1/ciclo/apertura/anular` (200), POST `/api/v1/ciclo/apertura/regenerar` (201)
- [X] T023 [US2] Tests integración anulación completa: `backend/tests/integration/test_apertura_anulacion.py` — crear apertura, anular, verificar REVERSAL balanceado, verificar asiento original inmutable, regenerar, verificar nuevo OPENING válido
- [X] T024 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_apertura_anulacion_tenant.py` — empresa A anula su apertura, empresa B no ve el REVERSAL ni puede anular la apertura de A

**Checkpoint**: User Stories 1 y 2 completas — apertura + anulación/regeneración funcional.

---

## Phase 5: User Story 3 — Evitar aperturas duplicadas o incompletas (Priority: P1) — cubre FR-002, FR-004

**Goal**: El sistema impide abrir un ejercicio si ya existe, si no hay cierre del anterior, o si el nuevo ejercicio no tiene rango de fechas.

**Independent Test**: Intentando una doble apertura o una apertura sin cierre previo, el sistema la rechaza con mensajes claros.

### Tests for User Story 3

- [X] T025 [P] [US3] Test bloqueo doble apertura: `backend/tests/unit/test_apertura_bloqueos.py` — verificar que se rechaza con 409: (a) ejercicio ya tiene apertura → `ejercicio_ya_abierto`, (b) ejercicio anterior no cerrado → `ejercicio_cerrado`, (c) ejercicio destino sin rango de fechas → `ejercicio_no_definido`
- [X] T026 [P] [US3] Test validación solapamiento: `backend/tests/unit/test_apertura_solapamiento.py` — crear ejercicio con rango solapado → rechazo de validación previa

### Implementation for User Story 3

- [X] T027 [US3] Implementar `validar_no_duplicada` en `backend/src/services/cycle/validacion_previa.py`: buscar asiento `OPENING` o `OPENING_REVERSAL` activo para el ejercicio destino; si existe `OPENING` → 409 `ejercicio_ya_abierto`
- [X] T028 [US3] Implementar `validar_cierre_previo` en `backend/src/services/cycle/validacion_previa.py`: buscar ejercicio anterior por empresa; si no existe o su estado no es `cerrado` → 409 `ejercicio_cerrado`
- [X] T029 [US3] Integrar validaciones en `generar_asiento_apertura`: ejecutar todas las validaciones previas antes de calcular saldos y persistir
- [X] T030 [US3] Tests integración bloqueos completos: `backend/tests/integration/test_apertura_bloqueos_completa.py` — escenarios end-to-end: doble apertura → 409, sin cierre → 409, sin rango fechas → 409, apertura tras anulación → 201
- [X] T031 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_apertura_bloqueos_tenant.py` — verificar que los bloqueos se aplican por empresa (la apertura de A no impide la de B)

**Checkpoint**: User Stories 1, 2 y 3 completas — ciclo de apertura funcional y robusto.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T032 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_apertura.py` — verificar que todo asiento (OPENING, OPENING_REVERSAL) tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry confirmado; verificar aislamiento empresa_id en todas las tablas
- [X] T033 [P] Hardening multi-tenant: `backend/tests/integration/test_apertura_full_tenant_isolation.py` — escenario completo cross-empresa: apertura A, consulta B, anulación B sobre A → todos rechazados
- [X] T034 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_apertura.py` — reproducir los 5 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T035 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [X] T036 Crear página frontend `frontend/src/app/apertura/page.tsx`: botón de apertura del ejercicio, consulta de estado, botón de anulación con confirmación
- [X] T037 Limpieza y documentación: actualizar docstrings en servicios cycle, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2 y US1 (necesita una apertura existente para anular).
- **US3 (Phase 5)**: Depende de Phase 2; validations se integran en US1; tests independientes.
- **Polish (Phase 6)**: Depende de las user stories completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Depende de US1 (necesita apertura existente para poder anular/regenerar).
- **US3 (P1)**: Validaciones se integran directamente en US1 (la apertura ya las ejecuta); tests se escriben independientemente para verificar bloqueos.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T007).
- Phase 3: tests [P] en paralelo (T010-T011).
- Phase 4: tests [P] en paralelo (T018-T019).
- Phase 5: tests [P] en paralelo (T025-T026).
- US3 puede ejecutarse en paralelo con US2 una vez completada Phase 2 (las validaciones se integran en US1).

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T010: "Test balance apertura en backend/tests/unit/test_apertura_balance.py"
Task T011: "Test correlatividad en backend/tests/unit/test_apertura_numeracion.py"

# Implementación secuencial (dependencias internas):
Task T012: "Validación previa en backend/src/services/cycle/validacion_previa.py"
Task T013: "Cálculo saldos en backend/src/services/cycle/apertura.py"
Task T014: "Generación asiento en backend/src/services/cycle/apertura.py"
Task T015: "Endpoints en backend/src/api/ciclo/routes.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T010-T017. Verificar quickstart Scenario 1 y 4.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP!).
3. + US3 → Test independiente → Deploy/Demo (bloqueos robustos).
4. + US2 → Test independiente → Deploy/Demo (anulación/regeneración).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 + US3 (apertura + bloqueos, van juntos).
   - Dev B: User Story 2 (anulación/regeneración, depende de Dev A).
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Cada user story debe ser completable y testeable independientemente (salvo US2 que depende de US1).
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.

---

## Estado real (implementación 2026-09-20)

Spec completada: **37/37 tareas** marcadas y puertas verdes (pytest 603 passed
SQLite+PG, ruff, mypy, `next build`). DESVIACIONES documentadas:

- **Transacción ACID**: los servicios usan `flush()` dentro del boundary del
  llamante (`get_db` de `database.py`), patrón del proyecto — NO
  `async with async_session.begin()` (T014/T020/T035).
- **Modelos**: `JournalEntry` vive en `backend/src/models/acct/journal.py` único
  (T006). `EjercicioContable` en `models/fiscal/ejercicio.py` con PK UUID (no
  compuesta; la unicidad multi-tenant se declara vía
  `UNIQUE(empresa_id, id)` + `UNIQUE(empresa_id, ejercicio)`).
- **Migración**: `backend/migrations/006_apertura.sql` (en vez de
  `models/migrations/`); registrada en `ORDEN_PREFERENTE` de
  `backend/src/db/migrate.py` tras `005`; enum `journal_entry_tipo` se amplía
  con `ADD VALUE IF NOT EXISTS` (PG 12+ permite dentro de transacción).
- **Estado destino tras apertura**: `EjercicioContable.estado` pasa de
  `abierto` → `con_apertura` (coherente con `estado` del quickstart); la
  anulación lo devuelve a `abierto` para permitir regeneración.
- **Saldos patrimoniales = grupos 1-3** (una línea direccional por cuenta, neto
  del ejercicio previo). Se excluye únicamente el asiento de cierre
  (`cierre_entry_id`), no la regularización, para conservar el resultado en
  `1290`. Consecuencia inherente al spec: si los grupos 1-3 no cuadran solos
  (p. ej. saldos preponderantes en 4/5), la apertura se rechaza con
  `asiento_desbalanceado`/`cuentas_patrimoniales_vacias`.
- **Endpoints**: registrados en `backend/src/api/ciclo/` (sub-router
  `apertura.py` + router versionado `routes.py` con `prefix="/api/v1"` y
  `Depends(get_empresa_id)`), montados en `main.py`. Códigos HTTP: apertura
  201, regenerar 201, anular 200, estado 200; 409/404/422 según
  `CicloError.status_code`.
- **Rechazo D8**: apertura sobre ejercicio cerrado distinto del previo →
  `422 ejercicio_no_definido` (el previo tampoco está definido), no 409.
- **Fixtures/helpers**: helpers de siembra duplicados en los test files de
  SPEC-009 (convención actual del repo, ver transversal G-del-futuro: extraer
  helper compartido en `conftest`).
- **Frontend**: `frontend/src/app/apertura/page.tsx` (consultar estado, abrir,
  anular, regenerar). `frontend/src/components/cycle/` queda con `.gitkeep`.