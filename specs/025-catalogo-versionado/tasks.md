# Tasks: Catálogo Versionado del Plan de Cuentas (SPEC-025)

**Input**: Design documents from `/specs/025-catalogo-versionado/`

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

**Purpose**: Inicializar módulo `catalog` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo catalog: `backend/src/models/catalog/__init__.py`, `backend/src/services/catalog/__init__.py`, `backend/src/api/catalogo.py`, `backend/src/config.py`
- [X] T002 [P] Configurar router catalog: registrar prefijo `/api/v1/catalogo` en `backend/src/api/catalogo.py` con dependency de sesión autenticada y empresa activa (cabecera, nunca path/body)
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/catalogo/`, `frontend/src/app/catalogo/[id]/`, `frontend/src/app/catalogo/importar/`, `frontend/src/app/catalogo/reclasificar/`, `frontend/src/components/catalog/`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/deps.py` con `get_empresa_id()` que extrae el `empresa_id` del contexto de sesión y bloquea acceso cross-tenant (403)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `CatalogoVersion` en `backend/src/models/catalog/catalogo_version.py`: empresa_id (PK), numero_version (BIGINT correlativo por empresa), codigo VARCHAR(20), fecha_inicio DATE, fecha_fin DATE NULL, estado ENUM (borrador/vigente/anulada), es_migracion BOOLEAN, creado_por, created_at; constraint unicidad (empresa_id, numero_version)
- [X] T006 [P] Crear modelo `CatalogoCuenta` en `backend/src/models/catalog/catalogo_cuenta.py`: empresa_id, version_id FK → CatalogoVersion, account_id FK compuesta (empresa_id, account_id) → account_plan (SPEC-001), codigo_version VARCHAR(8), nombre_version VARCHAR(200), estado ENUM (igual/nueva/renombrada/suprimida), parent_version_id NULL; constraints únicos (empresa_id, version_id, account_id) y (empresa_id, version_id, codigo_version)
- [X] T007 [P] Crear modelo `MapeoCuenta` en `backend/src/models/catalog/mapeo_cuenta.py`: empresa_id, version_origen_id FK, version_destino_id FK, cuenta_origen_id NULL FK, cuenta_destino_id NULL FK, tipo_movimiento ENUM (igual/renombrada/suprimida/nueva), requiere_reclasificacion BOOLEAN, origen ENUM (manifiesto/autogenerado); único (empresa_id, version_origen_id, version_destino_id, cuenta_origen_id)
- [X] T008 [P] Crear modelo `ReclasificacionSaldo` en `backend/src/models/catalog/reclasificacion_saldo.py`: empresa_id, version_destino_id FK, mapeo_id FK, cuenta_origen_id FK → account_plan, cuenta_destino_id FK → CatalogoCuenta, importe NUMERIC(18,4) check ≥ 0, asiento_id NULL FK → journal_entry (SPEC-002), estado ENUM (borrador/contabilizado/cuadrado)
- [X] T009 [P] Crear trigger `trg_catalogo_version_vigencia` en SQL aplicado por migración: rechaza solape de vigencia por empresa (BEFORE INSERT/UPDATE en `catalogo_version`); auditoría WORM compartida con el `plan.md` raíz
- [X] T010 [P] Tests de modelos fundacionales: `backend/tests/unit/test_catalogo_models.py` — verificar unicidad (empresa_id, numero_version), unicidad de proyección (empresa_id, version_id, account_id), FK compuesta empresa_id + solape rechazado
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_catalogo_tenant_isolation.py` — crear versión en empresa A, verificar que empresa B no la ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Registrar una nueva versión del plan de cuentas (Priority: P1) ?? MVP

**Goal**: El administrador incorpora una nueva versión del catálogo con vigencia, conservando las versiones anteriores intactas y resolviendo cada asiento con la versión de su fecha.

**Independent Test**: Creando una nueva versión del catálogo, los asientos antiguos siguen usando su versión original.

### Tests for User Story 1

- [X] T012 [P] [US1] Test de vigencia sin solapes: `backend/tests/unit/test_vigencia_solape.py` — crear versión A (01-01-2026 … NULL) y versión B solapada → 422/trigger; rangos contiguos (a fin de año inicio/fin) aceptados
- [X] T013 [P] [US1] Test de resolución histórica: `backend/tests/unit/test_resolucion_historica.py` — asiento de 2025 resuelve con la versión 2025; asiento de 2026 con la nueva; ninguna migración retroactiva (SC-001)
- [X] T014 [P] [US1] Test correlatividad de numero_version: `backend/tests/unit/test_numero_version.py` — crear 3 versiones en la misma empresa → numero_version 1, 2, 3 sin saltos; en empresa distinta → secuencia independiente

### Implementation for User Story 1

- [X] T015 [US1] Implementar servicio `registrar_version` en `backend/src/services/catalog/registro_version.py`: crear `CatalogoVersion` + `CatalogoCuenta` (proyecciones `igual` de la versión base) en transacción ACID; asignar `numero_version` correlativo con `SELECT ... FOR UPDATE` sobre secuencia bloqueada por empresa; registrar audit log
- [X] T016 [US1] Implementar servicio `resolver_version` en `backend/src/services/catalog/resolucion_historica.py`: lookup por (empresa_id, fecha) sobre vigencias; fallback a primera versión con `fecha_inicio` más antigua marcado como `fallback` trazable
- [X] T017 [US1] Implementar servicio `activar_version` en `backend/src/services/catalog/registro_version.py`: validar mapeos completos (consulta `validar_mapeo_completo`), estado borrador→vigente, audit log; si hay suprimidas con saldo y sin mapeo → 422
- [X] T018 [US1] Implementar endpoints en `backend/src/api/catalogo.py`: POST `/versiones` (201), GET `/versiones` (paginación+filtros), GET `/versiones/{id}`, POST `/versiones/{id}/activar` (200/422), GET `/vigente?fecha=` (200 con resolucion vigente/fallback), GET `/cuentas?version_id=&q=` (autocompletar por versión)
- [X] T019 [US1] Crear página frontend `frontend/src/app/catalogo/page.tsx`: listado de versiones con estado/fechas y links a detalle
- [X] T020 [US1] Crear página frontend `frontend/src/app/catalogo/[id]/page.tsx`: detalle de versión (árbol de cuentas con estado, mapeos, botón activar) y selector "cuenta vigente en fecha"
- [X] T021 [US1] Tests integración resolución: `backend/tests/integration/test_resolucion_integration.py` — crear dos versiones con vigencia 2025 y 2026, registrar asientos en ambos años, verificar que cada asiento indica la versión de su fecha (FR-003)
- [X] T022 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_catalogo_tenant_us1.py` — empresa A crea versión, empresa B no la ve en listado/detalle/vigente; intento de activar desde B → 404

