# Tasks: Gestión ONG (Subvenciones, Libros Oficiales y Caja) (SPEC-019)

**Input**: Design documents from `/specs/019-gestion-ong-libros-caja/`

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

**Purpose**: Inicializar módulo `ngo` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo ngo: `backend/src/models/ngo/__init__.py`, `backend/src/services/ngo/__init__.py`, `backend/src/api/ngo/__init__.py`
- [X] T002 [P] Configurar router ngo: registrar prefijo `/api/v1` en `backend/src/api/ngo/__init__.py` con dependency de sesión autenticada y cabecera de empresa activa
- [X] T003 [P] Crear utils de sesión: `backend/src/api/ngo/deps.py` con `get_empresa_activa()` que extrae el `empresa_id` de la sesión y bloquea acceso cross-tenant
- [X] T004 [P] Crear estructura frontend: `frontend/src/app/subvenciones/`, `frontend/src/app/libros/`, `frontend/src/app/caja/`, `frontend/src/components/ngo/`, y cliente HTTP reutilizando `frontend/src/services/client.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `Subvencion` en `backend/src/models/ngo/subvencion.py`: empresa_id PK, id, entidad_concedente, programa, referencia NULL, importe_concedido NUMERIC(18,4), ejercicio SMALLINT, estado ENUM(concedida/en_curso/justificada/reintegrada), partidas JSONB NULL, created_at, updated_at
- [X] T006 [P] Crear modelo `GastoImputado` en `backend/src/models/ngo/gasto_imputado.py`: empresa_id PK, id, subvencion_id FK compuesta, asiento_id FK, linea_id FK a `JournalEntryLine`, importe_asignado NUMERIC(18,4), partida NULL, created_at; índice (empresa_id, subvencion_id)
- [X] T007 [P] Crear modelos `LibroOficial` y `Legalizacion` en `backend/src/models/ngo/libros.py`: LibroOficial con empresa_id PK, id, ejercicio, tipo ENUM(diario/mayor/cuentas_anuales), periodo_desde/hasta, contenido_pdf BYTEA, sha256 CHAR(64), size_bytes, generado_por, created_at; Legalizacion con empresa_id PK, id, ejercicio, rango_asientos_desde/hasta, total_asientos, huella CHAR(64), fichero BYTEA, fecha_emision, fecha_legalizacion NULL, valido BOOLEAN, motivo_reemision NULL
- [X] T008 [P] Crear modelo `Caja` en `backend/src/models/ngo/caja.py`: empresa_id PK, id, nombre único por empresa, cuenta_570_id FK a subcuenta 570 (SPEC-001) con unicidad por empresa (1 caja = 1 570), tipo ENUM(caja/caja_chica), estado ENUM(activa/inactiva), created_at, updated_at
- [X] T009 [P] Crear modelos `MovimientoCaja` y `Arqueo` en `backend/src/models/ngo/arqueo.py`: MovimientoCaja (traza derivada del diario 570: caja_id FK, asiento_id, linea_id, tipo entrada/salida, importe, fecha) sin UPDATE/DELETE; Arqueo con empresa_id PK, id, caja_id FK, fecha, saldo_libros, efectivo_contado, diferencia NUMERIC(18,4), estado ENUM(cuadra/con_diferencia), decision ENUM(pendiente/aprobada/archivada) NULL, asiento_ajuste_id FK NULL, archivado BOOLEAN, detalle_diferencia NULL, created_at
- [X] T010 [P] Tests de modelos fundacionales: `backend/tests/unit/test_ngo_models.py` — unicidad nombre caja y 570, FK compuesta cross-tenant imposible, enums de estado, `diferencia` calculada como `efectivo_contado - saldo_libros`
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_ngo_tenant_isolation.py` — crear subvención/caja en empresa A, verificar que B no las ve; FK compuesta con empresa B → error

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Gestionar subvenciones y justificar gastos (Priority: P1) ?? MVP

