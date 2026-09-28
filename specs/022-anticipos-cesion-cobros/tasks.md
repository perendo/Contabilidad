# Tasks: Anticipos, Fondos a Cuenta y Cesión de Cobros (SPEC-022)

**Input**: Design documents from `/specs/022-anticipos-cesion-cobros/`

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
| FR-001 | Aislar anticipos, cesiones y aplicaciones por empresa | US1 |
| FR-002 | Registrar anticipos cliente/proveedor con asiento y aplicación | US2 |
| FR-003 | Permitir exceso residual como saldo a favor del tercero | US1 |
| FR-004 | Registrar cesiones de cobro con comisión y notificación | US3 |
| FR-005 | Impedir doble cobro de vencimiento cedido | US3 |
| FR-006 | Rechazar gestión en ejercicio cerrado | US1 |
| FR-007 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo treasury (anticipos/cesiones) en backend y frontend según plan.md.

- [x] T001 [P] Crear estructura del módulo treasury: `backend/src/models/treasury/__init__.py`, `backend/src/models/treasury/anticipo.py`, `backend/src/models/treasury/liquidacion_anticipo.py`, `backend/src/models/treasury/cesion.py`, `backend/src/models/treasury/notificacion_cesion.py`, `backend/src/services/treasury/__init__.py`, `backend/src/services/treasury/anticipo.py`, `backend/src/services/treasury/liquidacion.py`, `backend/src/services/treasury/cesion.py`, `backend/src/api/treasury/__init__.py`
- [x] T002 [P] Configurar router treasury: registrar prefijo `/api/v1` en `backend/src/api/treasury/routes.py` con dependency de sesión autenticada `empresa_id`
- [x] T003 [P] Crear estructura frontend: `frontend/src/app/anticipos/`, `frontend/src/app/cesiones/`, `frontend/src/components/treasury/`
- [x] T004 [P] Crear utils de sesión: `backend/src/api/treasury/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [x] T005 [P] Crear modelo `Anticipo` en `backend/src/models/treasury/anticipo.py`: campos empresa_id (PK compuesto), id UUID PK, tercero_id FK, tipo ENUM (CLIENTE/PROVEEDOR), cuenta_contable VARCHAR(12), fecha DATE, importe NUMERIC(18,4), concepto VARCHAR(255), estado ENUM (pendiente/parcialmente_aplicado/totalmente_aplicado), saldo_pendiente NUMERIC(18,4), asiento_id FK → JournalEntry, notas TEXT; constraint saldo_pendiente >= 0
- [x] T006 [P] Crear modelo `LiquidacionAnticipo` en `backend/src/models/treasury/liquidacion_anticipo.py`: empresa_id, id UUID PK, anticipo_id FK, factura_id FK → SPEC-007, fecha_aplicacion DATE, importe_aplicado NUMERIC(18,4), asiento_id FK, notas TEXT; constraint importe_aplicado > 0
- [x] T007 [P] Crear modelo `CesionCobro` en `backend/src/models/treasury/cesion.py`: empresa_id, id UUID PK, entidad_financiera VARCHAR(100), fecha_cesion DATE, comision NUMERIC(18,4) DEFAULT 0, tipo_comision ENUM (IMPORTE_FIJO/PORCENTAJE), importe_total_cedido NUMERIC(18,4), importe_neto_recibido NUMERIC(18,4), estado ENUM (activa/saldada/cancelada), asiento_id FK, notas TEXT
- [x] T008 [P] Crear modelo `CesionCobroDetalle` en `backend/src/models/treasury/cesion.py`: empresa_id, id UUID PK, cesion_id FK, vencimiento_id FK → SPEC-011, importe NUMERIC(18,4); constraint unicidad (cesion_id, vencimiento_id)
- [x] T009 [P] Crear modelo `NotificacionCesion` en `backend/src/models/treasury/notificacion_cesion.py`: empresa_id, id UUID PK, cesion_id FK, cliente_id FK → SPEC-008, fecha_notificacion DATE, medio ENUM (EMAIL/CORREO/REGISTRO), estado ENUM (pendiente/enviada), notas TEXT
- [x] T010 Implementar `get_empresa_id()` en `backend/src/api/treasury/deps.py`: extraer empresa_id de sesión autenticada; validar que la empresa está activa; raise 401 si no hay sesión
- [x] T011 [P] Tests de modelos fundacionales: `backend/tests/unit/test_anticipo_models.py` — verificar constraint saldo_pendiente >= 0, constraint importe_aplicado > 0, unicidad cesión-vencimiento, FK compuesta empresa_id
- [x] T012 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_anticipo_tenant_isolation.py` — crear anticipo en empresa A, verificar que empresa B no la ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Registrar anticipo de cliente y liquidarlo (Priority: P1) MVP — cubre FR-001, FR-003, FR-006, FR-007

