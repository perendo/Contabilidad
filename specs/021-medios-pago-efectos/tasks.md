# Tasks: Medios de Pago y Efectos (SPEC-021)

**Input**: Design documents from `/specs/021-medios-pago-efectos/`

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
| FR-001 | Aislar cartera de efectos y cobros/pagos por medio | US1 |
| FR-002 | Registrar efectos y liquidar al cobro o impago | US1 |
| FR-003 | Registrar cobros TPV/tarjeta/transferencia con comisión | US2 |
| FR-004 | Cartera de efectos con filtros por medio, estado, fecha | US3 |
| FR-005 | Reabrir vencimiento ante impago y registrar gastos | US1 |
| FR-006 | Rechazar gestión de efectos en ejercicio cerrado | US1 |
| FR-007 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo treasury (efectos) en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo treasury: `backend/src/models/treasury/__init__.py`, `backend/src/models/treasury/efecto.py`, `backend/src/models/treasury/cobro_medio.py`, `backend/src/models/treasury/comision.py`, `backend/src/services/treasury/__init__.py`, `backend/src/services/treasury/efecto.py`, `backend/src/services/treasury/cobro_medio.py`, `backend/src/services/treasury/cartera.py`, `backend/src/api/treasury/__init__.py`
- [X] T002 [P] Configurar router treasury: registrar prefijo `/api/v1` en `backend/src/api/treasury/routes.py` con dependency de sesión autenticada `empresa_id`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/efectos/`, `frontend/src/app/tesoreria/`, `frontend/src/components/treasury/`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/treasury/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `Efecto` en `backend/src/models/treasury/efecto.py`: campos empresa_id (PK compuesto), id UUID PK, tercero_id FK, tipo_efecto ENUM (CHEQUE/PAGARE/LETRA), numero_documento VARCHAR(50), fecha_emision DATE, fecha_vencimiento DATE, importe NUMERIC(18,4), moneda VARCHAR(3) DEFAULT 'EUR', estado ENUM (emitido/cobrado/impagado), asiento_cobro_id UUID NULL FK, asiento_impago_id UUID NULL FK, notas TEXT; constraint unicidad (empresa_id, tercero_id, tipo_efecto, numero_documento); constraint fecha_vencimiento >= fecha_emision
- [X] T006 [P] Crear modelo `CobroMedio` en `backend/src/models/treasury/cobro_medio.py`: empresa_id, id UUID PK, vencimiento_id FK → SPEC-011, medio_cobro ENUM (CHEQUE/PAGARE/LETRA/TARJETA/TRANSFERENCIA/CAJA), fecha_cobro DATE, importe_total NUMERIC(18,4), importe_comision NUMERIC(18,4) DEFAULT 0, importe_neto NUMERIC(18,4) calculado, cuenta_banco VARCHAR(12), asiento_cobro_id FK; constraint importe_comision >= 0 y <= importe_total
- [X] T007 [P] Crear modelo `ComisionBancaria` en `backend/src/models/treasury/comision.py`: empresa_id, id UUID PK, cobro_medio_id FK, banco_codigo VARCHAR(12), tipo_comision VARCHAR(50), importe NUMERIC(18,4), porcentaje NUMERIC(5,2) NULL, cuenta_contable VARCHAR(12) DEFAULT '626'
- [X] T008 Implementar `get_empresa_id()` en `backend/src/api/treasury/deps.py`: extraer empresa_id de sesión autenticada; validar que la empresa está activa; raise 401 si no hay sesión
- [X] T009 [P] Tests de modelos fundacionales: `backend/tests/unit/test_efecto_models.py` — verificar unicidad (empresa_id, tercero_id, tipo_efecto, numero_documento), constraint fecha_vencimiento >= fecha_emision, constraint importe_comision, FK compuesta empresa_id
- [X] T010 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_efecto_tenant_isolation.py` — crear efecto en empresa A, verificar que empresa B no la ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Gestionar la cartera de efectos (Priority: P1) MVP — cubre FR-001, FR-002, FR-005, FR-006, FR-007