**Goal**: El responsable de una ONG registra una subvención y asigna gastos de la contabilidad para justificarla, controlando el disponible y produciendo el informe (concedido/gastado/pendiente).

**Independent Test**: Registrando una subvención y asignándole gastos, el sistema controla el importe disponible y produce el informe de justificación; los gastos de otra empresa no pueden imputarse.

### Tests for User Story 1

- [X] T012 [P] [US1] Test disponible y exceso: `backend/tests/unit/test_subvencion_disponible.py` — verificar acumulado vs concedido; imputar que excede → rechazo 409; control por partidas del programa si aplican (decisión D10)
- [X] T013 [P] [US1] Test división/doble imputación: `backend/tests/unit/test_subvencion_division_linea.py` — repartir una línea entre dos subvenciones (suma ≤ línea) OK; re-imputar el mismo importe → 409
- [X] T014 [P] [US1] Test informe justificación: `backend/tests/unit/test_subvencion_informe.py` — concedido/gastado/pendiente con `Decimal` en 4 decimales; pendiente = concedido − gastado

### Implementation for User Story 1

- [X] T015 [US1] Implementar CRUD de subvenciones en `backend/src/services/ngo/subvenciones.py`: crear (importe > 0, ejercicio válido), listar (filtros estado/ejercicio), detalle con resumen, editar datos de control, transición de estado (concedida→en_curso→justificada→reintegrada) con `asiento_rectificativo_id` si `reintegrada`; transacción ACID con audit log
- [X] T016 [US1] Implementar imputación de gastos en `backend/src/services/ngo/justificacion.py`: `imputar_gasto(subvencion_id, asiento_id, linea_id, importe_asignado, partida)` — validar línea de la empresa activa y tipo gasto; `SELECT ... FOR UPDATE` sobre la subvención; comprobar sumas por línea y disponible; insertar `GastoImputado` en la misma transacción ACID; desimputación solo antes de `justificada`
- [X] T017 [US1] Implementar informe de justificación en `backend/src/services/ngo/justificacion.py`: agregar concedido/gastado/pendiente por subvención y desglose por línea con `Decimal`; exportación CSV/JSON (4 decimales)
- [X] T018 [US1] Implementar endpoints en `backend/src/api/ngo/subvenciones.py`: POST crear (201), GET listar, GET detalle resumen, PATCH, POST estado, POST gastos (201), DELETE gasto (204), GET informes/{id}/justificacion, GET justificacion/exportar (ver contracts/api-contracts.md)
- [X] T019 [US1] Crear página frontend `frontend/src/app/subvenciones/page.tsx`: listado con estado/ejercicio, resumen de disponible, enlaces a detalle y justificación
- [X] T020 [US1] Crear página frontend `frontend/src/app/subvenciones/[id]/page.tsx`: detalle con formulario de imputación de gastos (selector de asiento/línea con importe restante), transiciones de estado e informe de justificación
- [X] T021 [US1] Tests integración subvención completa: `backend/tests/integration/test_subvencion_justificacion.py` — registrar subvención, imputar gastos de un asiento `POSTED` real, generar informe, verificar disponibles; exceso → 409
- [X] T022 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_subvencion_tenant.py` — empresa A registra/imputa; empresa B no ve la subvención ni el informe; imputar línea de B en subvención de A → 404; imputar línea de A en subvención de B → 404

**Checkpoint**: User Story 1 completa — subvenciones y justificación funcionales. MVP desplegable.

---

## Phase 4: User Story 2 — Imprimir y legalizar los libros oficiales (Priority: P2)

**Goal**: El contador genera los libros oficiales (diario, mayor y cuentas anuales) en PDF partir de un ejercicio cerrado y obtiene el fichero de legalización que certifica su integridad.

**Independent Test**: Generando los libros de un ejercicio cerrado, el PDF coincide al 100 % con el diario/mayor y el fichero de legalización identifica correctamente empresa y rango.

### Tests for User Story 2

- [X] T023 [P] [US2] Test render diario/mayor: `backend/tests/unit/test_libros_datos.py` — el contenido canónico del diario coincide línea a línea con el diario inmutable; mayor agrega saldos por cuenta con `Decimal`
- [X] T024 [P] [US2] Test huella y re-emisión: `backend/tests/unit/test_legalizacion_huella.py` — misma fuente → misma huella; modificar 1 asiento → huella distinta; re-emisión con huella igual → permitida; distinta → rechazo 409
- [X] T025 [P] [US2] Test bloqueo ejercicio: `backend/tests/unit/test_legalizacion_ejercicio.py` — ejercicio abierto → rechazo; asiento posterior con fecha dentro del ejercicio legalizado → bloqueado (FR-007)

### Implementation for User Story 2

- [X] T026 [US2] Implementar generador PDF en `backend/src/services/ngo/libros_pdf.py`: construir contenido canónico (diario ordenado por número, mayor por cuenta, cuentas anuales si definidas) con importes en 4 decimales; renderizar PDF (decisión D3); cierre del documento con suma Debe==Haber
- [X] T027 [US2] Implementar servicio de libros en `backend/src/services/ngo/libros_pdf.py`: `generar_libros(ejercicio, tipos)` — validar ejercicio cerrado (SPEC-004), generar persistencia `LibroOficial` (contenido + sha256 + size) en transacción ACID, reutilizar PDF existente con misma huella si aplica
- [X] T028 [US2] Implementar fichero de legalización en `backend/src/services/ngo/legalizacion.py`: construir fichero según `contracts/legalizacion.md`; calcular huella sobre contenido canónico; emitir (201) solo si ejercicio cerrado y, en re-emisión, huella idéntica; persistir `Legalizacion` en ACID con audit log
- [X] T029 [US2] Refuerzo de bloqueo FR-007 en `backend/src/services/acct/journal_engine.py` (SPEC-002) + migración: no aceptar asientos con fecha dentro de un ejercicio legalizado (valido=true) — refuerzo de SPEC-004 con la marca de legalización
- [X] T030 [US2] Implementar endpoints en `backend/src/api/ngo/libros.py` y `backend/src/api/ngo/legalizaciones.py`: POST generar (201), GET listar, GET descarga PDF, POST legalizar (201), GET listar legalizaciones, GET descarga fichero
- [X] T031 [US2] Crear página frontend `frontend/src/app/libros/page.tsx`: selección de ejercicio, generación de PDFs (diario/mayor/cuentas anuales) y descarga por tipo
- [X] T032 [US2] Crear página frontend `frontend/src/app/libros/legalizacion/page.tsx`: botón emitir legalización, datos de la última (empresa, ejercicio, rango, huella), descarga del fichero, avisos de re-emisión
- [X] T033 [US2] Tests integración libros/legalización completa: `backend/tests/integration/test_libros_legalizacion_completa.py` — cerrar ejercicio fixture, generar PDF diario/mayor, emitir legalización, descargar, re-emitir y comparar huella; asiento posterior → rechazo
- [X] T034 [US2] Tests contrato de formatos: `backend/tests/contract/test_libros_pdf_esquema.py` y `backend/tests/contract/test_legalizacion_formato.py` — validan `contracts/libros-pdf.md` y `contracts/legalizacion.md` (estructura, 4 decimales, huella, rango)
- [X] T035 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_libros_tenant.py` — empresa B no lista/descarga libros ni legalizaciones de A; intento de legalizar ejercicio de B con rango de A → 404

