# Tasks: Vencimientos, Cobros y Pagos (SPEC-011)

**Input**: Design documents from `/specs/011-cobros-y-pagos/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitucion V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

**Alcance**: las remesas de esta feature cubren SOLO agrupacion/estado/trazabilidad. La generacion de ficheros SEPA/CSB 19.19, mandatos y plazos pertenece a SPEC-020 (no planificar aqui).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripcion

---

## Trazabilidad FR ↔ User Story

| Requisito | Descripción breve | User Story |
|---|---|---|
| FR-001 | Aislar vencimientos, cobros y pagos por empresa | US1 |
| FR-002 | Generar vencimientos y gestionar sus estados | US1 |
| FR-003 | Registrar cobros/pagos con asiento vinculado atómico | US1 |
| FR-004 | Acumular parciales sin exceder, saldar al igualar | US2 |
| FR-005 | Agrupar vencimientos en remesas con estado trazable | US3 |
| FR-006 | Calcular informe antigüedad de saldos por tercero | US3 |
| FR-007 | Rechazar gestión con asiento en ejercicio cerrado | US1 |
| FR-008 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar modulo `treasury` en backend y frontend segun plan.md.

- [X] T001 [P] Crear estructura del modulo treasury: `backend/src/models/treasury/__init__.py`, `backend/src/services/treasury/__init__.py`, `backend/src/services/treasury/vencimientos.py`, `backend/src/services/treasury/cobros_pagos.py`, `backend/src/services/treasury/remesas.py`, `backend/src/services/treasury/antiguedad.py`, `backend/src/api/treasury/__init__.py`
- [X] T002 [P] Configurar routers treasury: registrar prefijos `/api/v1/vencimientos`, `/api/v1/remesas`, `/api/v1/antiguedad` en `backend/src/api/treasury/routes.py` con dependency de sesion autenticada `empresa_id`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/vencimientos/`, `frontend/src/app/cobros/`, `frontend/src/app/remesas/`, `frontend/src/app/antiguedad/`, `frontend/src/components/treasury/`
- [X] T004 [P] Crear utils de sesion: `backend/src/api/treasury/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesion y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningun trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `Vencimiento` en `backend/src/models/treasury/vencimiento.py`: empresa_id (PK compuesta), numero_vencimiento BIGINT, ejercicio INT, factura_id FK, tercero_id FK, tipo ENUM (cobro/pago), fecha_vencimiento DATE, importe NUMERIC(18,4) > 0, acumulado NUMERIC(18,4) DEFAULT 0, saldo_pendiente NUMERIC(18,4), estado ENUM (pendiente/parcial/cobrado/remesado), remesa_id FK NULL; constraint acumulado <= importe; constraint unicidad (empresa_id, ejercicio, numero_vencimiento)
- [X] T006 [P] Crear modelo `CobroPago` en `backend/src/models/treasury/cobro_pago.py`: empresa_id, numero_operacion BIGINT, vencimiento_id FK, fecha DATE, tipo ENUM, importe NUMERIC(18,4) > 0, cuenta_tesoreria VARCHAR(20), journal_entry_id FK UNIQUE (SPEC-002), created_at/created_by/ip; constraint unicidad (empresa_id, ejercicio, numero_operacion)
- [X] T007 [P] Crear modelo `Remesa` en `backend/src/models/treasury/remesa.py`: empresa_id, numero_remesa BIGINT, ejercicio INT, tipo ENUM (cobro/pago), fecha_creacion DATE, fecha_cargo_prevista DATE NULL, estado ENUM (borrador/emitida), n_vencimientos INT, importe_total NUMERIC(18,4); constraint unicidad (empresa_id, ejercicio, numero_remesa)
- [X] T008 [P] Implementar bloqueo de ejercicio cerrado en `backend/src/services/treasury/deps.py`: consulta de estado del ejercicio por (empresa_id, fecha) y rechazo 409 `ejercicio_cerrado`
- [X] T009 [P] Tests de modelos fundacionales: `backend/tests/unit/test_treasury_models.py` — verificar unicidad (empresa_id, ejercicio, numero_*), constraint acumulado <= importe, FK compuesta empresa_id
- [X] T010 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_treasury_tenant_isolation.py` — crear vencimiento/cobro en empresa A, verificar que empresa B no los ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Cobrar el vencimiento de una factura (Priority: P1) — MVP — cubre FR-001, FR-002, FR-003, FR-007, FR-008

**Goal**: El usuario cobra un vencimiento; el sistema registra el cobro, genera el asiento balanceado (banco/caja vs deuda del tercero) y actualiza el saldo pendiente.

