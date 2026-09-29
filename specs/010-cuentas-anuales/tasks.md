# Tasks: Cuentas Anuales (SPEC-010)

**Input**: Design documents from `/specs/010-cuentas-anuales/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitucion V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementacion y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3, US4)
- Incluir ruta exacta del archivo en la descripcion

---

## Trazabilidad FR ↔ User Story

| Requisito | Descripción breve | User Story |
|---|---|---|
| FR-001 | Formular Balance de Situación con cuadre A=P+PN | US1 |
| FR-002 | Formular PyG con resultado exacto en precisión decimal | US2 |
| FR-003 | Aislar cuentas anuales por empresa y ejercicio | US1 |
| FR-004 | Balances provisionales, formulación solo ejercicios cerrados | US3 |
| FR-005 | Cuentas anuales formuladas como documento inmutable | US3 |
| FR-006 | Resultado PyG coincidente con regularización SPEC-004 | US2 |
| FR-007 | Cumplir constitución en flujo completo | US1 |
| FR-008 | Formular EFE por actividades con cuadre | US4 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar modulo `reporting` en backend y frontend.

- [X] T001 [P] Crear estructura del modulo reporting: `backend/src/models/reporting/__init__.py`, `backend/src/services/reporting/__init__.py`, `backend/src/services/reporting/formulacion.py`, `backend/src/services/reporting/agrupacion.py`, `backend/src/api/cuentas_anuales/__init__.py`, `backend/src/api/cuentas_anuales/routes.py`
- [X] T002 [P] Configurar router cuentas-anuales: registrar prefijo `/api/v1/cuentas-anuales` en `backend/src/api/cuentas_anuales/routes.py` con dependency de sesion autenticada `empresa_id`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/cuentas-anuales/`, `frontend/src/app/balance/`, `frontend/src/app/pyg/`, `frontend/src/app/efe/`, `frontend/src/components/reporting/`
- [X] T004 [P] Crear utils de sesion: `backend/src/api/cuentas_anuales/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesion y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelo de configuracion y logica de agrupacion que toda user story requiere.

**CRITICAL**: Ningun trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `ConfiguracionInforme` en `backend/src/models/reporting/configuracion.py`: empresa_id, ejercicio, informe_tipo ENUM, agrupacion_id FK, cuenta_ini/cuenta_fin, actividad_efe ENUM NULL; constraint unicidad (empresa_id, ejercicio, informe_tipo, agrupacion_id)
- [X] T006 [P] Implementar servicio de agrupacion en `backend/src/services/reporting/agrupacion.py`: resolver para cada cuenta su masa/partida segun configuracion; si no hay configuracion, clasificar en "Otros" con advertencia
- [X] T007 [P] Implementar consulta de saldos por cuenta en `backend/src/services/reporting/saldos.py`: agregar JournalEntryLine por (empresa_id, ejercicio, account_id) filtrando asientos POSTED; devolver saldos `Decimal` exactos
- [X] T008 [P] Tests de modelos fundacionales: `backend/tests/unit/test_reporting_models.py` — verificar unicidad de configuracion, clasificacion "Otros", calculo de saldos
- [X] T009 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_reporting_tenant_isolation.py` — configuracion en empresa A no visible en B; saldos de A no visibles en B

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Generar el Balance de Situacion (Priority: P1) — MVP — cubre FR-001, FR-003, FR-007

**Goal**: El sistema agrega los saldos por estructura de balance y verifica el cuadre Activo == Pasivo + Patrimonio.

**Independent Test**: Generando el Balance de un ejercicio, la igualdad se cumple y solo incluye datos de la empresa activa.

### Tests for User Story 1

- [X] T010 [P] [US1] Test cuadre balance: `backend/tests/unit/test_balance_cuadre.py` — con saldos conocidos en grupos 1-3, verificar total_activo == total_pasivo + total_patrimonio con Decimal exacto
- [X] T011 [P] [US1] Test agrupacion y exclusiones: `backend/tests/unit/test_balance_agrupacion.py` — verificar masas correctas, que grupos 6-7 no aparecen, clasificacion "Otros" cuando no hay configuracion; flag balance_descuadrado si no cuadra

### Implementation for User Story 1

