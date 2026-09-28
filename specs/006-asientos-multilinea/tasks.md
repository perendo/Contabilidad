# Tasks: Asientos Contables Multilínea (SPEC-006)

**Input**: Design documents from `/specs/006-asientos-multilinea/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3, US4)
- Incluir ruta exacta del archivo en la descripción

---

## Trazabilidad FR ↔ User Story

| Requisito | Descripción breve | User Story |
|---|---|---|
| FR-001 | Admitir N líneas Debe y M Haber sin límite fijo | US1 |
| FR-002 | Exigir al menos una partida en cada lado | US2 |
| FR-003 | Balance estricto multilínea con precisión decimal | US1 |
| FR-004 | Persistir cabecera y líneas en transacción indivisible | US1 |
| FR-005 | Anular con asiento rectificativo invertido | US3 |
| FR-006 | Validar cuentas existen, apuntables y empresa activa | US1 |
| FR-007 | Admitir líneas repetidas sin colapsar ni rechazar | US1 |
| FR-008 | Conservar líneas en importación/exportación masiva | US4 |
| FR-009 | Interfaz de entrada con varias partidas por teclado | US1 |
| FR-010 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo de validación y anulación multilínea en backend y frontend.

- [x] T001 [P] Crear estructura del módulo: `backend/src/services/journal/__init__.py`, `backend/src/services/journal/validador_multilinea.py`, `backend/src/services/journal/anulador.py`
- [x] T002 [P] Crear estructura frontend: `frontend/src/app/contabilidad/asientos/nuevo/`, `frontend/src/components/journal/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Validador multilínea y utilidades que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [x] T003 Implementar validador multilínea en `backend/src/services/journal/validador_multilinea.py`: función `validar_asiento_multilinea(lineas: list[dict], empresa_id: int) -> list[ErrorValidacion]` que verifica: (a) al menos una línea con debe>0, (b) al menos una línea con haber>0, (c) ninguna línea con debe=0 y haber=0, (d) ninguna línea con debe>0 y haber>0, (e) sum(debe)==sum(haber) en Decimal, (f) todas las cuentas existen y son apuntables, (g) límite configurable de líneas (default 100)
- [x] T004 [P] Tests del validador multilínea: `backend/tests/unit/test_validador_multilinea.py` — tests: balance 3:2 (pasa), lado vacío (rechaza), desbalanceo (rechaza), línea con ambos campos (rechaza), línea vacía (rechaza), cuenta inexistente (rechaza), límite de líneas (rechaza), cuenta repetida admitida (pasa), 1:1 clásico (pasa)
- [x] T005 [P] Tests de aislamiento multi-tenant foundational: `backend/tests/integration/test_multilinea_tenant_isolation.py` — crear asiento en empresa A, verificar que empresa B no lo ve; intentar anular desde B → 404

**Checkpoint**: Foundation ready — user story implementation puede empezar.

---

## Phase 3: User Story 1 — Registrar asiento multilínea (Priority: P1) ?? MVP — cubre FR-001, FR-003, FR-004, FR-006, FR-007, FR-009, FR-010

**Goal**: El contador registra un asiento con varias partidas al Debe y varias al Haber, todo a la vez, con balance estricto y persistencia indivisible.

**Independent Test**: Registrando un asiento con 3 débitos y 2 créditos balanceados, se persisten las 5 partidas de forma indivisible; uno desbalanceado se rechaza entero.

### Tests for User Story 1

- [x] T006 [P] [US1] Test creación multilínea balanceada: `backend/tests/unit/test_crear_multilinea.py` — crear asiento 3:2 con Debe==Haber, verificar 5 líneas persistidas, total_debe==total_haber, cabecera y líneas indivisibles
- [x] T007 [P] [US1] Test rechazo desbalanceo: `backend/tests/unit/test_rechazo_desbalanceo.py` — asiento 2:1 desbalanceado → 422, verificar que NO se crea ninguna línea ni cabecera
- [x] T008 [P] [US1] Test rechazo lado vacío: `backend/tests/unit/test_rechazo_lado_vacio.py` — asiento sin Debe → 422 lado_vacio DEBE; sin Haber → 422 lado_vacio HABER

