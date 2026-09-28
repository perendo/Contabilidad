# Tasks: Multi-Divisa (SPEC-016)

**Input**: Design documents from `/specs/016-multi-divisa/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`; tipos de cambio `NUMERIC(18,8)`. Endpoints bajo `/api/v1/...` con empresa activa en cabecera de sesión (SPEC-003/015), nunca en path ni body.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar el módulo `forex` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo `forex`: `backend/src/models/monedas/__init__.py`, `backend/src/services/forex/__init__.py`, `backend/src/api/forex.py`, `backend/src/api/acct/` (reutilización del motor SPEC-002, no se crea de nuevo)
- [X] T002 [P] Configurar router `forex`: registrar prefijo `/api/v1` en `backend/src/api/forex.py` con dependencies de empresa activa y permisos (SPEC-003/015)
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/divisas/`, `frontend/src/app/divisas/tipos/`, `frontend/src/app/divisas/asientos/`, `frontend/src/app/divisas/valoracion/`, `frontend/src/components/forex/`, `frontend/src/services/client.ts` (cabecera de empresa activa)
- [X] T004 [P] Crear utils de sesión: `backend/src/api/forex/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `Moneda` en `backend/src/models/monedas/moneda.py`: id, empresa_id (PK compuesta), codigo_iso CHAR(3) CHECK ISO 4217, es_funcional BOOLEAN, activa BOOLEAN; una sola funcional por empresa (índice parcial único); unicidad (empresa_id, codigo_iso)
- [X] T006 [P] Crear modelo `TipoCambio` en `backend/src/models/monedas/tipo_cambio.py`: id, empresa_id, divisa_id FK, fecha DATE, ratio NUMERIC(18,8) CHECK > 0, usos_posteados INT DEFAULT 0, sellado BOOLEAN DEFAULT false; UNIQUE (empresa_id, divisa_id, fecha); CHECK sellado = (usos_posteados > 0)
- [X] T007 [P] Crear modelo `AsientoDivisa` en `backend/src/models/monedas/asiento_divisa.py`: id, empresa_id, asiento_id FK → SPEC-002 JournalEntry (uno a uno), divisa_id FK, tipo_cambio_id FK, fecha DATE, importe_total_divisa NUMERIC(18,4), importe_total_funcional NUMERIC(18,4)
- [X] T008 [P] Crear modelo `LineaDivisa` en `backend/src/models/monedas/asiento_divisa.py`: id, empresa_id, asiento_divisa_id FK compuesta, linea_id FK → SPEC-002 JournalEntryLine, importe_divisa NUMERIC(18,4), importe_funcional NUMERIC(18,4), es_linea_redondeo BOOLEAN DEFAULT false
- [X] T009 [P] Crear modelo `DiferenciaCambio` en `backend/src/models/monedas/diferencia_cambio.py`: id, empresa_id, ejercicio, fecha_valoracion, cuenta_id FK, divisa_id FK, saldo_divisa, saldo_funcional_previo, tipo_cierre_id FK, saldo_funcional_valorado, diferencia, asiento_id FK → SPEC-002, estado (calculada/asentada); UNIQUE (empresa_id, ejercicio, fecha_valoracion, cuenta_id, divisa_id)
- [X] T010 [P] Tests de modelos fundacionales: `backend/tests/unit/test_moneda_models.py` — verificar una sola funcional por empresa, UNIQUE (empresa, divisa, fecha), FK compuestas empresa_id, CHECK sellado ↔ usos, UNIQUE valoración
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_moneda_tenant_models.py` — monedas/tipos/asientos-divisa/diferencias de A invisibles para B en todas las consultas

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Asentar operaciones en moneda extranjera (Priority: P1) ?? MVP

**Goal**: El usuario registra un asiento en divisa; el sistema guarda importe en divisa y funcional con el tipo de la fecha, cuadrando la partida doble en ambas.

**Independent Test**: Registrando un asiento en divisa con su tipo de cambio, el asiento cuadra en divisa y en moneda funcional.

### Tests for User Story 1

- [X] T012 [P] [US1] Test conversión y redondeo: `backend/tests/unit/test_conversion.py` — ratio 1.085 → equivalente `Decimal` exacto con `ROUND_HALF_EVEN` a 4 decimales; casos con remanente imputado a línea de redondeo
- [X] T013 [P] [US1] Test cuadre doble moneda: `backend/tests/unit/test_cuadre_doble_moneda.py` — Debe==Haber en divisa Y funcional (fixtures con cuadre a mano); asiento con desbalance → rechazado (backend, no UI)
- [X] T014 [P] [US1] Test tipo de la fecha: `backend/tests/unit/test_tipo_fecha.py` — sin tipo para la fecha y sin tipo explícito → 422; tipo explícito persistido y sellado en la misma transacción
- [X] T015 [P] [US1] Test aislamiento US1: `backend/tests/integration/test_asiento_divisa_tenant.py` — asiento de A no visible para B (404); B no puede usar el tipo de A

### Implementation for User Story 1

- [X] T016 [US1] Implementar servicio de conversión en `backend/src/services/forex/conversion.py`: función pura `convertir(importe_divisa, ratio, contexto_redondeo) -> Decimal` y `linea_redondeo(total_exacto, lineas)` que imputa el remanente (cuenta 668/769) sin romper el balance
- [X] T017 [US1] Implementar servicio de tipos en `backend/src/services/forex/tipos.py`: registro (validar UNIQUE empresa+divisa+fecha), PATCH de tipo sin sellar (audit), consulta/historial, y `obtener_tipo_fecha_flexible` (existente o explícito del body)
- [X] T018 [US1] Implementar servicio `registrar_asiento_divisa` en `backend/src/services/forex/asiento_divisa.py`: convertir líneas, validar cuadre doble, crear asiento via motor SPEC-002 (numeración correlativa), persistir AsientoDivisa + LineaDivisa, sellar el tipo con contador, auditoría; todo en una transacción `async with async_session.begin()`
- [X] T019 [US1] Implementar endpoints en `backend/src/api/forex.py`: `GET /api/v1/divisas`, `POST /api/v1/divisas`, `POST /api/v1/tipos-cambio`, `PATCH /api/v1/tipos-cambio/{id}`, `GET /api/v1/tipos-cambio`, `POST /api/v1/asientos-divisa`, `GET /api/v1/asientos-divisa/{id}`
- [X] T020 [US1] Crear frontend `frontend/src/app/divisas/asientos/nuevo/page.tsx`: entrada de líneas en divisa con equivalencia funcional preview, selección de tipo (o ratio explícito), alerta de línea de redondeo
- [X] T021 [US1] Crear frontend `frontend/src/app/divisas/tipos/page.tsx`: alta/consulta de tipos por divisa y fecha, indicador `sellado`
- [X] T022 [US1] Tests integración asiento divisa completo: `backend/tests/integration/test_asiento_divisa_completa.py` — registrar con tipo existente y con tipo explícito; verificar cuadre en ambas monedas y sellado del tipo; asiento consultable por detalle (divisa/ratio/funcional)
- [X] T023 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_asiento_divisa_tenant.py` — escenario completo: A registra su asiento; B no ve asiento ni tipo; B registra el suyo sin mezclar numeración (SPEC-002 por empresa+ejercicio)