**Independent Test**: Cobrando un vencimiento se genera el asiento de pago balanceado y el saldo pendiente del cliente baja.

### Tests for User Story 1

- [X] T011 [P] [US1] Test balance asiento cobro: `backend/tests/unit/test_asiento_cobro_balance.py` — Debe 572/570 == Haber 430, con Decimal exacto; sin el asiento POSTED el cobro no se devuelve como registrado
- [X] T012 [P] [US1] Test actualizacion de saldo: `backend/tests/unit/test_cobro_saldo.py` — cobro total deja saldo_pendiente 0.0000 y estado cobrado; segundo cobro -> 409 vencimiento_saldado

### Implementation for User Story 1

- [X] T013 [US1] Implementar `registrar_cobro` en `backend/src/services/treasury/cobros_pagos.py`: validar ejercicio abierto (deps), validar saldo pendiente, crear `CobroPago` + `JournalEntry` (Debe 572/570 | Haber 430) en una sola transaccion ACID (`async with async_session.begin()`), actualizar vencimiento, audit log
- [X] T014 [US1] Implementar `registrar_pago` en `backend/src/services/treasury/cobros_pagos.py`: identico con asiento Debe 400 | Haber 572/570 para vencimientos de pago
- [X] T015 [US1] Implementar direccion de cuenta de tesoreria en `backend/src/services/treasury/cobros_pagos.py`: por defecto 572 (banco) o 570 (caja) configurado por empresa; override por request con validacion de cuenta activa
- [X] T016 [US1] Implementar endpoints en `backend/src/api/treasury/routes.py`: POST `/vencimientos/{id}/cobrar` (200), POST `/vencimientos/{id}/pagar` (200), GET `/vencimientos` (paginado), GET `/vencimientos/{id}` (detalle con cobros), GET `/vencimientos/{id}/cobros` (historial)
- [X] T017 [US1] Tests integracion cobro completo: `backend/tests/integration/test_cobro_completo.py` — crear factura+vencimiento (SPEC-007), cobrar, verificar asiento balanceado y saldo a 0
- [X] T018 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_cobro_tenant.py` — empresa A cobra su vencimiento, empresa B no ve el vencimiento ni el asiento; intento de cobro desde B -> 404
- [X] T019 [US1] Tests bloqueo ejercicio cerrado US1: `backend/tests/integration/test_cobro_cerrado.py` — vencimiento en ejercicio cerrado -> 409; asiento no creado

**Checkpoint**: User Story 1 completa — cobros/pagos funcionales con asiento balanceado. MVP desplegable parcial.

---

## Phase 4: User Story 2 — Registrar cobros y pagos parciales (Priority: P1) — cubre FR-004

**Goal**: El usuario registra parciales; el acumulado nunca excede el importe y el vencimiento se salda al igualarlo.

**Independent Test**: Registrando parciales, el acumulado nunca supera el importe y al igualarlo el vencimiento queda saldado.

### Tests for User Story 2

- [X] T020 [P] [US2] Test parciales acumulados: `backend/tests/unit/test_parciales_acumulados.py` — sucesion de parciales: estado parcial/cobrado segun acumulado; exceso -> 422 exceso_importe
- [X] T021 [P] [US2] Test precision de parciales: `backend/tests/unit/test_parciales_precision.py` — 3 parciales de 1/3 de 1.0000 suman exactamente; cierre solo al igualar (nunca con +/- centimos)
- [X] T022 [P] [US2] Test balance cada parcial: `backend/tests/unit/test_parciales_balance.py` — cada parcial genera su propio asiento balanceado (Debe==Haber)

### Implementation for User Story 2

- [X] T023 [US2] Extraer logica de acumulacion en `backend/src/services/treasury/cobros_pagos.py`: `calcular_acumulado(vencimiento)` con Decimal; transicion de estado automatica (parcial<importe, cobrado==importe)
- [X] T024 [US2] Integrar validacion de exceso en `registrar_cobro/registrar_pago`: rechazar 422 si importe > saldo_pendiente; nunca superar acumulado > importe (validacion + check DB)
- [X] T025 [US2] Tests integracion parciales completo: `backend/tests/integration/test_parciales_completo.py` — vencimiento de 300 con 3 parciales de 100, estados parcial/cobrado, asientos balanceados por parcial
- [X] T026 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_parciales_tenant.py` — parciales de A no afectan saldos de B; B no ve los cobros parciales de A

**Checkpoint**: User Stories 1 y 2 completas — cobros/pagos totales y parciales.

---