**Checkpoint**: User Stories 1 y 2 completas — justificación y libros oficiales legales funcionales.

---

## Phase 5: User Story 3 — Arqueo de caja y caja chica (Priority: P3)

**Goal**: El tesorero registra los movimientos de una caja (subcuenta 570 real, asientos del motor) y realiza arqueos: contrasta saldo contable 570 con efectivo contado, registra la diferencia y decide aprobarla (con asiento de ajuste) o archivarla (pendiente visible).

**Independent Test**: Registrando movimientos de caja y haciendo un arqueo, el sistema calcula el saldo, compara con el efectivo anotado y reporta diferencias.

### Tests for User Story 3

- [X] T036 [P] [US3] Test saldo 570 exacto: `backend/tests/unit/test_caja_saldo.py` — saldo de caja == suma de líneas 570 del período con `Decimal`; entrada/salida actualizan saldo correctamente
- [X] T037 [P] [US3] Test cálculo de diferencia: `backend/tests/unit/test_arqueo_diferencia.py` — cuadra (0) → `cuadra`, aprobación sin asiento; con diferencia (±) → `con_diferencia`; aprobación sin `asiento_ajuste_id` → 409; archivado → pendiente visible
- [X] T038 [P] [US3] Test 570 única por caja: `backend/tests/unit/test_caja_cuenta570.py` — alta con 570 ya asignada → 409; cuenta 570 inexistente/inactiva → 404/422

