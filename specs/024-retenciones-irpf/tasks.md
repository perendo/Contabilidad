# Tasks: Retenciones IRPF y Modelos 111/115/190 (SPEC-024)

**Input**: Design documents from `/specs/024-retenciones-irpf/`

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
| FR-001 | Aislar retenciones y liquidaciones por empresa | US1 |
| FR-002 | Acumular retenciones IRPF por periodo y alquileres | US1 |
| FR-003 | Generar modelos 111 y 115 con deuda 4751 cuadrada | US1 |
| FR-004 | Generar asiento liquidación 4751 vs 572 atómico | US2 |
| FR-005 | Generar modelo 190 anual por perceptor con NIF | US3 |
| FR-006 | Recalcular retenciones desde rectificativas | US1 |
| FR-007 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo fiscal (retenciones) en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo fiscal: `backend/src/models/fiscal/__init__.py`, `backend/src/models/fiscal/retencion.py`, `backend/src/models/fiscal/liquidacion_retenciones.py`, `backend/src/models/fiscal/modelo_111.py`, `backend/src/models/fiscal/modelo_115.py`, `backend/src/models/fiscal/modelo_190.py`, `backend/src/services/fiscal/__init__.py`, `backend/src/services/fiscal/retenciones.py`, `backend/src/services/fiscal/liquidacion_retenciones.py`, `backend/src/services/fiscal/modelo_111_gen.py`, `backend/src/services/fiscal/modelo_115_gen.py`, `backend/src/services/fiscal/modelo_190_gen.py`, `backend/src/api/fiscal/__init__.py`
- [X] T002 [P] Configurar router fiscal: registrar prefijo `/api/v1/fiscal/retenciones` en `backend/src/api/fiscal/routes_retenciones.py` con dependency de sesión autenticada `empresa_id`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/fiscal/retenciones/`, `frontend/src/app/fiscal/liquidacion/`, `frontend/src/app/fiscal/modelos/`, `frontend/src/components/fiscal/`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/fiscal/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `LiquidacionRetenciones` en `backend/src/models/fiscal/liquidacion_retenciones.py`: campos empresa_id (PK compuesto), id UUID PK, ejercicio INT, trimestre INT (1-4), periodo VARCHAR(7), total_base_retenciones NUMERIC(18,4), total_retenciones NUMERIC(18,4), n_perceptores INT, estado ENUM (pendiente/liquidado), fecha_liquidacion DATE NULL, asiento_id UUID NULL FK, modelo_111_id UUID NULL FK, modelo_115_id UUID NULL FK, notas TEXT; constraint unicidad (empresa_id, ejercicio, trimestre)
- [X] T006 [P] Crear modelo `RetencionPeriodo` en `backend/src/models/fiscal/retencion.py`: empresa_id, id UUID PK, liquidacion_retenciones_id FK, tercero_id FK → SPEC-008, nif VARCHAR(9), nombre VARCHAR(100), tipo_retencion ENUM (IRPF_PROFESIONALES/IRPF_ARRENDAMIENTOS/IRPF_OBRAS/IRPF_OTROS), base_imponible NUMERIC(18,4), tipo_porcentaje NUMERIC(5,2), retencion_practicada NUMERIC(18,4), facturas JSONB
- [X] T007 [P] Crear modelo `Modelo111` en `backend/src/models/fiscal/modelo_111.py`: empresa_id, id UUID PK, liquidacion_retenciones_id FK, ejercicio INT, trimestre INT, fecha_generacion TIMESTAMPTZ, contenido JSONB, hash_contenido CHAR(64)
- [X] T008 [P] Crear modelo `Modelo115` en `backend/src/models/fiscal/modelo_115.py`: empresa_id, id UUID PK, liquidacion_retenciones_id FK, ejercicio INT, trimestre INT, fecha_generacion TIMESTAMPTZ, contenido JSONB, hash_contenido CHAR(64)
- [X] T009 [P] Crear modelo `Modelo190` en `backend/src/models/fiscal/modelo_190.py`: empresa_id, id UUID PK, ejercicio INT, fecha_generacion TIMESTAMPTZ, contenido JSONB, hash_contenido CHAR(64), n_perceptores INT
- [X] T010 Implementar `get_empresa_id()` en `backend/src/api/fiscal/deps.py`: extraer empresa_id de sesión autenticada; validar que la empresa está activa; raise 401 si no hay sesión
- [X] T011 [P] Tests de modelos fundacionales: `backend/tests/unit/test_retenciones_models.py` — verificar unicidad (empresa_id, ejercicio, trimestre), constraint retencion_practicada = base × tipo, FK compuesta empresa_id
- [X] T012 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_retenciones_tenant_isolation.py` — crear liquidación en empresa A, verificar que empresa B no la ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Acumular retenciones del periodo e ingresar el modelo 111 (Priority: P1) MVP — cubre FR-001, FR-002, FR-003, FR-006, FR-007