**Goal**: El usuario emite/registra cheques, pagarés y letras con fecha de vencimiento y estado. Al vencimiento liquida el efecto (cobro o impago) generando el asiento correspondiente.

**Independent Test**: Registrando un efecto y liquidándolo al vencimiento se genera el asiento balanceado y el efecto cambia de estado.

### Tests for User Story 1

- [X] T011 [P] [US1] Test cobro efecto balance: `backend/tests/unit/test_efecto_cobro_balance.py` — crear efecto, cobrar, verificar Debe==Haber (572 vs 431); verificar que el efecto cambia a `cobrado`; verificar que asiento_cobro_id se registra
- [X] T012 [P] [US1] Test impago REVERSAL balance: `backend/tests/unit/test_efecto_impago_balance.py` — crear efecto, impagar con gastos, verificar Debe==Haber (431+626 vs 572); sin gastos: Debe 431 | Haber 572; verificar asiento original NO modificado
- [X] T013 [P] [US1] Test transiciones de estado: `backend/tests/unit/test_efecto_estados.py` — emitido→cobrado ok; emitido→impagado ok; cobrado→impagado rechazo; impagado→cobrado rechazo; doble cobro → 409

### Implementation for User Story 1

- [X] T014 [US1] Implementar servicio `registrar_efecto` en `backend/src/services/treasury/efecto.py`: crear Efecto con estado `emitido`, validar ejercicio abierto, validar unicidad de documento, persistir con audit log en transacción ACID
- [X] T015 [US1] Implementar servicio `cobrar_efecto` en `backend/src/services/treasury/efecto.py`: validar estado `emitido`, validar ejercicio abierto, crear asiento Debe 572 | Haber 431 (partida doble validada), cambiar estado a `cobrado`, registrar asiento_cobro_id, todo en transacción ACID
- [X] T016 [US1] Implementar servicio `impagar_efecto` en `backend/src/services/treasury/efecto.py`: validar estado `emitido`, validar ejercicio abierto, crear asiento REVERSAL (Debe 431 [+ 626 si gastos] | Haber 572), cambiar estado a `impagado`, reapertura del vencimiento (SPEC-011) a `pendiente`, todo en transacción ACID con audit log
- [X] T017 [US1] Implementar endpoints en `backend/src/api/treasury/efectos.py`: POST registrar (201), POST cobrar (200), POST impago (200), GET listar cartera (paginación), GET detalle (con asientos)
- [X] T018 [US1] Crear página frontend `frontend/src/app/efectos/nuevo/page.tsx`: formulario de registro de efecto (tipo, tercero, documento, fechas, importe)
- [X] T019 [US1] Crear página frontend `frontend/src/app/efectos/[id]/page.tsx`: detalle de efecto con estado, botones cobrar/impagar, asientos asociados
- [X] T020 [US1] Crear listado frontend `frontend/src/app/efectos/page.tsx`: tabla paginada con filtros (estado, tipo, tercero, fechas), links a detalle
- [X] T021 [US1] Tests integración cobro completo: `backend/tests/integration/test_efecto_cobro_completo.py` — crear efecto, cobrar, verificar asiento balanceado, verificar cambio de estado, verificar auditoría
- [X] T022 [US1] Tests integración impago completo: `backend/tests/integration/test_efecto_impago_completo.py` — crear efecto, impagar con gastos, verificar REVERSAL balanceado, verificar reapertura del vencimiento, verificar que asiento original no fue modificado
- [X] T023 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_efecto_tenant.py` — empresa A crea efecto y lo cobra, empresa B no lo ve; intento de cobrar desde empresa B → 404

**Checkpoint**: User Story 1 completa — cartera de efectos funcional con cobro e impago. MVP desplegable.

---

## Phase 4: User Story 2 — Registrar cobros por TPV/tarjeta y transferencia (Priority: P2) — cubre FR-003

**Goal**: El usuario registra un cobro/pago por tarjeta (TPV) o transferencia directa contra un vencimiento, incluyendo la comisión bancaria. El sistema genera el asiento neto con la cuenta de comisión.

**Independent Test**: Registrando un cobro por tarjeta con comisión se genera el asiento con el neto y la cuenta de gasto de comisión.

### Tests for User Story 2

- [X] T024 [P] [US2] Test cobro TPV con comisión: `backend/tests/unit/test_cobro_medio_comision.py` — crear cobro TARJETA con comisión, verificar Debe==Haber (572 neto + 626 comisión | 430 total); neto = total - comisión; comisión 0 → solo 572 vs 430
- [X] T025 [P] [US2] Test cobro transferencia sin comisión: `backend/tests/unit/test_cobro_transferencia.py` — crear cobro TRANSFERENCIA sin comisión, verificar Debe 572 | Haber 430; comisión = 0

### Implementation for User Story 2

- [X] T026 [P] [US2] Implementar servicio `registrar_cobro_medio` en `backend/src/services/treasury/cobro_medio.py`: recibir vencimiento_id, medio_cobro, fecha_cobro, cuenta, comisión; validar vencimiento `pendiente`, ejercicio abierto; calcular importe_neto; crear asiento Debe 572 (neto) + 626 (comisión) | Haber 430 (total); persistir CobroMedio y ComisionBancaria; todo en transacción ACID
- [X] T027 [US2] Implementar endpoints en `backend/src/api/treasury/cobros_medio.py`: POST registrar (201), GET listar (paginación con filtros), GET detalle (con asiento y comisiones)
- [X] T028 [US2] Crear página frontend `frontend/src/app/tesoreria/cobros/page.tsx`: formulario de cobro por medio con selección de vencimiento, medio, comisión
- [X] T029 [US2] Tests integración cobro TPV completo: `backend/tests/integration/test_cobro_medio_completo.py` — crear vencimiento, cobrar por TARJETA con comisión, verificar asiento balanceado con 626, verificar cambio de estado del vencimiento
- [X] T030 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_cobro_medio_tenant.py` — empresa A cobra con comisión, empresa B no ve el cobro ni la comisión