### Implementation for User Story 1

- [x] T009 [US1] Implementar servicio `crear_asiento_multilinea` en `backend/src/services/journal/motor.py`: recibir cabecera + lista de líneas, llamar a `validar_asiento_multilinea`, si pasa: asignar `numero_asiento` correlativo (empresa_id, ejercicio) con `SELECT ... FOR UPDATE`, persistir `JournalEntry` + `JournalEntryLine` en `async with async_session.begin()`, registrar audit log. Si falla, devolver errores sin escribir nada
- [x] T100 [US1] Implementar endpoint POST `/api/v1/asientos` en `backend/src/api/journal.py`: recibir body con fecha, concepto, lineas (array de cuenta/debe/haber/detalle), llamar a `crear_asiento_multilinea`, devolver 201 con el asiento creado o 422 con errores de validación
- [x] T101 [US1] Tests integración creación multilínea: `backend/tests/integration/test_crear_multilinea_completa.py` — crear asiento 3:2 vía endpoint, verificar respuesta 201, verificar JournalEntry + 5 JournalEntryLine en BD, verificar Debe==Haber
- [x] T102 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_crear_multilinea_tenant.py` — empresa A crea asiento 3:2, empresa B no lo ve en GET /asientos/{id}
- [x] T103 [US1] Tests constitución V US1: `backend/tests/unit/test_constitucion_multilinea_crear.py` — verificar que todo asiento creado tiene Debe==Haber; verificar que no se crea ningún asiento desbalanceado

**Checkpoint**: User Story 1 completa — asientos multilínea funcionales. MVP desplegable.

---

## Phase 4: User Story 2 — Registrar asiento clásico 1:1 (Priority: P1) — cubre FR-002

**Goal**: El contador también puede registrar la forma clásica (1 débito, 1 crédito); el sistema trata ambos casos igual con al menos una partida por lado.

**Independent Test**: Registrando un asiento 1:1 balanceado, se guarda correctamente; registrando un asiento con un lado vacío, se rechaza.

### Tests for User Story 2

- [x] T104 [P] [US2] Test caso clásico 1:1: `backend/tests/unit/test_caso_classico_1_1.py` — crear asiento 1:1 balanceado, verificar persistencia correcta
- [x] T105 [P] [US2] Test 1 línea por lado: `backend/tests/unit/test_minimo_dos_lados.py` — verificar que exactamente 1 línea por lado es válido; 0 en un lado es rechazado

### Implementation for User Story 2

- [x] T106 [US2] No requiere implementación adicional: el servicio `crear_asiento_multilinea` de T009 ya acepta el caso 1:1. Verificar que el endpoint y el validador lo soportan correctamente.
- [x] T107 [US2] Tests integración 1:1: `backend/tests/integration/test_caso_classico_completo.py` — crear asiento 1:1 vía endpoint, verificar persistencia, verificar que el listado lo muestra correctamente
- [x] T108 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_classico_tenant.py` — empresa A crea 1:1, empresa B no lo ve

**Checkpoint**: User Stories 1 y 2 completas — asientos 1:1 y N:M funcionales.

---

## Phase 5: User Story 3 — Anular asiento multilínea (Priority: P2) — cubre FR-005

**Goal**: El contador anula un asiento multilínea ya asentado; el sistema genera el rectificativo con todas las líneas invertidas y el original permanece intacto.

**Independent Test**: Anulando un asiento de 3 débitos y 2 créditos, el rectificativo contiene 2 débitos y 3 créditos invertidos y permanece balanceado.

### Tests for User Story 3