**Checkpoint**: User Story 1 completa — alta de versiones con vigencia y resolución histórica. MVP desplegable.

---

## Phase 4: User Story 2 — Importar el catálogo de una nueva normativa (Priority: P2)

**Goal**: El usuario importa una actualización normativa (CSV/JSON) con altas/renombrados/bajas y mapeo entre versiones, con advertencia y bloqueo ante mapeos incompletos.

**Independent Test**: Importando una actualización con mapeo, las cuentas nuevas se incorporan y las renombradas se enlazan.

### Tests for User Story 2

- [X] T023 [P] [US2] Test parser de importación: `backend/tests/unit/test_import_parser.py` — CSV/JSON válido con altas/renombrados/bajas; fila mal formada → 422 con motivo por fila
- [X] T024 [P] [US2] Test de mapeo de renombrados: `backend/tests/unit/test_import_mapeo.py` — cuenta renombrada queda enlazada por `MapeoCuenta` origen→destino; cuenta nueva incorporada a la proyección de la nueva versión
- [X] T025 [US2] Test de suprimida sin mapeo: `backend/tests/unit/test_mapeo_incompleto.py` — baja sin destino → 200 con `pendientes_mapeo`; activación bloqueada (422) hasta resolver (edge case spec)

### Implementation for User Story 2