**Goal**: El usuario cobra por anticipado a un cliente. El sistema registra el cobro en 438 y al aplicar contra factura lo liquida con trazabilidad.

**Independent Test**: Cobrando un anticipo y aplicándolo luego contra factura, el anticipo reduce la deuda y queda trazada la liquidación.

### Tests for User Story 1

- [x] T013 [P] [US1] Test asiento anticipo cliente: `backend/tests/unit/test_anticipo_cliente_balance.py` — crear anticipo CLIENTE, verificar Debe==Haber (572 vs 438); verificar saldo_pendiente = importe; verificar cambio de estado
- [x] T014 [P] [US1] Test liquidación anticipo cliente: `backend/tests/unit/test_liquidacion_cliente_balance.py` — crear anticipo, liquidar contra factura, verificar Debe==Haber (430 vs 438); verificar saldo_pendiente actualizado; verificar estado
- [x] T015 [P] [US1] Test exceso anticipo > factura: `backend/tests/unit/test_anticipo_exceso.py` — liquidar anticipo de 3000 contra factura de 2000, verificar saldo_pendiente=1000; intentar liquidar más que el saldo → rechazo

### Implementation for User Story 1

- [x] T016 [US1] Implementar servicio `registrar_anticipo` en `backend/src/services/treasury/anticipo.py`: crear Anticipo con estado `pendiente`, calcular saldo_pendiente=importe, crear asiento Debe 572 | Haber 438 (CLIENTE), validar ejercicio abierto, persistir con audit log en transacción ACID
- [x] T017 [US1] Implementar servicio `liquidar_anticipo` en `backend/src/services/treasury/liquidacion.py`: recibir anticipo_id + lista de aplicaciones; validar saldo suficiente; crear LiquidacionAnticipo por cada aplicación; crear asiento Debe 430 | Haber 438 por cada aplicación; actualizar saldo_pendiente y estado del anticipo; todo en transacción ACID
- [x] T018 [US1] Implementar endpoints en `backend/src/api/treasury/anticipos.py`: POST registrar (201), POST liquidar (200), GET listar (paginación), GET detalle (con liquidaciones), GET liquidaciones de un anticipo
- [x] T019 [US1] Crear página frontend `frontend/src/app/anticipos/nuevo/page.tsx`: formulario de registro de anticipo (tercero, tipo, fecha, importe, concepto)
- [x] T020 [US1] Crear página frontend `frontend/src/app/anticipos/[id]/page.tsx`: detalle de anticipo con saldo, liquidaciones, botón liquidar
- [x] T021 [US1] Crear listado frontend `frontend/src/app/anticipos/page.tsx`: tabla paginada con filtros (tipo, estado, tercero), links a detalle
- [x] T022 [US1] Tests integración anticipo cliente completo: `backend/tests/integration/test_anticipo_cliente_completo.py` — crear anticipo, liquidar contra factura, verificar asientos balanceados, verificar saldo, verificar auditoría
- [x] T023 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_anticipo_tenant.py` — empresa A crea anticipo y lo liquida, empresa B no lo ve; intento de liquidar desde empresa B → 404

**Checkpoint**: User Story 1 completa — anticipo de cliente funcional con liquidación. MVP desplegable.

---

## Phase 4: User Story 2 — Registrar anticipo a proveedor y liquidarlo (Priority: P1) — cubre FR-002

**Goal**: El usuario paga por anticipado a un proveedor. El sistema lo registra en 407/408 y lo liquida contra facturas de compra posteriores.

**Independent Test**: Pagando un anticipo y recibiendo la factura de compra, el anticipo reduce la deuda y el resto se paga.

### Tests for User Story 2

- [x] T024 [P] [US2] Test asiento anticipo proveedor: `backend/tests/unit/test_anticipo_proveedor_balance.py` — crear anticipo PROVEEDOR, verificar Debe==Haber (407 vs 572); verificar saldo_pendiente
- [x] T025 [P] [US2] Test liquidación anticipo proveedor: `backend/tests/unit/test_liquidacion_proveedor_balance.py` — crear anticipo, liquidar contra factura compra, verificar Debe==Haber (407 vs 410)

### Implementation for User Story 2

- [x] T026 [P] [US2] Implementar servicio `registrar_anticipo_proveedor` en `backend/src/services/treasury/anticipo.py`: crear Anticipo PROVEEDOR, asiento Debe 407/408 | Haber 572; reutilizar servicio `registrar_anticipo` con parámetro tipo=PROVEEDOR
- [x] T027 [US2] Implementar servicio `liquidar_anticipo_proveedor` en `backend/src/services/treasury/liquidacion.py`: recibir anticipo_id + factura_id; crear LiquidacionAnticipo; asiento Debe 407 | Haber 410; actualizar saldo; reutilizar servicio `liquidar_anticipo`
- [x] T028 [US2] Crear página frontend `frontend/src/app/anticipos/nuevo/page.tsx`: extender formulario para soportar tipo PROVEEDOR con cuentas 407/408
- [x] T029 [US2] Tests integración anticipo proveedor completo: `backend/tests/integration/test_anticipo_proveedor_completo.py` — crear anticipo, liquidar, verificar asientos balanceados
- [x] T030 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_anticipo_prov_tenant.py` — empresa A crea anticipo proveedor, empresa B no lo ve