**Checkpoint**: User Story 1 completa — registro de asientos en divisa con cuadre doble. MVP desplegable.

---

## Phase 4: User Story 2 — Valorar saldos en divisa a cierre (Priority: P2)

**Goal**: Al cierre, el contador valora los saldos en divisa pendientes con el tipo de cierre y se genera el asiento de diferencias de cambio de forma balanceada.

**Independent Test**: Valuando saldos en divisa a cierre, la diferencia de cambio se calcula exacta y se asienta balanceada.

### Tests for User Story 2

- [X] T024 [P] [US2] Test cálculo de diferencias: `backend/tests/unit/test_diferencia_cambio.py` — `diferencia = saldo_divisa × tipo_cierre − saldo_funcional_previo` con `Decimal`; signo correcto (pérdida 668 / ganancia 769); 4 decimales exactos
- [X] T025 [P] [US2] Test asiento de diferencia balanceado: `backend/tests/unit/test_asiento_diferencia.py` — Debe==Haber exacto; vinculo al cierre (SPEC-004); sin modificación de saldos previos (constitución II)
- [X] T026 [P] [US2] Test validaciones de valoración: `backend/tests/unit/test_valoracion_validaciones.py` — ejercicio cerrado → 409; sin tipo de cierre → 422; valoración duplicada (ejercicio, fecha, cuenta, divisa) → 409
- [X] T027 [P] [US2] Test aislamiento US2: `backend/tests/integration/test_valoracion_tenant.py` — valoración de A invisible para B; B no valora los saldos de A (404)

