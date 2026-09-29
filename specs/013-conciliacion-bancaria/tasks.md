# Tasks: Conciliación Bancaria (SPEC-013)

**Input**: Design documents from `/specs/013-conciliacion-bancaria/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

> **Nota sobre el recuento**: las 54 tareas originales se marcaron todas el 2026-09-19, y ese día la spec se dio por cerrada. El 2026-09-29 se añadieron **22 tareas más** (T055–T076) tras una corrección sobre la aplicación real que encontró dos cosas que la spec no cubría: el formato **XLSX** que entrega la banca, y la **migración SQL** que le faltaba a la spec entera. Ver «Estado real (2026-09-29)» al final del fichero, que explica por qué las puertas de la spec se pueden haber dado en verde con la conciliación sin funcionar.

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`. Endpoints bajo `/api/v1/...` con empresa activa en cabecera de sesión (SPEC-003/015), nunca en path ni body.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Trazabilidad FR ↔ User Story

| Requisito | Descripción breve | User Story |
|---|---|---|
| FR-001 | Importar extractos 572 norma 43/19 con duplicados | US1 |
| FR-002 | Aislar extractos y conciliación por empresa | US1 |
| FR-003 | Proponer cruces automáticos y cruce manual | US2 |
| FR-004 | Mantener saldo extracto, libros, pendientes y diferencia | US3 |
| FR-005 | Archivar período conciliado solo con diferencia cero | US3 |
| FR-006 | Precisión decimal exacta en importes y diferencia | US3 |
| FR-007 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar el módulo de conciliación en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo `reconciliation`: `backend/src/models/treasury/__init__.py`, `backend/src/services/reconciliation/__init__.py`, `backend/src/services/reconciliation/layouts.py` (mapa de offsets del layout norma 43/19), `backend/src/api/reconciliation.py`, `backend/tests/fixtures/`
- [X] T002 [P] Configurar router `reconciliation`: registrar prefijo `/api/v1` en `backend/src/api/reconciliation.py` con dependencies de empresa activa y permisos (SPEC-003/015)
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/conciliacion/`, `frontend/src/app/conciliacion/importar/`, `frontend/src/components/reconciliation/`, `frontend/src/services/client.ts` (cabecera de empresa activa)
- [X] T004 [P] Crear utils de sesión: `backend/src/api/reconciliation/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `ExtractoBancario` en `backend/src/models/treasury/extracto_bancario.py`: empresa_id (PK compuesta), cuenta_id FK → SPEC-001 Cuenta (572), fecha_inicio, fecha_fin, saldo_inicial NUMERIC(18,4), saldo_final NUMERIC(18,4), nombre_fichero VARCHAR(255), sha256 CHAR(64) UNIQUE por empresa, estado (importado/duplicado), n_movimientos INT
- [X] T006 [P] Crear modelo `MovimientoBancario` en `backend/src/models/treasury/movimiento_bancario.py`: empresa_id, extracto_id FK compuesta, orden INT UNIQUE por (empresa_id, extracto_id, orden), fecha_operacion, fecha_valor, concepto VARCHAR(255), importe NUMERIC(18,4) CHECK > 0, signo ENUM (D/H), referencia VARCHAR(80), estado (pendiente/conciliado/alertado)
- [X] T007 [P] Crear modelo `Conciliacion` en `backend/src/models/treasury/conciliacion.py`: empresa_id, cuenta_id FK, ejercicio, fecha_inicio, fecha_fin, extracto_id FK, saldo_banco/saldo_libros/diferencia NUMERIC(18,4), estado (abierta/cerrada), periodo_conciliado_id NULL; check diferencia = saldo_banco − saldo_libros
- [X] T008 [P] Crear modelo `CruceConciliacion` en `backend/src/models/treasury/conciliacion.py`: empresa_id, conciliacion_id FK, movimiento_id FK UNIQUE por empresa, apunte_id FK → SPEC-002 JournalEntryLine UNIQUE por empresa (confirmados), importe NUMERIC(18,4), signo, origen (auto/manual), prioridad (propuesto/candidato), estado (pendiente_confirmar/confirmado), fecha_cruce NULL, usuario_id, confirmado_por_remesa BOOLEAN
- [X] T009 [P] Crear modelo `PeriodoConciliado` en `backend/src/models/treasury/periodo_conciliado.py`: empresa_id, conciliacion_id FK, ejercicio, numero_periodo BIGINT UNIQUE por (empresa_id, ejercicio), fecha_inicio, fecha_fin, saldo_banco, saldo_libros, diferencia NUMERIC(18,4) CHECK = 0, fecha_cierre, usuario_id
- [X] T010 [P] Crear modelo `AlertaConciliacion` en `backend/src/models/treasury/alerta_conciliacion.py`: empresa_id, conciliacion_id FK, tipo (movimiento_sin_apunte/apunte_sin_extracto/importe_concepto_dudoso), movimiento_id NULL, descripcion VARCHAR(255), estado (abierta/resuelta)
- [X] T011 [P] Tests de modelos fundacionales: `backend/tests/unit/test_conciliacion_models.py` — verificar unicidad sha256 por empresa, unicidad (extracto_id, orden), unicidad movimiento/apunte en cruces, check diferencia período = 0, FK compuestas empresa_id
- [X] T012 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_conciliacion_tenant_models.py` — crear extracto en empresa A, verificar que empresa B no lo ve en ninguna consulta (extractos, movimientos, cruces, períodos, alertas)

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Importar un extracto bancario (Priority: P1) ?? MVP — cubre FR-001, FR-002, FR-007

**Goal**: El usuario importa el extracto de la cuenta 572 (norma 43/19 o CSV); los movimientos se cargan, se muestra el saldo de extracto y se detectan duplicados.

**Independent Test**: Importar un extracto de una cuenta 572 carga sus movimientos y muestra el saldo; reimportar el mismo fichero → rechazo; un extracto de otra empresa → rechazo por aislamiento.

### Tests for User Story 1

- [X] T013 [P] [US1] Test parser norma 43/19: `backend/tests/unit/test_parser_norma_43.py` — parsear fixture válido, verificar cabecera (saldos), 3 movimientos (signo D/H correcto por código 21/22), control 98 cuadra; línea malformada → error con nº de registro
- [X] T014 [P] [US1] Test parser CSV normalizado: `backend/tests/unit/test_parser_csv.py` — fixture CSV ↔ mismo DTO que norma 43; totales cuadran
- [X] T015 [P] [US1] Test detección de duplicados: `backend/tests/unit/test_duplicados_extracto.py` — misma huella → 409 `extracto_duplicado`; mismo fichero renombrado → detectado por (cuenta, rango, saldos, nº movimientos)
- [X] T016 [P] [US1] Test aislamiento importación: `backend/tests/integration/test_importacion_tenant.py` — fichero con cuenta de otra empresa → 404; el extracto de A no aparece en listado de B

### Implementation for User Story 1

- [X] T017 [US1] Implementar parser en `backend/src/services/reconciliation/parsers.py`: función `parse_extracto(bytes, layout) -> ExtractoDTO` sobre el mapa de offsets de `layouts.py`; variante CSV normalizada; validación de cuadre saldo/Σ importes y longitud de línea; sin estado
- [X] T018 [US1] Implementar servicio `importar_extracto` en `backend/src/services/reconciliation/importacion.py`: validar cuenta 572 del plan de la empresa activa (aislamiento), calcular sha256, detectar duplicados (huella + solapamiento), persistir ExtractoBancario + MovimientosBancario en una sola transacción ACID con audit log (`async with async_session.begin()`); si algo falla no persiste nada
- [X] T019 [US1] Implementar endpoint `POST /api/v1/extractos` en `backend/src/api/reconciliation.py`: multipart (file + layout opcional), 201/409/422 conforme [contracts/api-contracts.md](contracts/api-contracts.md)
- [X] T020 [US1] Implementar endpoints GET extractos y GET extracto detalle (con movimientos paginados) en `backend/src/api/reconciliation.py`
- [X] T021 [US1] Crear página frontend `frontend/src/app/conciliacion/importar/page.tsx`: subida de fichero, selección de cuenta 572 y layout, preview de saldos/nº movimientos, manejo de error duplicado
- [X] T022 [US1] Crear listado frontend `frontend/src/app/conciliacion/page.tsx`: tabla de extractos con saldos, estado y acceso a conciliación
- [X] T023 [US1] Tests integración importación completa: `backend/tests/integration/test_importacion_completa.py` — importar fixture → extracto + 3 movimientos + saldo correctos; reimportar → 409 sin doble carga; fichero malformado → 422 sin persistencia parcial
- [X] T024 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_importacion_tenant.py` — escenario completo: A importa y ve su extracto; B no lo ve ni por detalle ni por id; B intenta subir el fichero de A con su sesión → 404