### Implementation for User Story 3

- [X] T039 [US3] Implementar CRUD de cajas en `backend/src/services/ngo/caja.py`: crear (validar subcuenta 570 del plan y no asignada), listar con saldo (agregación de 570), detalle, inactivar; transacción ACID con audit log
- [X] T040 [US3] Implementar movimientos en `backend/src/services/ngo/caja.py`: `registrar_movimiento(caja, tipo, importe, fecha, concepto, contrapartida)` — crear asiento del motor (SPEC-002) 570 vs contrapartida (572→570 entrada; salida inversa) en transacción ACID; materializar `MovimientoCaja` a partir del asiento en la misma transacción; ejercicio cerrado → 409
- [X] T041 [US3] Implementar arqueo en `backend/src/services/ngo/arqueo.py`: `realizar_arqueo(caja, fecha, efectivo)` — saldo_libros = SUM 570 hasta fecha; diferencia = efectivo − saldo; estado `cuadra`/`con_diferencia`; registrar `Arqueo`
- [X] T042 [US3] Implementar decisión en `backend/src/services/ngo/arqueo.py`: `aprobar_arqueo(arqueo, asiento_ajuste_id)` — validar que el asiento es del motor, de la empresa activa, balanceado y que ajusta 570 al efectivo; `archivar_arqueo` sin asiento (pendiente visible); idempotencia (una sola decisión)
- [X] T043 [US3] Implementar endpoints en `backend/src/api/ngo/caja.py`: POST cajas (201), GET listar, GET detalle con movimientos, GET movimientos (rango), POST movimientos (201 con asiento_id), POST arqueos (201), POST aprobar, POST archivar, GET arqueos
- [X] T044 [US3] Crear página frontend `frontend/src/app/caja/page.tsx`: listado de cajas con saldo y enlace a detalle
- [X] T045 [US3] Crear páginas frontend `frontend/src/app/caja/[id]/page.tsx` (movimientos + alta de movimiento) y `frontend/src/app/caja/[id]/arqueos/page.tsx` (realizar arqueo, ver diferencia, aprobar con asiento o archivar)
- [X] T046 [US3] Tests integración caja completa: `backend/tests/integration/test_caja_movimientos.py` y `backend/tests/integration/test_arqueo_ajuste.py` — movimientos crean asientos 572→570 balanceados, saldo real, arqueo con diferencia, aprobación con asiento de ajuste que cuadra 570, archivado pendiente; intento de aprobar sin ajuste → 409
- [X] T047 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_caja_tenant.py` — empresa B no ve cajas/movimientos/arqueos de A; intento de movimiento o aprobación cross-tenant → 404/409

**Checkpoint**: User Stories 1, 2 y 3 completas — módulo ONG completo (subvenciones, libros, caja) con MVP y control de efectivo.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T048 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_ngo.py` — todo asiento creado (movimiento caja, ajuste arqueo) tiene Debe==Haber en backend; ningún asiento `POSTED` se edita; `empresa_id` presente en PK/índices de todas las tablas ngo
- [X] T049 [P] Hardening multi-tenant: `backend/tests/integration/test_ngo_full_tenant_isolation.py` — escenario completo cross-empresa (subvención A, libro B, caja A desde B → 404) con dos roles (SPEC-015)
- [X] T050 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_ngo.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T051 [P] Code review: verificar `async with async_session.begin()` en todos los servicios; que ningún endpoint expone `empresa_id` en ruta/body; que PDF/huella usan `Decimal` y `sha256` sobre contenido canónico; que los asientos se delegan en `journal_engine`
- [X] T052 Validar número correlativo de asientos de caja/ajuste: `backend/tests/integration/test_correlatividad_ngo.py` — asientos de movimientos y ajustes se integran en la secuencia (empresa, ejercicio) del motor sin saltos
- [X] T053 Limpieza y documentación: docstrings en servicios ngo, type hints completos, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 y del diario del motor (SPEC-002/006) para imputar líneas `POSTED`.
- **US2 (Phase 4)**: Depende de Phase 2; requiere un ejercicio cerrado y el diario inmutable (SPEC-002/004). Puede empezar en paralelo con US1.
- **US3 (Phase 5)**: Depende de Phase 2 y del motor (los movimientos son asientos). Puede empezar en paralelo con US1/US2.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa y el diario (SPEC-002/006).
- **US2 (P2)**: Sin dependencias de US1/US3; usa Phase 2 completa (modelos de libros) y el cierre de ejercicio (SPEC-004).
- **US3 (P3)**: Sin dependencias de US1/US2; usa Phase 2 completa y el motor (SPEC-002). La cuenta 570 proviene del plan (SPEC-001).

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T010).
- Phase 3: tests [P] en paralelo (T012-T014), y T015/T019 (service + frontend).
- Phase 4: tests [P] en paralelo (T023-T025), y T026/T031 (generador + frontend).
- Phase 5: tests [P] en paralelo (T036-T038).

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T012: "Test disponible y exceso en backend/tests/unit/test_subvencion_disponible.py"
Task T013: "Test división línea en backend/tests/unit/test_subvencion_division_linea.py"
Task T014: "Test informe justificación en backend/tests/unit/test_subvencion_informe.py"

