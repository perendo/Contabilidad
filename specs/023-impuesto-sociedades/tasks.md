# Tasks: Impuesto sobre Sociedades (Modelo 200) (SPEC-023)

**Input**: Design documents from `/specs/023-impuesto-sociedades/`

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
| FR-001 | Aislar cálculo y contabilización IS por empresa/ejercicio | US1 |
| FR-002 | Calcular base imposible desde resultado contable | US1 |
| FR-003 | Calcular cuota con tipo y deducciones configuradas | US1 |
| FR-004 | Descontar pagos a cuenta 473 y cuota diferencial | US1 |
| FR-005 | Generar asiento 630 contra 473/4752/4757 atómico | US2 |
| FR-006 | Exportar modelo 200 y validar consistencia | US3 |
| FR-007 | Cálculo provisional en cierres intermedios | US1 |
| FR-008 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo fiscal (IS) en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo fiscal: `backend/src/models/fiscal/__init__.py`, `backend/src/models/fiscal/calculo_is.py`, `backend/src/models/fiscal/ajuste_extracontable.py`, `backend/src/models/fiscal/modelo_200.py`, `backend/src/services/fiscal/__init__.py`, `backend/src/services/fiscal/impuesto_sociedades.py`, `backend/src/services/fiscal/modelo_200_gen.py`, `backend/src/api/fiscal/__init__.py`
- [X] T002 [P] Configurar router fiscal: registrar prefijo `/api/v1/fiscal` en `backend/src/api/fiscal/routes.py` con dependency de sesión autenticada `empresa_id`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/fiscal/impuesto-sociedades/`, `frontend/src/app/fiscal/modelo-200/`, `frontend/src/components/fiscal/`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/fiscal/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `CalculoIS` en `backend/src/models/fiscal/calculo_is.py`: campos empresa_id (PK compuesto), id UUID PK, ejercicio INT, resultado_contable NUMERIC(18,4), ajustes_positivos NUMERIC(18,4), ajustes_negativos NUMERIC(18,4), base_imponible NUMERIC(18,4), tipo_impositivo NUMERIC(5,2), cuota_integra NUMERIC(18,4), deducciones NUMERIC(18,4), cuota_liquida NUMERIC(18,4), pagos_a_cuenta NUMERIC(18,4), cuota_diferencial NUMERIC(18,4), provisional BOOLEAN DEFAULT true, estado ENUM (borrador/calculado/contabilizado), asiento_id UUID NULL FK, notas TEXT; constraint unicidad (empresa_id, ejercicio) para definitivos; constraint tipo_impositivo > 0
- [X] T006 [P] Crear modelo `AjusteExtracontable` en `backend/src/models/fiscal/ajuste_extracontable.py`: empresa_id, id UUID PK, calculo_is_id FK, tipo ENUM (AJUSTE_POSITIVO/AJUSTE_NEGATIVO/DEDUCCION/BONIFICACION), descripcion VARCHAR(500), referencia_normativa VARCHAR(255) NULL, importe NUMERIC(18,4); constraint importe > 0
- [X] T007 [P] Crear modelo `Modelo200` en `backend/src/models/fiscal/modelo_200.py`: empresa_id, id UUID PK, calculo_is_id FK, fecha_generacion TIMESTAMPTZ, contenido JSONB, hash_contenido CHAR(64)
- [X] T008 Implementar `get_empresa_id()` en `backend/src/api/fiscal/deps.py`: extraer empresa_id de sesión autenticada; validar que la empresa está activa; raise 401 si no hay sesión
- [X] T009 [P] Tests de modelos fundacionales: `backend/tests/unit/test_is_models.py` — verificar unicidad (empresa_id, ejercicio) para definitivos, constraint tipo_impositivo > 0, constraint importe ajuste > 0, FK compuesta empresa_id
- [X] T010 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_is_tenant_isolation.py` — crear cálculo en empresa A, verificar que empresa B no la ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Calcular la base y la cuota del IS (Priority: P1) MVP — cubre FR-001, FR-002, FR-003, FR-004, FR-007, FR-008

