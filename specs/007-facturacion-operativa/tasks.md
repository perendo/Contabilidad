# Tasks: Facturación Operativa (SPEC-007)

**Input**: Design documents from `/specs/007-facturacion-operativa/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

**Nota**: La spec incluye aclaraciones integradas — recargo de equivalencia (FR-010) y criterio de caja (FR-011) — incorporadas en US1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo `invoice`/`invoicing` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo: `backend/src/models/invoice/__init__.py`, `backend/src/models/invoice/factura.py`, `backend/src/models/invoice/factura_linea.py`, `backend/src/models/invoice/serie_factura.py`, `backend/src/services/invoicing/__init__.py`
- [X] T002 [P] Crear estructura de servicios: `backend/src/services/invoicing/numeracion.py`, `backend/src/services/invoicing/calculo_impuestos.py`, `backend/src/services/invoicing/emision.py`, `backend/src/services/invoicing/rectificacion.py`, `backend/src/services/invoicing/asiento_factura.py`, `backend/src/services/invoicing/recargo_equivalencia.py`, `backend/src/services/invoicing/criterio_caja.py`
- [X] T003 [P] Crear router API: `backend/src/api/invoicing.py` con prefijo `/api/v1/facturacion`, dependency de sesión autenticada `empresa_id`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/invoicing/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant
- [X] T005 [P] Crear estructura frontend: `frontend/src/app/facturacion/facturas/`, `frontend/src/app/facturacion/series/`, `frontend/src/components/invoicing/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos base y cálculos de impuestos que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T006 [P] Crear modelo `SerieFactura` en `backend/src/models/invoice/serie_factura.py`: empresa_id (PK), codigo VARCHAR(10), nombre, prefijo, sufijo, siguiente_numero BIGINT, estado ENUM (activa/inactiva); constraint único (empresa_id, codigo)
- [X] T007 [P] Crear modelo `Factura` en `backend/src/models/invoice/factura.py`: empresa_id, serie_id FK, numero BIGINT, ejercicio INT, fecha DATE, tipo ENUM (VENTA/COMPRA/RECTIFICATIVA), tercero_id FK SPEC-008, factura_original_id FK NULL, importe_base/iva/recargo/irpf/total NUMERIC(18,4), regimen_caja BOOLEAN, iva_devengado BOOLEAN, estado ENUM (borrador/emitida/anulada), asiento_id FK SPEC-002 NULL; constraint unicidad (empresa_id, serie_id, ejercicio, numero)
- [X] T008 [P] Crear modelo `FacturaLinea` en `backend/src/models/invoice/factura_linea.py`: empresa_id, factura_id FK, descripcion, cantidad NUMERIC(18,4), precio_unitario NUMERIC(18,4), porcentaje_descuento NUMERIC(5,2), base NUMERIC(18,4), tipo_iva/cuota_iva, tipo_recargo/cuota_recargo, tipo_irpf/base_irpf/cuota_irpf; check cantidad>0, precio>0, descuento 0..100
- [X] T009 [P] Implementar servicio de cálculo de impuestos en `backend/src/services/invoicing/calculo_impuestos.py`: función `calcular_linea(linea) -> dict` que calcula base (cantidad×precio×(1−descuento)), cuota_iva, cuota_recargo (FR-010), cuota_irpf en `Decimal`, con redondeo a 2 decimales por línea; función `calcular_totales(lineas) -> dict` que agrega base/iva/recargo/irpf/total
- [X] T010 [P] Implementar servicio de recargo de equivalencia en `backend/src/services/invoicing/recargo_equivalencia.py`: tipos 5,20 / 1,40 / 0,50; cuota separada 477/472 recargo; solo si la empresa está en régimen (configuración SPEC-001)
- [X] T011 [P] Implementar servicio de criterio de caja en `backend/src/services/invoicing/criterio_caja.py`: función que marca `regimen_caja=true`, `iva_devengado=false`, dejando el IVA 477/472 diferido para SPEC-012
- [X] T012 [P] Tests de cálculo de impuestos: `backend/tests/unit/test_calculo_impuestos.py` — verificar base/IVA/recargo/IRPF exactos a 4 decimales; redondeo línea a línea; base negativa rechazada; descuento 100% → base 0; sin error de redondeo acumulado
- [X] T013 [P] Tests de modelos fundacionales: `backend/tests/unit/test_invoice_models.py` — unicidad (empresa_id, serie_id, ejercicio, numero), check constraints de línea, estado ENUM
- [X] T014 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_invoice_tenant_isolation.py` — crear serie/factura en empresa A, verificar que empresa B no las ve

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Emitir factura con asiento automático (Priority: P1) ?? MVP

**Goal**: El usuario emite una factura de venta/compra con sus líneas, IVA, IRPF (y recargo/criterio de caja si aplican); se asigna el número correlativo y se genera el asiento balanceado vinculado.

**Independent Test**: Emitiendo una factura se genera el número correlativo y un asiento balanceado enlazado; no se puede emitir en ejercicio cerrado.

### Tests for User Story 1

- [X] T015 [P] [US1] Test correlatividad factura: `backend/tests/unit/test_correlatividad_factura.py` — emitir 3 facturas en la misma serie y ejercicio, verificar numero correlativo sin saltos; serie o ejercicio distinto → secuencia independiente
- [X] T016 [P] [US1] Test asiento factura balanceado: `backend/tests/unit/test_asiento_factura_balance.py` — emitir factura venta con IVA, verificar asiento Debe==Haber (430 vs 700+477); con IRPF (475); con recargo (477 recargo separado)
- [X] T017 [P] [US1] Test cálculo IRPF: `backend/tests/unit/test_calculo_irpf.py` — verificar importe_irpf y asiento con 475; base+IVA−IRPF == total
- [X] T018 [P] [US1] Test ejercicio cerrado: `backend/tests/unit/test_factura_ejercicio_cerrado.py` — emitir factura con fecha en ejercicio cerrado → 400; sin persistiendo número ni asiento
- [X] T019 [P] [US1] Test recargo equivalencia: `backend/tests/unit/test_recargo_equivalencia.py` — cuota recargo separada en cuenta 477 recargo; importe_total = base + IVA + recargo
- [X] T020 [P] [US1] Test criterio de caja: `backend/tests/unit/test_criterio_caja.py` — factura con regimen_caja=true, iva_devengado=false, IVA íntegro en 477 diferido

### Implementation for User Story 1

- [X] T021 [US1] Implementar servicio de numeración en `backend/src/services/invoicing/numeracion.py`: asignar `numero` correlativo por (empresa_id, serie_id, ejercicio) con `SELECT ... FOR UPDATE` en secuencia bloqueada dentro de la misma transacción; reservar número anulado (no se reutiliza); formatear como `{prefijo}{correlativo}`
- [X] T022 [US1] Implementar servicio `emitir_factura` en `backend/src/services/invoicing/emision.py`: validar estado `borrador`, validar fecha en ejercicio abierto, validar tercero (SPEC-008), calcular impuestos con `calculo_impuestos`, aplicar recargo (FR-010) y criterio de caja (FR-011) si la empresa está en régimen, asignar número, crear el asiento vinculado, cambiar estado a `emitida`, todo en transacción ACID con audit log
- [X] T023 [US1] Implementar generador de asiento en `backend/src/services/invoicing/asiento_factura.py`: crear JournalEntry (tipo NORMAL) + JournalEntryLine balanceado: venta → Debe 430 (total) | Haber 700 (base) + 477 (IVA) + 477 (recargo) − 475/473 (IRPF); compra → Debe 600… + 472 (IVA + recargo) | Haber 410 (total) − 475 (IRPF); usar el motor de SPEC-002/006
- [X] T024 [US1] Implementar endpoints en `backend/src/api/invoicing.py`: POST crear factura borrador (201), POST emitir (200), GET listar (paginación), GET detalle (con líneas y asiento)
- [X] T025 [US1] Crear página frontend `frontend/src/app/facturacion/facturas/nueva/page.tsx`: formulario de factura con líneas dinámicas (cantidad, precio, descuento, tipo IVA, tipo recargo, tipo IRPF), resumen de totales, botón emitir
- [X] T026 [US1] Crear página frontend `frontend/src/app/facturacion/facturas/[id]/page.tsx`: detalle de factura con líneas e asiento vinculado
- [X] T027 [US1] Crear listado frontend `frontend/src/app/facturacion/facturas/page.tsx`: tabla paginada con filtros (serie/estado/fecha/ejercicio)
- [X] T028 [US1] Tests integración emisión completa: `backend/tests/integration/test_emision_factura.py` — crear factura, emitir, verificar número correlativo, asiento balanceado (Debe==Haber), tercero con subcuenta 430/410, respuesta de la API
- [X] T029 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_emision_factura_tenant.py` — empresa A emite factura, empresa B no la ve en listado/detalle
- [X] T030 [US1] Tests constitución V US1: `backend/tests/unit/test_constitucion_factura_emision.py` — verificar balance del asiento, inmutabilidad del asiento emitido, aislamiento empresa_id