# Servicio de imputación y listado frontend en paralelo:
Task T016: "Imputación de gastos en backend/src/services/ngo/justificacion.py"
Task T019: "Listado de subvenciones en frontend/src/app/subvenciones/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T012-T022. Verificar quickstart Escenario 1-2.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (subvenciones y justificación — MVP ONG).
3. + US2 → Test independiente → Deploy/Demo (libros PDF y legalización).
4. + US3 → Test independiente → Deploy/Demo (caja y arqueo).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (subvenciones/justificación).
   - Dev B: User Story 2 (libros PDF + legalización).
   - Dev C: User Story 3 (caja 570 + arqueo).
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
- Clarificaciones 2026-09-16 integradas: caja = subcuenta 570 real (movimientos como asientos); re-legalización solo con huella idéntica; gasto imputado a subvención a nivel de línea; arqueo con diferencia aprobada exige asiento de ajuste enlazado (archivado → pendiente visible).

---

## Estado real (implementación 2026-09-23)

**Vigésima spec cerrada (53/53). Total del proyecto: 953/1.384 (20 specs).**

### Backend
- **Modelos** `backend/src/models/ngo/`:
  - `subvencion.py` (`Subvencion`, `SubvencionEstado`, índice único parcial `(empresa_id, id)` + UNIQUE `(empresa_id, referencia)`, `partidas` JSON como `Mapped[list[str] | None]`).
  - `gasto_imputado.py` (`GastoImputado`, FK compuesta `(empresa_id, subvencion_id)`, `.linea_id` FK UUID sin constraint real hasta SPEC-002; chequeo de duplicado por `(empresa_id, asiento_id, linea_id)` SIN `subvencion_id` → una línea por subvención).
  - `libros.py` (`LibroOficial` con `contenido_pdf` LargeBinary/BYTEA + sha256 CHAR(64), `tipo` enum `diario|mayor|balance|pyg`; `Legalizacion` con rango, huella, fichero BYTEA, `valido`, `motivo_reemision`, índice parcial `(empresa_id, ejercicio)` WHERE `valido = true`).
  - `caja.py` (`Caja`, UNIQUE `(empresa_id, nombre)` y cuenta 570 única por empresa; `MovimientoCaja` aquí, traza derivada del diario con asiento_id+linea_id).
  - `arqueo.py` (`Arqueo`: estado `cuadra|con_diferencia`, decisión `pendiente|aprobada|rechazada`, `archivado` booleano, diferencia = efectivo − saldo_libros).