**Goal**: El usuario prepara el IS del ejercicio con ajustes extracontables, deducciones y pagos a cuenta. El sistema calcula base imponible, cuota y diferencial.

**Independent Test**: Calculando el IS con ajustes y pagos a cuenta se obtiene la cuota diferencial correcta.

### Tests for User Story 1

- [X] T011 [P] [US1] Test cálculo IS completo: `backend/tests/unit/test_calculo_is.py` — crear cálculo con resultado=100000, ajuste_pos=12000, deduccion=8000, pagos_473=20000, tipo=25%; verificar: base=112000, cuota_integra=28000, cuota_liquida=20000, cuota_diferencial=0
- [X] T012 [P] [US1] Test cálculo con cuota diferencial positiva: `backend/tests/unit/test_calculo_is_positivo.py` — pagos_473 < cuota_liquida → cuota_diferencial > 0 (a pagar)
- [X] T013 [P] [US1] Test cálculo con cuota diferencial negativa: `backend/tests/unit/test_calculo_is_negativo.py` — pagos_473 > cuota_liquida → cuota_diferencial < 0 (a devolver)
- [X] T014 [P] [US1] Test cálculo provisional se sobrescribe: `backend/tests/unit/test_calculo_is_provisional.py` — crear provisional, recalcular, verificar que se actualiza; crear definitivo → bloquea segundo definitivo

### Implementation for User Story 1

- [X] T015 [US1] Implementar servicio `calcular_is` en `backend/src/services/fiscal/impuesto_sociedades.py`: obtener resultado contable del cierre (SPEC-004), sumar ajustes, calcular base, aplicar tipo impositivo, restar deducciones, obtener pagos a cuenta del submayor 473, calcular cuota diferencial; persistir CalculoIS con estado `calculado`; todo en transacción ACID
- [X] T016 [US1] Implementar servicio `agregar_ajuste` en `backend/src/services/fiscal/impuesto_sociedades.py`: crear AjusteExtracontable; recalcular totales del cálculo; validar ejercicio abierto y cálculo no contabilizado
- [X] T017 [US1] Implementar servicio `eliminar_ajuste` en `backend/src/services/fiscal/impuesto_sociedades.py`: eliminar ajuste; recalcular totales; validar cálculo no contabilizado
- [X] T018 [US1] Implementar endpoints en `backend/src/api/fiscal/calculos_is.py`: POST crear cálculo (201), POST recalcular (200), POST agregar ajuste (201), GET listar (paginación), GET detalle (con ajustes), DELETE ajuste
- [X] T019 [US1] Crear página frontend `frontend/src/app/fiscal/impuesto-sociedades/nuevo/page.tsx`: formulario de creación de cálculo (ejercicio, provisional)
- [X] T020 [US1] Crear página frontend `frontend/src/app/fiscal/impuesto-sociedades/[id]/page.tsx`: detalle del cálculo con ajustes, deducciones, botón recalcular, botón contabilizar
- [X] T021 [US1] Tests integración cálculo completo: `backend/tests/integration/test_is_calculo_completo.py` — crear cálculo, agregar ajustes, recalcular, verificar base/cuota/diferencial correctos
- [X] T022 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_is_tenant.py` — empresa A calcula IS, empresa B no lo ve; intento de calcular desde empresa B → 404

**Checkpoint**: User Story 1 completa — cálculo del IS funcional. MVP desplegable.

---

## Phase 4: User Story 2 — Contabilizar el gasto por impuesto (Priority: P1) — cubre FR-005

**Goal**: El usuario contabiliza el impuesto del ejercicio. El sistema genera el asiento 630 contra 473/4752 de forma balanceada y atómica.

**Independent Test**: Contabilizando el IS se genera el asiento 630/473/4752 balanceado.

### Tests for User Story 2

- [X] T023 [P] [US2] Test asiento IS a pagar: `backend/tests/unit/test_asiento_is_pagar.py` — cuota_diferencial > 0, verificar Debe==Haber (630 cuota_liquida vs 473 pagos + 4752 diferencial)
- [X] T024 [P] [US2] Test asiento IS a devolver: `backend/tests/unit/test_asiento_is_devolver.py` — cuota_diferencial < 0, verificar Debe==Haber (630 cuota_liquida + 4709 diferencial vs 473 pagos)
- [X] T025 [P] [US2] Test asiento IS cuota cero: `backend/tests/unit/test_asiento_is_cero.py` — cuota_liquida = pagos_a_cuenta, verificar Debe==Haber (630 vs 473)

### Implementation for User Story 2

- [X] T026 [P] [US2] Implementar servicio `contabilizar_is` en `backend/src/services/fiscal/impuesto_sociedades.py`: validar estado `calculado`; crear asiento balanceado (partida doble validada en backend): si cuota_diferencial > 0: Debe 630 (cuota_liquida) | Haber 473 (pagos) + 4752 (diferencial); si < 0: Debe 630 + 4709 (diferencial) | Haber 473; si = 0: Debe 630 | Haber 473; cambiar estado a `contabilizado`; todo en transacción ACID con audit log
- [X] T027 [US2] Implementar endpoint POST `/api/v1/fiscal/is/calculos/{id}/contabilizar` en `backend/src/api/fiscal/calculos_is.py`
- [X] T028 [US2] Crear botón "Contabilizar" en `frontend/src/app/fiscal/impuesto-sociedades/[id]/page.tsx` con confirmación
- [X] T029 [US2] Tests integración contabilización completa: `backend/tests/integration/test_is_contabilizacion.py` — calcular, contabilizar, verificar asiento balanceado con Debe==Haber, verificar cambio de estado, verificar que no se puede contabilizar dos veces
- [X] T030 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_is_contab_tenant.py` — empresa A contabiliza, empresa B no ve el asiento