**Checkpoint**: User Stories 1 y 2 completas — anticipos de clientes y proveedores con liquidación.

---

## Phase 5: User Story 3 — Ceder cobros (confirming/factoring) con notificación (Priority: P2) — cubre FR-004, FR-005

**Goal**: El usuario cede cobros de clientes a una entidad (factoring/confirming). El sistema registra la cesión, la notificación al cliente y la comisión de la operación.

**Independent Test**: Cediendo un cobro con notificación se registra la cesión y el cliente queda notificado; el vencimiento no puede cobrarse de nuevo.

### Tests for User Story 3

- [x] T031 [P] [US3] Test cesión balance: `backend/tests/unit/test_cesion_balance.py` — crear cesión con 2 vencimientos, verificar Debe==Haber (572+662 vs 430); verificar que los vencimientos pasan a estado cedido; verificar importe_neto_recibido = total - comision
- [x] T032 [P] [US3] Test impedir doble cobro: `backend/tests/unit/test_cesion_doble_cobro.py` — intentar cobrar vencimiento cedido → rechazo 409; intentar ceder vencimiento ya cedido → rechazo 409
- [x] T033 [P] [US3] Test cesión solo vencimientos pendientes: `backend/tests/unit/test_cesion_vencimientos_pendientes.py` — cesión con vencimiento ya cobrado → rechazo 409; cesión vacía → 422

### Implementation for User Story 3