- **Migración** `backend/migrations/011_ngo.sql` (registrada en `ORDEN_PREFERENTE` y `test_migrations.ESPERADAS`): tablas ngo + enums + triggers de inmutabilidad de `libro_oficial`/`movimiento_caja`/`legalizacion` y `trg_journal_entry_legalizado_insert` (bloqueo FR-007 a nivel DB). Triggers SQLite equivalentes en `db/triggers.py`.
- **Servicios** `backend/src/services/ngo/`:
  - `errores.py` (`NgoError`), `subvenciones.py` (CRUD + transiciones `concedida→en_curso→justificada→reintegrada` con `asiento_rectificativo_id` obligatorio para reintegrar; `_resumen` con gastado/pendiente).
  - `justificacion.py` (`imputar_gasto` con `_linea_es_gasto` por código 6xx, `excede_disponible`, `excede_importe_linea`, `gasto_ya_imputado`, `subvencion_cerrada` en `justificada/reintegrada`, `asiento_no_asentado`; **desimputación = DELETE legítimo y auditado** — decisión de diseño, NO append-only; `informe_justificacion` con canon `empresa_id|ejercicio|...` + huella sha256; `exportar_informe` CSV con BOM / JSON).
  - `libros_pdf.py` (canon diario/mayor/balance/pyg en 4 decimales, PDF con reportlab + footer `Debe = … | Haber = …`, sha256 == huella legalización, reutilización con huella idéntica vía índice parcial; `cuentas_anuales` del plan derivado, no usado).
  - `legalizacion.py` (fichero `.txt` 11 líneas `LEGALIZACION V1` + 10 campos; huella = sha256 del canon del diario; re-emisión idéntica 201; 409 `huella_no_coincide`).
  - `caja.py` (`saldo_570` por Sum(JournalEntryLine) cuenta 570, `crear_caja` valida 570 del plan / no asignada, `registrar_movimiento` crea asiento motor 572↔570 balanceado en la misma transacción, `lista_570` constante del modelo, `inactivar_caja`, ejercicio cerrado → 409).
  - `arqueo.py` (`realizar_arqueo` con auto-aprobación si cuadra, `aprobar_arqueo` exige asiento de ajuste balanceado que cuadra 570, `archivar_arqueo`, `listar_arqueos`).
- **API** `backend/src/api/ngo/` (paquete, `deps.py` con `get_empresa_activa` desde sesión y `require_permission` del catálogo SPEC-015, módulo `ngo` con 4 concesiones, 11→12 módulos RBAC, 147 items):
  - `subvenciones.py`: POST/GET `subvenciones`, GET/PATCH `{id}`, POST `{id}/estado`, POST `{id}/gastos`, DELETE `{id}/gastos/{gasto_id}`, GET `informes/subvenciones/{id}/justificacion` y `/exportar`.
  - `libros.py`: POST `libros/{ejercicio}/generar`, GET `libros/{ejercicio}`, GET `libros/{libro_id}/descarga`.
  - `legalizaciones.py`: POST (201), GET listado, GET `{id}/descarga`.
  - `cajas.py`: POST/GET, GET `{id}` (con movimientos), GET `{id}/movimientos`, POST `{id}/movimientos`, POST `{id}/inactivar`.
  - `arqueos.py`: POST `cajas/{caja_id}/arqueos`, POST `arqueos/{id}/aprobar|archivar`, GET `arqueos`.