## Phase 5: User Story 3 — Emitir remesas e informes de antiguedad (Priority: P2) — cubre FR-005, FR-006

**Goal**: El usuario agrupa vencimientos en remesas de cobro/pago con estado y trazabilidad, y consulta el informe de antiguedad de saldos por tercero por rangos. La generacion de ficheros SEPA/CSB 19.19 es de SPEC-020.

**Independent Test**: Emitiendo una remesa y consultando la antiguedad, los vencimientos se agrupan correctamente y el informe clasifica por rango.

### Tests for User Story 3

- [X] T027 [P] [US3] Test remesa agrupacion: `backend/tests/unit/test_remesa_agrupacion.py` — crear remesa con vencimientos pendientes/parciales, calcular importe_total y n_vencimientos; vencimiento cobrado no remesable -> 422; vencimiento ya remesado -> 409
- [X] T028 [P] [US3] Test estado tras emitir: `backend/tests/unit/test_remesa_estado.py` — emitir remesa cambia vencimientos a `remesado`; remesa ya emitida -> 409 idempotencia
- [X] T029 [P] [US3] Test antiguedad rangos: `backend/tests/unit/test_antiguedad_rangos.py` — vencimientos a 10/45/75/95 dias clasifican en rango_30/60/90/90mas; suma de rangos == saldo pendiente total

### Implementation for User Story 3