**Checkpoint**: User Story 1 completa — emisión de facturas con asiento automático funcional. MVP desplegable.

---

## Phase 4: User Story 2 — Rectificar factura (abono) (Priority: P2)

**Goal**: El usuario emite factura rectificativa (abono); el sistema genera el asiento de anulación invertido respetando la inmutabilidad del asiento original.

**Independent Test**: Rectificando una factura se genera la factura abono con su número correlativo y el asiento invertido, sin alterar el original.

### Tests for User Story 2

- [X] T031 [P] [US2] Test rectificativa invertida: `backend/tests/unit/test_rectificativa_invertida.py` — rectificar factura de 2 líneas, verificar líneas de la RECTIFICATIVA invertidas y numeración propia
- [X] T032 [P] [US2] Test reversal balanceado: `backend/tests/unit/test_reversal_factura_balance.py` — verificar que el asiento REVERSAL cuadra Debe==Haber
- [X] T033 [P] [US2] Test original intacto: `backend/tests/unit/test_original_factura_intacto.py` — verificar que el asiento original NO fue modificado tras la rectificación

### Implementation for User Story 2

- [X] T034 [P] [US2] Implementar servicio `rectificar_factura` en `backend/src/services/invoicing/rectificacion.py`: crear `Factura` tipo RECTIFICATIVA con `factura_original_id` y líneas invertidas (como SPEC-006), asignar número correlativo de su serie, generar asiento REVERSAL invertido enlazado, todo en transacción ACID con audit log; admitir rectificación sobre factura ya rectificada enlazando a la original
- [X] T035 [US2] Implementar endpoint POST `/api/v1/facturacion/facturas/{id}/rectificar` en `backend/src/api/invoicing.py`: verificar que la factura está `emitida` (409 si borrador/anulada), llamar a `rectificar_factura`, devolver 201 con la RECTIFICATIVA y el asiento REVERSAL
- [X] T036 [US2] Crear página frontend `frontend/src/app/facturacion/facturas/[id]/rectificar/page.tsx`: formulario de abono con motivo y selección de líneas (total o parcial)
- [X] T037 [US2] Tests integración rectificación completa: `backend/tests/integration/test_rectificacion_completa.py` — emitir factura, rectificar, verificar RECTIFICATIVA con líneas invertidas, REVERSAL balanceado, original intacto
- [X] T038 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_rectificacion_tenant.py` — empresa A rectifica, empresa B no ve la RECTIFICATIVA ni el REVERSAL
- [X] T039 [US2] Tests constitución V US2: `backend/tests/unit/test_constitucion_factura_rectificacion.py` — inmutabilidad del original, REVERSAL balanceado, aislamiento

**Checkpoint**: User Stories 1 y 2 completas — emisión y rectificación funcionales.

---

## Phase 5: User Story 3 — Gestionar serie, numeración y estados (Priority: P2)

**Goal**: El usuario configura series por empresa y conoce el estado de cada factura (borrador/emitida/anulada); numeración correlativa sin saltos con reserva de anulados.

**Independent Test**: Emitiendo y anulando facturas en una serie, la numeración avanza correlativamente y los estados quedan registrados.

### Tests for User Story 3

- [X] T040 [P] [US3] Test reserva de números anulados: `backend/tests/unit/test_reserva_numero_anulado.py` — anular factura, verificar que el número NO se reutiliza y el estado es `anulada`
- [X] T041 [P] [US3] Test estados factura: `backend/tests/unit/test_estados_factura.py` — verificar transiciones borrador→emitida→anulada; bloqueo de borrado de emitida (409); borrado de borrador permitido
- [X] T042 [P] [US3] Test serie inactiva: `backend/tests/unit/test_serie_inactiva.py` — emitir factura con serie inactiva → bloqueo
- [X] T043 [P] [US3] Test anulación factura: `backend/tests/unit/test_anulacion_factura.py` — anular factura emitida por rectificativa total → estado `anulada` y numeración reservada

### Implementation for User Story 3

- [X] T044 [US3] Implementar CRUD de series en `backend/src/services/invoicing/numeracion.py` y endpoints en `backend/src/api/invoicing.py`: POST crear serie, GET listado, PATCH estado (activa/inactiva); validar unicidad (empresa_id, codigo)
- [X] T045 [US3] Implementar endpoint POST `/api/v1/facturacion/facturas/{id}/anular` en `backend/src/api/invoicing.py`: marcar factura `emitida` como `anulada` (requiere licencia de rectificativa total); 409 si no está emitida
- [X] T046 [US3] Implementar DELETE `/api/v1/facturacion/facturas/{id}`: solo facturas `borrador` (204); 409 si emitida o anulada
- [X] T047 [US3] Crear página frontend `frontend/src/app/facturacion/series/page.tsx`: CRUD de series y configuración de prefijo/sufijo
- [X] T048 [US3] Tests integración estados y numeración: `backend/tests/integration/test_estados_numeracion.py` — emitir, anular, rectificar y verificar reserva de números y estados correctos
- [X] T049 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_series_tenant.py` — empresa A crea serie, empresa B no la ve ni la usa

