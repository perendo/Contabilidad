# Tasks: Contabilidad Habitual, Informes y Cierre de Ejercicio (SPEC-004)

**Input**: Design documents from `/specs/004-informes-y-cierre/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (cuadre Debe==Haber, bloqueo de periodos y aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`. Depende de los motores de SPEC-001, SPEC-002 y SPEC-003.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3, US4)
- Incluir ruta exacta del archivo en la descripción

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulos de informes, cierre e invoicing en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura de módulos: `backend/src/services/reports/__init__.py`, `backend/src/services/closing/__init__.py`, `backend/src/services/invoicing/__init__.py`, `backend/src/api/reports/__init__.py`
- [X] T002 [P] Configurar routers: `backend/src/api/reports/informes.py` (informes), `backend/src/api/fiscal.py` (ejercicios y cierre) con dependency `get_empresa_id()` de `backend/src/api/deps.py`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/informes/sumas-saldos/page.tsx`, `frontend/src/app/informes/mayor/page.tsx`, `frontend/src/app/cierre/page.tsx`, `frontend/src/components/reports/`
- [X] T004 [P] Crear helpers de agregación: `backend/src/services/reports/common.py` — `rollup_code(code, level)` (prefijo de N dígitos), util de `Decimal` para sumas de NUMERIC(18,4), sin `float`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos base (`fiscal_year`, `invoice`) y guarda de ejercicios cerrados que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `FiscalYear` en `backend/src/models/acct/fiscal_year.py`: empresa_id, year, date_start, date_end, is_closed, closed_at, regularizacion_entry_id/cierre_entry_id FK → journal_entry; `UNIQUE (empresa_id, year)`
- [X] T006 [P] Crear modelo `Invoice` en `backend/src/models/ar/invoice.py`: empresa_id, tipo (emitida/recibida), ejercicio, numero_seq, nif_tercero, fecha, base, cuota_iva, total, asiento_id FK NULL; `UNIQUE (empresa_id, ejercicio, numero_seq)`, `CHECK (total = base + cuota_iva)`
- [X] T007 [P] Crear migración DDL en `backend/migrations/005_fiscal_invoice.sql`: tablas `fiscal_year` e `invoice` con constraints multi-tenant (UNIQUE por empresa/ejercicio, CHECK total), FKs a `journal_entry`
- [X] T008 [P] Implementar guarda de ejercicio en el motor: `backend/src/services/journal/entry_service.py` — al crear/asentar/reversar un asiento, validar que la `fecha` cae en un `fiscal_year` existente y no cerrado de la empresa; si está cerrado → HTTP 400 (FR-007 SPEC-004); si no hay ejercicio → HTTP 400
- [X] T009 [P] Implementar util `next_numero_factura()` en `backend/src/services/invoicing/sequence_factura.py`: contador por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE` (patrón SPEC-002) para la numeración correlativa de facturas
- [X] T010 [P] Tests unit de modelos: `backend/tests/unit/test_fiscal_invoice_models.py` — `UNIQUE (empresa_id, year)`, `UNIQUE (empresa_id, ejercicio, numero_seq)`, CHECK `total = base + cuota_iva`, reglas de vínculo `asiento_id`
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_fiscal_tenant_isolation.py` — ejercicio y factura de empresa A no visibles desde empresa B

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Balance de Sumas y Saldos (Priority: P1) ?? MVP

**Goal**: Generar el Balance de Sumas y Saldos por rango de fechas y nivel de profundidad; agregar Debe/Haber/saldo por cuenta; siempre cuadra y solo incluye la empresa activa.

**Independent Test**: Generando el informe para varios rangos y niveles, Sum(Debe)==Sum(Haber) y solo incluye asientos de la empresa activa.

### Tests for User Story 1

- [X] T012 [P] [US1] Test cuadre siempre: `backend/tests/unit/test_trial_balance_cuadre.py` — para múltiples rangos y niveles, `suma_debe == suma_haber` en el consolidado (FR-003/SC-001)
- [X] T013 [P] [US1] Test agregación por nivel: `backend/tests/unit/test_trial_balance_nivel.py` — roll-up por prefijo de código; nivel superior al plan → agrega al mayor disponible sin error (FR-002)
- [X] T014 [P] [US1] Test aislamiento balance: `backend/tests/integration/test_trial_balance_aislamiento.py` — asientos de otra empresa en el mismo rango jamás se incluyen (SC-003)

### Implementation for User Story 1

- [X] T015 [US1] Implementar servicio `trial_balance()` en `backend/src/services/reports/trial_balance.py`: agregación SQL (`SUM` sobre líneas de asientos con efecto de la empresa activa) uniendo `journal_entry`+`account_plan`, filtro de fechas, roll-up por nivel con `common.rollup_code`, presentación en `Decimal`
- [X] T016 [US1] Implementar endpoint GET `/api/v1/reports/trial-balance` en `backend/src/api/reports/informes.py`: 200 con `{ total_debe, total_haber, cuadra, items }`; 422 rango/level inválidos
- [X] T017 [US1] Crear página frontend `frontend/src/app/informes/sumas-saldos/page.tsx`: filtros de fecha/nivel y tabla del balance con totales, marcado visual del cuadre
- [X] T018 [US1] Crear componente frontend `frontend/src/components/reports/TrialBalanceTable.tsx`: tabla con sumas/saldos por cuenta al nivel
- [X] T019 [US1] Tests integración balance completo: `backend/tests/integration/test_trial_balance_integracion.py` — sembrar asientos en A y B, validar agregación, totales, cuadre y exclusión de B

**Checkpoint**: User Story 1 completa — informe de control del ejercicio funcional.

---

## Phase 4: User Story 2 — Libro Mayor de una subcuenta (Priority: P1)

**Goal**: Extracto cronológico de una subcuenta de la empresa activa con Debe, Haber y saldo acumulado exacto.

**Independent Test**: Consultando el mayor de una subcuenta se obtienen solo sus apuntes de la empresa activa, ordenados cronológicamente, con saldo acumulado correcto; subcuenta de otra empresa → negada.

### Tests for User Story 2

- [X] T020 [P] [US2] Test saldo acumulado: `backend/tests/unit/test_ledger_saldo_acumulado.py` — secuencia {debe, haber, saldo_acumulado} exacta en Decimal para una subcuenta con movimientos mixtos (FR-004)
- [X] T021 [P] [US2] Test aislamiento mayor: `backend/tests/integration/test_ledger_aislamiento.py` — mayor de subcuenta de otra empresa → 404 sin datos; subcuenta sin movimientos → 200 vacío (edge case)

### Implementation for User Story 2

- [X] T022 [US2] Implementar servicio `ledger()` en `backend/src/services/reports/ledger.py`: movimientos cronológicos (fecha, numero, concepto, debe, haber) con saldo acumulado en `Decimal`; filtra `empresa_id + account_id`
- [X] T023 [US2] Implementar endpoint GET `/api/v1/reports/ledger/{account_id}` en `backend/src/api/reports/informes.py`: 200 con `{ cuenta, saldo_inicial, movimientos, saldo_final }`; 404 si la subcuenta no pertenece a la empresa activa
- [X] T024 [US2] Crear página frontend `frontend/src/app/informes/mayor/page.tsx`: selector de subcuenta (AccountAutocomplete de SPEC-001) y tabla del mayor con saldo acumulado
- [X] T025 [US2] Crear componente frontend `frontend/src/components/reports/LedgerTable.tsx`: tabla cronológica con saldo acumulado
- [X] T026 [US2] Tests integración mayor completo: `backend/tests/integration/test_ledger_integracion.py` — apuntes en A y B sobre la misma subcuenta de código, verificar que el mayor de A solo ve los de A con saldo correcto

**Checkpoint**: User Stories 1 y 2 completas — informe de cuadre y Mayor funcionales. MVP de informes desplegable.

---

## Phase 5: User Story 3 — Cerrar el ejercicio contable (Priority: P2)

**Goal**: Cierre atómico: regularización (grupos 6/7), asiento de cierre y bloqueo `is_closed`, juntos o ninguno; rechazo de cierre doble o con borradores pendientes.

**Independent Test**: Ejecutando el cierre aparecen regularización y cierre y el ejercicio queda bloqueado; si falla a mitad, el ejercicio permanece abierto.

### Tests for User Story 3

- [X] T027 [P] [US3] Test atomicidad del cierre: `backend/tests/integration/test_cierre_atomico.py` — inyectar un fallo a mitad → ejercicio abierto sin asientos de regularización/cierre (FR-008/SC-004)
- [X] T028 [P] [US3] Test doble cierre: `backend/tests/unit/test_doble_cierre.py` — segundo cierre → 409 sin asientos duplicados (FR-009)
- [X] T029 [P] [US3] Test cierre con borradores: `backend/tests/unit/test_cierre_borradores.py` — DRAFT en el rango → 422; tras asentarlos/anularlos → cierre OK (edge case)
- [X] T030 [P] [US3] Test balance de asientos de cierre: `backend/tests/unit/test_cierre_balance.py` — regularización y cierre cuadran (Debe==Haber) y quedan `POSTED` inmutables (FR-010)
- [X] T031 [P] [US3] Test bloqueo de ejercicio cerrado: `backend/tests/integration/test_bloqueo_cerrado.py` — crear/asentar/reversar asiento con fecha en ejercicio `is_closed` → 400 sin persistir (FR-007/SC-002); creación → 400
- [X] T032 [P] [US3] Test aislamiento cierre: `backend/tests/integration/test_cierre_aislamiento.py` — cerrar ejercicio de otra empresa → 404/403 sin efectos sobre la otra empresa

### Implementation for User Story 3

- [X] T033 [US3] Implementar servicio `cerrar_ejercicio()` en `backend/src/services/closing/close_year.py`: en `async with async_session.begin()` (1) `SELECT ... FOR UPDATE` del `fiscal_year`, (2) validar abierto y sin DRAFT, (3) construir asiento de regularización (grupos 6/7 → 129) balanceado con el motor de SPEC-002, (4) asiento de cierre saldando balance, (5) `is_closed=True`, `closed_at`, guardar ids, auditar CLOSE_YEAR/REGULARIZATION/CLOSING_ENTRY
- [X] T034 [US3] Implementar servicio de recálculo de saldos de cierre: `backend/src/services/closing/close_year.py` — detección de cuentas con saldo (balance/patrimoniales) y cuentas de gestión (grupos 6/7) según `account_plan`
- [X] T035 [US3] Implementar endpoint POST `/api/v1/fiscal-years/{year}/close` en `backend/src/api/fiscal.py`: 200 / 409 (cerrado, cierre concurrente) / 404 / 422 (borradores); auditar en la misma transacción
- [X] T036 [US3] Implementar endpoint GET `/api/v1/fiscal-years` en `backend/src/api/fiscal.py`: listado de ejercicios de la empresa activa
- [X] T037 [US3] Crear página frontend `frontend/src/app/cierre/page.tsx`: listado de ejercicios con estado, botón de cierre con confirmación y mensaje de errores (borradores pendientes, ya cerrado)
- [X] T038 [US3] Tests integración cierre completo: `backend/tests/integration/test_cierre_completo.py` — cierre real con datos, verificar asientos balanceados, números correlativos del diario, `is_closed`, y que tras el cierre un asiento nuevo en el rango da 400

**Checkpoint**: User Stories 1, 2 y 3 completas — cierre de ejercicio operativo e inmovilización del periodo.

---

## Phase 6: User Story 4 — Registrar y conservar facturas (Priority: P2)

**Goal**: Persistir facturas emitidas/recibidas con precisión exacta (base, IVA, total), numeración correlativa por (empresa, ejercicio) y vínculo al asiento; entidad conservada (sin API de gestión en esta feature).

**Independent Test**: Almacenando facturas de distintos tipos se conservan sus importes sin errores de redondeo y su numeración es correlativa; factura de otra empresa inaccesible.

### Tests for User Story 4

- [X] T039 [P] [US4] Test precisión decimal: `backend/tests/unit/test_invoice_precision.py` — base/IVA/total con 4 decimales exactos; `total == base + cuota`; entrada con >4 decimales → normalizada a 4 (FR-005/SC-005); sin `float`
- [X] T040 [P] [US4] Test correlatividad facturas: `backend/tests/unit/test_invoice_correlatividad.py` — 3 facturas en 2026 → números 1,2,3; 2027 → secuencia independiente; duplicado → 409 (FR-006)
- [X] T041 [P] [US4] Test inmutabilidad/vínculo: `backend/tests/unit/test_invoice_inmutabilidad.py` — factura vinculada a asiento no se borra ni se re-vincula (data-model); sin DELETE
- [X] T042 [P] [US4] Test aislamiento facturas: `backend/tests/integration/test_invoice_aislamiento.py` — factura de empresa B no accesible desde A a nivel de servicio (SC-003)

### Implementation for User Story 4

- [X] T043 [US4] Implementar servicio `crear_factura()` en `backend/src/services/invoicing/invoice_service.py`: validar tipo/importes (normalización 4 decimales), asignar `numero_seq` con `next_numero_factura()` atómicamente, `CHECK total = base + cuota`, vínculo opcional a asiento; auditar CREATE_INVOICE en la misma transacción (`async with async_session.begin()`)
- [X] T044 [US4] Implementar `vincular_asiento()` en `backend/src/services/invoicing/invoice_service.py`: fijar `asiento_id` una única vez (inmutable tras el vínculo) con validación de pertenencia al tenant
- [X] T045 [US4] Tests integración facturas: `backend/tests/integration/test_invoice_integracion.py` — crear factura emitida y recibida vía servicio, verificar precisión y correlatividad en DB, verificar que el vínculo al asiento respeta el tenant
- [X] T046 [US4] Documentar la diferida API de facturas: actualizar `contracts/api-contracts.md` y registrar en la feature posterior correspondiente (TL;DR: solo servicio + entidad en esta feature)

**Checkpoint**: User Stories 1, 2, 3 y 4 completas — contabilidad habitual, informes y cierre funcionales.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T047 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_informes.py` — todo balance/mayor/cierre: cuadre Debe==Haber, inmutabilidad de asientos de cierre, aislamiento `empresa_id`, fechas en cerrado → 400, precisiones sin `float`
- [X] T048 [P] Hardening multi-tenant: `backend/tests/integration/test_informes_full_tenant_isolation.py` — escenario completo: escribir en A, leer informes desde B, cerrar ejercicio de B sobre A → 403/404; sin fuga de datos
- [X] T049 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_informes.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T050 [P] Cierre concurrente: `backend/tests/integration/test_cierre_concurrente.py` — dos peticiones simultáneas → un 200 y un 409 (lock `FOR UPDATE`)
- [X] T051 [P] Chequeo de integración con el diario: `backend/tests/integration/test_integracion_cierre_diario.py` — los asientos de regularización/cierre se numeran en la secuencia del diario (SPEC-002) sin saltos y quedan `POSTED`
- [X] T052 [P] Code review: verificar uso de `async with async_session.begin()` en cierre/invoicing; ningún endpoint expone `empresa_id` del request; `Decimal` en agregaciones y saldos; guarda `is_closed` en todos los puntos de escritura del diario; PAYLOAD de auditoría con cadenas Decimal
- [X] T053 Limpieza y documentación: actualizar docstrings en servicios de informes/cierre/invoicing, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories; T008 requiere que `journal/entry_service.py` (SPEC-002) exista.
- **US1 (Phase 3)**: Depende de Phase 2 completa y de asientos de SPEC-002 (datos).
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **US3 (Phase 5)**: Depende de Phase 2, SPEC-001 (cuentas de plan) y SPEC-002 (motor/num). Puede empezar en paralelo con US1/US2.
- **US4 (Phase 6)**: Depende de Phase 2; puede empezar en paralelo con US1-US3.
- **Polish (Phase 7)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa y datos de SPEC-002.
- **US2 (P1/MVP)**: Sin dependencias de US1/US3; usa Phase 2 completa.
- **US3 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa, SPEC-001 (plan/grupos 6/7, 129) y SPEC-002 (asientos, numeración).
- **US4 (P2)**: Sin dependencias de US1-US3; usa Phase 2 completa; el vínculo de factura a asiento usa SPEC-002.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos/guarda/secuencia [P] en paralelo (T005-T010).
- Phase 3: tests [P] en paralelo (T012-T014).
- Phase 4: tests [P] en paralelo (T020-T021).
- Phase 5: tests [P] en paralelo (T027-T032), servicio [P] con US3.
- Phase 6: tests [P] en paralelo (T039-T042).
- US1, US2, US3, US4 pueden iniciarse en paralelo una vez completada Phase 2.