**Goal**: El usuario consulta las retenciones IRPF generadas en facturas (SPEC-007) y de alquileres. El sistema acumula por trimestre y genera el modelo 111/115 con la cuota a ingresar.

**Independent Test**: Consultando retenciones del trimestre se genera el 111 con el importe acumulado y la deuda (4751) cuadrada.

### Tests for User Story 1

- [X] T013 [P] [US1] Test acumulación retenciones: `backend/tests/unit/test_acumulacion_retenciones.py` — crear facturas con retención en Q3, crear liquidación Q3, verificar total_retenciones = suma de retenciones de facturas; verificar n_perceptores correcto
- [X] T014 [P] [US1] Test modelo 111 balance: `backend/tests/unit/test_modelo_111_balance.py` — generar modelo 111, verificar que contenido tiene los bloques correctos; verificar que total_retenciones coincide con la liquidación
- [X] T015 [P] [US1] Test modelo 115 solo arrendamientos: `backend/tests/unit/test_modelo_115_filtro.py` — generar modelo 115 solo con retenciones tipo IRPF_ARRENDAMIENTOS; verificar que no incluye profesionales
- [X] T016 [P] [US1] Test duplicidad liquidación: `backend/tests/unit/test_liquidacion_duplicada.py` — intentar crear segunda liquidación para el mismo trimestre → 409

### Implementation for User Story 1

- [X] T017 [US1] Implementar servicio `acumular_retenciones` en `backend/src/services/fiscal/retenciones.py`: consultar facturas con retención (SPEC-007) del trimestre natural; agrupar por tercero_id, tipo_retencion; calcular base_imponible y retencion_practicada; crear LiquidacionRetenciones + RetencionPeriodo; todo en transacción ACID
- [X] T018 [US1] Implementar servicio `generar_modelo_111` en `backend/src/services/fiscal/modelo_111_gen.py`: recibir liquidacion_id; generar contenido JSONB con bloques del modelo 111 (ver contracts/modelo-111.md); calcular hash SHA-256; persistir Modelo111
- [X] T019 [US1] Implementar servicio `generar_modelo_115` en `backend/src/services/fiscal/modelo_115_gen.py`: recibir liquidacion_id; filtrar solo retenciones de arrendamiento; generar contenido JSONB con bloques del modelo 115 (ver contracts/modelo-115.md); calcular hash SHA-256; persistir Modelo115
- [X] T020 [US1] Implementar endpoints en `backend/src/api/fiscal/retenciones.py`: POST crear liquidación (201), GET listar liquidaciones (paginación), GET detalle liquidación, GET retenciones por liquidación, POST generar 111 (201), POST generar 115 (201), GET descargar 111/115
- [X] T021 [US1] Crear página frontend `frontend/src/app/fiscal/retenciones/nueva/page.tsx`: formulario de creación de liquidación trimestral
- [X] T022 [US1] Crear página frontend `frontend/src/app/fiscal/retenciones/[id]/page.tsx`: detalle de liquidación con retenciones por perceptor, botones generar 111/115
- [X] T023 [US1] Crear listado frontend `frontend/src/app/fiscal/retenciones/page.tsx`: tabla paginada con filtros (ejercicio, trimestre, estado)
- [X] T024 [US1] Tests integración acumulación completa: `backend/tests/integration/test_acumulacion_completa.py` — crear facturas con retención, crear liquidación, verificar acumulación correcta, generar 111, verificar modelo
- [X] T025 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_retenciones_tenant.py` — empresa A acumula retenciones, empresa B no las ve

**Checkpoint**: User Story 1 completa — acumulación y modelos 111/115 funcionales. MVP desplegable.

---

## Phase 4: User Story 2 — Contabilizar la liquidación trimestral (Priority: P2) — cubre FR-004

**Goal**: El usuario realiza el pago/ingreso de la retención. El sistema genera el asiento (4751 contra 572) y deja el periodo liquidado.

**Independent Test**: Liquidando el trimestre se genera el asiento de pago de retenciones y el 4751 queda a cero.

### Tests for User Story 2

- [X] T026 [P] [US2] Test asiento liquidación: `backend/tests/unit/test_asiento_liquidacion_retenciones.py` — crear liquidación con total_retenciones=5000, contabilizar, verificar Debe==Haber (4751 vs 572); verificar cambio de estado a liquidado
- [X] T027 [P] [US2] Test liquidación ya contabilizada: `backend/tests/unit/test_liquidacion_duplicada_contab.py` — intentar contabilizar dos veces → 409
- [X] T028 [P] [US2] Test liquidación sin retenciones: `backend/tests/unit/test_liquidacion_sin_retenciones.py` — liquidación con total=0 → 422

### Implementation for User Story 2

- [X] T029 [P] [US2] Implementar servicio `contabilizar_liquidacion` en `backend/src/services/fiscal/liquidacion_retenciones.py`: validar estado `pendiente` y total_retenciones > 0; crear asiento Debe 4751 (total_retenciones) | Haber 572 (total_retenciones); cambiar estado a `liquidado`; registrar fecha_liquidacion; todo en transacción ACID con audit log
- [X] T030 [US2] Implementar endpoint POST `/api/v1/fiscal/retenciones/liquidaciones/{id}/contabilizar` en `backend/src/api/fiscal/retenciones.py`
- [X] T031 [US2] Crear botón "Contabilizar" en `frontend/src/app/fiscal/retenciones/[id]/page.tsx` con confirmación
- [X] T032 [US2] Tests integración liquidación completa: `backend/tests/integration/test_liquidacion_completa.py` — crear liquidación, contabilizar, verificar asiento balanceado, verificar estado, verificar que no se puede contabilizar dos veces
- [X] T033 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_liquidacion_tenant.py` — empresa A liquida, empresa B no ve el asiento