### Implementation for User Story 2

- [X] T028 [US2] Implementar servicio `valorar_saldos_cierre` en `backend/src/services/forex/valoracion.py`: iterar saldos vivos por cuenta en divisa de la empresa activa, verificar tipo de cierre, computar diferencia, crear asiento balanceado (Debe 668 o Haber 769) via SPEC-002 vinculado al cierre, persistir `DiferenciaCambio` única por período, auditoría; transacción ACID
- [X] T029 [US2] Implementar endpoints en `backend/src/api/forex.py`: `POST /api/v1/valoraciones`, `GET /api/v1/diferencias-cambio`
- [X] T030 [US2] Crear frontend `frontend/src/app/divisas/valoracion/page.tsx`: selección de ejercicio/fecha, preview de diferencias por cuenta/divisa, ejecución y listado de valoraciones
- [X] T031 [US2] Tests integración valoración completa: `backend/tests/integration/test_valoracion_completa.py` — con saldos vivos en USD y tipo de cierre, genera asiento balanceado 668/769, `DiferenciaCambio` persistida, segunda llamada → 409
- [X] T032 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_valoracion_tenant.py` — escenario completo: A valora y asienta; B no ve la valoración ni el asiento; B valora sus propios saldos sin mezcla

**Checkpoint**: User Stories 1 y 2 completas — divisa y valoración a cierre funcionales.

---

## Phase 5: User Story 3 — Cambios históricos del tipo de cambio (Priority: P2)

**Goal**: El usuario consulta los tipos aplicados por fecha y divisa, y el sistema bloquea la modificación del tipo usado en asientos posteados.

**Independent Test**: Consultando el tipo de una fecha de un asiento posteado, es el mismo y no se puede alterar.

### Tests for User Story 3

- [X] T033 [P] [US3] Test histórico por divisa/fecha: `backend/tests/unit/test_historial_tipos.py` — consultas por divisa, rango y sellado; los tipos sellados siguen visibles en el histórico
- [X] T034 [P] [US3] Test inmutabilidad del tipo: `backend/tests/unit/test_inmutabilidad_tipo.py` — PATCH/DELETE de un tipo con usos_posteados > 0 → 409; violación directa en base de datos rechazada (constraint)
- [X] T035 [P] [US3] Test historial por asiento: `backend/tests/unit/test_historial_asiento.py` — el tipo consultado por asiento id coincide con el usado y es `sellado=true` (FR-003/SC-002)
- [X] T036 [P] [US3] Test aislamiento US3: `backend/tests/integration/test_tipos_tenant.py` — empresa B no ve el historial de A; B no puede corregir un tipo de A (404)

### Implementation for User Story 3

- [X] T037 [US3] Implementar servicio de consulta histórica en `backend/src/services/forex/tipos.py`: `historial(filtros)`, `historial_por_asiento(asiento_id)` y `corregir_tipo(id, ratio, motivo)` que solo actúa sobre tipos sin sellar (audit si parsea)
- [X] T038 [US3] Implementar endpoints en `backend/src/api/forex.py`: `GET /api/v1/tipos-cambio/historial?asiento_id=...` (reproduce el tipo usado por cada asiento posteado)
- [X] T039 [US3] Aplicar bloqueo de sellado en el servicio de escritura: `backend/src/services/forex/tipos.py` — antes de PATCH, verificar `sellado`; 409 con motivo; el contador de usos se incrementa solo en la transacción de posteado del asiento (T018)
- [X] T040 [US3] Crear frontend `frontend/src/app/divisas/tipos/historial/page.tsx`: tabla por divisa/fecha con estado sellado y consulte por asiento
- [X] T041 [US3] Tests integración histórico completo: `backend/tests/integration/test_historial_completa.py` — tras postear asiento, el tipo aparece sellado en el histórico y su modificación → 409 (API y DB); consulta por asiento devuelve el mismo ratio
- [X] T042 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_tipos_tenant.py` — escenario completo: A sella y blokea; B no ve tipos ni historial de A; B no puede corregir tipos de A (404)