- [X] T012 [US1] Implementar `generar_balance` en `backend/src/services/reporting/formulacion.py`: agregar saldos por estructura (ConfiguracionInforme), calcular totales con `Decimal`, verificar cuadre antes de devolver; si no cuadra -> 422 `balance_descuadrado`
- [X] T013 [US1] Implementar comparativo con ejercicio anterior en `backend/src/services/reporting/comparativo.py`: si request `comparativo=true` y existe informe previo, incluir columnas comparativas
- [X] T014 [US1] Implementar endpoint GET `/api/v1/cuentas-anuales/{ejercicio}/balance` en `backend/src/api/cuentas_anuales/routes.py` (200; 422 balance_descuadrado)
- [X] T015 [US1] Implementar endpoint de configuracion POST/PATCH `/api/v1/cuentas-anuales/configuracion` en `backend/src/api/cuentas_anuales/config.py`
- [X] T016 [US1] Tests integracion balance completo: `backend/tests/integration/test_balance_completo.py` — crear asientos en A, generar balance, verificar cuadre y solo cuentas 1-3
- [X] T017 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_balance_tenant.py` — empresa A y B con saldos distintos, cada una ve solo los suyos; intento desde B de obtener configuracion de A -> 404

**Checkpoint**: User Story 1 completa — Balance funcional. MVP desplegable parcial.

---

## Phase 4: User Story 2 — Generar la Cuenta de Perdidas y Ganancias (Priority: P1) — cubre FR-002, FR-006

**Goal**: El sistema agrega ingresos y gastos por grupos 6-7 y verifica que el resultado coincide con el cierre.

**Independent Test**: Generando la PyG, el resultado coincide con la diferencia Ingresos - Gastos y con el saldo de la cuenta de resultados.

### Tests for User Story 2

- [X] T018 [P] [US2] Test PyG resultado: `backend/tests/unit/test_pyg_resultado.py` — verificar resultado = Ingresos - Gastos con Decimal exacto
- [X] T019 [P] [US2] Test coincidencia con cierre: `backend/tests/unit/test_pyg_coincide_cierre.py` — con asiento de regularizacion correcto, coincide_cierre=true; con regularizacion ausente/incorrecta, coincide_cierre=false y flag `descuadre_cierre`

### Implementation for User Story 2

- [X] T020 [P] [US2] Implementar `generar_pyg` en `backend/src/services/reporting/pyg.py`: agregar grupos 6 y 7 por partida, calcular resultado, comparar con asiento de cierre (SPEC-004)
- [X] T021 [US2] Implementar endpoint GET `/api/v1/cuentas-anuales/{ejercicio}/pyg` en `backend/src/api/cuentas_anuales/routes.py` (200; 409 descuadre_cierre en modo oficial)
- [X] T022 [US2] Tests integracion PyG completa: `backend/tests/integration/test_pyg_completo.py` — crear gestion + regularizacion, generar PyG, verificar coincidencia con cierre
- [X] T023 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_pyg_tenant.py` — empresa B no ve la PyG de A; resultado de A no contamina el de B

**Checkpoint**: User Stories 1 y 2 completas — Balance y PyG funcionales.

---

## Phase 5: User Story 4 — Formular el Estado de Flujos de Efectivo EFE (Priority: P2) — cubre FR-008

**Goal**: El sistema formula el EFE por actividades con cuadre de saldo inicial + movimientos = saldo final.

**Independent Test**: Generando el EFE, los saldos coinciden con la tesoreria del ejercicio.

### Tests for User Story 4

- [X] T024 [P] [US4] Test cuadre EFE: `backend/tests/unit/test_efe_cuadre.py` — saldo_final == saldo_inicial + movimientos; variacion == variacion_tesoreria_balance
- [X] T025 [P] [US4] Test clasificacion por actividad: `backend/tests/unit/test_efe_clasificacion.py` — movimientos de grupo 5 clasificados por contrapartida; reasignacion manual; no clasificado -> operativa por defecto con aviso

### Implementation for User Story 4

