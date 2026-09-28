# Tasks: Presupuestos y Desviaciones (SPEC-026)

**Input**: Design documents from `/specs/026-presupuestos-desviaciones/`

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

**Purpose**: Inicializar módulo `budget` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo budget: `backend/src/models/budget/__init__.py`, `backend/src/services/budget/__init__.py`, `backend/src/api/presupuestos.py`, `backend/src/config.py`
- [X] T002 [P] Configurar router presupuestos: registrar prefijo `/api/v1/presupuestos` en `backend/src/api/presupuestos.py` con dependency de sesión autenticada y empresa activa (cabecera, nunca path/body)
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/presupuestos/`, `frontend/src/app/presupuestos/seguimiento/`, `frontend/src/app/presupuestos/informes/`, `frontend/src/components/budget/`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/deps.py` con `get_empresa_id()` que extrae el `empresa_id` del contexto de sesión y bloquea acceso cross-tenant (403)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `Presupuesto` en `backend/src/models/budget/presupuesto.py`: empresa_id (PK), ejercicio INT, cuenta_id FK → account_plan (SPEC-001, FK compuesta empresa_id), centro_coste_id UUID NULL FK → CentroCoste (SPEC-017, FK compuesta empresa_id), importe NUMERIC(18,4), tipo ENUM (gasto/ingreso), periodo_id NULL FK → PeriodoSeguimiento; constraint único (empresa_id, ejercicio, cuenta_id, centro_coste_id)
- [X] T006 [P] Crear modelo `PeriodoSeguimiento` en `backend/src/models/budget/periodo_seguimiento.py`: empresa_id (PK), ejercicio INT, numero_periodo BIGINT correlativo por (empresa_id, ejercicio) con secuencia bloqueada, fecha_inicio DATE, fecha_fin DATE, estado ENUM (abierto/cerrado), fecha_cierre TIMESTAMPTZ NULL, cerrado_por VARCHAR(200) NULL; constraint único (empresa_id, ejercicio, numero_periodo); constraint: solo un estado=abierto por (empresa_id, ejercicio)
- [X] T007 [P] Crear modelo `Desviacion` (snapshot) en `backend/src/models/budget/desviacion.py`: empresa_id (PK), periodo_id FK → PeriodoSeguimiento, cuenta_id FK → account_plan, centro_coste_id UUID NULL FK → CentroCoste, importe_presupuestado NUMERIC(18,4), importe_real NUMERIC(18,4), desviacion_absoluta NUMERIC(18,4), desviacion_relativa NUMERIC(7,4) NULL, sin_presupuesto BOOLEAN; constraint único (empresa_id, periodo_id, cuenta_id, centro_coste_id); tabla inmutable al cerrar (UPDATE/DELETE prohibido por trigger o servicio)
- [X] T008 [P] Crear servicio `calcular_signo_real` utilitario en `backend/src/services/budget/utils.py`: función pura `calcular_real(cuenta_grupo, importe_debe, importe_haber) -> Decimal` aplicando convención grupo 6 → SUM(Debe), grupo 7 → SUM(Haber); con `Decimal` (constitución: precision 4 dec.)
- [X] T009 [P] Tests de modelos fundacionales: `backend/tests/unit/test_budget_models.py` — verificar unicidad (empresa_id, ejercicio, cuenta_id, centro_coste_id); unicidad de numero_periodo por (empresa, ejercicio); constraint solo un periodo abierto; FK compuesta empresa_id
- [X] T010 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_budget_tenant_isolation.py` — crear presupuesto y periodo en empresa A, verificar que empresa B no los ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Definir el presupuesto anual por cuenta y centro (Priority: P1) ?? MVP

**Goal**: El usuario define el presupuesto anual desglosado por cuenta y centro de coste (si activo); el sistema almacena importes y rechaza duplicados.

**Independent Test**: Registrando un presupuesto anual por cuenta y centro, el sistema lo almacena y lo consulta por ejercicio sin duplicados.

### Tests for User Story 1

- [X] T011 [P] [US1] Test de duplicidad rechazada: `backend/tests/unit/test_presupuesto_duplicado.py` — insertar la misma combinación dos veces → la segunda rechaza (FR-005)
- [X] T012 [P] [US1] Test de cuenta inapunteable rechazada: `backend/tests/unit/test_cuenta_inapunteable.py` — intentar presupuestar una cuenta nivel 2 (is_selectable=false) → 422

### Implementation for User Story 1

- [X] T013 [US1] Implementar servicio `guardar_presupuesto` en `backend/src/services/budget/presupuesto_service.py`: crear/actualizar `Presupuesto` en transacción ACID; validar cuenta is_selectable=true de la empresa activa; validar que si hay `centro_coste_id`, pertenece a la empresa; validar que el periodo de seguimiento esté abierto (409 si cerrado); audit log
- [X] T014 [US1] Implementar servicio `importar_presupuesto` en `backend/src/services/budget/presupuesto_service.py`: importación en lote (CSV/JSON) validada fila por fila (Pydantic v2); atomicidad: si alguna fila falla, toda la importación se aborta (o reporta parcial según diseño); audit log con payload de importación
- [X] T015 [US1] Implementar endpoints en `backend/src/api/presupuestos.py`: POST `/` (200/422/409), POST `/importar` (200), GET `/` con filtros (200)
- [X] T016 [US1] Crear página frontend `frontend/src/app/presupuestos/page.tsx`: listado de líneas de presupuesto por ejercicio, formulario de alta, validación de duplicado
- [X] T017 [US1] Tests integración importación: `backend/tests/integration/test_importar_presupuesto.py` — importar 5 líneas, verificar que quedan almacenadas y que el listado las muestra
- [X] T018 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_presupuesto_tenant.py` — empresa A crea presupuesto, empresa B no lo ve; intento de guardar desde B con cuenta de A → 422