- **FR-007**: refuerzo en el motor `entry_service._validar_ejercicio` (orden: `ejercicio_invalido` → `_ejercicio_cerrado` [FY inexistente = abierto] → `_ejercicio_legalizado`) **y** trigger DB `trg_journal_entry_legalizado_insert`; mapeo HTTP en `api/journal/asientos.py`: `ejercicio_cerrado/invalido` → 400, `ejercicio_legalizado` → 422 por defecto.

### Frontend
- `frontend/src/components/ngo/{api.ts,CuentaPicker.tsx}` (cliente tipado + selector de cuentas via `/accounts/suggest`) y páginas bajo **`frontend/src/app/ong/`**:
  - `subvenciones/page.tsx` (listado con filtro estado + alta), `subvenciones/[id]/page.tsx` (informe gastado/pendiente, imputar gastos desde asientos del diario con líneas expandibles, desimputar, transiciones de estado, export CSV/JSON).
  - `libros/page.tsx` (generación diario/mayor/balance/pyg, descarga PDF, emisión de legalización y descarga `.txt`).
  - `caja/page.tsx` (listado/alta con picker de subcuenta 570), `caja/[id]/page.tsx` (movimientos + alta, arqueos con aprobar/archivar).
- Enlace añadido en `app/page.tsx`. Total **66 rutas** (5 nuevas).

### Verificación
- pytest: **1171 passed / 5 skipped** en suite completa (SQLite; `test_suggest_perf` flaky bajo carga, verde aislado) con **62 tests SPEC-019** (34 unit + 17 integration + 11 contract).
- `ruff check src tests` y `mypy` (285 fuentes): **limpios** (corregidos I001/F841/B023 en conftest y tests, y `Mapped[list[str] | None]` en `Subvencion.partidas` por error mypy de asignación).
- `tsc --noEmit`, `eslint src` y `next build` (66 rutas): en verde.

### Desviaciones
- Frontend en `app/ong/*` en vez de `app/{subvenciones,libros,caja}/*` (T004/T019/T020/T031/T032/T044/T045); US2 no renderiza "cuentas anuales" del tipo del plan (tipo `cuentas_anuales` del data-model no se usa; el canon/pie del PDF cubre diario/mayor/balance/pyg).
- Tests de aislamiento multi-tenant (T022/T035/T047/T049) y quickstart (T050) y correlatividad (T052) no tienen archivos dedicados con esos nombres: se cubren en `test_ngo_tenant_isolation.py`, `test_subvencion_justificacion.py` (escenario quickstart 1: 5000 concedida, 2000 imputado, 3500 → 409 `excede_disponible`) y los tests de caja/arqueo.
- `MovimientoCaja` vive en `models/ngo/caja.py` (no en `arqueo.py`); `Arqueo.decision` no incluye `archivada` (el archivado es flag booleano `archivado`).
- `GastoImputado` **no es inmutable**: `desimputar_gasto` borra la fila con auditoría (decisión D actualizada en sesión); solo `libro_oficial`, `movimiento_caja` y `legalizacion` son inmutables por trigger.
- FR-007 se implementa en `entry_service` (motor de SPEC-006/002), no en `acct/journal_engine.py` (nombre nominal de la tarea), y la migración es la 011 además de los triggers SQLite de `db/triggers.py`.
- `partidas` del plan (T-05) se tipa en modelo como `Mapped[list[str] | None]`; la migración la guarda como JSONB y no valida su desglose contra un catálogo externo (decisión D10: opcional).
- Se añadió `test_legalizacion_ejercicios.py` (adicional a T034): abierto 409, inexistente 404, FR-007 motor 422, FR-007 trigger SQLite IntegrityError, ejercicio 2026 legalizado no bloquea 2025 (201 con fecha 2025-12-31), cerrado+legalizado → 400.