- [X] T030 [US3] Implementar `crear_remesa` en `backend/src/services/treasury/remesas.py`: validar vencimientos elegibles (pendiente/parcial, empresa activa, ejercicio abierto), asignar numero_remesa correlativo con `SELECT ... FOR UPDATE`, calcular importe_total, persistir en transaccion ACID con audit log
- [X] T031 [US3] Implementar `emitir_remesa` en `backend/src/services/treasury/remesas.py`: cambiar estado a `emitida` y vencimientos a `remesado` (sin generar fichero: SEPA/CSB es SPEC-020); validar idempotencia
- [X] T032 [US3] Implementar `eliminar_remesa_borrador` en `backend/src/services/treasury/remesas.py`: solo estado borrador; vencimientos vuelven a `pendiente`
- [X] T033 [US3] Implementar `calcular_antiguedad` en `backend/src/services/treasury/antiguedad.py`: agrupar saldos pendientes por tercero y rango a fecha de corte; verificar suma de rangos como assert defensivo
- [X] T034 [US3] Implementar endpoints en `backend/src/api/treasury/routes.py`: POST `/remesas` (201), GET `/remesas` (paginado), GET `/remesas/{id}` (detalle), POST `/remesas/{id}/emitir` (200), DELETE `/remesas/{id}` (200), GET `/antiguedad` (200)
- [X] T035 [US3] Tests integracion remesa completo: `backend/tests/integration/test_remesa_completo.py` — crear remesa, emitir, verificar estados y trazabilidad; vencimiento remesado no puede cobrarse directamente (409)
- [X] T036 [US3] Tests integracion antiguedad completo: `backend/tests/integration/test_antiguedad_completo.py` — con vencimientos de varias fechas, verificar clasificacion por rango y suma
- [X] T037 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_remesa_tenant.py` — remesa y antiguedad de A no visibles en B; intento de emitir remesa de A desde B -> 404

**Checkpoint**: User Stories 1, 2 y 3 completas — gestion de tesoreria funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validacion y robustez.

- [X] T038 [P] Validar constitucion V en todos los flujos: `backend/tests/unit/test_constitucion_treasury.py` — verificar que todo asiento (cobro, pago, parcial) tiene Debe==Haber; verificar que no se actualiza/borra ningun JournalEntry confirmado; verificar aislamiento empresa_id en todas las tablas
- [X] T039 [P] Hardening multi-tenant: `backend/tests/integration/test_treasury_full_tenant_isolation.py` — escenario completo cross-empresa (cobro A, pago B, remesa A consultada desde B -> 404)
- [X] T040 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_cobros.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T041 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transaccion ACID); verificar que ningun endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [X] T042 [P] Verificar integracion con SPEC-020: `backend/tests/integration/test_remesa_integra_spec020.py` — la remesa emitida en 011 expone el estado correcto para que SPEC-020 recupere los vencimientos (contrato de estados: borrador/emitida/remesado)
- [X] T043 Crear paginas frontend `frontend/src/app/vencimientos/page.tsx` y `frontend/src/app/cobros/page.tsx`: listado de vencimientos con estados y accion de cobro/pago con validacion informativa del saldo
- [X] T044 [P] Crear paginas frontend `frontend/src/app/remesas/page.tsx` y `frontend/src/app/antiguedad/page.tsx`: agrupacion de vencimientos en remesa y tabla de antiguedad por tercero/rango
- [X] T045 Limpieza y documentacion: actualizar docstrings en servicios treasury, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1 (comparte servicio de cobros_pagos).
- **US3 (Phase 5)**: Depende de Phase 2; usa Vencimiento de US1 (estados pendiente/cobrado) y de USAEM consigo (remesa consume vencimientos validos).
- **Polish (Phase 6)**: Depende de las user stories completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1)**: Depende de US1 (reutiliza el registro de cobros/pagos y su asiento); puede implementarse en paralelo sobre los mismos servicios.
- **US3 (P2)**: Depende de US1 (remesa solo incluye vencimientos con estados de US1); antiguedad depende de vencimientos y de sus saldos (US1/US2).

### Within Each User Story

- Tests ANTES de la implementacion (TDD constitucion V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integracion y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T008).
- Phase 3: tests [P] en paralelo (T011-T012).
- Phase 4: tests [P] en paralelo (T020-T022) y puede partir con US1 en paralelo.
- Phase 5: tests [P] en paralelo (T027-T029).
- US1 y US3 pueden ejecutarse en paralelo una vez completa Phase 2 (US3 depende de estados de vencimiento que se disponibizan en Phase 2).

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T011: "Test balance asiento cobro en backend/tests/unit/test_asiento_cobro_balance.py"
Task T012: "Test actualizacion saldo en backend/tests/unit/test_cobro_saldo.py"

# Implementacion secuencial (dependencias internas):
Task T013: "registrar_cobro en backend/src/services/treasury/cobros_pagos.py"
Task T014: "registrar_pago en backend/src/services/treasury/cobros_pagos.py"
Task T016: "Endpoints en backend/src/api/treasury/routes.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. Completar Phase 4: User Story 2 (MVP junto a US1: parciales imprescindible para tesoreria real).
5. **PARAR y VALIDAR**: Ejecutar T011-T026. Verificar quickstart Scenario 1, 2, 3 y 6.
6. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 + US2 → Test independiente → Deploy/Demo (MVP!).
3. + US3 → Test independiente → Deploy/Demo (remesas de agrupacion + antiguedad).
4. + Polish → Validacion constitucional completa.
5. Integrar con SPEC-020 para el fichero SEPA/CSB de las remesas emitidas.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (cobro/pago total + asiento).
   - Dev B: User Story 2 (parciales) en paralelo sobre el mismo servicio.
   - Dev C: User Story 3 (remesas de agrupacion + antiguedad).
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo logico.
- Parar en cada checkpoint para validar story independientemente.
- Constitucion V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.
- RECORDATORIO de alcance: la generacion de ficheros SEPA/CSB 19.19, mandatos y plazos NO se planifica aqui; pertenece a SPEC-020 (T042 solo verifica integracion de estados).

## Estado real (auditoría 2026-09-17)

- **Implementado**: scaffold mínimo `backend/src/models/ar/vencimiento.py` (estado, ejercicio, fecha, importe, `fecha_factura`) usado por SPEC-020.
- **Pendiente**: resto de la feature (cobros/pagos, endpoints, tests).

## Estado real (implementación 2026-09-19, 45/45)

Desviaciones documentadas:
- **T005**: `Vencimiento` extendido en `models/ar/` (no `models/treasury/`): +`tipo` (cobro/pago), +`acumulado`, +`remesa_id`; `saldo_pendiente` es **propiedad derivada** (`importe - acumulado`), no columna. Estados `parcial`/`remesado` añadidos al enum. `numero_vencimiento` se omite (SPEC-020 usa `recibo_num`).
- **T007/T030-T034/T044**: la agrupación de vencimientos en remesas y la generación de ficheros ya están implementadas en **SPEC-020** (`services/remittance/emision.py`, `api/treasury/remesas.py`); SPEC-011 no las duplica (alcance "solo agrupación" cubierto por 020). La antigüedad sí es nueva.
- **T015**: cuenta de tesorería por defecto **572** (banco) para cobros y pagos; override por request (p. ej. `570`).
- **T008**: la guarda de ejercicio cerrado se implementa en `services/treasury/cobros_pagos.py` (consulta `FiscalYear`), no en `deps.py`.
- **T043/T044 frontend**: `/vencimientos`, `/cobros`, `/antiguedad` (SPEC-020 ya aporta `/remesas`).
- Puertas: 15 tests nuevos en verde, ruff + mypy limpios, `next build` con las 3 páginas nuevas.