**Checkpoint**: User Story 1 completa — presupuesto anual por cuenta/centro. MVP desplegable.

---

## Phase 4: User Story 2 — Seguimiento y comparación presupuesto vs real (Priority: P2)

**Goal**: El usuario compara el real del diario (SPEC-002) con el presupuesto, calculando desviación absoluta y relativa por cuenta/centro; las cuentas sin presupuesto aparecen con desviación = real.

**Independent Test**: Consultando la desviación por cuenta/centro, los valores cuadran con real − presupuesto con precisión de 4 decimales.

### Tests for User Story 2

- [X] T019 [P] [US2] Test de cálculo de desviación absoluta: `backend/tests/unit/test_desviacion_absoluta.py` — real=45000, presupuesto=48000 → desviación absoluta=-3000.0000; real=50000, presupuesto=48000 → desviación=2000.0000; verificación de signo según convención gasto/ingreso
- [X] T020 [P] [US2] Test de desviación relativa: `backend/tests/unit/test_desviacion_relativa.py` — presupuesto≠0 → relativa calculada; presupuesto=0 → null; verificación de precisión `NUMERIC(7,4)` en la razón (SC-005)
- [X] T021 [US2] Test de cuenta sin presupuesto: `backend/tests/unit/test_sin_presupuesto.py` — cuenta con real≠0 y sin línea de presupuesto → sin_presupuesto=true, desviación=real

### Implementation for User Story 2