---

## Parallel Example: User Story 3

```bash
# Tests en paralelo:
Task T027: "Test atomicidad en backend/tests/integration/test_cierre_atomico.py"
Task T028: "Test doble cierre en backend/tests/unit/test_doble_cierre.py"
Task T029: "Test borradores en backend/tests/unit/test_cierre_borradores.py"
Task T030: "Test balance asientos de cierre en backend/tests/unit/test_cierre_balance.py"
Task T031: "Test bloqueo cerrado en backend/tests/integration/test_bloqueo_cerrado.py"

# Servicio de cierre y endpoint en paralelo (archivos distintos):
Task T033: "close_year.py (servicio de cierre atómico)"
Task T035: "fiscal.py (endpoint POST close)"
```

---

## Implementation Strategy

### MVP First (User Story 1 y 2)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1 (Balance de Sumas y Saldos).
4. Completar Phase 4: User Story 2 (Libro Mayor).
5. **PARAR y VALIDAR**: Ejecutar T012-T026. Verificar quickstart Scenarios 1, 2, 6.
6. Desplegar/demo si listo (informes de control funcionales).

### Incremental Delivery

1. Setup + Foundational → Foundation ready (incluida la guarda `is_closed` para SPEC-002).
2. + US1 → Test independiente → Deploy/Demo (Balance).
3. + US2 → Test independiente → Deploy/Demo (Mayor).
4. + US3 → Test independiente → Deploy/Demo (cierre atómico e inmovilización).
5. + US4 → Test independiente → Deploy/Demo (facturas con precisión y numeración).
6. + Polish → Validación constitucional completa (cuadre, bloqueo y aislamiento).

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos (guarda `is_closed` bloquea a SPEC-002).
2. Una vez Foundational lista:
   - Dev A: User Story 1 (Balance) y User Story 2 (Mayor).
   - Dev B: User Story 3 (Cierre de ejercicio).
   - Dev C: User Story 4 (Facturas).
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- La guarda `is_closed` (T008) se integra en la fase Foundational de **esta** feature pero modifica el motor de asientos de SPEC-002 (acuerdo cross-feature documentado).
- Informes derivados (sin tabla materializada); el cierre decide "generar o no" dentro de una sola transacción (juntos o ninguno).
- La API de gestión de facturas se difiere (assumption de la spec); esta feature persiste la entidad por servicio y prueba numeración/precisión/inmutabilidad.
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de cuadre (Debe==Haber) + bloqueo de periodos + aislamiento multi-tenant.