- [x] T109 [P] [US3] Test anulación invertida: `backend/tests/unit/test_anulacion_invertida.py` — asiento 3:2 → rectificativo 2:3, verificar inversión de cada línea (debe↔haber)
- [x] T110 [P] [US3] Test anulación balanceada: `backend/tests/unit/test_anulacion_balance.py` — verificar Debe==Haber en rectificativo, verificar que suma neta rectificativo + original = 0
- [x] T111 [P] [US3] Test original intacto: `backend/tests/unit/test_original_intacto.py` — verificar que el asiento original no fue modificado después de la anulación

### Implementation for User Story 3

- [x] T112 [US3] Implementar servicio `anular_asiento` en `backend/src/services/journal/anulador.py`: recibir `asiento_original_id`, verificar que está `POSTED`, crear nuevo `JournalEntry` con `tipo=REVERSAL` y `asiento_original_id`, crear líneas invertidas (cada línea original: si debe=X → nueva haya=X, si haber=Y → nueva debe=Y), calcular balance del rectificativo, persistir todo en `async with async_session.begin()`, registrar audit log
- [x] T113 [US3] Implementar endpoint POST `/api/v1/asientos/{id}/anular` en `backend/src/api/journal.py`: verificar que el asiento pertenece a la empresa activa, llamar a `anular_asiento`, devolver 201 con el rectificativo o 409 si no está POSTED
- [x] T114 [US3] Tests integración anulación completa: `backend/tests/integration/test_anulacion_completa.py` — crear asiento 3:2, anular, verificar rectificativo creado con líneas invertidas, verificar asiento original intacto, verificar que ambos están balanceados
- [x] T115 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_anulacion_tenant.py` — empresa A crea y anula, empresa B no ve ni el original ni el rectificativo
- [x] T116 [US3] Tests constitución V US3: `backend/tests/unit/test_constitucion_anulacion.py` — verificar inmutabilidad del original, verificar que rectificativo es un JournalEntry nuevo, verificar balance

**Checkpoint**: User Stories 1, 2 y 3 completas — creación y anulación multilínea funcional.

---

## Phase 6: User Story 4 — Importar y exportar asientos multilínea (Priority: P3) — cubre FR-008

**Goal**: El contador importa y exporta asientos multilínea por archivos CSV/Excel sin perder líneas.

**Independent Test**: Exportando un asiento multilínea e importándolo de vuelta, el número de partidas y su balance se conservan.

### Tests for User Story 4

- [x] T117 [P] [US4] Test exportación multilínea: `backend/tests/unit/test_exportar_multilinea.py` — exportar asiento 3:2, verificar que el CSV/XLSX tiene 5 filas (una por línea), todas del mismo numero_asiento
- [x] T118 [P] [US4] Test importación multilínea: `backend/tests/unit/test_importar_multilinea.py` — importar archivo con grupo multilínea, verificar que se crea el asiento con todas las líneas y balance correcto
- [x] T119 [P] [US4] Test roundtrip: `backend/tests/unit/test_roundtrip_multilinea.py` — crear asiento 3:2, exportar, importar de vuelta, verificar mismo número de partidas y balance

### Implementation for User Story 4

- [x] T120 [P] [US4] Ampliar exportador en `backend/src/services/importexport/exportador.py`: verificar que la generación CSV/XLSX de SPEC-005 incluye todas las líneas de cada asiento multilínea (una fila por JournalEntryLine, misma columna numero_asiento para agrupar)
- [x] T121 [P] [US4] Ampliar importador en `backend/src/services/importexport/importador.py`: verificar que el parseador de SPEC-005 agrupa correctamente las filas multilínea por numero_asiento y pasa la lista completa de líneas al validador de SPEC-006
- [x] T122 [US4] Tests integración import-export multilínea: `backend/tests/integration/test_importexport_multilinea.py` — exportar asiento 3:2, importar, verificar que se crea el asiento con todas las líneas y Debe==Haber
- [x] T123 [US4] Tests aislamiento multi-tenant US4: `backend/tests/integration/test_importexport_multilinea_tenant.py` — empresa A exporta, empresa B importa el mismo archivo → cuentas no encontradas

**Checkpoint**: User Stories 1, 2, 3 y 4 completas — flujo completo multilínea funcional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [x] T124 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_multilinea_full.py` — verificar que todo asiento (creado, importado) tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry; verificar aislamiento empresa_id en todas las operaciones
- [x] T125 [P] Hardening multi-tenant: `backend/tests/integration/test_multilinea_full_tenant_isolation.py` — escenario completo cross-empresa (crear A, anular A, consultar B → 404, importar B con archivo de A → cuentas no encontradas)
- [x] T126 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_multilinea.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [x] T127 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes; verificar que no se usa `float` en la suma de líneas
- [x] T128 Frontend entrada contable: `frontend/src/components/journal/line-editor.tsx` — componente de filas dinámicas con teclado (Enter añadir fila, Tab mover, Ctrl+Supr eliminar); indicador de balance en tiempo real
- [x] T129 Frontend página nueva: `frontend/src/app/contabilidad/asientos/nuevo/page.tsx` — formulario de entrada multilínea optimizado por teclado, integrado con el componente line-editor
- [x] T130 Limpieza y documentación: actualizar docstrings en servicios journal, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **US3 (Phase 5)**: Depende de Phase 3 (requiere asientos creados para anular).
- **US4 (Phase 6)**: Depende de Phase 2; puede empezar en paralelo con US1/US3; integra con SPEC-005.
- **Polish (Phase 7)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1)**: Sin dependencias de US1; usa Phase 2 completa; se ejecuta en paralelo con US1.
- **US3 (P2)**: Depende de US1 (necesita asientos multilínea para anular).
- **US4 (P3)**: Depende de Phase 2; integra con SPEC-005; puede ejecutarse en paralelo.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T002).
- Phase 2: tests [P] en paralelo (T004-T005).
- Phase 3: tests [P] en paralelo (T006-T008).
- Phase 4: tests [P] en paralelo (T104-T105).
- Phase 5: tests [P] en paralelo (T109-T111).
- Phase 6: tests [P] en paralelo (T117-T119), ampliaciones [P] (T120-T121).
- US1, US2, US4 pueden ejecutarse en paralelo una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T006: "Test creación multilínea en backend/tests/unit/test_crear_multilinea.py"
Task T007: "Test rechazo desbalanceo en backend/tests/unit/test_rechazo_desbalanceo.py"
Task T008: "Test rechazo lado vacío en backend/tests/unit/test_rechazo_lado_vacio.py"