- [X] T022 [US2] Implementar servicio `calcular_desviaciones` en `backend/src/services/budget/desviaciones.py`: recibir `(empresa_id, ejercicio, filtro)`, consultar `SUM(Debe)/SUM(Haber)` del diario (SPEC-002) por cuenta en el periodo, aplicar `calcular_signo_real` de utils, combinar con el presupuesto, calcular desviación absoluta (`Decimal`) y relativa (`Decimal` con redondeo 4 dec.; `null` si presupuesto=0); incluir combinaciones `sin_presupuesto=true` para cuentas reales sin presupuesto
- [X] T023 [US2] Implementar servicio `obtener_periodo_actual` en `backend/src/services/budget/desviaciones.py`: consultar el periodo `abierto` por (empresa_id, ejercicio); devolver `numero_periodo`, `estado`, `fecha_cierre` (null si abierto)
- [X] T024 [US2] Implementar endpoints en `backend/src/api/presupuestos.py`: GET `/seguimiento?ejercicio=&cuenta_id=&centro_coste_id=` (200), GET `/seguimiento/periodo?ejercicio=` (200)
- [X] T025 [US2] Crear página frontend `frontend/src/app/presupuestos/seguimiento/page.tsx`: tabla comparativa (cuenta, centro, presupuesto, real, desviación absoluta, relativa, flag sin_presupuesto) con filtros por centro/cuenta/mes
- [X] T026 [US2] Tests integración desviación completa: `backend/tests/integration/test_seguimiento_completo.py` — crear presupuesto (US1), registrar asientos de gasto reales (SPEC-002), consultar desviación y verificar que `real − presupuesto == desviación_absoluta` con precisión exacta de 4 decimales
- [X] T027 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_seguimiento_tenant.py` — empresa A registra presupuesto y asientos reales, empresa B ve desviaciones vacías (aislamiento del diario + presupuesto)

**Checkpoint**: User Stories 1 y 2 completas — presupuesto + seguimiento de desviaciones.

---

## Phase 5: User Story 3 — Informes y cierres de seguimiento (Priority: P2)

**Goal**: El usuario genera informes de desviación acumulada por centro y cuenta, y cierra el seguimiento de un periodo dejando la desviación final registrada como trazable (snapshot inmutable).

**Independent Test**: Generando un informe de desviación, se listan todas las cuentas/centros con sus valores; al cerrar, el snapshot queda persistido e inmutable.

### Tests for User Story 3

- [X] T028 [P] [US3] Test de informe lista todas las cuentas/centros: `backend/tests/unit/test_informe_completo.py` — verificar que el informe incluye tanto cuentas con presupuesto como `sin_presupuesto`; total_presupuestado == suma(importe_presupuestado); total_real == suma(importe_real)
- [X] T029 [P] [US3] Test de cierre genera snapshot trazable: `backend/tests/unit/test_cierre_snapshot.py` — al cerrar, la tabla `Desviacion` tiene filas por cada combinación; el periodo queda `cerrado`; la fecha de cierre y el actor quedan registrados
- [X] T030 [US3] Test de modificación post-cierre rechazada: `backend/tests/unit/test_cierre_bloqueo.py` — intento de guardar presupuesto después del cierre → 409; intento de cerrar un periodo ya cerrado → 409

### Implementation for User Story 3

- [X] T031 [US3] Implementar servicio `generar_informe_desviacion` en `backend/src/services/budget/informe_desviacion.py`: consultar desviaciones por (empresa_id, ejercicio, rango_feche o mes); generar `total_presupuestado`, `total_real` y agrupación por centro/cuenta; exportar JSON con items paginados
- [X] T032 [US3] Implementar servicio `cerrar_periodo` en `backend/src/services/budget/cierre_periodo.py`: cambiar `PeriodoSeguimiento.estado → cerrado`, registrar `fecha_cierre` y `cerrado_por`, calcular y persistir `Desviacion` (snapshot inmutable) para cada combinación presente en el presupuesto o en el diario; todo en `async with async_session.begin()`; audit log con `action = CIERRE_PERIODO`
- [X] T033 [US3] Implementar endpoints en `backend/src/api/presupuestos.py`: GET `/informes/desviacion?ejercicio=&centro_coste_id=&mes=` (200) y POST `/informes/cerrar` (200/409/422)
- [X] T034 [US3] Crear página frontend `frontend/src/app/presupuestos/informes/page.tsx`: informe acumulado por centro/cuenta con totales, botón "Cerrar periodo" con confirmación
- [X] T035 [US3] Tests integración cierre completo: `backend/tests/integration/test_cierre_completo.py` — crear presupuesto y asientos, generar informe, cerrar periodo, verificar snapshot inmutable; intentar modificar presupuesto → 409
- [X] T036 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_cierre_tenant.py` — empresa A cierra, empresa B no ve su snapshot; intento de cerrar desde B el periodo de A → 404

**Checkpoint**: User Stories 1, 2 y 3 completas — presupuesto, seguimiento, informes y cierre de periodo.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación constitucional y robustez.

