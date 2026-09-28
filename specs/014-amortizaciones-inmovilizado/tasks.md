# Tasks: Amortizaciones del Inmovilizado (SPEC-014)

**Input**: Design documents from `/specs/014-amortizaciones-inmovilizado/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`. Endpoints bajo `/api/v1/...` con empresa activa en cabecera de sesión (SPEC-003/015), nunca en path ni body.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar el módulo `inmovilizado` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo `inmovilizado`: `backend/src/models/inmovilizado/__init__.py`, `backend/src/services/inmovilizado/__init__.py`, `backend/src/api/inmovilizado.py`, `backend/src/services/acct/__init__.py` (reutilización del motor SPEC-002, no se crea de nuevo)
- [X] T002 [P] Configurar router `inmovilizado`: registrar prefijo `/api/v1` en `backend/src/api/inmovilizado.py` con dependencies de empresa activa y permisos (SPEC-003/015)
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/inmovilizado/`, `frontend/src/app/inmovilizado/alta/`, `frontend/src/app/inmovilizado/[id]/`, `frontend/src/components/inmovilizado/`, `frontend/src/services/client.ts` (cabecera de empresa activa)
- [X] T004 [P] Crear utils de sesión: `backend/src/api/inmovilizado/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `ActivoInmovilizado` en `backend/src/models/inmovilizado/activo.py`: empresa_id (PK compuesta), numero_activo VARCHAR(40) UNIQUE por empresa, cuenta_id FK → SPEC-001, descripcion, fecha_alta, coste_amortizable NUMERIC(18,4) CHECK > 0, vida_util INT CHECK > 0, metodo ENUM (lineal/regresivo), porcentaje_regresivo NUMERIC(5,2) NULL (requerido si regresivo), estado ENUM (en_uso/dado_de_baja), fecha_baja NULL, cuenta_gasto_id, cuenta_acumulada_id
- [X] T006 [P] Crear modelo `PlanAmortizacion` en `backend/src/models/inmovilizado/plan_amortizacion.py`: empresa_id, activo_id FK compuesta, ejercicio INT, periodo INT, cuota NUMERIC(18,4), acumulado NUMERIC(18,4), estado (pendiente/amortizado); unicidad (empresa_id, activo_id, ejercicio, periodo); CHECK acumulado <= (SELECT coste del activo) — regla reforzada en servicio + test
- [X] T007 [P] Crear modelo `AmortizacionGenerada` en `backend/src/models/inmovilizado/amortizacion_generada.py`: empresa_id, activo_id FK, ejercicio, periodo, asiento_id FK → SPEC-002 JournalEntry, cuota NUMERIC(18,4), reapertura_de UUID NULL; UNIQUE (empresa_id, activo_id, ejercicio, periodo)
- [X] T008 [P] Crear modelo `BajaActivo` en `backend/src/models/inmovilizado/baja_activo.py`: empresa_id, activo_id FK (único), fecha_baja, precio_venta NUMERIC(18,4) CHECK >= 0, amortizacion_hasta_baja, amortizacion_acumulada, valor_neto_contable, resultado, asiento_id FK → SPEC-002, tipo ENUM (venta/retirada)
- [X] T009 [P] Tests de modelos fundacionales: `backend/tests/unit/test_inmovilizado_models.py` — verificar unicidad numero_activo por empresa, UNIQUE (activo, ejercicio, periodo) en plan y generada, CHECK coste > 0, FK compuestas empresa_id
- [X] T010 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_inmovilizado_tenant_models.py` — crear activo y plan en empresa A, verificar que empresa B no los ve en activos/plan/generadas/bajas

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Dar de alta un activo fijo (Priority: P1) ?? MVP

**Goal**: El usuario registra un elemento del inmovilizado (21x) con coste, vida útil, método y fecha; el sistema calcula y valida el plan de amortización.

**Independent Test**: Alta de un activo con método y vida útil correctos genera el plan con la cuota calculada y validada (sin exceder el coste; regresivo con cuotas decrecientes).

### Tests for User Story 1

- [X] T011 [P] [US1] Test cálculo plan lineal: `backend/tests/unit/test_plan_lineal.py` — 60 cuotas `Decimal("250.0000")` para 15.000/60; acumulado final exacto; última cuota ajustada a `coste − Σ previas` si hay resto de redondeo
- [X] T012 [P] [US1] Test cálculo plan regresivo: `backend/tests/unit/test_plan_regresivo.py` — cuotas decrecientes con % sobre valor residual; acumulado final == coste; ninguna cuota negativa; tope `acumulado <= coste` (FR-006)
- [X] T013 [P] [US1] Test validación de alta: `backend/tests/unit/test_alta_activo.py` — coste <= 0 → 422; vida_util <= 0 → 422; regresivo sin porcentaje → 422; porcentaje fuera de (0,100) → 422
- [X] T014 [P] [US1] Test aislamiento US1: `backend/tests/integration/test_activo_tenant.py` — empresa A da de alta y ve su activo/plan; empresa B no lo ve, ni por número ni por id (404)

### Implementation for User Story 1

- [X] T015 [US1] Implementar servicio de cálculo de plan en `backend/src/services/inmovilizado/plan.py`: función `calcular_plan(coste, vida_util, metodo, porcentaje, fecha_alta, config_empresa) -> list[Cuota]` con `Decimal` y contexto `ROUND_HALF_EVEN`; prorrateo inicial según config (mensual o por días); ajuste de última cuota; validación `acumulado <= coste`
- [X] T016 [US1] Implementar servicio de alta/edición en `backend/src/services/inmovilizado/activo.py`: validar cuenta 21x y grupos 681/281 del plan de la empresa activa; calcular plan; persistir reactivo + plan en una sola transacción ACID con audit; `editar_activo` recalcula el plan futuro desde el próximo período (constitución II)
- [X] T017 [US1] Implementar `POST /api/v1/activos`, `POST /api/v1/activos/plan/calcular`, `GET /api/v1/activos`, `GET /api/v1/activos/{id}`, `PATCH /api/v1/activos/{id}` en `backend/src/api/inmovilizado.py`
- [X] T018 [US1] Crear página frontend `frontend/src/app/inmovilizado/alta/page.tsx`: formulario (cuenta 21x, coste, vida útil, método, % si regresivo, fecha alta) con preview del plan calculado
- [X] T019 [US1] Crear detalle frontend `frontend/src/app/inmovilizado/[id]/page.tsx`: datos del activo, tabla del plan con estado, acción editar
- [X] T020 [US1] Crear listado frontend `frontend/src/app/inmovilizado/page.tsx`: tabla paginada con filtros (estado/cuenta), links a detalle
- [X] T021 [US1] Tests integración alta completa: `backend/tests/integration/test_alta_activo_completa.py` — alta → 201 con plan validado; calcular_plan sin persistir; PATCH recalculca plan futuro sin tocar posteados
- [X] T022 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_activo_tenant.py` — escenario completo: A alta y edita, B no ve plan ni activo; B intenta alta con el numero_activo de A → sin conflicto ni exposición (independiente por empresa)