# Implementación secuencial después de tests:
Task T009: "Servicio crear_asiento_multilinea en backend/src/services/journal/motor.py"
Task T100: "Endpoint POST asientos en backend/src/api/journal.py"
Task T101: "Tests integración en backend/tests/integration/test_crear_multilinea_completa.py"
Task T102: "Tests aislamiento en backend/tests/integration/test_crear_multilinea_tenant.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T006-T103. Verificar quickstart Scenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 + US2 → Test independiente → Deploy/Demo (MVP! creación multilínea y 1:1).
3. + US3 → Test independiente → Deploy/Demo (anulación multilínea).
4. + US4 → Test independiente → Deploy/Demo (importación/exportación multilínea).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 + US2 (creación, paralela entre sí).
   - Dev B: User Story 3 (anulación, requiere US1 completa).
   - Dev C: User Story 4 (import/export, paralela).
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
- Esta feature no crea tablas nuevas; amplía las validaciones sobre JournalEntry y JournalEntryLine de SPEC-002.
- El motor multilínea es la base para SPEC-005 (importación), SPEC-007 (facturación) y cualquier futuro módulo que genere asientos.

---

## Estado real (implementacion 2026-09-20)

40/40 tareas cerradas (trazabilidad FR <> US verificada). Sin migraciones nuevas (amplia validaciones sobre `JournalEntry` y
`JournalEntryLine` de SPEC-002).