- [X] T026 [US4] Implementar `generar_efe` en `backend/src/services/reporting/efe.py`: calcular saldos inicial/final del grupo 5, clasificar movimientos por actividad, verificar cuadre con variacion del balance
- [X] T027 [US4] Implementar `clasificar_movimiento` en `backend/src/services/reporting/efe.py`: permitir reasignacion manual de actividad con validacion de que el ejercicio no este formulado oficialmente
- [X] T028 [US4] Implementar endpoints en `backend/src/api/cuentas_anuales/routes.py`: GET `/efe` (200; 409 efe_descuadrado en oficial), PATCH `/efe/clasificacion` (200)
- [X] T029 [US4] Tests integracion EFE completo: `backend/tests/integration/test_efe_completo.py` — crear cobros/pagos en grupo 5, generar EFE, verificar cuadre y variacion
- [X] T030 [US4] Tests aislamiento multi-tenant US4: `backend/tests/integration/test_efe_tenant.py` — empresa B no ve el EFE de A

**Checkpoint**: User Stories 1, 2 y 4 completas — Balance, PyG y EFE funcionales.

---

## Phase 6: User Story 3 — Formular y bloquear las cuentas anuales (Priority: P2) — cubre FR-004, FR-005

**Goal**: El contador formula y aprueba las cuentas anuales del ejercicio cerrado; quedan inmutables y trazables.

**Independent Test**: Formulando las cuentas anuales de un ejercicio cerrado, quedan inmutables y con su trazabilidad.

### Tests for User Story 3

- [X] T031 [P] [US3] Test formulacion requiere cierre: `backend/tests/unit/test_formulacion_requisitos.py` — ejercicio no cerrado -> 409; balance no cuadra -> 422; pyg no coincide -> 409
- [X] T032 [P] [US3] Test inmutabilidad de formulacion: `backend/tests/unit/test_formulacion_inmutabilidad.py` — generacion de formulacion con hash sha256; segunda formulacion sin anular -> 409 `ya_formulada`; anulacion registra motivo y usuario

### Implementation for User Story 3

- [X] T033 [US3] Crear modelo `FormulacionCuentasAnuales` en `backend/src/models/reporting/formulacion.py`: empresa_id, ejercicio, numero_formulacion BIGINT (correlativo), fecha_formulacion TIMESTAMPTZ, usuario_id, contenido_hash CHAR(64), estado ENUM, motivo_anulacion; constraint unico (empresa_id, ejercicio, numero_formulacion)
- [X] T034 [US3] Implementar `formular` en `backend/src/services/reporting/formulacion.py`: validar ejercicio cerrado y cuadres; generar snapshot de informes, calcular hash sha256, asignar numero_formulacion correlativo por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE`, persistir en transaccion ACID con audit log
- [X] T035 [US3] Implementar `anular_formulacion` en `backend/src/services/reporting/formulacion.py`: verificar permiso de administrador, registrar anulacion con motivo y trazabilidad; el snapshot original permanece en historico
- [X] T036 [US3] Implementar endpoints en `backend/src/api/cuentas_anuales/routes.py`: POST `/formular` (201), POST `/anular-formulacion` (200), GET `/formulaciones` (200)
- [X] T037 [US3] Tests integracion formulacion completa: `backend/tests/integration/test_formulacion_completa.py` — cerrar ejercicio, formular, verificar hash, anular, reformular, verificar numeracion 1 y 2
- [X] T038 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_formulacion_tenant.py` — formulacion en A no visible ni anulable desde B

**Checkpoint**: User Stories 1, 2, 3 y 4 completas — cuentas anuales funcionales.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validacion y robustez.

- [X] T039 [P] Validar constitucion V en todos los flujos: `backend/tests/unit/test_constitucion_reporting.py` — todo importe calculado en Decimal; balance/pyg/efe cuadran; no se mutan asientos ni formulaciones anuladas
- [X] T040 [P] Hardening multi-tenant: `backend/tests/integration/test_reporting_full_tenant_isolation.py` — escenario completo cross-empresa: asientos A, formulacion A, consultas B -> todas aisladas
- [X] T041 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_cuentas_anuales.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T042 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transaccion ACID); verificar que ningun endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [X] T043 Crear pagina frontend `frontend/src/app/cuentas-anuales/page.tsx`: selector de ejercicio, pestañas Balance/PyG/EFE, boton Formular con confirmacion si ejercicio cerrado
- [X] T044 [P] Crear paginas frontend `frontend/src/app/balance/page.tsx`, `frontend/src/app/pyg/page.tsx`, `frontend/src/app/efe/page.tsx`: visualizacion de informes con importes a 4 decimales y flags de cuadre
- [X] T045 Limpieza y documentacion: actualizar docstrings en servicios reporting, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **US4 (Phase 5)**: Depende de Phase 2; puede empezar en paralelo con US1/US2.
- **US3 (Phase 6)**: Depende de Phase 2 y de US1/US2/US4 (formulacion congela los tres informes).
- **Polish (Phase 7)**: Depende de las user stories completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1/MVP)**: Sin dependencias de US1; usa Phase 2 completa.
- **US4 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa.
- **US3 (P2)**: Depende de US1, US2 y US4 (la formulacion sella los tres informes).