**Checkpoint**: User Story 1 completa — alta de activos con plan calculado y validado. MVP desplegable.

---

## Phase 4: User Story 2 — Generar los asientos de amortización del período (Priority: P1)

**Goal**: El usuario genera los asientos 681/281 del período para los activos en uso, balanceados y sin duplicados, restringidos al ejercicio abierto.

**Independent Test**: Generando la amortización de un período se crean asientos balanceados 681/281 y no se duplican para el mismo período; un período ya amortizado se bloquea o se reabre con trazabilidad.

### Tests for User Story 2

- [X] T023 [P] [US2] Test balance asiento amortización: `backend/tests/unit/test_asiento_amortizacion_balance.py` — cada asiento 681/281 tiene Debe==Haber exacto en `Decimal`; importe = cuota del plan; acumulado correcto
- [X] T024 [P] [US2] Test antidupilcación: `backend/tests/unit/test_no_duplicados_amortizacion.py` — generar dos veces el mismo (activo, ejercicio, periodo) → 409; constraint UNIQUE no violable
- [X] T025 [P] [US2] Test ejercicio cerrado: `backend/tests/unit/test_ejercicio_cerrado_amortizacion.py` — generar para ejercicio cerrado → 409 (SPEC-004)
- [X] T026 [P] [US2] Test reapertura con REVERSAL: `backend/tests/unit/test_reabrir_amortizacion.py` — reabrir genera `REVERSAL` balanceado enlazado al asiento previo; el previo no se modifica (constitución II); regeneración marca `reapertura_de`
- [X] T027 [P] [US2] Test aislamiento US2: `backend/tests/integration/test_amortizacion_tenant.py` — A genera; B no ve generadas ni asientos de A; B intenta generar para el activo de A → 404