**Checkpoint**: User Story 1 completa — importación de extractos con duplicados y aislamiento. MVP desplegable.

---

## Phase 4: User Story 2 — Conciliar apuntes con movimientos (Priority: P1) — cubre FR-003

**Goal**: El usuario cruza los apuntes contables 572 con los movimientos del extracto, aceptando propuestas automáticas o haciendo el cruce manual; cada cruce es trazable.

**Independent Test**: Conciliando apuntes y movimientos, los cruces quedan registrados con fecha y actor y el saldo conciliado coincide con la diferencia entre saldos.

### Tests for User Story 2

- [X] T025 [P] [US2] Test propuesta automática: `backend/tests/unit/test_matching.py` — individuo importe igual + signo opuesto → propuesta `propuesto` si el concepto coincide, `candidato` si no; importe distinto → sin propuesta; movimientos y apuntes ya conciliados → excluidos
- [X] T026 [P] [US2] Test cruce manual y trazabilidad: `backend/tests/unit/test_cruce.py` — confirmar cruce → estado confirmado con fecha_cruce/usuario; deshacer pre-cierre → pendiente; doble cruce del mismo movimiento/apunte → 409; verificarse que el JournalEntry POSTED NO fue modificado (constitución II)
- [X] T027 [P] [US2] Test acoplamiento SPEC-020: `backend/tests/integration/test_cruce_remesa.py` — confirmar el cruce de un cobro de remesa → `ReciboRemesa.estado=cobrado` y no se crea segundo asiento
- [X] T028 [P] [US2] Test aislamiento US2: `backend/tests/integration/test_cruce_tenant.py` — empresa B no ve cruces/propuestas de A; cruzando desde B → 404