### Backend

- `backend/src/services/journal/validador_multilinea.py`: `validar_asiento_multilinea`
  (lado_vacio, desbalanceo, precision >4, importe_negativo, cuenta inexistente / no
  apuntable, limite 100 lineas, cuentas repetidas admitidas). `MultilineaError` con
  `__first__` y errores en `validation_errors`.
- `backend/src/services/journal/motor.py`: `crear_asiento_multilinea` (usa
  `crear_borrador` + `asentar` de SPEC-002, numeracion correlativa con
  `next_numero`), `obtener_asiento` y `listar_asientos` (paginado con
  limit/offset y filtros por estado/fecha; `AsientoError` page_size_invalido/estado_invalido).
- `backend/src/services/journal/anulador.py`: `anular_asiento` delega en
  `services.journal.reversal.anular` de SPEC-002 y devuelve el contrato
  `{"asiento_rectificativo": {...}, "asiento_original_id": ...}`.
- API en `backend/src/api/journal/asientos.py` (router versionado `/api/v1/asientos`
  con `Depends(get_empresa_id)`): `POST /asientos` (201/422), `POST /asientos/{id}/anular`
  (201/404/409), `GET /asientos` (paginado + filtros), `GET /asientos/{id}` (404).
  Errores 422 con `detail.id`: lado_vacio, desbalanceo, linea_invalida,
  cuenta_no_encontrada, cuenta_no_apuntable, precision_invalida, importe_negativo,
  limite_lineas_excedido; 409 estado_invalido; 400 ejercicio_cerrado/ejercicio_invalido.
- `main.py`: registrado `asientos_router`; se reordeno `importexport_router`
  ANTES de `asientos_router` para que las rutas estaticas `/exportar` e
  `/importar/*` ganen a la plantilla `/asientos/{entry_id}` (uuid).

### Frontend

- `frontend/src/components/journal/line-editor.tsx` (T128): filas dinamicas con
  AccountAutocomplete por codigo, Enter anade fila, Ctrl+Supr elimina, indicador de
  balance en tiempo real, boton Guardar deshabilitado si no cuadra.
- `frontend/src/app/contabilidad/asientos/nuevo/page.tsx` (T129/T002): formulario
  multilinea que crea via `POST /api/v1/asientos` y navega al detalle.

### Desviaciones

- `reversal.anular` de SPEC-002 marca el original `POSTED` -> `CANCELLED` (es la
  unica transicion permitida por los triggers de inmutabilidad). El requisito
  "original intacto" se interpreta como contenido (concepto, fecha, tipo, lineas) sin
  cambios; el estado pasa a CANCELLED por diseno de SPEC-002.
- Import/export (T120/T121) quedo como verificacion: el exportador de SPEC-005 ya
  emite una fila por `JournalEntryLine` y el parseador agrupa por `numero_asiento`;
  no hizo falta ampliar codigo. Tests T117-T119/T122-T123 lo cubren, incluyendo el
  rechazo cross-tenant (cuenta exclusiva de A -> cuenta_no_encontrada en B, status 422
  cuando no hay asientos validos).
- `asientos_client` del conftest monta `importexport_router` + `asientos_router`
  (mismo orden que `main.py`) para que los tests HTTP de import/export funcionen.

### Verificacion

- pytest SQLite: 644 passed / 5 skipped. PostgreSQL 16.4 real (esquema limpio +
  migraciones 000-006): 649 passed / 0 skipped.
- ruff check src tests: all checks passed. mypy: no issues found in 135 source files.
- Frontend: tsc --noEmit OK, eslint src OK, next build 31 rutas
  (incluye /contabilidad/asientos/nuevo).