**Checkpoint**: User Stories 1 y 2 completas — cálculo + contabilización del IS.

---

## Phase 5: User Story 3 — Obtener el modelo 200 y su presentación (Priority: P2) — cubre FR-006

**Goal**: El usuario genera el soporte del modelo 200 con los datos calculados para su presentación.

**Independent Test**: Generando el modelo 200 se obtienen todos los bloques con importes consistentes.

### Tests for User Story 3

- [X] T031 [P] [US3] Test generación modelo 200: `backend/tests/unit/test_modelo_200.py` — generar modelo a partir de cálculo contabilizado, verificar que contiene los 5 bloques; verificar que la validación de consistencia pasa
- [X] T032 [P] [US3] Test validación de inconsistencias: `backend/tests/unit/test_modelo_200_validacion.py` — si base_imponible ≠ resultado + ajustes → 422; si cuota_integra ≠ base × tipo → 422

### Implementation for User Story 3

- [X] T033 [P] [US3] Implementar servicio `generar_modelo_200` en `backend/src/services/fiscal/modelo_200_gen.py`: recibir calculo_is_id; validar que está contabilizado; validar consistencia de datos; generar contenido JSONB con los 5 bloques (ver contracts/modelo-200.md); calcular hash SHA-256; persistir Modelo200; todo en transacción ACID
- [X] T034 [US3] Implementar servicio `descargar_modelo_200` en `backend/src/services/fiscal/modelo_200_gen.py`: convertir contenido JSONB a PDF/CSV; establecer Content-Disposition para descarga
- [X] T035 [US3] Implementar endpoints POST crear modelo (201), GET descargar en `backend/src/api/fiscal/modelo_200.py`
- [X] T036 [US3] Crear página frontend `frontend/src/app/fiscal/modelo-200/page.tsx`: listado de modelos generados, botón generar nuevo, botón descargar
- [X] T037 [US3] Tests integración modelo 200 completo: `backend/tests/integration/test_modelo_200_completo.py` — calcular IS, contabilizar, generar modelo, verificar bloques y consistencia
- [X] T038 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_modelo_200_tenant.py` — empresa A genera modelo, empresa B no lo ve

**Checkpoint**: User Stories 1, 2 y 3 completas — flujo total de IS funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T039 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_is.py` — verificar que todo asiento del IS tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry confirmado; verificar aislamiento empresa_id en todas las tablas
- [X] T040 [P] Hardening multi-tenant: `backend/tests/integration/test_is_full_tenant_isolation.py` — escenario completo cross-empresa (cálculo A, contabilización B, modelo A → todos 404)
- [X] T041 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_is.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T042 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [X] T043 Validación de ejercicios cerrados: verificar que el IS definitivo requiere ejercicio cerrado (SPEC-002/004)
- [X] T044 Limpieza y documentación: actualizar docstrings en servicios fiscal, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2 y de US1 (requiere cálculo para contabilizar). No puede empezar en paralelo con US1.
- **US3 (Phase 5)**: Depende de Phase 2, US1 y US2 (requiere cálculo contabilizado para generar modelo).
- **Polish (Phase 6)**: Depende de las user stories completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1)**: Depende de US1 (requiere cálculo para contabilizar). Secuencial con US1.
- **US3 (P2)**: Depende de US1 y US2 (requiere cálculo contabilizado). Secuencial con US1+US2.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T007).
- Phase 3: tests [P] en paralelo (T011-T014).
- Las User Stories NO pueden ejecutarse en paralelo (US2 depende de US1; US3 depende de US1+US2).

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T011: "Test cálculo IS completo en backend/tests/unit/test_calculo_is.py"
Task T012: "Test cálculo positivo en backend/tests/unit/test_calculo_is_positivo.py"
Task T013: "Test cálculo negativo en backend/tests/unit/test_calculo_is_negativo.py"
Task T014: "Test cálculo provisional en backend/tests/unit/test_calculo_is_provisional.py"