### Implementation for User Story 2

- [X] T029 [US2] Implementar servicio de propuestas en `backend/src/services/reconciliation/matching.py`: cruce por importe `Decimal` exacto + signo; normalización de concepto para prioridad `propuesto`; no duplica cruces existentes ni toca los confirmados; sin escritura (solo cálculo de candidatos)
- [X] T030 [US2] Implementar servicio de cruce en `backend/src/services/reconciliation/cruce.py`: `confirmar_cruce` (validar importe exacto, unicidad movimiento/apunte, transacción ACID con audit), `deshacer_cruce` (bloqueado si período archivado); con función `notificar_cobro_remesa()` que llama a SPEC-020 en la misma transacción si `apunte_id` es de un cobro de remesa
- [X] T031 [US2] Implementar endpoint `POST /api/v1/conciliaciones/{id}/propuestas` en `backend/src/api/reconciliation.py`
- [X] T032 [US2] Implementar endpoint `POST /api/v1/conciliaciones/{id}/cruces` en `backend/src/api/reconciliation.py`
- [X] T033 [US2] Implementar endpoint `DELETE /api/v1/conciliaciones/{id}/cruces/{cruce_id}` en `backend/src/api/reconciliation.py`
- [X] T034 [US2] Crear pantalla frontend `frontend/src/app/conciliacion/[id]/page.tsx`: lista de propuestas (propuesto/candidato), confirmar/deshacer cruces, marcado manual, indicador de diferencia en vivo
- [X] T035 [US2] Tests integración cruce completo: `backend/tests/integration/test_conciliacion_completa.py` — generar propuestas, confirmar (fecha/actor), verificar diferencia = saldo_banco − saldo_libros tras cada cruce, deshacer y volver a conciliar
- [X] T036 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_cruce_tenant.py` — A genera propuestas y confirma cruces; B no ve nada y sus intentos → 404; verificar que la diferencia de B no refleja actividad de A

**Checkpoint**: User Stories 1 y 2 completas — conciliación funcional con propuestas, cruces manuales y trazabilidad.

---

## Phase 5: User Story 3 — Calcular la diferencia de saldos y cerrar (Priority: P2) — cubre FR-004, FR-005, FR-006

**Goal**: El usuario conoce saldo banco, saldo libros y diferencia; al cerrar con diferencia cero se archiva; si no, se informa de pendientes.

**Independent Test**: Con todos los movimientos conciliados, la diferencia es cero y el período conciliado queda archivado con número correlativo; con pendientes el cierre advierte sin archivar.

### Tests for User Story 3

- [X] T037 [P] [US3] Test cálculo de saldos: `backend/tests/unit/test_saldos.py` — saldo_banco = extracto.saldo_final; saldo_libros = Σ(Haber−Debe) apuntes 572 del rango en `Decimal`; diferencia exacta 4 decimales (nunca float)
- [X] T038 [P] [US3] Test cierre y archivo: `backend/tests/unit/test_cierre.py` — diferencia `0.0000` → PeriodoConciliado creado con numero_periodo correlativo por (empresa, ejercicio); diferencia != 0 → rechazo 409 con pendientes y sin archivar; DELETE de cruce del período archivado → 409 (inmutabilidad)
- [X] T039 [P] [US3] Test correlatividad del período: `backend/tests/unit/test_correlatividad_periodo.py` — cerrar 2 períodos en el mismo ejercicio → numero_periodo 1, 2 sin saltos; otro ejercicio → serie independiente
- [X] T040 [P] [US3] Test aislamiento US3: `backend/tests/integration/test_cierre_tenant.py` — A cierra y archiva; B no ve el período ni la numeración de A; B no puede cerrar una conciliación de A

### Implementation for User Story 3

- [X] T041 [US3] Implementar servicio de saldos e informe en `backend/src/services/reconciliation/saldos.py`: saldo_banco, saldo_libros (consulta sobre apuntes 572 de la empresa activa), diferencia `Decimal`, y listados de pendientes (movimientos sin cruzar y apuntes sin extracto) y alertas
- [X] T042 [US3] Implementar servicio `cerrar_periodo` en `backend/src/services/reconciliation/cierre.py`: si diferencia == `Decimal("0.0000")` asigna numero_periodo atómicamente (SELECT ... FOR UPDATE de la secuencia por (empresa, ejercicio)), archiva (inmutable), audita; si diferencia != 0 → 409 con pendientes, sin archivar; ejercicio cerrado → 409 (SPEC-004)
- [X] T043 [US3] Implementar endpoints en `backend/src/api/reconciliation.py`: `GET /api/v1/conciliaciones/{id}` (informe completo), `POST /api/v1/conciliaciones/{id}/cerrar`, `GET /api/v1/periodos-conciliados`
- [X] T044 [US3] Implementar endpoint resolución de alerta `POST /api/v1/conciliaciones/{id}/alertas/{alerta_id}/resolver` en `backend/src/api/reconciliation.py`
- [X] T045 [US3] Crear frontend `frontend/src/app/conciliacion/[id]/informe/page.tsx`: saldo banco, saldo libros, diferencia, pendientes y alertas; botón cerrar con confirmación
- [X] T046 [US3] Crear frontend `frontend/src/app/conciliacion/periodos/page.tsx`: listado de períodos archivados con numero_periodo y saldos
- [X] T047 [US3] Tests integración cierre completo: `backend/tests/integration/test_cierre_completo.py` — conciliar todo → diferencia 0 → cerrar archiva con numero_periodo; conciliar solo una parte → 409 con pendientes, no archiva; período archivado inmutable
- [X] T048 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_cierre_tenant.py` — escenario completo: A archiva, B no ve el período archivado (listado ni detalle) ni puede cerrar por delegado