- [X] T026 [US2] Implementar parser de importación en `backend/src/services/catalog/importacion_catalogo.py`: parsear CSV/JSON (altas/renombrados/bajas) y bloque de mapeo con validación Pydantic v2; devolver errores por fila
- [X] T027 [US2] Implementar servicio `importar_catalogo` en `backend/src/services/catalog/importacion_catalogo.py`: crear `CatalogoVersion` (borrador, es_migracion=true) + `CatalogoCuenta` + `MapeoCuenta` (autogenerado para igualdad) en transacción ACID; audit log con payload de importación
- [X] T028 [US2] Implementar servicio `validar_mapeo_completo` en `backend/src/services/catalog/importacion_catalogo.py`: detectar suprimidas/renombradas con saldo ≠ 0 sin destino (FR-004/FR-006); devolver `pendientes_mapeo` con motivo
- [X] T029 [US2] Implementar endpoint POST `/api/v1/catalogo/importar` en `backend/src/api/catalogo.py`: multipart `file` (`text/csv`/`application/json`) o body JSON; devolver nuevas/renombradas/suprimidas/mapeos/pendientes
- [X] T030 [US2] Crear página frontend `frontend/src/app/catalogo/importar/page.tsx`: carga de fichero, validación previa, vista de pendientes de mapeo y confirmación de importación
- [X] T031 [US2] Tests integración importación completa: `backend/tests/integration/test_import_completa.py` — importar catálogo con renombrado y alta, activar versión, verificar incorporación de nuevas y enlace de renombradas
- [X] T032 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_import_tenant.py` — empresa A importa normativa, empresa B no ve la versión importada ni sus mapeos

**Checkpoint**: User Stories 1 y 2 completas — versiones + importación normativa trazable.

---

## Phase 5: User Story 3 — Reclasificar saldos al cambiar de versión (Priority: P2)

**Goal**: Al abrir un nuevo ejercicio con versión distinta, el usuario revisa y confirma la reclasificación de saldos según el mapeo; los asientos `ADJUSTMENT` cuadran y el balance de apertura (SPEC-009) encaja.

**Independent Test**: Reclasificando los saldos de apertura con el mapeo se generan los movimientos en las cuentas nuevas y el balance cuadra.

### Tests for User Story 3

- [X] T033 [P] [US3] Test de balance de reclasificación: `backend/tests/unit/test_reclasificacion_balance.py` — todo asiento ADJUSTMENT cumple Debe==Haber; Sum(saldos origen) == Sum(saldos destino) (FR-005/SC-003)
- [X] T034 [P] [US3] Test de cuenta suprimida con saldo: `backend/tests/unit/test_reclasificacion_suprimida.py` — cuenta suprimida con saldo ≠ 0 y sin mapeo → preview 422 y activación bloqueada (FR-004)
- [X] T035 [P] [US3] Test de precisión: `backend/tests/unit/test_reclasificacion_precision.py` — importes con 4 decimales exactos, suma neta sin errores de redondeo (SC-005)

### Implementation for User Story 3

- [X] T036 [US3] Implementar servicio `preview_reclasificacion` en `backend/src/services/catalog/reclasificacion_saldos.py`: por cuenta con saldo ≠ 0 proponer destino según `MapeoCuenta` y calcular importes con `Decimal`; validar saldos origen/destino
- [X] T037 [US3] Implementar servicio `confirmar_reclasificacion` en `backend/src/services/catalog/reclasificacion_saldos.py`: generar asientos `ADJUSTMENT` del motor SPEC-002 (Debe==Haber en backend), registrar `ReclasificacionSaldo` (borrador→contabilizado→cuadrado) y vincular al asiento de apertura de SPEC-009; todo en `async with async_session.begin()`, audit log; NUNCA modificar asientos históricos (constitución II)
- [X] T038 [US3] Implementar endpoints en `backend/src/api/catalogo.py`: GET `/reclasificar/preview?version_id=&ejercicio=` (200/422) y POST `/reclasificar/confirmar` (200/409/422)
- [X] T039 [US3] Crear página frontend `frontend/src/app/catalogo/reclasificar/page.tsx`: previsualización de traslados (origen→destino, importe), confirmación y resultado con asientos vinculados
- [X] T040 [US3] Tests integración con apertura: `backend/tests/integration/test_reclasificacion_apertura.py` — tras confirmar reclasificación, generar apertura del ejercicio (SPEC-009) y verificar que el balance de apertura cuadra con el nuevo catálogo (US3 scenario 2)
- [X] T041 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_reclasificacion_tenant.py` — empresa A reclasifica, empresa B no ve reclasificaciones ni asientos ADJUSTMENT de A