- [x] T034 [P] [US3] Implementar servicio `registrar_cesion` en `backend/src/services/treasury/cesion.py`: validar vencimientos `pendientes`, calcular comisión, crear CesionCobro + CesionCobroDetalle, crear asiento Debe 572 (neto) + 662 (comisión) | Haber 430 (total), cambiar estado vencimientos a `cedido`, todo en transacción ACID
- [x] T035 [US3] Implementar servicio `registrar_notificacion` en `backend/src/services/treasury/cesion.py`: crear NotificacionCesion con estado `enviada`; validar que el cliente está asociado a los vencimientos cedidos
- [x] T036 [US3] Implementar servicio `saldar_cesion` en `backend/src/services/treasury/cesion.py`: cambiar estado de CesionCobro a `saldada`; validar que está en estado `activa`
- [x] T037 [US3] Implementar endpoints en `backend/src/api/treasury/cesiones.py`: POST crear cesión (201), POST notificar (200), POST saldar (200), GET listar (paginación), GET detalle (con vencimientos y notificaciones)
- [x] T038 [US3] Crear página frontend `frontend/src/app/cesiones/nueva/page.tsx`: formulario de cesión con selección de vencimientos pendientes, entidad, comisión
- [x] T039 [US3] Crear página frontend `frontend/src/app/cesiones/[id]/page.tsx`: detalle de cesión con vencimientos, notificaciones, botones notificar/saldar
- [x] T040 [US3] Crear listado frontend `frontend/src/app/cesiones/page.tsx`: tabla paginada con filtros (estado, entidad), links a detalle
- [x] T041 [US3] Tests integración cesión completa: `backend/tests/integration/test_cesion_completa.py` — crear cesión, verificar asiento balanceado, notificar, saldar; verificar doble cobro bloqueado
- [x] T042 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_cesion_tenant.py` — empresa A cede cobros, empresa B no ve la cesión

**Checkpoint**: User Stories 1, 2 y 3 completas — flujo total de anticipos y cesiones funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [x] T043 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_anticipos.py` — verificar que todo asiento (anticipo, liquidación, cesión, comisión) tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry confirmado; verificar aislamiento empresa_id en todas las tablas
- [x] T044 [P] Hardening multi-tenant: `backend/tests/integration/test_anticipos_full_tenant_isolation.py` — escenario completo cross-empresa (anticipo A, cesión B, liquidación A desde B → todos 404)
- [x] T045 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_anticipos.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [x] T046 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [x] T047 Validación de ejercicios cerrados: verificar que anticipos y cesiones rechazan con 409 si el ejercicio está cerrado (SPEC-002/004)
- [x] T048 Limpieza y documentación: actualizar docstrings en servicios treasury, verificar type hints, ejecutar lint/typecheck

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
- **US2 (P1)**: Sin dependencias de US1/US3; usa Phase 2 completa. Puede empezar en paralelo con US1.
- **US3 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T009).
- Phase 3: tests [P] en paralelo (T013-T015).
- Phase 4: tests [P] en paralelo (T024-T025).
- Phase 5: tests [P] en paralelo (T031-T033).
- US1, US2, US3 pueden ejecutarse en paralelo por separado una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T013: "Test asiento anticipo cliente en backend/tests/unit/test_anticipo_cliente_balance.py"
Task T014: "Test liquidación anticipo cliente en backend/tests/unit/test_liquidacion_cliente_balance.py"
Task T015: "Test exceso anticipo en backend/tests/unit/test_anticipo_exceso.py"

# Servicios secuenciales (dependen de modelos Phase 2):
Task T016: "registrar_anticipo en backend/src/services/treasury/anticipo.py"
Task T017: "liquidar_anticipo en backend/src/services/treasury/liquidacion.py"

# Frontend en paralelo tras endpoints:
Task T019: "Formulario nuevo anticipo en frontend/src/app/anticipos/nuevo/page.tsx"
Task T020: "Detalle anticipo en frontend/src/app/anticipos/[id]/page.tsx"
Task T021: "Listado anticipos en frontend/src/app/anticipos/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T013-T023. Verificar quickstart Scenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP!).
3. + US2 → Test independiente → Deploy/Demo (anticipos proveedores).
4. + US3 → Test independiente → Deploy/Demo (cesiones factoring).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (anticipos de clientes + liquidación).
   - Dev B: User Story 2 (anticipos de proveedores + liquidación).
   - Dev C: User Story 3 (cesiones factoring + notificación).
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

## Estado real (implementación 2026-09-24)