**Checkpoint**: User Stories 1 y 2 completas — acumulación + liquidación + modelos 111/115.

---

## Phase 5: User Story 3 — Generar el modelo 190 anual (Priority: P2) — cubre FR-005

**Goal**: El usuario genera el modelo 190 con el resumen anual de retenciones e ingresos a cuenta por perceptor.

**Independent Test**: Generando el 190 se listan los perceptores con sus retenciones anuales.

### Tests for User Story 3

- [X] T034 [P] [US3] Test generación 190: `backend/tests/unit/test_modelo_190.py` — crear liquidaciones de Q1-Q4 con retenciones, generar 190, verificar que contiene todos los perceptores del año; verificar que la suma anual = suma de trimestrales
- [X] T035 [P] [US3] Test validación NIF: `backend/tests/unit/test_190_validacion_nif.py` — generar 190 con perceptor sin NIF → 422 con lista de perceptores incompletos
- [X] T036 [P] [US3] Test 190 duplicado: `backend/tests/unit/test_190_duplicado.py` — generar 190 para un ejercicio, intentar generar otro → 409

### Implementation for User Story 3

- [X] T037 [P] [US3] Implementar servicio `validar_nif_perceptores` en `backend/src/services/fiscal/modelo_190_gen.py`: consultar todos los perceptores con retenciones del ejercicio; verificar que todos tienen NIF en SPEC-008; retornar lista de los que faltan
- [X] T038 [US3] Implementar servicio `generar_modelo_190` en `backend/src/services/fiscal/modelo_190_gen.py`: recibir ejercicio; validar NIF; agregar retenciones por perceptor (Q1-Q4); generar contenido JSONB con bloques del modelo 190 (ver contracts/modelo-190.md); calcular hash SHA-256; persistir Modelo190; todo en transacción ACID
- [X] T039 [US3] Implementar endpoints POST validar NIF, POST crear 190 (201), GET descargar 190 en `backend/src/api/fiscal/retenciones.py`
- [X] T040 [US3] Crear página frontend `frontend/src/app/fiscal/modelos/190/page.tsx`: listado de modelos 190 generados, botón validar NIF, botón generar, botón descargar
- [X] T041 [US3] Tests integración 190 completo: `backend/tests/integration/test_190_completo.py` — crear liquidaciones de 4 trimestres, generar 190, verificar bloques y consistencia anual
- [X] T042 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_190_tenant.py` — empresa A genera 190, empresa B no lo ve

**Checkpoint**: User Stories 1, 2 y 3 completas — flujo total de retenciones funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T043 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_retenciones.py` — verificar que todo asiento de liquidación tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry confirmado; verificar aislamiento empresa_id en todas las tablas
- [X] T044 [P] Hardening multi-tenant: `backend/tests/integration/test_retenciones_full_tenant_isolation.py` — escenario completo cross-empresa (acumulación A, liquidación B, 190 A → todos 404)
- [X] T045 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_retenciones.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T046 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [X] T047 Rectificativas: verificar que al emitir factura rectificativa (SPEC-007), la retención del periodo se recalcula automáticamente en la acumulación
- [X] T048 Limpieza y documentación: actualizar docstrings en servicios fiscal, verificar type hints, ejecutar lint/typecheck

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
- **US2 (P2)**: Sin dependencias de US1; usa Phase 2 completa. Puede ejecutarse en paralelo con US1.
- **US3 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa. Puede ejecutarse en paralelo.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T009).
- Phase 3: tests [P] en paralelo (T013-T016).
- Phase 4: tests [P] en paralelo (T026-T028).
- Phase 5: tests [P] en paralelo (T034-T036).
- US1, US2, US3 pueden ejecutarse en paralelo por separado una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T013: "Test acumulación retenciones en backend/tests/unit/test_acumulacion_retenciones.py"
Task T014: "Test modelo 111 balance en backend/tests/unit/test_modelo_111_balance.py"
Task T015: "Test modelo 115 filtro en backend/tests/unit/test_modelo_115_filtro.py"
Task T016: "Test duplicidad liquidación en backend/tests/unit/test_liquidacion_duplicada.py"