**Checkpoint**: User Stories 1, 2 y 3 completas — conciliación bancaria completa con control de saldo y cierre.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación constitucional y robustez.

- [X] T049 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_conciliacion.py` — ningún asiento POSTED modificado/borrado por cruces o cierre; verificar que todo cálculo de saldo/diferencia usa `Decimal` y nunca `float`; verificar aislamiento empresa_id en todas las tablas de conciliación
- [X] T050 [P] Hardening multi-tenant: `backend/tests/integration/test_conciliacion_full_tenant_isolation.py` — escenario completo cross-empresa (extracto de A, cruces de B, período archivado de A consultado por B → todos 404)
- [X] T051 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_conciliacion.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T052 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint deriva `empresa_id` de path/body (solo cabecera de sesión); verificar Decimal/NUMERIC(18,4) en saldos, movimientos e importes de cruce
- [X] T053 Validación de ejercicios cerrados: verificar que abrir conciliación y cerrar período rechazan con 409 si el ejercicio está cerrado (SPEC-002/004)
- [X] T054 Limpieza y documentación: actualizar docstrings en servicios `reconciliation`, verificar type hints, ejecutar lint/typecheck; revisar fixtures de extracto con casos límite (importe 0, concepto vacío, fichero vacío)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1 (los modelos y tests de matching/cruce dependen de los modelos fundacionales de los cruces).
- **US3 (Phase 5)**: Depende de Phase 2; empieza en paralelo pero sus tests de cierre requieren los servicios de saldos (T041) que no dependen de US1/US2.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Sin dependencias de US1/US3; usa Phase 2 completa; el cruce de un cobro de remesa (T027/T030) integra con SPEC-020 sin requerir la emisión completa de remesas.
- **US3 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa; el archivo (PeriodoConciliado) depende de que existan cruces confirmados en el rango para alcanzar diferencia cero.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios (parser → cruce → saldos/cierre) antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T010).
- Phase 3: tests [P] en paralelo (T013-T016), parser y servicio [P] (T017 coherente con T018).
- Phase 4: tests [P] en paralelo (T025-T028), matching + cruce [P] (T029-T030).
- Phase 5: tests [P] en paralelo (T037-T040), saldos + cierre [P] (T041-T042).
- US1, US2 y US3 pueden ejecutarse en paralelo por separado una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T013: "Test parser norma 43 en backend/tests/unit/test_parser_norma_43.py"
Task T015: "Test duplicados en backend/tests/unit/test_duplicados_extracto.py"

# Parser y servicio de importación en paralelo:
Task T017: "Parser en backend/src/services/reconciliation/parsers.py"
Task T018: "Servicio importar_extracto en backend/src/services/reconciliation/importacion.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T013-T024. Verificar quickstart Scenario 1 y 2.
5. Desplegar/demo si listo (importación de extractos con duplicados y aislamiento).

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP!).
3. + US2 → Test independiente → Deploy/Demo (propuestas y cruces).
4. + US3 → Test independiente → Deploy/Demo (informe y cierre).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (parser + importación).
   - Dev B: User Story 2 (matching + cruces + confirmación remesa SPEC-020).
   - Dev C: User Story 3 (saldos + cierre).
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
- Acoplamiento SPEC-020 (confirmación de cobro de remesa) es transversal al cruce; sus pruebas viven en T027/T030 del US2.

## Estado real (auditoría 2026-09-17)

- **Implementado**: scaffold `backend/src/models/treasury/cobro_conciliado.py` (idempotencia por `(empresa_id, movimiento_id)`) consumido por SPEC-020.
- **Pendiente**: resto de la feature (importación de extractos, cruce, endpoints, tests).

## Estado real (implementación 2026-09-19, 54/54)

Desviaciones documentadas:
- **Layout norma 43/19 concreto**: se fija un layout de referencia de 100 caracteres
  (cabecera 01, operaciones 21/22, control 98) en `services/reconciliation/layouts.py`;
  los offsets por entidad quedaban como NEEDS CLARIFICATION en el contrato. Los fixtures
  viven en `backend/tests/fixtures/`.
- **Cuenta del extracto**: el fichero declara el **código de cuenta** (`5720`) en la
  cabecera; el servicio lo valida contra el plan de la empresa activa. El endpoint acepta
  `cuenta` como campo multipart (necesario para el CSV, que no la declara).
- **T037/D5**: `saldo_banco = extracto.saldo_final` (el fixture fija `saldo_inicial=0`);
  `saldo_libros = Σ(Haber−Debe)` de apuntes `572*` POSTED del rango; `diferencia =
  saldo_banco − saldo_libros`. Cierre exige `Decimal("0.0000")`.
- **T030**: el acoplamiento SPEC-020 marca `ReciboRemesa.estado=cobrado` (y
  `fecha_cobro` del movimiento) cuando el apunte cruce coincide con `asiento_cobro_id`,
  sin crear un segundo asiento.
- **T019/T020/T034/T045/T046**: endpoints y páginas frontend creados
  (`/conciliacion`, `/conciliacion/importar`, `/conciliacion/[id]`,
  `/conciliacion/periodos`); la alerta se genera vía `POST /conciliaciones/{id}/alertas`
  (además de la resolución `.../alertas/{id}/resolver`).
- **Fixtures**: `extracto_43_19_{valido,duplicado,otra_empresa,malformado}.txt` y
  `extracto_csv_normalizado.csv`.
- Puertas: 21 tests nuevos en verde; ruff + mypy limpios; `next build` con las 4 rutas nuevas.


---

# Corrección 2026-09-29: XLSX de banco y migración SQL

Trabajo **fuera del ciclo de tareas** de la spec, a petición del usuario sobre la
aplicación en funcionamiento. Detalle en [`correcciones.md`](../../../correcciones.md) y
[AGENTS.md](../../../AGENTS.md) §52.

Estas tareas están **hechas y verificadas**. Se numeran a partir de T055 para no
renumerar las 54 anteriores, y porque renumerarlas rompería la trazabilidad de las
puertas que las citan.

## Phase 7: Migration SQL (bloqueante — sin esto, la spec no funcionaba)

- [X] T055 [P] [US1] Escribir `backend/migrations/024_conciliacion.sql` con los 9 enums y las 6 tablas (`extracto_bancario`, `movimiento_bancario`, `conciliacion`, `cruce_conciliacion`, `periodo_conciliado`, `alerta_conciliacion`), 2 CHECK de cuadre, 5 FKs compuestas por `empresa_id` y la unicidad de `sha256` por empresa. **Era lo que faltaba para que la spec entera funcionara**: sin esta migración las 6 tablas solo existían por el `create_all` de los tests de SQLite y `POST /api/v1/extractos` devolvía 500 en PostgreSQL.
- [X] T056 [P] [US1] Registrar `024_conciliacion.sql` en `src/db/migrate.py::ORDEN_PREFERENTE` y en `tests/unit/test_migrations.py::ESPERADAS`, y añadir las 6 tablas a `TABLAS_ESPERADAS` de `tests/integration/test_pg_schema.py`.
- [X] T057 [US1] Hacer `024_conciliacion.sql` **idempotente**, con la guarda de `pg_constraint` en cada `ADD CONSTRAINT`. `db.migrate` reaplica los ficheros ya aplicados y el fixture `pg_engine` aplica sobre la base de verdad sin borrar el esquema: los dos escriben encima, y un `ADD CONSTRAINT` sin guardia tumba la migración entera en el segundo pase.
- [X] T058 [US1] Triggers de inmutabilidad de `movimiento_bancario` y `periodo_conciliado` en la migración. **El de `movimiento_bancario` compara columna a columna y deja pasar `estado`**: confirmar un cruce lo pasa a `conciliado` y deshacerlo lo devuelve a `pendiente` (`services/reconciliation/cruce.py:129` y `:173`), así que un trigger append-only habría hecho la conciliación inservible, que es su función entera.
- [X] T059 [US1] Aplicar sobre PostgreSQL 18.6 real y comprobar idempotencia: `db.migrate` 24/24 y la segunda pasada sin efecto.

## Phase 8: Formato XLSX de banco (US1)

- [X] T060 [P] [US1] Declarar el catálogo de formatos `LAYOUTS` en `services/reconciliation/layouts.py`, que **no existía** (solo estaban los que el parser discriminaba), con las columnas obligatorias y opcionales del XLSX.
- [X] T061 [P] [US1] `parse_xlsx_bancario()` en `services/reconciliation/parsers.py` y sus ayudantes: `normalizar_columna` (compara cabeceras sin tildes), `importe_de_celda` (`Decimal(str(float))` cuantizado a 4, nunca aritmética en `float`), `_fecha_xlsx` (cuatro formatos), `_buscar_cabecera` (la busca en las 40 primeras filas, no asume la 1), `_saldo_final_desde_cadena`, `_divisa_eur`, `_referencia_xlsx` e `_iban_de_la_hoja`.
- [X] T062 [US1] Derivar el `saldo_inicial` de la columna `Saldo` encadenando `saldo[i] − importe[i] == saldo[i+1]`, y **rechazar** el extracto descuadrado. Es el equivalente del registro de control `98` de la norma 43, sin registro de control.
- [X] T063 [US1] Hacer `parse_extracto` estricto: un `layout` desconocido se rechaza (`layout_desconocido`) en vez de caer en la norma 43 por defecto.
- [X] T064 [P] [US1] `_validar_layout()` en `api/reconciliation.py`: 422 con la **lista** de los formatos válidos, antes de leer el fichero.
- [X] T065 [P] [US1] `ExtractoDTO.iban`; el error `cuenta_requerida` dice cuál es el IBAN del extracto; el `payload` de auditoría lleva `layout`, `iban` y `saldo_inicial`.
- [X] T066 [US1] Frontend: tercera opción en el desplegable de `/conciliacion/importar`, `accept` con `.xlsx,.xlsm`, el formato **sigue al fichero** elegido, texto de ayuda por formato y aviso de que la cuenta hay que ponerla a mano.

## Phase 9: Tests de la corrección

- [X] T067 [P] [US1] `tests/unit/test_parser_xlsx.py` (31): forma del formato, cadena de saldos, orden ascendente y descendente, sin metadatos, fecha de Excel, cabecera sin tildes, IBAN, pie de totales, y los 7 rechazos. Constructor en `tests/unit/extracto_xlsx_support.py` con un XLSX **sintético**.
- [X] T068 [P] [US1] `tests/integration/test_importacion_xlsx.py` (14): persistencia, signo e importe positivo, IBAN en la auditoría, cuenta obligatoria, cuenta inexistente, duplicado, descuadre sin dejar nada a medias, USD, aislamiento entre empresas y 4 tests HTTP.
- [X] T069 [P] [US1] `tests/unit/test_extracto_layouts.py` (12): el desplegable y el catálogo dicen lo mismo, `accept` incluye `.xlsx`, y la API acepta lo del catálogo y rechaza lo demás **diciendo lo que sí hay**.
- [X] T070 [US1] Contrato PostgreSQL en `tests/integration/test_pg_schema.py`: las 6 tablas existen, `UPDATE ... SET estado` se admite, el `UPDATE` de contenido y el `DELETE` se rechazan, `periodo_conciliado` es append-only, `importe > 0` y unicidad de `sha256`.
- [X] T071 [US1] Guard que faltaba, en `tests/unit/test_migrations.py`: `test_toda_tabla_del_orm_tiene_migracion` cruza los `__tablename__` de `src/models/` con los `CREATE TABLE` de `migrations/`, más dos guards que impiden que `TABLAS_SIN_MIGRACION` mienta en ninguna de las dos direcciones.
- [X] T072 [US1] Verificar los cinco guards **reintroduciendo su defecto** uno a uno, y documentar el resultado. Un guard que no se ha visto fallar no es un guard.
- [X] T073 [US1] Prueba de humo contra la aplicación real (HTTP + PostgreSQL 18.6) que sube el fichero de `Data/`, comprueba 201/409/422 y **deja la base como estaba**.

## Phase 10: Discrepancias de contrato detectadas (documentadas, no resueltas)

- [X] T074 [US1] Anotar que `concepto_norma` aparece en `contracts/api-contracts.md` y **nunca se implementó**. Queda declarado como discrepancia.
- [X] T075 [US1] Anotar que la respuesta 422 no incluye `registro` ni `campo` aunque el contrato los declara, y que sehfajaron en el mensaje.

## Deuda que esta corrección ha destapado y NO ha pagado

- [X] T076 [US1] Inventariar las **27 tablas del ORM sin migración** que quedan, de SPEC-005/007/008/010/011/012/014/020, en `TABLAS_SIN_MIGRACION`. Facturación, terceros, remesas SEPA, inmovilizado y libros de IVA son features enteras: es trabajo de un día por spec. Lo que sí se ha hecho es dejar la lista escrita y protegida por dos guards, para que la deuda sea visible y no crezca en silencio. **Consecuencia para el usuario: importar facturas, remesas, vencimientos o inmovilizado devuelve 500 en la aplicación real, por el mismo motivo que tenía esta spec.**

## Estado real (2026-09-29, +22 tareas, 76/76)

Detalle largo en [`correcciones.md`](../../../correcciones.md).

**Lo que se corrigió**, en dos bloques:
1. **XLSX de banco** (`xlsx_bancario`): el formato que entrega la banca electrónica, con
   la derivación del `saldo_inicial` desde la columna de saldos y el rechazo del extracto
   descuadrado.
2. **Migración `024_conciliacion.sql`**: las 6 tablas de esta spec.

**Por qué hizo falta lo segundo para que lo primero sirviera.** Esta spec se cerró el
2026-09-19 con 54/54 tareas y todas sus puertas en verde, y aun así **su conciliación
era inservible en la aplicación real**: las 6 tablas no existían en PostgreSQL porque
solo las creaba el `create_all` de los tests de SQLite. `POST /api/v1/extractos`
devolvía 500 con `UndefinedTableError`. Sin la migración, todo lo demás de esta
sección habría pasado sus puertas y seguido sin funcionar.

**Por qué ninguna puerta lo vio.** `test_migrations.py` comprueba que las migraciones
**declaradas** estén en el inventario, no que cada tabla del ORM tenga una. Un modelo
sin migración no está en el inventario, así que no hay nada que faltar. Lo agravó que
en las 20 specs posteriores **cada una** añadiera su migración sin que nadie notara
que faltaba la de una anterior. La puerta nueva (`T071`) cruza modelos con esquema, que
es lo que habría parado la spec entera.

**Lecciones que se llevan a `research.md`**: el formato real del XLSX y sus
consecuencias de parser (`D1-bis`), y que un trigger de inmutabilidad tiene que leerse
contra el código que lo va a disparar, no contra la constitución que dice cumplir.

**Lo que queda abierto, y no se ha hecho**: el IBAN no se persiste como columna (solo
queda en el `payload` de la auditoría); no existe maestro IBAN → cuenta, y no debería
existir sin su propia spec; `POST /api/v1/extractos` no tiene límite de tamaño; y el
fixture `extracto_43_19_duplicado.txt` sigue huérfano, sin ninguna prueba que lo use.
