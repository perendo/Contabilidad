# Tasks: Cierre Intermedio y Reapertura Controlada (SPEC-028)

**Input**: Design documents from `/specs/028-cierre-intermedio/`

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
| FR-001 | Cierres intermedios bloqueando contabilización del periodo | US1 |
| FR-002 | Cierre anual con regularización, apertura y bloqueo | US2 |
| FR-003 | Reapertura solo sin legalizar, con permiso y justificación | US3 |
| FR-004 | Reapertura con rectificación preservando inmutabilidad | US3 |
| FR-005 | Exigir reapertura/cierre de un solo periodo a la vez | US3 |
| FR-006 | Registrar cada reapertura con justificación y fecha | US3 |
| FR-007 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar el módulo `closing/` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo closing: `backend/src/models/closing/__init__.py`, `backend/src/models/closing/periodo_cerrado.py`, `backend/src/models/closing/balanza_periodo.py`, `backend/src/models/closing/cierre_ejercicio.py`, `backend/src/models/closing/solicitud_reapertura.py`
- [X] T002 [P] Crear servicios: `backend/src/services/closing/__init__.py`, `backend/src/services/closing/periodo.py`, `backend/src/services/closing/balanza.py`, `backend/src/services/closing/reglas_cierre.py`, `backend/src/services/closing/cierre_anual.py`, `backend/src/services/closing/reapertura.py`
- [X] T003 [P] Configurar router: crear `backend/src/api/closing.py` registrar endpoints bajo `/api/v1/cierres` con dependency de sesión autenticada `get_empresa_id()`
- [X] T004 [P] Crear estructura frontend: `frontend/src/app/cierres/page.tsx`, `frontend/src/app/cierres/intermedio/`, `frontend/src/app/cierres/anual/`, `frontend/src/app/cierres/reaperturas/`, `frontend/src/app/cierres/[id]/`, `frontend/src/components/closing/`, ampliar `frontend/src/services/client.ts` con métodos de cierre

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 Crear modelo `PeriodoCerrado` en `backend/src/models/closing/periodo_cerrado.py`: empresa_id BIGINT NOT NULL, ejercicio INT, tipo ENUM(MES/TRIMESTRE), periodo INT, fecha_ini DATE, fecha_fin DATE, estado ENUM(abierto/cerrado/reabierto_ajuste/cerrado_ajustado), cerrado_por UUID, cerrado_at TIMESTAMPTZ, balanza_id UUID NULL, n_reaperturas INT DEFAULT 0, created_at; constraint UNIQUE(empresa_id, ejercicio, tipo, periodo)
- [X] T006 Crear modelo `BalanzaPeriodo` y `BalanzaPeriodoLinea` en `backend/src/models/closing/balanza_periodo.py`: cabecera empresa_id, periodo_id FK UNIQUE, ejercicio, tipo, fecha_ini/fecha_fin, fecha_generacion, total_debe NUMERIC(18,4), total_haber NUMERIC(18,4), sha256 CHAR(64); línea empresa_id, balanza_id FK, cuenta_id FK, codigo, nombre, nivel, debe NUMERIC(18,4), haber NUMERIC(18,4), saldo NUMERIC(18,4); FK compuesta empresa_id
- [X] T007 Crear modelo `CierreEjercicio` en `backend/src/models/closing/cierre_ejercicio.py`: empresa_id, ejercicio INT, estado ENUM(completado/reapertura_pendiente), fecha_cierre, resultado_ejercicio NUMERIC(18,4), asiento_regularizacion_id FK, asiento_cierre_id FK, asiento_apertura_id FK NULL, cerrado_por, cerrado_at; UNIQUE(empresa_id, ejercicio)
- [X] T008 Crear modelo `SolicitudReapertura` en `backend/src/models/closing/solicitud_reapertura.py`: empresa_id, ejercicio INT, numero_solicitud BIGINT correlativo, periodo_id FK NULL, tipo_periodo ENUM(MES/TRIMESTRE/ANUAL), motivo TEXT, estado ENUM(pendiente/aprobada/reabierta/cerrada/rechazada), usuario_solicitante, fecha_solicitud, aprobada_por, fecha_aprobacion, asiento_rectificacion_id FK NULL, fecha_cierre_efectivo, nota_impacto TEXT NULL; UNIQUE(empresa_id, ejercicio, numero_solicitud)
- [X] T009 Ampliar `JournalEntry` en `backend/src/models/acct/asiento.py`: añadir al ENUM tipo los valores `REGULARIZACION`, `CIERRE`, `APERTURA`, `ADJUSTMENT`, `REVERSAL`; añadir campo `reverses_id UUID NULL` FK self-referencing; añadir campo `cierre_id UUID NULL` FK → CierreEjercicio; crear migración PostgreSQL; crear trigger `chk_journal_entry_fecha_abierta` que INSERT en JournalEntry falla si la fecha cae en un periodo cerrado (PeriodoCerrado) de la misma empresa
- [X] T010 Tests unitarios de modelos: `backend/tests/unit/test_periodo_cerrado.py` — verificar unicidad(empresa_id,ejercicio,tipo,periodo), FK compuesta empresa_id, constraint estado ENUM, correlatividad numero_solicitud
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_closing_tenant_isolation.py` (parte 1: modelos) — crear periodo cerrado en empresa A, verificar que empresa B no lo ve en ninguna consulta; verificar que el trigger rechaza asiento en periodo cerrado de otra empresa
- [X] T012 Crear servicio `reglas_cierre.py` en `backend/src/services/closing/reglas_cierre.py`: función `validar_periodo_abierto(fecha, empresa_id, session)` que consulta PeriodoCerrado y rechaza 409; función `validar_ejercicio_cerrado(ejercicio, empresa_id)`; función `validar_reapertura_autorizada(solicitud, empresa_id)` (SPEC-015 permisos, SPEC-010 legalización/formulación, SPEC-023 IS liquidado)
- [X] T013 Tests de reglas de reapertura: `backend/tests/unit/test_reglas_reapertura.py` — verificar rechazo sin motivo, uno a la vez, rechazo ejercicio legalizado/formulado, nota_impacto obligatoria si IS liquidado

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Cerrar un periodo intermedio (mes/trimestre) (Priority: P1) ← MVP — cubre FR-001, FR-007

**Goal**: El usuario cierra un mes o trimestre bloqueando la contabilización en ese periodo y generando el balance de comprobación (snapshot) sin mutar el diario.

**Independent Test**: Cerrando el mes, no se pueden asentar nuevos asientos en ese periodo y la balanza cuadra (Sum Debe == Sum Haber); el diario no se crea ni modifica.

### Tests for User Story 1

- [X] T014 [P] [US1] Test cuadre balanza: `backend/tests/unit/test_balanza_cuadre.py` — generar balanza para un periodo con movimientos; verificar `total_debe == total_haber` exactamente (Decimal); verificar que suma(líneas.debe)==total_debe; verificar `periodo_sin_movimientos` → cero == cero
- [X] T015 [P] [US1] Test bloqueo contabilización: `backend/tests/unit/test_periodo_cerrado.py` (parte 2) — cerrar mes 3; intentar crear asiento con fecha 15/03/2026 → 409 `periodo_cerrado`; asiento con fecha 15/04/2026 → aceptado (fuera de rango)
- [X] T016 [P] [US1] Test no mutación del diario: `backend/tests/unit/test_balanza_cuadre.py` (parte 2) — tras cierre intermedio, verificar que no se ha INSERTado ni UPDATEado ningún JournalEntry/JournalEntryLine nuevo; el snapshot NO modifica asientos existentes
- [X] T017 [US1] Test aislamiento multi-tenant US1: `backend/tests/integration/test_closing_tenant_isolation.py` (parte 2) — empresa A cierra mes 3, empresa B no ve ese periodo en listado; consultar balanza de A desde B → 404; empresa B puede cerrar su propio mes 3 sin conflicto

### Implementation for User Story 1

- [X] T018 [US1] Implementar servicio `calcular_balanza_periodo` en `backend/src/services/closing/balanza.py`: consultar asientos POSTED de la empresa activa cuya fecha caiga en el rango del periodo; agrupar por cuenta (Debe/Haber/Saldo); calcular totales; persistir `BalanzaPeriodo` + `BalanzaPeriodoLinea` en transacción ACID; calcular sha256 del snapshot; validar `total_debe == total_haber` antes de persistir; toda la operación auditada
- [X] T019 [US1] Implementar servicio `cerrar_periodo_intermedio` en `backend/src/services/closing/periodo.py`: validar que el periodo está `abierto` (409 si cerrado); validar ejercicio abierto; invocar `calcular_balanza_periodo`; INSERT `PeriodoCerrado` con estado `cerrado` y `balanza_id` en la misma transacción ACID; audit log; todo con `async with async_session.begin()`
- [X] T020 [US1] Integrar validación de periodo cerrado en el servicio de creación de asientos (ampliación): `backend/src/services/acct/asiento.py` (o el path donde SPEC-002 crea asientos) añadir llamada a `reglas_cierre.validar_periodo_abierto(fecha, empresa_id)` antes de INSERT; rechazar 409 `periodo_cerrado` sin persistir nada
- [X] T021 [US1] Implementar endpoints de cierres intermedios en `backend/src/api/closing.py`: POST `/api/v1/cierres/intermedios` (201, body `ejercicio/tipo/periodo`), GET `/api/v1/cierres/intermedios` (listado paginado con filtros), GET `/api/v1/cierres/intermedios/{periodo_id}/balanza` (200 con líneas)
- [X] T022 [US1] Crear página frontend `frontend/src/app/cierres/intermedio/page.tsx`: formulario de selección de ejercicio/tipo/periodo, confirmación, vista de resultado con balanza
- [X] T023 [US1] Crear componente `frontend/src/components/closing/BalanzaTabla.tsx`: tabla de balanza de comprobación con columnas código/nombre/debe/haber/saldo; importes formateados con 4 decimales
- [X] T024 [US1] Tests integración cierre intermedio: `backend/tests/integration/test_cierre_intermedio_flujo.py` — crear asientos en mes 3, cerrar mes 3, verificar balanza cuadra, verificar que asiento posterior en mes 3 rechazado 409, verificar asiento en mes 4 aceptado
- [X] T025 [US1] Tests contract API: `backend/tests/contract/test_closing_api_contracts.py` (parte 1) — verificar respuesta 201/409/422 del POST cierre intermedio según body

**Checkpoint**: User Story 1 completa — cierres intermedios funcionales con bloqueo y balanza. MVP desplegable.

---

## Phase 4: User Story 2 — Cerrar el ejercicio anual completo (Priority: P1) — cubre FR-002

**Goal**: El usuario cierra el ejercicio completo: genera asientos de regularización, cierre y bloqueo del ejercicio; integra con SPEC-004 y SPEC-009 (apertura).

**Independent Test**: Cerrando el ejercicio, los asientos de regularización y cierre cuadran (Debe==Haber), el ejercicio queda `is_closed` y la numeración del siguiente ejercicio inicia en 1.

### Tests for User Story 2

- [X] T026 [P] [US2] Test balance regularización/cierre/apertura: `backend/tests/unit/test_cierre_anual_balance.py` — crear saldo ficticio de grupos 6-7; ejecutar cierre anual; verificar Debe==Haber en asiento_regularizacion, asiento_cierre y asiento_apertura (3 asientos balanceados)
- [X] T027 [P] [US2] Test inmutabilidad: `backend/tests/unit/test_cierre_anual_balance.py` (parte 2) — intentar UPDATE/DELETE sobre los asientos de cierre → falla trigger DB (verificar que trigger `chk_journal_entry_immutable_posted` rechaza la operación)
- [X] T028 [P] [US2] Test idempotencia doble cierre: `backend/tests/integration/test_cierre_anual_flujo.py` (parte 1) — cierre anual → 201; reintentar mismo ejercicio → 409 sin generar asientos duplicados
- [X] T029 [US2] Test requisito periodos intermedios: `backend/tests/integration/test_cierre_anual_flujo.py` (parte 2) — intentar cierre anual con mes 5 abierto → 409 `periodos_intermedios_pendientes`; cerrar todos los meses → cierre anual acepta
- [X] T030 [US2] Test aislamiento US2: `backend/tests/integration/test_closing_tenant_isolation.py` (parte 3) — empresa A cierra ejercicio, empresa B no ve su cierre ni sus asientos de cierre; empresa B puede cerrar su propio ejercicio

### Implementation for User Story 2

- [X] T031 [US2] Implementar servicio `calcular_regularizacion` en `backend/src/services/closing/cierre_anual.py`: consultar saldos de cuentas de gestión (grupos 6-7) de la empresa activa en el ejercicio; calcular el resultado; generar las líneas del asiento de regularización (Debe/Haber) con importes en `Decimal`; validar `total_debe == total_haber`
- [X] T032 [US2] Implementar servicio `generar_cierre_anual` en `backend/src/services/closing/cierre_anual.py`: validar todos los periodos intermedios cerrados; validar ejercicio no cerrado; invocar `calcular_regularizacion` → crear JournalEntry tipo `REGULARIZACION` POSTED; crear JournalEntry tipo `CIERRE` POSTED (saldar grupos 6-7 contra cuenta de resultados); marcar ejercicio `is_closed=True`; INSERT `CierreEjercicio` con `asiento_regularizacion_id` y `asiento_cierre_id`; todo en transacción ACID `async with async_session.begin()`
- [X] T033 [US2] Integrar invocación de apertura (SPEC-009): tras completar el cierre, el servicio llama al endpoint o servicio de apertura de SPEC-009 para generar el asiento de apertura del siguiente ejercicio (si existe definido); registrar `asiento_apertura_id` en `CierreEjercicio`
- [X] T034 [US2] Implementar endpoints de cierre anual en `backend/src/api/closing.py`: POST `/api/v1/cierres/anual` (201), GET `/api/v1/cierres/anual/{ejercicio}` (200)
- [X] T035 [US2] Crear página frontend `frontend/src/app/cierres/anual/page.tsx`: formulario de cierre anual con validación previa (periodos cerrados), vista de resultado con IDs de asientos generados
- [X] T036 [US2] Tests integración cierre anual completo: `backend/tests/integration/test_cierre_anual_flujo.py` (parte 3) — crear ejercicio con datos, cerrar periodos intermedios, ejecutar cierre, verificar asientos generados, verificar `is_closed=true`, verificar que asiento nuevo en el ejercicio rechazado
- [X] T037 [US2] Tests contract API cierre anual: `backend/tests/contract/test_closing_api_contracts.py` (parte 2) — verificar 201/409/422 del POST cierre anual y 200/404 del GET

**Checkpoint**: User Stories 1 y 2 completas — cierres intermedios + anual funcional.

---

## Phase 5: User Story 3 — Reapertura controlada de periodos cerrados (Priority: P2) — cubre FR-003, FR-004, FR-005, FR-006

**Goal**: El usuario solicita la reapertura de un periodo cerrado; el sistema exige justificación, aprobación y genera un asiento de rectificación que re-cerra el periodo tras el ajuste, preservando la inmutabilidad del original.

**Independent Test**: Reabriendo un periodo cerrado se genera una solicitud con justificación, se aprueba, el usuario publica el asiento rectificativo y el periodo se re-cierra con `n_reaperturas` incrementado.

### Tests for User Story 3

- [X] T038 [P] [US3] Test exigencia justificación: `backend/tests/unit/test_reglas_reapertura.py` (parte 2) — solicitud sin `motivo` → 422; solicitud con motivo vacío → 422
- [X] T039 [P] [US3] Test uno a la vez: `backend/tests/unit/test_reglas_reapertura.py` (parte 3) — solicitud activa (pendiente/aprobada/reabierta) impide segunda solicitud para el mismo periodo → 409
- [X] T040 [P] [US3] Test balance asiento rectificativo: `backend/tests/unit/test_reapertura_reversal_balance.py` — crear asiento `ADJUSTMENT` balanceado con fecha dentro del periodo reabierto; tras registrar rectificación, verificar `asiento_rectificacion_id` enlazado, `PeriodoCerrado.estado=cerrado_ajustado`, `n_reaperturas+1`; verificar que el asiento original NO fue modificado (constitución II)
- [X] T041 [US3] Test rechazo ejercicio legalizado/formulado: `backend/tests/unit/test_reglas_reapertura.py` (parte 4) — simular ejercicio con `cuentas_anuales.formulado=True` (SPEC-010); solicitar reapertura → 409 `ejercicio_legalizado`
- [X] T042 [US3] Test rechazo IS liquidado sin nota: `backend/tests/unit/test_reglas_reapertura.py` (parte 5) — simular IS liquidado (SPEC-023); solicitar reapertura sin `nota_impacto` → 409 `is_liquidado`; con `nota_impacto` → acepta (201)
- [X] T043 [US3] Test aislamiento US3: `backend/tests/integration/test_closing_tenant_isolation.py` (parte 4) — empresa A solicita reapertura, empresa B no la ve; empresa B no puede aprobar la solicitud de A → 404

### Implementation for User Story 3

- [X] T044 [US3] Implementar servicio `solicitar_reapertura` en `backend/src/services/closing/reapertura.py`: validar periodo cerrado; validar `motivo` obligatorio; validar una sola solicitud activa por periodo; validar legalización/formulación del ejercicio (SPEC-010); validar IS liquidado (SPEC-023) — si liquidado sin `nota_impacto` → rechazo; asignar `numero_solicitud` correlativo por `(empresa_id, ejercicio)` con `SELECT ... FOR UPDATE`; INSERT `SolicitudReapertura(estado=pendiente)` en transacción ACID con audit log
- [X] T045 [US3] Implementar servicio `aprobar_rechazar_reapertura` en `backend/src/services/closing/reapertura.py`: validar estado `pendiente`; validar permiso de aprobación (SPEC-015); cambiar `estado=aprobada` o `rechazada`; registrar `aprobada_por` y `fecha_aprobacion`; si `aprobada`, cambiar `PeriodoCerrado.estado=reabierto_ajuste` para desbloquear el periodo; todo en transacción ACID
- [X] T046 [US3] Implementar servicio `ejecutar_reapertura` (rectificar) en `backend/src/services/closing/reapertura.py`: validar `SolicitudReapertura.estado=reabierta`; validar que el `asiento_id` proporcionado existe, es de la empresa activa, tiene `tipo` ADJUSTMENT/REVERSAL y `estado` POSTED, y su fecha cae en el rango del periodo reabierto; cambiar `PeriodoCerrado.estado=cerrado_ajustado`, incrementar `n_reaperturas`, registrar `asiento_rectificacion_id`, `fecha_cierre_efectivo`, `estado=cerrada`; todo en transacción ACID `async with async_session.begin()` con audit log
- [X] T047 [US3] Implementar endpoints de reapertura en `backend/src/api/closing.py`: POST `/api/v1/cierres/reaperturas` (201), POST `/{id}/aprobar` (200), POST `/{id}/rechazar` (200), POST `/{id}/rectificar` (200), GET `/api/v1/cierres/reaperturas` (listado)
- [X] T048 [US3] Crear página frontend `frontend/src/app/cierres/reaperturas/page.tsx`: listado de solicitudes, formulario de nueva solicitud con campos ejercicio/tipo/periodo/motivo/nota_impacto
- [X] T049 [US3] Crear página frontend `frontend/src/app/cierres/[id]/page.tsx`: detalle de periodo/cierre con botones aprobar/rechazar (según rol), campo para registrar `asiento_id` de rectificación
- [X] T050 [US3] Tests integración reapertura completa: `backend/tests/integration/test_reapertura_flujo.py` — cerrar mes, solicitar reapertura, aprobar, crear asiento ADJUSTMENT en SPEC-002, rectificar → re-cierre automático, verificar `n_reaperturas=1`, verificar asiento original intacto; reintentar doble reapertura → 409; reintentar re-cierre sin asiento → 409
- [X] T051 [US3] Tests contract API reapertura: `backend/tests/contract/test_closing_api_contracts.py` (parte 3) — verificar 201/403/409/422 de POST reaperturas; 200/403/409 de aprobación/rechazo/rectificación

**Checkpoint**: User Stories 1, 2 y 3 completas — flujo total de cierres y reaperturas funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T052 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_closing.py` — verificar que todo asiento de cierre (regularización/cierre/apertura/rectificativo) tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry POSTED (trigger funciona); verificar aislamiento empresa_id en todas las tablas closing
- [X] T053 [P] Hardening multi-tenant completo: `backend/tests/integration/test_closing_tenant_isolation.py` (escenario final) — empresa A cierra ejercicio, solicita reapertura, rectifica; empresa B no ve nada de A (cierres, balanzas, solicitudes, asientos de cierre); empresa B opera independientemente
- [X] T054 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_closing.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T055 [P] Code review transversal: verificar que todos los servicios closing usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint recibe `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes de balanza y asientos; verificar que trigger DB `chk_journal_entry_fecha_abierta` existe
- [X] T056 Validación cross-módulo: verificar que FACTURACION (SPEC-007), COBROS/PAGOS (SPEC-011) y AMORTIZACIONES (SPEC-014) rechazan 409 al crear asientos en periodos cerrados del módulo closing
- [X] T057 Limpieza y documentación: actualizar docstrings en servicios closing; verificar type hints; ejecutar lint/typecheck (`ruff check`, `mypy`); ejecutar `pytest` completo del módulo

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **US3 (Phase 5)**: Depende de Phase 2; USA asientos de US2 (cierre anual como prueba de rechazo de reapertura); recomendado después de US2, pero conceptualmente independiente de US1.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1)**: Sin dependencias de US1/US3; usa Phase 2 completa; integra con SPEC-004/009.
- **US3 (P2)**: Sin dependencias de US1; puede integrarse con US2 (cierre anual como caso de rechazo a reapertura); usa Phase 2 completa.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios (ya creados en Phase 2; este story solo referencia).
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: modelos [P] en paralelo (T005-T008); tests modelos [P] (T010-T011).
- Phase 3: tests [P] en paralelo (T014-T016).
- Phase 4: tests [P] en paralelo (T026-T027).
- Phase 5: tests [P] en paralelo (T038-T040).
- US1 y US2 pueden ejecutarse en paralelo por separado una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T014: "Test cuadre balanza en backend/tests/unit/test_balanza_cuadre.py"
Task T015: "Test bloqueo contabilización en backend/tests/unit/test_periodo_cerrado.py"
Task T016: "Test no mutación diario en backend/tests/unit/test_balanza_cuadre.py"

# Servicios en paralelo (distintos archivos):
Task T018: "Balanza en backend/src/services/closing/balanza.py"
Task T019: "Cierre periodo en backend/src/services/closing/periodo.py"
Task T020: "Bloqueo cross-módulo en backend/src/services/acct/asiento.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T014-T025. Verificar quickstart Scenario 1 y Scenario 6 (aislamiento).
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP! cierres intermedios).
3. + US2 → Test independiente → Deploy/Demo (cierre anual completo).
4. + US3 → Test independiente → Deploy/Demo (reapertura controlada).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (cierres intermedios + bloqueo + balanza).
   - Dev B: User Story 2 (cierre anual + regularización + apertura).
   - Dev C: User Story 3 (reapertura controlada — requiere entender flujo de US2 para tests de rechazo).
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar (TDD).
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.
- El trigger DB `chk_journal_entry_fecha_abierta` protege contra inserciones bypass del servicio; su migración se crea en T009.
- La numeración de `SolicitudReapertura` es correlativa por `(empresa_id, ejercicio)` y se asigna atómicamente (SELECT FOR UPDATE), sin saltos.
- El snapshot de balanza es inmutable (una vez persistido, no se modifica); la balanza es el "balance registrado" que alimenta SPEC-029 (export integral).

---

## Estado real (implementacion 2026-09-26)

**SPEC-028 cerrada 57/57 (28ª spec del proyecto).** Todas las puertas
verificadas: `pytest` (suite completa), `ruff`, `mypy` (377 fuentes),
`next build` (100 rutas) y `019_cierres.sql` aplicada sobre PostgreSQL 18.6 real
(11 pruebas del contrato `test_pg_schema.py` en verde).

### Ficheros creados

| Capa | Ficheros |
|---|---|
| Modelos | `models/closing/{periodo_cerrado,balanza_periodo,cierre_ejercicio,solicitud_reapertura,secuencia_reapertura}.py` + `__init__.py` |
| Servicios | `services/closing/{errores,reglas_cierre,balanza,periodo,cierre_anual,reapertura,secuencia}.py` + `__init__.py` |
| API | `api/closing.py` (router `/api/v1/cierres`, 11 endpoints) |
| Migracion | `migrations/019_cierres.sql` (5 tablas, 5 enums, 2 CHECK de cuadre, 6 triggers) |
| Triggers SQLite | 5 sentencias nuevas en `db/triggers.py` |
| Tests | `closing_support.py` + 7 unitarios + 6 de integracion/contrato |
| Frontend | `components/closing/{api.ts,BalanzaTabla.tsx}` + `app/cierres/**` (5 rutas) |

### Desviaciones documentadas

1. **Boundary ACID**: el texto de T019/T032/T044/T046 pide
   `async with async_session.begin()`; el boundary autoritativo del proyecto es
   `get_db` + `flush()` (ver constitution/AGENTS §3). Todos los servicios hacen
   `flush()` y nunca `commit()`; `test_closing_review.py` lo verifica por AST.
2. **`reverses_id` / `cierre_id`**: ya existian como `original_id` y
   `referencia_cierre_id` en `JournalEntry`, asi que la ampliacion del
   data-model (T009) solo anade los tipos `REGULARIZACION` y `CIERRE` al enum
   (`OPENING`/`REVERSAL`/`ADJUSTMENT` ya estaban). Sin columnas nuevas.
3. **`cerrado_por` / `usuario_solicitante`**: `VARCHAR(120)` en vez de UUID, para
   alinear con `User.id` (BIGINT) y con `created_by` de SPEC-002.
4. **Tabla de calendario**: no se persiste un `PeriodoCerrado` por periodo
   abierto (research D2 lo descarta). El GET con `ejercicio` + `tipo` devuelve
   el calendario completo fusionado con las filas existentes, de modo que
   `abierto` es un estado derivado y `periodo_id` llega `null`.
5. **Aprobacion y ejecucion**: `aprobar` marca la solicitud `reabierta` en un
   solo paso (dos acciones de auditoria: `APROBAR_REAPERTURA` y
   `REABRIR_PERIODO`). El contrato solo expone un endpoint de aprobacion, asi
   que el servicio `marcar_reabierta` compone `aprobar_reapertura` y deja el
   estado listo para `rectificar`.
6. **Exencion de tipos en el bloqueo**: `REGULARIZACION`, `CIERRE`, `OPENING` y
   `OPENING_REVERSAL` pueden asentarse en un periodo cerrado, porque el cierre
   anual se fecha el ultimo dia del ejercicio, que pertenece al ultimo mes
   cerrado por definicion (research D9).
7. **`cuenta_id` de la balanza** es `BIGINT` (el `id` real de `account_plan`),
   no `UUID` como dice el `data-model.md`; la FK es compuesta
   `(empresa_id, cuenta_id) -> account_plan (tenant_id, id)`.
8. **`resultado_ejercicio`** se calcula con signo de beneficio
   (`ingresos - gastos`), que coincide con el saldo acreedor final de la 1290.
9. **RBAC**: modulo nuevo `cierres` sembrado en los tres sitios coherentes
   (`catalogo.py`, `007_rbac.sql`, trigger `trg_companies_rbac_seed`). Los
   recuentos de SPEC-015 pasan de 13 a 14 modulos, 98 a 106 permisos y 160 a
   173 concesiones. `aprobar` queda como operacion exclusiva de ADMIN.
10. **API**: se anade `GET /cierres/reaperturas/{id}` (detalle con el periodo
    asociado, necesario para la pantalla `[id]` del frontend) y el campo del
    periodo asociado se llama `periodo_cerrado` para no chocar con el numero de
    `periodo` de la solicitud.
11. **Cross-modulo (T056)**: la validacion se prueba sobre el motor de SPEC-002,
    el motor multilinea de SPEC-006 (punto de entrada compartido por SPEC-007,
    SPEC-014 y SPEC-018) y el trigger. Los servicios de factura y plantilla se
    comprueban a nivel de fuente, porque su firma real (`emitir_factura(
    factura_id)`, `generar_asiento(plantilla_id)`) exige el fixture completo de
    cada spec para alcanzar la fecha.
12. **Lecciones**: (a) `balanza_periodo` referencia `periodo_cerrado`, asi que el
    periodo se inserta **antes** del snapshot; (b) un `PeriodoCerrado` en
    `reabierto_ajuste` no es bloqueante, de modo que el asiento rectificativo se
    puede asentar y el mes vuelve a contar como pendiente para el cierre anual;
    (c) `original_id` de un rectificativo debe fijarse **al crear** el asiento: un
    POSTED es inmutable y el UPDATE lo rechaza (por eso `crear_borrador` acepta
    ahora `original_id`); (d) un `tipo` de periodo desconocido lanzaba
    `ValueError` (500) y ahora se coacciona a 422 `tipo_periodo_invalido`.