# Servicios secuenciales (dependen de modelos Phase 2):
Task T015: "calcular_is en backend/src/services/fiscal/impuesto_sociedades.py"
Task T016: "agregar_ajuste en backend/src/services/fiscal/impuesto_sociedades.py"

# Frontend en paralelo tras endpoints:
Task T019: "Formulario nuevo cálculo en frontend/src/app/fiscal/impuesto-sociedades/nuevo/page.tsx"
Task T020: "Detalle cálculo en frontend/src/app/fiscal/impuesto-sociedades/[id]/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T011-T022. Verificar quickstart Scenario 1 y 4.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP!).
3. + US2 → Test independiente → Deploy/Demo (contabilización del IS).
4. + US3 → Test independiente → Deploy/Demo (modelo 200).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (cálculo del IS).
   - Dev B espera a Dev A para US2 (contabilización).
   - Dev C espera a Dev B para US3 (modelo 200).
3. Las stories son secuenciales por dependencia; no hay paralelismo entre ellas.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Las User Stories de IS son secuenciales (US1→US2→US3) por dependencia de datos.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.

## Estado real (implementación 2026-09-24)

- **44/44 tareas completadas**: modelos, servicios, API, frontend, migración 014,
  triggers PostgreSQL/SQLite y pruebas de las tres historias.
- **Puertas SPEC-023**: 49 pruebas backend verdes, 4 contratos PostgreSQL 16 verdes,
  ruff + mypy limpios (312 fuentes), TypeScript + ESLint + Next build verdes con 80 rutas.
- **Suite global**: 1354 passed / 5 skipped; el único fallo de la corrida fue
  `test_suggest_perf`, flaky conocido, y sus 2 pruebas quedaron verdes aisladas.
- **Desviaciones**: boundary ACID del proyecto (`get_db` + `flush`) en vez de un
  `async_session.begin()` anidado; cuentas apuntables 6300/4730/4752/4709; campos
  domiciliarios no existentes en `Company` se exportan como `null`; Modelo 200 se
  descarga en CSV UTF-8 determinista en vez de PDF.
- **Cierre PostgreSQL**: un cálculo definitivo exige ejercicio cerrado; su contabilización
  usa el servicio fiscal explícito con balance validado y `next_numero`, evitando el guard
  genérico del motor que rechaza cualquier asiento en un ejercicio cerrado.