### Within Each User Story

- Tests ANTES de la implementacion (TDD constitucion V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integracion y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T007).
- Phase 3: tests [P] en paralelo (T010-T011).
- Phase 4: tests [P] en paralelo (T018-T019).
- Phase 5: tests [P] en paralelo (T024-T025).
- Phase 6: tests [P] en paralelo (T031-T032).
- US1, US2 y US4 pueden ejecutarse en paralelo por separado una vez completada Phase 2.

---

## Parallel Example: User Story 2

```bash
# Tests en paralelo:
Task T018: "Test PyG resultado en backend/tests/unit/test_pyg_resultado.py"
Task T019: "Test coincidencia cierre en backend/tests/unit/test_pyg_coincide_cierre.py"

# Implementacion:
Task T020: "Servicio generar_pyg en backend/src/services/reporting/pyg.py"
Task T021: "Endpoint PyG en backend/src/api/cuentas_anuales/routes.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1 (Balance).
4. Completar Phase 4: User Story 2 (PyG).
5. **PARAR y VALIDAR**: Ejecutar T010-T023. Verificar quickstart Scenario 1, 2 y 6.
6. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 + US2 → Test independiente → Deploy/Demo (MVP!).
3. + US4 → Test independiente → Deploy/Demo (EFE).
4. + US3 → Test independiente → Deploy/Demo (formulacion oficial).
5. + Polish → Validacion constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (Balance).
   - Dev B: User Story 2 (PyG).
   - Dev C: User Story 4 (EFE).
3. Tras A/B/C: Dev D: User Story 3 (formulacion oficial + inmutabilidad).
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Cada user story debe ser completable y testeable independientemente (salvo US3 que depende de US1/US2/US4).
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo logico.
- Parar en cada checkpoint para validar story independientemente.
- Constitucion V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.

---

## Estado real (implementación 2026-09-20)

45/45 tareas completadas. Puertas en verde: pytest **738 passed / 5 skipped** (SQLite) y
**743 passed / 0 skipped** (PostgreSQL 16.4 real, esquema migrado 000–006); `ruff` + `mypy`
limpios (167 fuentes); `tsc` + `eslint` + `next build` **40 rutas**
(incl. `/cuentas-anuales`, `/balance`, `/pyg`, `/efe`).

### Desviaciones documentadas

1. **T003/T004 (estructura API)**: implementado como paquete `backend/src/api/cuentas_anuales/`
   (`__init__.py`, `deps.py`, `routes.py`, `config.py`) en lugar del módulo único
   `api/cuentas_anuales.py`, siguiendo el patrón de `api/ciclo`/`api/invoicing`. `deps.py`
   re-exporta `api.deps.get_empresa_id` (JWT + `X-Empresa-Activa`, nunca del cliente).
2. **T005 (`ConfiguracionInforme`)**: no existe una tabla `Agrupacion` en SPEC-001, por lo que
   se usa `agrupacion_codigo` + `agrupacion_nombre` + rango `[cuenta_ini, cuenta_fin]` en lugar
   de una FK. Único `(empresa_id, ejercicio, informe_tipo, agrupacion_codigo, cuenta_ini)`.
3. **T006 (agrupación)**: sin configuración, las cuentas se clasifican en `"Otros"` y el informe
   expone `hay_cuentas_sin_agrupar=true` (research D1). El endpoint `POST/PATCH /configuracion`
   reemplaza el juego de reglas de `(empresa, ejercicio, informe_tipo)`.
4. **T012 (balance)**: el lado de cada cuenta se deriva (grupo 1 → patrimonio, grupos 2/3 →
   activo, grupos 4/5 por signo del saldo) y el resultado de gestión (grupos 6-7) se incorpora al
   patrimonio; con partida doble el cuadre `Activo == Pasivo + Patrimonio` es estructuralmente
   verdadero, por lo que `422 balance_descuadrado` solo se dispara ante datos no balanceados
   (p. ej. corrupción), no por mala configuración.
5. **Modelos nuevos sin migración SQL**: `FormulacionCuentasAnuales` (snapshot JSON + sha256 +
   correlativo por empresa/ejercicio), `ClasificacionEfe` (override manual de actividad) y
   `ConfiguracionInforme` se crean vía `Base.metadata.create_all` en tests (precedente de
   `models/ar`/`treasury`); no se añadió `migrations/007_*.sql`. `usuario_id` es `String(120)`
   (email del actor) en lugar de UUID FK a SPEC-003.
6. **`modo=oficial`**: exige `FiscalYear.is_closed` (SPEC-004) y responde `409 ejercicio_no_cerrado`
   en balance/PyG/EFE; en PyG oficial exige además `coincide_cierre` (`409 descuadre_cierre`).
7. **T020 (PyG)**: el resultado de gestión se reconstruye excluyendo los asientos de regularización
   y cierre; `resultado_cierre` se toma del asiento de regularización (`FiscalYear.regularizacion_entry_id`,
   cuenta `129`). Ausente → `coincide_cierre=false` + `descuadre_cierre=true`.
8. **T026 (EFE)**: `saldo_inicial_tesoreria` procede de los asientos `OPENING` del ejercicio (SPEC-009);
   cada movimiento de grupo 5 se clasifica por la contrapartida de mayor importe (grupo 2 → inversión,
   grupo 1 → financiación, resto → operativa) y admite override manual (`ClasificacionEfe`).
   `variacion_balance` es la variación de tesorería del ejercicio (grupo 5), por lo que el cuadre es
   estructural.
9. **Ficheros de test consolidados**: en lugar de los ~16 nombres `unit/test_*.py` del backlog, los
   tests viven en `tests/unit/test_reporting_agrupacion.py` (T008/T010/T011),
   `tests/unit/test_constitucion_reporting.py` (T039/T040),
   `tests/integration/test_cuentas_anuales_us{1,2,3,4}.py` y
   `tests/integration/test_quickstart_cuentas_anuales.py` (T041). La fixture `cuentas_client`
   (`tests/conftest.py`) siembra PGC + cuenta `129` + diario distinto en empresas A=10/B=20.
10. **T042 (transacción ACID)**: los servicios usan `flush()` dentro del boundary de `get_db`
    (patrón obligatorio del proyecto), no `async with async_session.begin()` anidado; ningún endpoint
    acepta `empresa_id` del body/path y todos los importes son `Decimal`/`NUMERIC(18,4)`.
11. **T044 (frontend)**: vistas presentacionales en `frontend/src/components/reporting/`
    (`BalanceView`, `PygView`, `EfeView`) reutilizadas por la página principal y las páginas dedicadas.


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

- `configuracion_informe`
- `formulacion_cuentas_anuales`

## Qué se ha hecho, y qué no

**Sí**: un guard nuevo en `tests/unit/test_migrations.py`,
`test_toda_tabla_del_orm_tiene_migracion`, que cruza los `__tablename__` de
`src/models/` con los `CREATE TABLE` de `migrations/`. Con él, **una tabla nueva sin
migración se ve al escribir el modelo**, y no meses después. Las 27 están inventariadas
en `TABLAS_SIN_MIGRACION`, con dos guards que impiden que la lista mienta en ninguna de
las dos direcciones.

**No**: la migración de estas 2 tablas. Es trabajo de un día por spec —DDL, enums,
índices, unicidades, FKs compuestas por `empresa_id`, triggers de inmutabilidad que
correspondan, el contrato en `test_pg_schema.py` y los tasks que lo nombren— y no cabe
en una corrección puntual. Lo que **no** hay que hacer es volver a dar la spec por
cerrada sin mirar este apartado: la spec está implementada y probada, y aun así su
funcionalidad no se puede usar.