### Implementation for User Story 2

- [X] T028 [US2] Implementar servicio `generar_amortizacion(ejercicio, periodo)` en `backend/src/services/inmovilizado/generacion.py`: seleccionar activos `en_uso` de la empresa activa con fila del plan pendiente; validar ejercicio abierto; crear asiento 681 (Debe) / 281 (Haber) por activo vía motor SPEC-002 en la misma transacción `async with async_session.begin()`; insertar `AmortizacionGenerada`; marcar plan → amortizado; audit
- [X] T029 [US2] Implementar servicio `reabrir_amortizacion(id)` en `backend/src/services/inmovilizado/generacion.py`: generar `REVERSAL` del asiento previo (SPEC-002), desmarcar plan, registrar `reapertura_de` (solo ejercicio abierto; 409 en cerrado)
- [X] T030 [US2] Implementar `POST /api/v1/amortizaciones/generar`, `GET /api/v1/amortizaciones`, `POST /api/v1/amortizaciones/{id}/reabrir` en `backend/src/api/inmovilizado.py`
- [X] T031 [US2] Implementar dependencia de ejercicio abierto en `backend/src/services/inmovilizado/generacion.py`: verificar SPEC-004 (cierre) antes de crear asientos; rechazo 409 si cerrado
- [X] T032 [US2] Crear página frontend `frontend/src/app/inmovilizado/amortizaciones/page.tsx`: selección de ejercicio/período, botón generar, listado de generadas, acción reabrir con motivo
- [X] T033 [US2] Tests integración generación completa: `backend/tests/integration/test_generacion_completa.py` — generar período con 2 activos → 2 asientos balanceados, planes `amortizado`; regenerar → 409; reabrir → REVERSAL + regeneración
- [X] T034 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_amortizacion_tenant.py` — escenario completo: A genera sus 2 activos; B no ve generadas ni asientos; B genera para su empresa sin mezclar numeración (SPEC-002 por empresa+ejercicio)

**Checkpoint**: User Stories 1 y 2 completas — alta con plan y generación de asientos 681/281 sin duplicados.

---

## Phase 5: User Story 3 — Baja de un activo y ajuste (Priority: P2)

**Goal**: El contador registra la baja/venta; el sistema calcula la amortización hasta la fecha, el VNC y genera el asiento de baja balanceado con resultado.

**Independent Test**: Bajando un activo se registra su amortización hasta la baja y el asiento de baja cuadra con el valor neto contable.

### Tests for User Story 3

- [X] T035 [P] [US3] Test prorrateo hasta la baja: `backend/tests/unit/test_baja_prorrateo.py` — prudiente cuota parcial a la fecha de baja según config mensual/días; acumulado a la baja coherente con el plan
- [X] T036 [P] [US3] Test asiento de baja balanceado: `backend/tests/unit/test_baja_asiento.py` — Debe 281 (acumulado) + 572 (precio) | Haber 21x (coste) con saldo en 671 (pérdida) o 771 (beneficio); Debe==Haber exacto en `Decimal`; `resultado = precio − VNC`
- [X] T037 [P] [US3] Test baja saca del plan: `backend/tests/unit/test_baja_sale_plan.py` — tras baja, generar no incluye el activo; no se genera más cuotas (FR-005)
- [X] T038 [P] [US3] Test aislamiento US3: `backend/tests/integration/test_baja_tenant.py` — empresa B no puede dar de baja el activo de A (404); B no ve la baja de A

### Implementation for User Story 3

- [X] T039 [US3] Implementar servicio `dar_de_baja` en `backend/src/services/inmovilizado/baja.py`: prorratear amortización hasta fecha de baja; calcular acumulado, VNC y resultado con `Decimal`; crear asiento de baja balanceado vía SPEC-002 (Debe 281 + 572/570; Haber 21x; saldo 671/771); marcar activo `dado_de_baja` con fecha; todo en transacción ACID con audit
- [X] T040 [US3] Implementar `POST /api/v1/activos/{id}/baja` en `backend/src/api/inmovilizado.py`
- [X] T041 [US3] Crear frontend `frontend/src/app/inmovilizado/[id]/baja/page.tsx`: formulario fecha/precio/tipo, preview del asiento (281, 572, VNC, resultado), confirmación
- [X] T042 [US3] Tests integración baja completa: `backend/tests/integration/test_baja_completa.py` — amortizar hasta baja (parcial), calcular VNC, generar asiento balanceado donde izquierda = derecha, estado `dado_de_baja`, activo fuera de las siguientes generaciones
- [X] T043 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_baja_tenant.py` — escenario completo: A da de baja su activo; B no ve la baja ni el asiento (404)