# Servicios secuenciales (dependen de modelos Phase 2):
Task T017: "acumular_retenciones en backend/src/services/fiscal/retenciones.py"
Task T018: "generar_modelo_111 en backend/src/services/fiscal/modelo_111_gen.py"
Task T019: "generar_modelo_115 en backend/src/services/fiscal/modelo_115_gen.py"

# Frontend en paralelo tras endpoints:
Task T021: "Formulario nueva liquidación en frontend/src/app/fiscal/retenciones/nueva/page.tsx"
Task T022: "Detalle liquidación en frontend/src/app/fiscal/retenciones/[id]/page.tsx"
Task T023: "Listado retenciones en frontend/src/app/fiscal/retenciones/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T013-T025. Verificar quickstart Scenario 1 y 3.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP!).
3. + US2 → Test independiente → Deploy/Demo (liquidación trimestral).
4. + US3 → Test independiente → Deploy/Demo (modelo 190 anual).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (acumulación + modelos 111/115).
   - Dev B: User Story 2 (liquidación trimestral).
   - Dev C: User Story 3 (modelo 190 anual).
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

## Estado real (implementación 2026-09-25)

SPEC-024 cerrada **48/48**. Total del proyecto: **1.141/1.384 tareas** (24 specs completas).

- **Modelos**: `RetencionPeriodo`, `LiquidacionRetenciones`, `Modelo111`, `Modelo115` y `Modelo190`, con UUID, `UNIQUE(empresa_id,id)`, FKs compuestas, `NUMERIC(18,4)` y uniques por periodo. `FacturaLinea` añade categoría IRPF y dirección de inmueble para clasificar profesionales, arrendamientos, obras y otros.
- **Migración `015_retenciones_irpf.sql`**: tablas, unicidades, checks, triggers de estado final y modelos append-only, seed/backfill de la cuenta 4751 y trigger para empresas nuevas. Espejo SQLite en `db/triggers.py`; aplicada sobre PostgreSQL 16 real.
- **Servicios**: acumulación trimestral tenant-scoped desde facturas emitidas/anuladas, signo de rectificativas, grupos por tercero/tipo/tasa, auditoría y `flush()` ACID; modelos 111/115/190 con cuatro bloques, JSON canónico, SHA-256 y CSV UTF-8 BOM.
- **Liquidación**: asiento POSTED correlativo y balanceado `Debe 4751 | Haber cuenta bancaria`, estado final inmutable y auditoría WORM en la misma transacción.
- **API**: `/api/v1/fiscal/retenciones` con `get_empresa_id`, RBAC `fiscal`, listados, detalle, contabilización, generación/descarga 111/115/190 y validación NIF. La empresa nunca se recibe en body/path.
- **Frontend**: listado, alta y detalle de liquidaciones, acciones 111/115/contabilización y página anual 190 con descarga autenticada. `next build` genera **85 rutas**.
- **Pruebas**: **56 pruebas nuevas** cubren modelos, US1/US2/US3, rectificativas, constitución, aislamiento, API, descargas y los seis escenarios quickstart. PostgreSQL 16: **5 passed** para migración/triggers 015.
- **Desviaciones**: el boundary ACID real del proyecto es `get_db` + `flush()`; PostgreSQL aún no migra las tablas operativas de SPEC-007/008, por lo que la FK a `tercero` y las columnas de `factura_linea` se crean condicionalmente cuando existen; la clasificación legacy por porcentaje solo se usa si la factura no trae categoría explícita; el modelo 190 deja `null` los campos de domicilio no estructurados disponibles en `Company`/`Tercero`.
- **Verificación**: **1410 passed / 7 skipped** (las 2 pruebas `test_suggest_perf`, flaky bajo carga, verdes aisladas), PostgreSQL **5 passed**, ruff + mypy limpios (**324 fuentes**), `tsc` + ESLint + `next build` verdes.