**Checkpoint**: User Stories 1, 2 y 3 completas — flujo total de facturación funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T050 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_invoicing.py` — verificar que todo asiento generado (emisión, rectificación) tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry; verificar aislamiento empresa_id en todas las tablas de facturación
- [X] T051 [P] Hardening multi-tenant: `backend/tests/integration/test_invoicing_full_tenant_isolation.py` — escenario completo cross-empresa (serie A, factura A, rectificativa B desde A → todos 404)
- [X] T052 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_facturacion.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T053 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [X] T054 Verificar recargo de equivalencia y criterio de caja en integración: `backend/tests/integration/test_fr010_fr011_integracion.py` — emitir factura con recargo y criterio de caja, verificar cuota separada y diferimiento IVA en la BD
- [X] T055 Ambiguity check: verificar que una factura no puede emitirse dos veces (idempotencia), que los números no se reutilizan ni perforan, y que las cuentas 430/410 provienen del maestro SPEC-008
- [X] T056 Limpieza y documentación: actualizar docstrings en servicios invoicing, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 3 (necesita una factura emitida para rectificar).
- **US3 (Phase 5)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Depende de US1 (necesita facturas emitidas).
- **US3 (P2)**: Sin dependencias de US2; puede operar en paralelo usando facturas de US1.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1 y 2: todos los [P] en paralelo.
- Phase 3: tests [P] en paralelo (T015-T020); servicios [P] de cálculo (T009-T011).
- Phase 4: tests [P] en paralelo (T031-T033); servicio [P] (T034).
- Phase 5: tests [P] en paralelo (T040-T043).
- US1 y US3 pueden ejecutarse en paralelo una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T015: "Test correlatividad factura en backend/tests/unit/test_correlatividad_factura.py"
Task T016: "Test asiento balanceado en backend/tests/unit/test_asiento_factura_balance.py"
Task T017: "Test cálculo IRPF en backend/tests/unit/test_calculo_irpf.py"
Task T018: "Test ejercicio cerrado en backend/tests/unit/test_factura_ejercicio_cerrado.py"
Task T019: "Test recargo equivalencia en backend/tests/unit/test_recargo_equivalencia.py"
Task T020: "Test criterio de caja en backend/tests/unit/test_criterio_caja.py"

# Servicios de impuestos en paralelo:
Task T009: "Cálculo impuestos en backend/src/services/invoicing/calculo_impuestos.py"
Task T010: "Recargo equivalencia en backend/src/services/invoicing/recargo_equivalencia.py"
Task T011: "Criterio de caja en backend/src/services/invoicing/criterio_caja.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T015-T030. Verificar quickstart Scenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP! emisión con asiento automático).
3. + US2 → Test independiente → Deploy/Demo (rectificativas).
4. + US3 → Test independiente → Deploy/Demo (series, numeración, estados).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (emisión + asiento automático, incluye FR-010/FR-011).
   - Dev B: User Story 3 (series, numeración, estados).
3. Dev A entrega US1; Dev B entrega US3; después:
   - Dev A: User Story 2 (rectificativas).
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
- Dependencias externas: SPEC-001 (plan de cuentas + config IVA/IRPF), SPEC-002/006 (motor de asientos), SPEC-004 (ejercicios), SPEC-008 (terceros con subcuenta 430/410), SPEC-012 (criterio de caja gestión del devengo).

---

## Estado real (implementación 2026-09-20)

56/56 tareas completadas. Puertas en verde: pytest **696 passed / 5 skipped** (SQLite),
`ruff` + `mypy` limpios (152 fuentes), `tsc` + `eslint` + `next build` **36 rutas**
(incl. `/facturacion/{facturas,facturas/nueva,facturas/[id],facturas/[id]/rectificar,series}`).

### Desviaciones documentadas

1. **T003/T004 (estructura API)**: implementado como paquete `backend/src/api/invoicing/`
   (`__init__.py`, `deps.py`, `routes.py`, `series.py`, `facturas.py`) en lugar del
   módulo único `api/invoicing.py`, alineado con el patrón de `api/ciclo/`. `deps.py`
   re-exporta `api.deps.get_empresa_id` (JWT + `X-Empresa-Activa`, nunca del cliente).
2. **Sin migración SQL**: `serie_factura`, `factura` y `factura_linea` se crean vía
   `Base.metadata.create_all` en tests (precedente de `models/ar`); no se añadió
   `migrations/007_*.sql`, por lo que la verificación PostgreSQL real (opt-in) sigue
   cubriendo solo el esquema migrado 000–006.
3. **T006 (PK de `SerieFactura`)**: PK es `id` UUID con `UNIQUE(empresa_id, id)` y
   `UNIQUE(empresa_id, codigo)` (la tarea sugería `empresa_id` como PK); se mantiene la
   convención del proyecto y el filtrado multi-tenant por `empresa_id` en claves e índices.
4. **T021 (numeración)**: el correlativo por `(empresa_id, serie_id, ejercicio)` se deriva
   como `MAX(numero)+1` entre las facturas del ejercicio bajo `SELECT ... FOR UPDATE`
   sobre la fila de la serie (secuencia bloqueada, const. IV); `SerieFactura.siguiente_numero`
   se conserva como contador global (high-water). También por serie o ejercicio distinto
   la secuencia es independiente y los números anulados quedan reservados.
5. **T023 (asiento)**: emisión vía motor multilínea SPEC-002/006 (POSTED + correlativo de
   diario). Cuentas por defecto de config SPEC-001: venta `4300` (total) / `7000` + `4770`
   + `4772` (recargo) − `4750` (IRPF al Debe); compra `6000` + `4720` + `4722` / `4100`
   (total) + `4750` (IRPF al Haber). La subcuenta del tercero (430/410) se resuelve desde
   `TerceroSubcuenta` de SPEC-008.
6. **T034 (rectificación)**: rectificación total invierte las líneas reales del asiento
   original; la parcial (`lineas`) reconstruye e invierte solo el abono. `factura_original_id`
   enlaza siempre a la factura raíz del encadenamiento; el asiento original nunca se toca.
7. **Ficheros de test consolidados**: en lugar de los ~20 nombres de fichero `unit/test_*.py`
   del backlog, los tests viven en `tests/unit/test_invoicing_calculo.py` (T012/T019/T020),
   `tests/integration/test_facturacion_us1.py` (T015–T030), `tests/integration/test_facturacion_us2.py`
   (T031–T039), `tests/integration/test_facturacion_us3.py` (T040–T049) y
   `tests/unit/test_constitucion_facturacion.py` (T030/T039/T050). La fixture
   `facturacion_client` (`tests/conftest.py`) siembra PGC + cuentas fiscales `472/4720/4722`,
   `475/4750`, `477/4770/4772`, terceros con subcuentas 430/410 y una serie activa por empresa.
8. **T052 (quickstart)**: los 6 escenarios de `quickstart.md` quedan cubiertos por los tests
   de integración equivalentes (no se creó `test_quickstart_facturacion.py`).
9. **T053 (transacción ACID)**: los servicios usan `flush()` dentro del boundary de `get_db`
   (patrón obligatorio del proyecto), no `async with async_session.begin()` anidado; ningún
   endpoint acepta `empresa_id` del body/path y todos los importes son `Decimal`/`NUMERIC(18,4)`.
10. **T046 (DELETE)**: `204` al borrar un borrador y `409 estado_invalido` si la factura
    no está en borrador (emitida o anulada); el estado se comprueba explícitamente.
11. **FR-011 (criterio de caja)**: `regimen_caja=true` + `iva_devengado=false`; el IVA se
    contabiliza íntegro en 477/472 quedando diferido (la gestión del devengo pertenece a SPEC-012).


---

# Deuda conocida (2026-09-29): esta spec no tiene migración SQL

Anotada durante la corrección de SPEC-013, que descubrió que **esta spec tampoco la
tenía**. No es una tarea hecha: es un estado que hace que la funcionalidad **no exista
en la aplicación real**. Detalle del hallazgo en [AGENTS.md](../../../AGENTS.md) §52.3 y
[`correcciones.md`](../../../correcciones.md) §3.

## Qué pasa

Las tablas de esta spec existen en los tests porque `Base.metadata.create_all` las
crea en el SQLite en memoria. **En PostgreSQL no existen**: no hay fichero en
`backend/migrations/` que las cree, así que cualquier endpoint que las use responde
**500** con `UndefinedTableError` contra la base de datos real.

Todas las puertas de la spec pasaron en verde cuando se cerró. Ninguna lo detectó
porque `test_migrations.py` comprueba que las migraciones **declaradas** estén en el
inventario, no que cada tabla del ORM tenga una: un modelo sin migración no está en el
inventario, así que no hay nada que faltar.

## Tablas afectadas

- `factura`
- `factura_linea`
- `serie_factura`

## Qué se ha hecho, y qué no

**Sí**: un guard nuevo en `tests/unit/test_migrations.py`,
`test_toda_tabla_del_orm_tiene_migracion`, que cruza los `__tablename__` de
`src/models/` con los `CREATE TABLE` de `migrations/`. Con él, **una tabla nueva sin
migración se ve al escribir el modelo**, y no meses después. Las 27 están inventariadas
en `TABLAS_SIN_MIGRACION`, con dos guards que impiden que la lista mienta en ninguna de
las dos direcciones.

**No**: la migración de estas 3 tablas. Es trabajo de un día por spec —DDL, enums,
índices, unicidades, FKs compuestas por `empresa_id`, triggers de inmutabilidad que
correspondan, el contrato en `test_pg_schema.py` y los tasks que lo nombren— y no cabe
en una corrección puntual. Lo que **no** hay que hacer es volver a dar la spec por
cerrada sin mirar este apartado: la spec está implementada y probada, y aun así su
funcionalidad no se puede usar.