**Checkpoint**: User Stories 1 y 2 completas — efectos + cobros por medio con comisiones.

---

## Phase 5: User Story 3 — Conciliar medios y estados en tesorería (Priority: P2) — cubre FR-004

**Goal**: El usuario consulta la cartera de efectos y los cobros/pagos por medio para controlar la tesorería y detectar efectos pendientes o impagados.

**Independent Test**: Consultando la cartera, cada efecto muestra su medio, vencimiento y estado correctos.

### Tests for User Story 3

- [X] T031 [P] [US3] Test filtros cartera: `backend/tests/unit/test_cartera_filtros.py` — crear efectos con distintos estados y medios, filtrar por estado→solo los de ese estado; filtrar por tipo→solo los de ese tipo; filtrar por rango fechas→solo los dentro del rango; sin filtros→todos los de la empresa
- [X] T032 [P] [US3] Test agrupación por medio y estado: `backend/tests/unit/test_cartera_agrupacion.py` — verificar que la cartera agrupa correctamente por medio y estado

### Implementation for User Story 3

- [X] T033 [P] [US3] Implementar servicio `consultar_cartera` en `backend/src/services/treasury/cartera.py`: consultar efectos con filtros (estado, tipo, tercero, fechas); agrupar por medio y estado; paginación; retornar totales por grupo
- [X] T034 [US3] Implementar endpoint GET `/api/v1/efectos` con query params de filtros y paginación en `backend/src/api/treasury/efectos.py`
- [X] T035 [US3] Implementar servicio `detalle_cobro_medio` en `backend/src/services/treasury/cobro_medio.py`: retornar cobro con su asiento y desglose de comisiones
- [X] T036 [US3] Crear página frontend `frontend/src/app/tesoreria/page.tsx`: dashboard de tesorería con cartera agrupada por medio y estado
- [X] T037 [US3] Tests integración cartera completa: `backend/tests/integration/test_cartera_completa.py` — crear efectos con distintos estados/medios, consultar cartera, verificar agrupación y filtros; verificar paginación
- [X] T038 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_cartera_tenant.py` — empresa A crea efectos, empresa B no los ve en su cartera

**Checkpoint**: User Stories 1, 2 y 3 completas — flujo total de medios de pago funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T039 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_efectos.py` — verificar que todo asiento (cobro, impago, comisión) tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry confirmado; verificar aislamiento empresa_id en todas las tablas treasury
- [X] T040 [P] Hardening multi-tenant: `backend/tests/integration/test_efectos_full_tenant_isolation.py` — escenario completo cross-empresa (efecto A, cobro B desde A → todos 404)
- [X] T041 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_efectos.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T042 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [X] T043 Validación de ejercicios cerrados: verificar que efectos y cobros rechazan con 409 si el ejercicio está cerrado (SPEC-002/004)
- [X] T044 Limpieza y documentación: actualizar docstrings en servicios treasury, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **US3 (Phase 5)**: Depende de Phase 2; puede empezar en paralelo con US1 y US2.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Sin dependencias de US1/US3; usa Phase 2 completa.
- **US3 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa; integra con US1 y US2 al consultar la cartera.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T007).
- Phase 3: tests [P] en paralelo (T011-T013).
- Phase 4: tests [P] en paralelo (T024-T025).
- Phase 5: tests [P] en paralelo (T031-T032).
- US1, US2, US3 pueden ejecutarse en paralelo por separado una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T011: "Test cobro efecto balance en backend/tests/unit/test_efecto_cobro_balance.py"
Task T012: "Test impago REVERSAL balance en backend/tests/unit/test_efecto_impago_balance.py"
Task T013: "Test transiciones de estado en backend/tests/unit/test_efecto_estados.py"