Spec cerrada **48/48**. Puertas: pytest **1304 passed / 5 skipped** (SQLite;
`test_suggest_perf` flaky bajo carga, verde aislado), ruff + mypy limpios
(303 fuentes), `tsc` + `eslint` + `next build` **78 rutas** (6 nuevas:
`/anticipos`, `/anticipos/nuevo`, `/anticipos/[id]`, `/cesiones`,
`/cesiones/nueva`, `/cesiones/[id]`). Migración `013_anticipos.sql` (registrada
en `db/migrate.py` y `test_migrations.py`); triggers SQLite en `db/triggers.py`.

### Desviaciones documentadas

1. **FK en migración PG**: en `013_anticipos.sql` las columnas
   `factura_id`/`tercero_id`/`vencimiento_id` son UUID planos **sin constraint FK**
   (los modelos SQLAlchemy sí las declaran, válidas para el `create_all` de SQLite).
   Las FK compuestas reales en PG están a `journal_entry`/`anticipo`/`cesion_cobro`.
2. **Boundary ACID**: se usa el patrón del proyecto (`get_db` + `flush()` dentro
   del boundary), no `async with async_session.begin()` como indica el texto de T046.
3. **RBAC**: todos los endpoints bajo el módulo `treasury` existente
   (`require_permission("treasury", "ver"/"editar")`); no se creó un módulo
   `anticipos`/`cesiones`.
4. **Enums**: `TipoAnticipo`/`EstadoAnticipo` viven en `models/treasury/anticipo.py`
   (single file), no en `anticipo_models.py`.
5. **T047**: cubierto por `tests/integration/test_anticipos_ejercicios_cerrados.py`
   (409 `ejercicio_cerrado` en anticipo/liquidación/cesión con `FiscalYear` 2025
   cerrado sembrado en la fixture `anticipos_client`).
6. **Liquidación**: el asiento usa `haber = anticipo.cuenta_contable` (407/408/438)
   en vez de la cuenta fija del texto de T027; la cuantificación es
   422 `importe_supera_saldo` (aplicación individual) vs 409 `saldo_insuficiente`
   (suma acumulada).

### Tests SPEC-022 (44)

- unit: `test_anticipo_models` (T011), `test_anticipo_cliente_balance` (T013),
  `test_liquidacion_cliente_balance` (T014), `test_anticipo_exceso` (T015),
  `test_anticipo_proveedor_balance` (T024), `test_liquidacion_proveedor_balance`
  (T025), `test_cesion_balance` (T031), `test_cesion_doble_cobro` (T032),
  `test_cesion_vencimientos_pendientes` (T033), `test_constitucion_anticipos` (T043).
- integration: `test_anticipo_tenant_isolation` (T012),
  `test_anticipo_cliente_completo` (T022), `test_anticipo_tenant` (T023),
  `test_anticipo_proveedor_completo` (T029), `test_anticipo_prov_tenant` (T030),
  `test_cesion_completa` (T041), `test_cesion_tenant` (T042),
  `test_anticipos_full_tenant_isolation` (T044), `test_quickstart_anticipos`
  (T045, SC1–SC6), `test_anticipos_ejercicios_cerrados` (T047).
- Helper compartido `tests/unit/anticipo_support.py` (sembrar base de dos empresas,
  sumas/cuentas de un asiento, constantes `CLIENTE`/`PROVEEDOR`).

### Artefactos clave

- `backend/src/models/treasury/{anticipo,liquidacion_anticipo,cesion,notificacion_cesion}.py`
- `backend/src/services/treasury/{anticipo,liquidacion,cesion}.py` (+constantes en `common.py`)
- `backend/src/api/treasury/{anticipos,cesiones}.py` (router en `routes.py`)
- `backend/migrations/013_anticipos.sql`
- `backend/tests/unit/anticipo_support.py` y fixture `anticipos_client` en `conftest.py`
- `frontend/src/components/treasury/api.ts` (+SPEC-022) y `frontend/src/app/{anticipos,cesiones}/*`