**Checkpoint**: User Stories 1, 2 y 3 completas — ciclo de vida completo del inmovilizado (alta, plan, amortización, baja).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación constitucional y robustez.

- [X] T044 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_inmovilizado.py` — verificar que todo asiento (amortización y baja) tiene Debe==Haber; verificar que ningún `JournalEntry` `POSTED` se actualiza/borra (reapertura usa REVERSAL); verificar aislamiento empresa_id en todas las tablas de inmovilizado
- [X] T045 [P] Hardening multi-tenant: `backend/tests/integration/test_inmovilizado_full_tenant_isolation.py` — escenario completo cross-empresa (activo de A, generación de B, baja de A desde B → todos 404)
- [X] T046 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_inmovilizado.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T047 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint deriva `empresa_id` de path/body; verificar Decimal/NUMERIC(18,4) en cuotas, acumulados y valores; verificar que la creación de asientos delega en el motor SPEC-002
- [X] T048 Validar FR-006 a escala: `backend/tests/unit/test_coste_amortizable_tope.py` — planes con redondeo (costes no divisibles), revalorizaciones y correcciones: el acumulado nunca excede el coste en ninguna fila (constitución + FR-006)
- [X] T049 Limpieza y documentación: actualizar docstrings en servicios `inmovilizado`, verificar type hints, ejecutar lint/typecheck; revisar fixtures de cálculo (plans calculados a mano)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1 (los tests de balance/antiduplicado dependen del plan del US1 para generarlo con datos, pero los models y el servicio de generación son independientes).
- **US3 (Phase 5)**: Depende de Phase 2; en la práctica requiere el plan del US1 y los asientos del US2 para la integración (VNC acumulado), aunque el cálculo puede desarrollarse en paralelo.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Depende del plan del US1 (genera asientos sobre activos con plan) y del motor SPEC-002; usa Phase 2 completa.
- **US3 (P2)**: Depende del plan y de los asientos acumulados (VNC); usa Phase 2 completa.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios (plan → generación → baja) antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T008).
- Phase 3: tests [P] en paralelo (T011-T014), plan + alta [P] (T015-T016).
- Phase 4: tests [P] en paralelo (T023-T027), generación + reapertura [P] (T028-T029).
- Phase 5: tests [P] en paralelo (T035-T038), servicio baja [P] (T039).
- US1 puede ejecutarse antes de US2/US3; US2 y US3 dependen de US1 para datos pero sus cálculos se prueban en paralelo con fixtures.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T011: "Test plan lineal en backend/tests/unit/test_plan_lineal.py"
Task T012: "Test plan regresivo en backend/tests/unit/test_plan_regresivo.py"

# Servicios en paralelo:
Task T015: "Cálculo de plan en backend/src/services/inmovilizado/plan.py"
Task T016: "Servicio alta/edición en backend/src/services/inmovilizado/activo.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T011-T022. Verificar quickstart Scenario 1 y 2.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (alta de activos con plan).
3. + US2 → Test independiente → Deploy/Demo (asientos 681/281 automáticos).
4. + US3 → Test independiente → Deploy/Demo (baja/venta con resultado).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (alta + plan).
   - Dev B: User Story 2 (generación 681/281) tras el modelo de plan.
   - Dev C: User Story 3 (baja/venta) tras el modelo de plan.
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
- La numeración correlativa de asientos la garantiza SPEC-002 (constitución IV), no este módulo.
- Los ajustes de última cuota garantizan FR-006 (acumulado <= coste) en todos los planes.

---

## Estado real (implementación 2026-09-21)

49/49 tareas cerradas (corrección 2026-09-24: los docs decían 45/45 por error de
conteo; el fichero siempre listó T001–T049). **15ª spec completa** (total proyecto
714/1.384; corregido a 718/1.384). Verificada: pytest **820 passed / 5 skipped** (SQLite)
y **825 passed / 0 skipped** (PostgreSQL 16.4 real), `ruff` + `mypy` limpios (207 fuentes),
`next build` con las 4 rutas de inmovilizado.

- **Estructura API**: paquete `backend/src/api/inmovilizado/` (NO `api/inmovilizado.py`): `deps.py`, `activos.py` (POST `/activos`, POST `/activos/plan/calcular`, GET `/activos`, GET/PATCH `/activos/{id}`, POST `/activos/{id}/baja`) y `amortizaciones.py` (POST `/amortizaciones/generar`, GET `/amortizaciones`, `POST /amortizaciones/{id}/reabrir`), router global con prefix `/api/v1` en `routes.py` + `Depends(get_empresa_id)`; registrado en `main.py`.
- **Transacciones**: servicios hacen `flush()` dentro del boundary `get_db` (patrón del proyecto, constitución III); no usan `async with async_session.begin()` dentro del servicio (desviación textual de T028).
- **Plan**: firma `calcular_plan(coste, vida_util, metodo, porcentaje, fecha_alta, prorrateo="mensual"|"dias")` — el prorrateo es kwarg, no tabla de config de empresa (no se creó). Devuelve filas con `cuota`/`acumulado` como **strings de 4 decimales** (contrato API); posterior `Decimal(...)` al persistir. Regresivo = simulación natural hasta residual 0 con `LIMITE_ROWS_REGRESIVO=1200` (puede dar menos de `vida_util` filas); `replanear_pendientes` + `_replanear` en `activo.py` alinean el conteo tras PATCH (borran sobrantes con `del` — no rebind, el caller conserva la lista).
- **Modelo `AmortizacionGenerada`**: UNIQUE parcial `(empresa_id, activo_id, ejercicio, periodo)` WHERE `reabierta = false` (permite la cadena reapertura→regeneración), además de `reabierta`/`reapertura_de`/`created_at`.
- **Reapertura**: crea su propio `JournalEntry` REVERSAL (invertido, `original_id` enlazado, POSTED, `next_numero`, fecha = fin del periodo) **sin cambiar el estado** del original (permanece POSTED — desviación de `reversal.anular`, que marca CANCELLED). La fila original se marca `reabierta=True` y la regenerada enlaza `reapertura_de` → original (trazabilidad esperada en tests: original `reapertura_de=None, reabierta=True`).
- **Anti-duplicado**: `generar` devuelve **409 `periodo_ya_amortizado`** cuando no hay filas pendientes para (ejercicio, periodo); con omisiones parciales (no saldo, ejercicio cerrado, sin fila pendiente) 200 con `{generados, omitidos[]}` (motivo+code). Sin actividad devuelve `{generados: [], omitidos: [], sin_amortizaciones: true}`.
- **Baja**: asiento Debe 281X + 5720 (+ resultado 6710 pérdida / 7710 beneficio) | Haber 21X; `fraccion_cuota_baja(fecha_baja, prorrateo)` para días; **422 `fecha_baja_invalida`** si fecha anterior al alta; resultado = precio − VNC.
- **Cuentas por defecto**: gasto `6810`; acumulada derivada `CUENTA_ACUMULADA_PREFIJO + code[1:3]` (2100→2810, 2180→2818). El seed PGC **no se modifica**; `dar_de_alta` solo valida nivel 4 2xx apuntables. Fixtures plantan 218/2180/281/2818, 671/6710 y 771/7710.
- **Aislamiento**: fixture `inmovilizado_client` en `backend/tests/conftest.py` (tenants 10/20, IDs UUID fijos, `_cuentas(_)`, `_plan(_)`, `_crear(_)`, `_plantar_inmovilizado(_)`); helper `_plantar_para(_)`. **49 tests nuevos** (13 unit + 34 integration en `test_inmovilizado_generacion_baja_api.py` + 2 más).
- **Frontend**: `components/inmovilizado/api.ts`, `app/inmovilizado/{page,alta/,[id]/}` y `app/inmovilizado/amortizaciones/page.tsx` (lista + selección ejercicio/periodo + reabrir). El detalle `[id]` muestra el plan en lectura (los plan rows no llevan `generada_id`; la reapertura se hace desde la página de amortizaciones, que sí tiene los ids). Nav de `/` enlaza a `/inmovilizado`.
- **Lecciones**: `AccountPlan` se consulta por `tenant_id` (SPEC-001); la empresa activa siempre vía `Depends(get_empresa_id)`; `listar_amortizaciones` usa `select(AmortizacionGenerada).where(*filtros)` (evitar NameError de variables sueltas); los miembros de enum no admiten anotación `: str` (mypy); rama `porcentaje = None` exige `assert porcentaje_dec is not None` antes de `Decimal`.