# Servicios secuenciales (dependen de modelos Phase 2):
Task T014: "registrar_efecto en backend/src/services/treasury/efecto.py"
Task T015: "cobrar_efecto en backend/src/services/treasury/efecto.py"
Task T016: "impagar_efecto en backend/src/services/treasury/efecto.py"

# Frontend en paralelo tras endpoints:
Task T018: "Formulario nuevo efecto en frontend/src/app/efectos/nuevo/page.tsx"
Task T019: "Detalle efecto en frontend/src/app/efectos/[id]/page.tsx"
Task T020: "Listado cartera en frontend/src/app/efectos/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T011-T023. Verificar quickstart Scenario 1 y 2.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP!).
3. + US2 → Test independiente → Deploy/Demo (cobros TPV/transferencia con comisión).
4. + US3 → Test independiente → Deploy/Demo (cartera de efectos).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (efectos + cobro/impago).
   - Dev B: User Story 2 (cobros por TPV/transferencia).
   - Dev C: User Story 3 (cartera de conciliación).
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

---

## Estado real (implementación 2026-09-23)

Vigésimo primera spec cerrada (**44/44**). Verificación: pytest **1261 passed / 5 skipped**
(SQLite; `test_arbol_menos_500ms` de `test_suggest_perf` es flaky bajo carga y pasa
aislado), `ruff` limpio, `mypy` limpio (294 fuentes), `next build` **72 rutas**.

### Archivos creados/realmente tocados

- **Modelos** `backend/src/models/treasury/`: `efecto.py` (`Efecto`, `TipoEfecto`
  CHEQUE/PAGARE/LETRA, `EstadoEfecto` emitido/cobrado/impagado; checks importe>0 y
  `fecha_vencimiento >= fecha_emision`; UNIQUE `(empresa_id, tercero_id, tipo_efecto,
  numero_documento)`; índices `(empresa_id, estado, fecha_vencimiento)` y
  `(empresa_id, tercero_id)`), `cobro_medio.py` (`CobroMedio`, `MedioCobro` de 6 valores;
  checks `importe_total>0`, `importe_comision>=0`, `importe_comision<=importe_total`,
  `importe_neto>=0`; índices por empresa), `comision.py` (`ComisionBancaria`, `TipoComision`
  TPV/TRANSFERENCIA/CHEQUE/CAJA/OTRA; FK compuesta `(empresa_id, cobro_medio_id)`;
  `cuenta_contable` DEFAULT `'626'`).