**Checkpoint**: User Stories 1, 2 y 3 completas — multi-divisa funcional con histórico inmutable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación constitucional y robustez.

- [X] T043 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_forex.py` — verificar cuadre doble (Debe==Haber en divisa y funcional) en cada asiento divisa y de diferencia; verificar que nunca se modifica/borra un `JournalEntry` `POSTED` ni un tipo sellado; verificar aislamiento empresa_id en todas las tablas forex
- [X] T044 [P] Hardening multi-tenant: `backend/tests/integration/test_forex_full_tenant_isolation.py` — escenario completo cross-empresa (asiento divisa de A, valoración de B, tipo de A corregido por B → todos 404/409)
- [X] T045 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_forex.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T046 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que el sellado del tipo ocurre en la misma transacción que el posteo del asiento; verificar Decimal/NUMERIC(18,4) y NUMERIC(18,8) en importes y ratios; verificar que ningún endpoint deriva `empresa_id` de path/body
- [X] T047 Validar regla de redondeo a escala: `backend/tests/unit/test_redondeo_nunca_desequilibra.py` — batería de asientos con remanentes (tipos con 8 decimales, líneas múltiples, importes extremos) probando el invariante de doble balance (constitución I)
- [X] T048 Limpieza y documentación: actualizar docstrings en servicios `forex`, verificar type hints, ejecutar lint/typecheck; revisar fixtures de tipos y de cuadre doble (calculados a mano)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa y del marco de asientos SPEC-002.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1 (el cálculo de diferencias es independiente, pero la integración requiere tipos y saldos del US1).
- **US3 (Phase 5)**: Depende de Phase 2; puede empezar en paralelo con US1/US2 (el histórico y el sellado se integran con las escrituras de US1).
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa + motor SPEC-002.
- **US2 (P2)**: Depende de los saldos en divisa del US1; usa Phase 2 completa.
- **US3 (P2)**: Depende de los asientos del US1 para sellar tipos; usa Phase 2 completa; sin dependencia de US2.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios (conversión → tipos → registro/valoración) antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: modelos [P] en paralelo (T005-T009).
- Phase 3: tests [P] en paralelo (T012-T015), conversión + tipos [P] (T016-T017).
- Phase 4: tests [P] en paralelo (T024-T027), valoración [P] (T028).
- Phase 5: tests [P] en paralelo (T033-T036), histórico + sellado [P] (T037-T039).
- US1 sienta la base de asientos/tipos; US2 y US3 se integran después con datos de US1 pero sus cálculos se prueban en paralelo con fixtures.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T012: "Test conversión/redondeo en backend/tests/unit/test_conversion.py"
Task T013: "Test cuadre doble moneda en backend/tests/unit/test_cuadre_doble_moneda.py"

# Servicios en paralelo:
Task T016: "Conversión en backend/src/services/forex/conversion.py"
Task T017: "Tipos de cambio en backend/src/services/forex/tipos.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T012-T023. Verificar quickstart Scenario 1, 2 y 3.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (asientos en divisa con cuadre doble).
3. + US2 → Test independiente → Deploy/Demo (valoración y diferencias de cambio).
4. + US3 → Test independiente → Deploy/Demo (histórico inmutable de tipos).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (conversión + registro en divisa).
   - Dev B: User Story 2 (valoración a cierre) tras el modelo de tipos.
   - Dev C: User Story 3 (histórico + sellado) tras el modelo de asiento divisa.
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
- La regla de redondeo half-even por empresa es configuración; la línea de redondeo (668/769) garantiza que ningún remanente desequilibre el asiento (constitución I).
---

## Estado real (implementación 2026-09-22)

T048 tareas marcadas `[X]` y puertas en verde. Desviaciones documentadas frente
a este `tasks.md`:

1. **Paquete de API**: las tareas citan `backend/src/api/forex.py` (fichero);
   la implementación usa el paquete `backend/src/api/forex/` (`__init__.py`,
   `deps.py`, `routes.py`) registrado en `main.py` bajo `/api/v1`. Función
   equivalente, citación de archivo que no se cumple literalmente.
2. **Transacción ACID (T018/T028/T046)**: las tareas citan `async with
   async_session.begin()`; el proyecto usa el boundary compartido `get_db`
   (`backend/src/database.py`) con `flush()` dentro del servicio (patrón de
   todas las specs). El sellado del tipo ocurre en la misma transacción que el
   posteo del asiento (`sellar_tipo` en `registrar_asiento_divisa` antes del
   flush final) — verificado en T046.
3. **Ratios**: tareas citan `ratio_explicito`/`TipoCambio.ratio` con
   `NUMERIC(18,8)`; el body JSON del endpoint `POST /asientos-divisa` pasa el
   ratio explícito anidado en `tipo_ratio_explicito: {ratio}` (contract
   `api-contracts.md`), no plano en la raíz.
4. **`PATCH /tipos-cambio/{id}`**: entries del listado usan `serializar_tipo`
   que no expone `auditado`; los tests de T034/T041 NO asientan `auditado` en
   la respuesta (el 409 sí cubre el sellado por API y por constraint de DB).
5. **Ubicación de tests**: T045 (`test_quickstart_forex.py`) y T047
   (`test_redondeo_nunca_desequilibra.py`) se ubicaron en
   `tests/integration/` en vez de `tests/unit/` como cita la tarea; el resto
   de ficheros siguen su ruta citada.

### Verificación (2026-09-22)

- pytest: **965 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky bajo
  carga, verde aislado).
- ruff + mypy limpios (236 fuentes). `next build` **54 rutas** (5 nuevas:
  `/divisas`, `/divisas/tipos`, `/divisas/tipos/historial`,
  `/divisas/asientos/nuevo`, `/divisas/valoracion`).
- Corregido en esta sesión: `uq_diferencia_cierre_unica` incluía solo
  `(empresa, ejercicio, fecha)` e impedía más de una cuenta/divisa por
  valoración; ampliado a `(empresa_id, ejercicio, fecha_valoracion,
  cuenta_id, divisa_id)` en el modelo `diferencia_cambio.py` y en
  `migrations/008_forex.sql`.
- Lección reutilizable: `sqlite_where`/`postgresql_where` de los índices
  parciales deben envolverse en `text(...)` (no string cruda); los UUID de
  SQLite se almacenan como 32-hex y en consultas ORM se deben enlazar con
  `uuid.UUID(...)` (no `str`).