## Estado real (auditoría 2026-09-17)

- **Implementado**: T007 (`005_fiscal_invoice.sql`: tablas `fiscal_year` e `invoice`).
- **Desviación**: los FK a `journal_entry` usan `UUID` (no `BIGINT`) y FK compuesta `(empresa_id, id)`, para alinearse con el PK real de `journal_entry`.
- **Pendiente**: modelos `fiscal_year`/`invoice`, servicios de informes y cierre, guarda de ejercicio cerrado y todos los tests. El resto de tareas sigue sin empezar.

## Estado real (implementación 2026-09-19, 53/53)

Desviaciones documentadas respecto al texto de tareas:
- **T008**: ejercicio inexistente se trata como abierto (comportamiento ratificado por SPEC-002 `test_ejercicio_sin_fila_tratado_como_abierto`); cerrado → 400. Sin cambios de código.
- **T033/T034**: asientos de regularización/cierre usan `tipo=ADJUSTMENT` (el ENUM PG `journal_entry_tipo` no tiene valores CIERRE/REGULARIZACION y no se tocó la migración 003); `crear_borrador()` acepta nuevo kwarg opcional `tipo` (default GENERAL, sin regresión SPEC-002).
- **T033**: la regularización contabiliza contra la subcuenta auto-creada `1290` (la 129 de nivel 3 no es apuntable por el trigger `level >= 4` de SPEC-001); `1290` agrega en `129` en niveles ≤ 3.
- Puertas: 456 passed / 5 skipped, ruff + mypy (86 ficheros) limpios, `next build` 15 rutas.