- **Migración** `backend/migrations/012_efectos.sql` (enums + tablas + índices +
  triggers `trg_efecto_final_immutable_update/_delete` que bloquean UPDATE/DELETE de
  efectos en estado final). Registrada en `backend/src/db/migrate.py`
  (`ORDEN_PREFERENTE`) y en `backend/tests/unit/test_migrations.py` (`ESPERADAS`).
  Espejo SQLite en `backend/src/db/triggers.py`.
- **Servicios** `backend/src/services/treasury/`: `common.py` (`TesoreriaError` +
  constantes de cuenta 430/431/400/401/572/570/626 + `ejercicio_abierto`), `efecto.py`
  (`registrar_efecto`, `cobrar_efecto`, `impagar_efecto`), `cartera.py`
  (`consultar_cartera`, `agrupar_cartera`, `detalle_efecto`), `cobro_medio.py`
  (`registrar_cobro_medio`, `listar_cobros_medio`, `detalle_cobro_medio`).
- **API** `backend/src/api/treasury/`: `efectos.py` (POST/GET/GET id/`/cobrar`/`/impago`)
  y `cobros_medio.py` (POST/GET/GET id); registrados en `routes.py`. Todos con
  `Depends(get_empresa_id)` + `require_permission("treasury", ...)`.
- **Frontend**: `components/treasury/api.ts` (tipos + helpers de efectos y cobros-medio),
  `app/efectos/{page,nuevo,[id]}`, `app/tesoreria/{page,cobros}`, enlaces en `app/page.tsx`.
- **Fixture** `efectos_client` en `backend/tests/conftest.py` (A=10/B=20, PGC sembrado,
  un tercero y dos vencimientos pendientes por empresa, usuario ADMIN en ambas empresas
  y `FiscalYear` 2025 **cerrado** por empresa).

### Desviaciones respecto al plan

- **Impago no tiene vínculo directo a un vencimiento**: el `data-model.md` no incluye
  `vencimiento_id` en `Efecto`, por lo que la reapertura FR-005 se implementa de forma
  *best-effort* reabriendo **todos** los vencimientos del tercero en estado
  `cobrado`/`parcial`/`devuelto` (→ `pendiente`, `acumulado=0`). Documentado aquí y en
  el docstring del servicio.
- **Asientos a bajo nivel**: los asientos de efecto/cobro-medio se construyen con
  `JournalEntry`/`JournalEntryLine` + `verificar_balance` en vez de
  `crear_asiento_multilinea` (que exige cuentas del PGC como enteros y las cuentas
  `431`/`626` no están plantadas como enteros).
- **Nombres de test**: los archivos unit/integration se agruparon
  (`test_efecto_services.py` cubre T011–T013; `test_cobro_medio_services.py` cubre
  T024–T025; `test_cartera.py` cubre T031–T032; `test_efecto_routes.py` cubre
  T021–T023; `test_cobro_medio_routes.py` cubre T029–T030; y
  `test_efectos_full_tenant_isolation.py` cubre T010/T023/T030/T037/T038/T040) en lugar
  de un archivo por tarea con el nombre nominal.
- **T042 (code review)**: los servicios usan el boundary ACID del proyecto
  (`get_db` + `flush()`, equivalente a `async with async_session.begin()`), no la
  construcción literal `async with async_session.begin()` de la tarea. Ningún endpoint
  acepta `empresa_id` del body (solo `Depends(get_empresa_id)`); importes siempre
  `Decimal`/`NUMERIC(18,4)`. Se añadió validación de que el **tercero pertenece a la
  empresa activa** (`tercero_no_encontrado`, 404) como refuerzo de constitución III.
- **T043**: ejercicio cerrado cubierto a nivel servicio y HTTP (quickstart escenario 5).