**Checkpoint**: User Stories 1, 2 y 3 completas — versiones + importación + reclasificación de apertura.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación constitucional y robustez.

- [X] T042 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_catalogo.py` — verificar que todo asiento de reclasificación tiene Debe==Haber; que las versiones no se cruzan entre empresas; que ningún asiento histórico fue modificado en todo el flujo de versionado
- [X] T043 [P] Hardening multi-tenant: `backend/tests/integration/test_catalogo_full_tenant.py` — escenario completo cross-empresa (versión A, import B, reclasificación A confirmada desde B → todos 404/403)
- [X] T044 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_catalogo.py` — reproducir los 5 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T045 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` en body/path; verificar Decimal/NUMERIC(18,4) en importes de reclasificación
- [X] T046 Validación de ejercicio cerrado: verificar que la reclasificación rechaza con 409 si el ejercicio destino está cerrado (SPEC-002/004)
- [X] T047 Limpieza y documentación: actualizar docstrings en servicios catalog, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **US3 (Phase 5)**: Depende de Phase 2; requiere US2 parcialmente (mapeos de la importación alimentan la reclasificación) — puede preparar tests desde Phase 2+.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Sin dependencias de US1/US3; usa Phase 2 completa.
- **US3 (P2)**: Depende del modelo de mapeos de US2 (el preview usa `MapeoCuenta`); se recomienda completar US2 antes de confirmar reclasificaciones de versión importada.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T010).
- Phase 3: tests [P] en paralelo (T012-T014).
- Phase 4: tests [P] en paralelo (T023-T024).
- Phase 5: tests [P] en paralelo (T033-T035).
- US1, US2 pueden ejecutarse en paralelo por separado una vez completada Phase 2; US3 espera a US2 para el despliegue completo.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T012: "Test de vigencia sin solapes en backend/tests/unit/test_vigencia_solape.py"
Task T013: "Test de resolución histórica en backend/tests/unit/test_resolucion_historica.py"
Task T014: "Test correlatividad numero_version en backend/tests/unit/test_numero_version.py"

# Servicios de registro y resolución en paralelo:
Task T015: "Servicio registrar_version en backend/src/services/catalog/registro_version.py"
Task T016: "Servicio resolver_version en backend/src/services/catalog/resolucion_historica.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T012-T022. Verificar quickstart Escenarios 1 y 2.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP: versionado + resolución histórica).
3. + US2 → Test independiente → Deploy/Demo (importación normativa con mapeo).
4. + US3 → Test independiente → Deploy/Demo (reclasificación de saldos para apertura).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (registro de versión + resolución histórica).
   - Dev B: User Story 2 (importación normativa con mapeo).
   - Dev C: prepara tests de User Story 3 (balance de reclasificación y cuadre) y completa US3 cuando US2 entregue los mapeos.
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- El trigger `trg_catalogo_version_vigencia` hereda el estilo del `plan.md` raíz (SPEC-001); ningún endpoint expone `empresa_id` en body/path.
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.
## Estado real (implementación 2026-09-26)

SPEC-025 cerrada **47/47**. Total del proyecto: **1.188/1.384 tareas** (25 specs completas).

- **Modelos** (`models/catalog/`): `CatalogoVersion` (estados `borrador|activa|anulada`,
  `es_migracion` para la reserva PGC 2025, unicidad `(empresa_id, numero_version)`),
  `CatalogoCuenta` (proyección por versión con `codigo_version`/`nombre_version`, estado
  `igual|renombrada|suprimida|nueva` y FK compuesta a `account_plan`), `MapeoCuenta`
  (origen/destino, `tipo_movimiento`, `requiere_reclasificacion`, `origen`
  `manifiesto|autogenerado`) y `ReclasificacionSaldo` (importe `NUMERIC(18,4)`, estado
  `borrador|contabilizado|cuadrado` y `asiento_id`). Todos con UUID,
  `UNIQUE(empresa_id, id)` y `empresa_id` en índices/FKs.
- **Migración `016_catalogo.sql`**: cuatro tablas, enums, unicidades, checks e índices
  multi-tenant, más el trigger `trg_catalogo_version_vigencia` (BEFORE INSERT/UPDATE) que
  bloquea el **solape de vigencia por empresa** (FR-006) en el punto más cercano a la
  persistencia; el servicio replica la regla para devolver 422 legible. Espejo SQLite
  equivalente en `db/triggers.py`; aplicada y verificada sobre PostgreSQL 16 real.
- **Servicios** `services/catalog/`: `_comun.py` (proyección de la versión, helpers y
  validación de códigos), `versiones.py` (alta correlativa por empresa, activación con
  reserva de vigencia y resolución de la versión vigente en una fecha),
  `importacion_catalogo.py` (manifiesto CSV/JSON con `alta|renombrado|baja`, mapeo
  automático por código y reporte de pendientes), `mapeo.py` (consulta de la versión
  anterior y de los mapeos) y `reclasificacion_saldos.py` (preview tenant-scoped sobre
  saldos POSTED y confirmación con asientos `ADJUSTMENT` correlativos y balanceados por
  el motor de SPEC-002, sin tocar los asientos históricos). Auditoría y `flush()` dentro
  del boundary `get_db`.
- **API** `api/catalogo.py`: `/api/v1/catalogo/versiones` (alta/listado/activación),
  `/vigente`, `/cuentas`, `/mapeos`, `/importar/preview`, `/importar/confirmar` (multipart)
  y `/reclasificar/{preview,confirmar}` con `get_empresa_id` y guards
  `require_permission("catalogos", ...)`. La empresa nunca se recibe en body ni path.
- **Frontend**: `components/catalog/api.ts` y páginas `/catalogo` (listado con estado y
  fechas), `/catalogo/[id]` (detalle, activar, versión vigente en fecha, cuentas y
  mapeos), `/catalogo/importar` (fichero + pendientes) y `/catalogo/reclasificar`
  (preview, confirmación y asientos enlazados). `next build` genera **89 rutas**.
- **Pruebas**: **88 pruebas nuevas** (59 unitarias + 29 de integración) cubren modelos,
  US1/US2/US3, cuadre de los asientos de reclasificación, constitución (partida doble e
  inmutabilidad de los POSTED), aislamiento multi-tenant por user story, resolución
  histórica, la reserva de la versión PGC 2025 y los seis escenarios de quickstart.
  PostgreSQL 16: **6 passed** para la migración 016, el trigger de vigencia y las
  unicidades.
- **Desviaciones**: el boundary ACID autoritativo es `get_db` + `flush()` (no
  `async with async_session.begin()`); la versión migrada PGC 2025 se crea por código de
  reserva (`es_migracion`) y las versiones de normativa arrancan en la versión 2; la
  proyección excluye las cuentas ya renombradas, por lo que una cuenta renombrada en una
  versión anterior conserva su nombre y no puede renombrarse de nuevo; los tests T045/T047
  viven en `tests/unit/` y el contrato PostgreSQL en `tests/integration/test_pg_schema.py`.
- **Verificación**: **1497 passed / 8 skipped** (las 2 pruebas de `test_suggest_perf`,
  verdes aisladas), PostgreSQL 16 **6 passed**, ruff + mypy limpios (**337 fuentes**),
  `tsc` + ESLint + `next build` verdes.