- [X] T037 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_presupuestos.py` — verificar que toda desviación calculada usa `Decimal` (no float); que el real se calcula del diario cuyos asientos están balanceados; que no hay filtros cruzados entre empresas; que el snapshot del cierre es inmutable (UPDATE/DELETE rechazado)
- [X] T038 [P] Hardening multi-tenant: `backend/tests/integration/test_presupuestos_full_tenant.py` — escenario completo cross-empresa (presupuesto A, consulta B, cierre A desde B → todos 404/403)
- [X] T039 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_presupuestos.py` — reproducir los 5 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T040 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` en body/path; verificar Decimal/NUMERIC(18,4) en desviaciones y snapshot
- [X] T041 Validación de ejercicio cerrado: verificar que la creación de presupuesto rechaza 409 si el ejercicio está cerrado (SPEC-004)
- [X] T042 Limpieza y documentación: actualizar docstrings en servicios budget, verificar type hints, ejecutar lint/typecheck

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
- **US2 (P2)**: Sin dependencias de US1/US3; usa Phase 2 completa; el servicio `calcular_desviaciones` consume el motor de asientos (SPEC-002) en modo lectura.
- **US3 (P2)**: Sin dependencias directas de US1/US2; puede empezar con datos ficticios. El snapshot del cierre requiere que `calcular_desviaciones` exista (recomendable completar US2 antes).

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T010).
- Phase 3: tests [P] en paralelo (T011-T012).
- Phase 4: tests [P] en paralelo (T019-T020).
- Phase 5: tests [P] en paralelo (T028-T029).
- US1, US2, US3 pueden ejecutarse en paralelo por separado una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T011: "Test de duplicidad rechazada en backend/tests/unit/test_presupuesto_duplicado.py"
Task T012: "Test de cuenta inapunteable rechazada en backend/tests/unit/test_cuenta_inapunteable.py"

# Servicios en paralelo:
Task T013: "Servicio guardar_presupuesto en backend/src/services/budget/presupuesto_service.py"
Task T014: "Servicio importar_presupuesto en backend/src/services/budget/presupuesto_service.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T011-T018. Verificar quickstart Escenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP: presupuesto por cuenta/centro).
3. + US2 → Test independiente → Deploy/Demo (seguimiento y desviaciones).
4. + US3 → Test independiente → Deploy/Demo (informes y cierre trazable).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (alta y consulta de presupuesto).
   - Dev B: User Story 2 (cálculo de desviaciones contra el diario).
   - Dev C: User Story 3 (informes y cierre — puede empezar con datos de prueba).
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- El servicio `calcular_signo_real` aplica la convención de signos de `research.md` D2; se reutiliza en US2 y US3.
- La tabla `Desviacion` (snapshot) es inmutable por diseño (no se expone UPDATE/DELETE).
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.
---

## Estado real (implementacion 2026-09-26)

Vigésima sexta spec cerrada (42/42). Total del proyecto: **1.230/1.384** (26 specs).

### Backend

- **Modelos** `models/budget/`: `periodo_seguimiento.py` (`PeriodoSeguimiento` con
  `numero_periodo` correlativo por `(empresa, ejercicio)` e indice parcial UNIQUE
  `uq_periodo_seguimiento_abierto` para el "solo un periodo abierto por ejercicio";
  transicion unica `abierto -> cerrado` con `fecha_cierre`/`cerrado_por`),
  `presupuesto.py` (`Presupuesto` por combinacion cuenta-centro-ejercicio;
  unicidad FR-005 mediante **dos** indices parciales, `uq_presupuesto_sin_centro`
  y `uq_presupuesto_con_centro`, porque `centro_coste_id` es NULLABLE y NULL no
  colisiona en un UNIQUE normal) y `desviacion.py` (`Desviacion` snapshot
  append-only, mismos dos indices parciales, `desviacion_relativa NUMERIC(7,4)`).
  Todos con `UNIQUE(empresa_id, id)`, FKs compuestas por `empresa_id` hacia
  `account_plan (tenant_id, id)`, `centro_coste (empresa_id, id)` y
  `journal_entry`/`periodo_seguimiento`, e `empresa_id` en indices (constitucion III).
- **Migracion `017_presupuestos.sql`**: 3 tablas, 2 enums, unicidades, checks,
  indices parciales, 4 FKs compuestas cross-tenant y funcion
  `f_desviacion_append_only()` con los triggers `trg_desviacion_append_only_update/_delete`
  (constitucion II en el punto mas cercano a la persistencia). Registrada en
  `db/migrate.py` (`ORDEN_PREFERENTE`) y `test_migrations.ESPERADAS`; espejo
  SQLite en `db/triggers.py`.
- **Servicios** `services/budget/`: `errores.py` (`PresupuestoError` con `code`
  + `status_code`), `utils.py` (convencion de signos D2 `calcular_real`,
  `calcular_desviacion_absoluta`/`_relativa`, cuantizacion `c4`/`c4_ratio` a 4
  decimales, `cuenta_grupo`), `periodos.py` (correlatividad con
  `SELECT ... FOR UPDATE`, `asegurar_periodo`, `crear_periodo`, `cerrar_periodo`),
  `presupuesto_service.py` (`guardar_presupuesto` idempotente por combinacion,
  `importar_presupuesto` en lote con rollback atomico, `listar_presupuestos`),
  `desviaciones.py` (`calcular_desviaciones` agrega `SUM(Debe)`/`SUM(Haber)`
  del diario POSTED por combinacion y solo grupos 6/7, `obtener_periodo_actual`,
  `desviaciones_de_periodo`), `informe_desviacion.py` (`generar_informe_desviacion`
  con totales, subtotales por centro y lectura opcional desde el snapshot;
  `filas_desde_snapshot`) y `cierre_periodo.py` (`cerrar_periodo_desviaciones`
  persiste el snapshot e invierte el periodo en la misma transaccion,
  `listar_snapshots`).
- **API** `api/presupuestos.py` (modulo suelto, prefijo `/api/v1/presupuestos`):
  `POST/GET ""`, `POST /importar` (multipart CSV/JSON), `GET/POST /periodos`,
  `GET /seguimiento`, `GET /seguimiento/periodo`, `GET /seguimiento/snapshot`,
  `GET /informes/desviacion`, `POST /informes/cerrar`. Todos con
  `Depends(get_empresa_id)` y guardas `require_permission("presupuestos", ...)`
  (modulo RBAC nuevo); errores como `{"code", "detail"}` con 404/409/422.
- **RBAC**: modulo `presupuestos` anadido al catalogo de
  `services/security/catalogo.py`, a la migracion `007_rbac.sql` y al trigger
  SQLite `trg_companies_rbac_seed` (12 modulos de negocio, 98 permisos,
  160 concesiones por empresa). Recuentos de `test_matriz_evaluacion`,
  `test_rbac_tenant_models` y `test_quickstart_rbac` actualizados.

### Frontend

- `components/budget/api.ts` (cliente tipado + `formatearImporte`/`formatearPorcentaje`),
  `app/presupuestos/page.tsx` (listado + alta + importacion CSV),
  `app/presupuestos/seguimiento/page.tsx` (tabla comparativa con filtros
  ejercicio/mes/cuenta/centro) y `app/presupuestos/informes/page.tsx` (totales,
  subtotales por centro, tabla de cierre y boton "Cerrar periodo" con confirmacion,
  mas apertura de un periodo nuevo). Enlace en `app/page.tsx`. **92 rutas**.

### Pruebas (164 nuevas)

- Unit: `test_budget_models` (T009, 12), `test_presupuesto_duplicado` (T011, 5),
  `test_cuenta_inapunteable` (T012, 8), `test_desviacion_absoluta` (T019, 12),
  `test_desviacion_relativa` (T020, 9), `test_sin_presupuesto` (T021, 7),
  `test_informe_desviacion_completo` (T028, 5), `test_cierre_snapshot` (T029, 7),
  `test_cierre_bloqueo` (T030, 9), `test_constitucion_presupuestos` (T037, 15);
  helper compartido `tests/unit/budget_support.py`.
- Integracion: `test_budget_tenant_isolation` (T010, 5),
  `test_importar_presupuesto` (T017, 12), `test_presupuesto_tenant` (T018, 6),
  `test_seguimiento_completo` (T026, 11), `test_seguimiento_tenant` (T027, 6),
  `test_cierre_completo` (T035, 7), `test_cierre_tenant` (T036, 5),
  `test_presupuestos_full_tenant` (T038, 6), `test_quickstart_presupuestos`
  (T039, 8, los 5 escenarios de `quickstart.md`). Fixture `presupuestos_client`
  en `conftest.py` (empresas A=10/B=20, PGC, centro de coste, tres usuarios con
  matriz RBAC, helpers de asientos y ejercicio cerrado).
- PostgreSQL 16: `test_presupuestos_unicidad_y_snapshot_en_postgresql` en
  `tests/integration/test_pg_schema.py` (migracion 017, indices parciales,
  periodo unico abierto, snapshot append-only, rango del ratio).

### Lecciones reutilizables

- **NULL no colisiona en un UNIQUE**: para hacer efectiva la unicidad de
  (empresa, ejercicio, cuenta, centro) con `centro_coste_id` opcional hacen
  falta **dos** indices parciales UNIQUE (uno `WHERE centro_coste_id IS NULL` y
  otro `WHERE centro_coste_id IS NOT NULL`), tanto en SQLite (`Index(...,
  sqlite_where=..., postgresql_where=...)`) como en PostgreSQL.
- **Aggregar el diario por el codigo del plan, no solo por `account_id`**: la
  convencion de signos D2 depende del grupo PGC (6 = `SUM(Debe)`, 7 = `SUM(Haber)`),
  asi que la agregacion necesita `account_plan.code` para decidir el signo. Por
  eso el seguimiento se limita a los grupos 6 y 7: mezclar cuentas de balance
  haria que los totales del informe se anulasen por partida doble.
- `db.execute(select(Modelo))` devuelve tuplas (`.all()`), no instancias: usar
  `db.scalars(...)` cuando se filtran atributos de una entidad.
- Al anadir un modulo RBAC hay que actualizar **los tres** sitios coherentes
  (`catalogo.py`, `007_rbac.sql`, trigger `trg_companies_rbac_seed`) y los
  recuentos de permisos/concesiones de los tests de SPEC-015.
- Un test de nombre de fichero duplicado entre `tests/unit/` y `tests/integration/`
  rompe la recoleccion de pytest (import mode `prepend` sin `__init__.py`).
- Los triggers de inmutabilidad en SQLite se disparan al ejecutar el `UPDATE`/`DELETE`
  core; envolver el `execute` en `pytest.raises(IntegrityError)`.

### Desviaciones

- El boundary ACID autoritativo es `get_db` + `flush()` (no
  `async with async_session.begin()` literal de T032/T040).
- `cuenta_id` es `BIGINT` (el `id` real de `account_plan`), no `UUID` como dice el
  `data-model.md`; `centro_coste_id`/`periodo_id` si son `UUID`.
- `desviacion_relativa` se satura al rango de `NUMERIC(7,4)` (mas improbable en
  la practica) en vez de dejar fallar la columna; el test lo documenta.
- Solo las cuentas de los grupos 6 y 7 admiten presupuesto
  (`cuenta_no_presupuestable` 422); presupuestar una cuenta de balance haria que
  el informe sumase su contrapartida con signo opuesto.
- `guardar_presupuesto` es idempotente por combinacion: repetir con **otro** importe
  **actualiza** la linea; el 422 `duplicado_identico` se reserva al POST simple
  con importe identico (FR-005 del contrato). La importacion en lote reenvia el
  mismo fichero sin error (parametro `permitir_identico`).
- El ejercicio de un CSV importado se deduce del nombre del fichero
  (`presupuesto_2026.csv`, convencion del quickstart) o del campo `ejercicio`
  del formulario; si falta, 422 `parametro_invalido`.
- Se anaden `GET/POST /periodos` y `GET /seguimiento/snapshot`, endpoints no
  listados en el contrato pero necesarios para el ciclo abrir/cerrar y para
  consultar el snapshot; la API se comporta exactamente como en el quickstart.
- T028 nombra `test_informe_completo.py`, que ya existe en `tests/integration/`
  de SPEC-017; el test vive en `tests/unit/test_informe_desviacion_completo.py`
  para evitar la colision de modulo de pytest.
- El modulo frontend es `components/budget/` (no `widgets`) y las paginas se
  agrupan en `app/presupuestos/*` siguiendo la convencion de SPEC-025.

### Verificacion

- Suite completa: **1.651 passed / 9 skipped** (SQLite). El unico fallo de la
  corrida fue `tests/integration/test_suggest_perf.py::test_arbol_menos_500ms`,
  flaky conocido bajo carga de SPEC-001, **2 passed** aislado. Detalle por bloque:
  `tests/unit` **918 passed**, `tests/integration` **717 passed / 9 skipped**,
  `tests/contract` **16 passed**.
- PostgreSQL 16.4 real: migraciones 000-017 aplicadas sobre esquema limpio y
  **7 passed** en `test_pg_schema.py` (incluida la nueva
  `test_presupuestos_unicidad_y_snapshot_en_postgresql`).
- `ruff check src tests` limpio y `mypy -p api -p models -p services -p database
  -p base -p db -p main -p config` limpio (**350 fuentes**).
- `tsc --noEmit` + `eslint src` + `next build` verdes (**92 rutas**, 3 nuevas:
  `/presupuestos`, `/presupuestos/seguimiento`, `/presupuestos/informes`).