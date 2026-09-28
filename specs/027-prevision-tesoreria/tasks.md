# Tasks: Previsión y Flujo de Caja (SPEC-027)

**Input**: Design documents from `/specs/027-prevision-tesoreria/`

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

**Purpose**: Inicializar módulos `treasury` (models) y `cashflow` (services) en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo de tesorería: `backend/src/models/treasury/__init__.py`, `backend/src/models/treasury/prevision.py`, `backend/src/models/treasury/movimiento_prevision.py`, `backend/src/models/treasury/alerta_liquidez.py`, `backend/src/models/treasury/efe.py`
- [X] T002 [P] Crear estructura de servicios cashflow: `backend/src/services/cashflow/__init__.py`, `backend/src/services/cashflow/proyeccion.py`, `backend/src/services/cashflow/efe.py`, `backend/src/services/cashflow/alertas.py`, `backend/src/services/cashflow/clasificacion_actividad.py`, `backend/src/api/tesoreria.py`, `backend/src/config.py`
- [X] T003 [P] Configurar router tesoreria: registrar prefijo `/api/v1/tesoreria` en `backend/src/api/tesoreria.py` con dependency de sesión autenticada y empresa activa (cabecera, nunca path/body)
- [X] T004 [P] Crear estructura frontend: `frontend/src/app/tesoreria/`, `frontend/src/app/tesoreria/efe/`, `frontend/src/app/tesoreria/alertas/`, `frontend/src/components/cashflow/` y crear utils de sesión `backend/src/api/deps.py` con `get_empresa_id()` (bloquea acceso cross-tenant, 403)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `PrevisionTesoreria` en `backend/src/models/treasury/prevision.py`: empresa_id (PK), numero_prevision (BIGINT correlativo por empresa), fecha_generacion TIMESTAMPTZ, desde_fecha DATE, hasta_fecha DATE, granularidad ENUM (dia/semana/mes), saldo_inicial NUMERIC(18,4), saldo_final NUMERIC(18,4), estado ENUM (borrador/generada/anulada), creado_por; constraint hasta_fecha >= desde_fecha
- [X] T006 [P] Crear modelo `MovimientoPrevision` en `backend/src/models/treasury/movimiento_prevision.py`: empresa_id (PK), prevision_id NULL FK → PrevisionTesoreria, origen ENUM (vencimiento/remesa_cobro/pago_recurrente/cobro_estimado), vencimiento_id NULL FK → SPEC-011 (FK compuesta empresa_id), numero_recibo VARCHAR NULL, tipo ENUM (cobro/pago), importe NUMERIC(18,4) check > 0, fecha_prevista DATE NULL, frecuencia ENUM (unico/semanal/mensual/anual), concepto VARCHAR(200), incluido BOOLEAN
- [X] T007 [P] Crear modelo `AlertaLiquidez` en `backend/src/models/treasury/alerta_liquidez.py`: empresa_id (PK), prevision_id FK → PrevisionTesoreria, fecha DATE, saldo_proyectado NUMERIC(18,4) check < 0, importe_deficit NUMERIC(18,4), estado ENUM (abierta/atendida/ignorada), accion_sugerida ENUM (reprogramar_pago/incluir_ingreso), movimiento_origen_id NULL FK → MovimientoPrevision; único (empresa_id, prevision_id, fecha)
- [X] T008 [P] Crear modelos `InformeEFE` y `LineaEFE` en `backend/src/models/treasury/efe.py`: InformeEFE con empresa_id, ejercicio INT, saldo_inicial NUMERIC(18,4), saldo_final NUMERIC(18,4), cuadre BOOLEAN, sin_conciliar BOOLEAN, estado ENUM (borrador/formulado), formulado_por/fecha_formulacion; LineaEFE con empresa_id, informe_id FK, bloque ENUM (operativa/inversion/financiacion), cuenta_id FK → account_plan (SPEC-001, FK compuesta empresa_id), importe NUMERIC(18,4) firmado, override_usuario BOOLEAN
- [X] T009 [P] Crear servicios puros de soporte en `backend/src/services/cashflow/utils.py` y `backend/src/services/cashflow/clasificacion_actividad.py`: función `clasificar_bloque(cuenta_grupo) -> operativa/inversion/financiacion` (groups 6/7/tesoreria → operativa; grupo 2 → inversion; grupo 1/9/16/17 → financiacion) y utilidad `suma_decimal()` con `Decimal`
- [X] T010 [P] Tests de modelos fundacionales: `backend/tests/unit/test_cashflow_models.py` — verificar constraint de rango de prevision, FK compuesta empresa_id en vencimiento y cuenta, check importe > 0, alerta con saldo < 0
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_cashflow_tenant_isolation.py` — crear previsión en empresa A, verificar que empresa B no la ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Generar la previsión de tesorería (Priority: P1) ?? MVP

**Goal**: El usuario genera una previsión a partir de vencimientos pendientes (cobros esperados y pagos previstos); el sistema proyecta los flujos por día/semana/mes mostrando saldo disponible y movimientos.

**Independent Test**: Generando una previsión, los cobros y pagos esperados cuadran con los vencimientos pendientes por fecha de vencimiento.

### Tests for User Story 1

- [X] T012 [P] [US1] Test de proyección de vencimientos: `backend/tests/unit/test_proyeccion_escenarios.py` — vencimientos pendientes de SPEC-011/020 se proyectan según fecha prevista; agrupación día/semana/mes correcta (SC-001)
- [X] T013 [P] [US1] Test de exclusión de vencidos/cobrados: `backend/tests/unit/test_exclusion_previstos.py` — vencido cobrado/pagado excluido (FR-006); sin fecha prevista excluido con motivo; saldo parcial de medio ejercicio permitido (edge case)
- [X] T014 [US1] Test de saldo acumulado: `backend/tests/unit/test_saldo_acumulado.py` — para cada bucket, `saldo_k = saldo_inicial + Σ movimientos hasta k` con precisión Decimal exacta (SC-002)

### Implementation for User Story 1

- [X] T015 [US1] Implementar servicio `recuperar_movimientos_proyectables` en `backend/src/services/cashflow/proyeccion.py`: filtrar vencimientos pendientes por (empresa_id, fecha_prevista en rango), excluir vencidos/cobrados/pagados y sin fecha prevista; reportar `excluidos` con motivo
- [X] T016 [US1] Implementar servicio `generar_prevision` en `backend/src/services/cashflow/proyeccion.py`: crear `PrevisionTesoreria` + `MovimientoPrevision` (origenes vencimiento/remesa y manuales); asignar `numero_prevision` correlativo por empresa (SELECT ... FOR UPDATE, constitución IV); calcular `saldo_inicial` (SPEC-013 o balance SPEC-002), agrupar por granularidad y calcular saldo acumulado por bucket; todo en `async with async_session.begin()`; audit log
- [X] T017 [US1] Implementar endpoints en `backend/src/api/tesoreria.py`: POST `/previsiones` (201/422), GET `/previsiones` (paginación+filtros), GET `/previsiones/{id}` (200 con buckets/alertas, 404)
- [X] T018 [US1] Crear página frontend `frontend/src/app/tesoreria/page.tsx`: selector de rango y granularidad, generación de previsión y tabla de buckets (fecha, cobros, pagos, saldo)
- [X] T019 [US1] Crear página frontend `frontend/src/app/tesoreria/[id]/page.tsx`: detalle (buckets con saldo acumulado, lista de movimientos excluidos con motivo) y botón regenerar
- [X] T020 [US1] Tests integración previsión completa: `backend/tests/integration/test_prevision_completa.py` — crear vencimientos pendientes + movimiento manual, generar previsión y verificar que la suma de movimientos iguala el saldo_final y cada bucket
- [X] T021 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_prevision_tenant.py` — empresa A genera previsión, empresa B no la ve en listado/detalle; intento de regenerar desde B → 404

**Checkpoint**: User Story 1 completa — previsión de tesorería funcional. MVP desplegable.

---

## Phase 4: User Story 2 — Visualizar el flujo de efectivo consolidado (Priority: P2)

**Goal**: El usuario visualiza el EFE del ejercicio desglosado por tipo de operación (operativa, inversión, financiación), con cuadre de saldo inicial + movimientos = saldo final.

**Independent Test**: Generando el EFE, los saldos de apertura, movimientos y cierre cuadran entre sí.

### Tests for User Story 2

- [X] T022 [P] [US2] Test de clasificación por bloque: `backend/tests/unit/test_clasificacion_actividad.py` — cuentas del grupo 6/7/tesorería → operativa; grupo 2 → inversión; grupo 1/9/16/17 → financiacion; override del usuario respetado
- [X] T023 [P] [US2] Test de cuadre del EFE: `backend/tests/unit/test_efe_cuadre.py` — `saldo_inicial + Σ bloques == saldo_final`; si no cuadra → `cuadre=false` y informe no formulable (FR-004/SC-003)
- [X] T024 [US2] Test de cruce con conciliación: `backend/tests/unit/test_efe_cruce_conciliacion.py` — si la conciliación (SPEC-013) difiere por movimientos no conciliados → `sin_conciliar=true` con aviso, pero no bloquea (Assumptions)

### Implementation for User Story 2

- [X] T025 [US2] Implementar servicio `generar_efe` en `backend/src/services/cashflow/efe.py`: clasificar cuentas por actividad (clasificacion_actividad.py), calcular importes por bloque desde el diario (SPEC-002) filtrado por (empresa_id, ejercicio), calcular `saldo_inicial`/`saldo_final` y `cuadre` con Decimal; cruzar con el saldo de SPEC-013 para `sin_conciliar`
- [X] T026 [US2] Implementar servicio `formular_efe` en `backend/src/services/cashflow/efe.py`: aplicar overrides de clasificación del usuario, verificar cuadre, persistir `InformeEFE` + `LineaEFE` (estado borrador→formulado, snapshot immutable), audit log con `action = EFE_FORMULADO`
- [X] T027 [US2] Implementar endpoints en `backend/src/api/tesoreria.py`: GET `/efe?ejercicio=` (200 con bloques, 404), POST `/efe/formular` (200/409/422)
- [X] T028 [US2] Crear página frontend `frontend/src/app/tesoreria/efe/page.tsx`: informe por bloques con totales, verificación de cuadre visible, formulación con confirmación
- [X] T029 [US2] Tests integración EFE completo: `backend/tests/integration/test_efe_completo.py` — registrar asientos de tesorería y de inversión/financiación (SPEC-002), generar EFE, verificar tres bloques y cuadre; formular y verificar snapshot inmutable
- [X] T030 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_efe_tenant.py` — empresa A formula el EFE, empresa B no ve el informe ni puede formulario con sus datos

**Checkpoint**: User Stories 1 y 2 completas — previsión + EFE consolidado.

---

## Phase 5: User Story 3 — Alertar sobre necesidades de tesorería (Priority: P2)

**Goal**: El sistema detecta días/semanas/meses con saldo negativo proyectado, notifica en la UI y permite al usuario reprogamar pagos o incluir ingresos previstos.

**Independent Test**: Si la previsión muestra saldo negativo en algún periodo, el sistema lo notifica (alerta `abierta`).

### Tests for User Story 3

- [X] T031 [P] [US3] Test de detección de saldo negativo: `backend/tests/unit/test_detectar_alertas.py` — bucket con saldo < 0 → alerta creada con `importe_deficit` y `accion_sugerida` (FR-003/SC-004)
- [X] T032 [P] [US3] Test de límite de solvencia: `backend/tests/unit/test_saldo_cero.py` — bucket con saldo exactamente 0 → visible como límite sin alerta (edge case spec)
- [X] T033 [US3] Test de acción de alerta: `backend/tests/unit/test_accion_alerta.py` — `reprogramar_pago` actualiza `fecha_prevista` de `MovimientoPrevision`; `incluir_ingreso` crea un cobro; la alerta pasa a `atendida`; `ignorar` la desestima

### Implementation for User Story 3

- [X] T034 [US3] Implementar servicio `detectar_alertas` en `backend/src/services/cashflow/alertas.py`: recorrer buckets de la previsión, crear `AlertaLiquidez` para saldos < 0 en la misma transacción de generación de previsión; saldo = 0 no alerta
- [X] T035 [US3] Implementar servicio `gestionar_alerta` en `backend/src/services/cashflow/alertas.py`: `atender` (aplica reprogramar_pago/incluir_ingreso sobre MovimientoPrevision con auditoría) o `ignorar`; validar que la alerta no esté `atendida`/`ignorada` (409)
- [X] T036 [US3] Implementar endpoints en `backend/src/api/tesoreria.py`: GET `/alertas?prevision_id=&estado=` (200), POST `/alertas/{id}/atender` (200/409/422), POST `/alertas/{id}/ignorar` (200/409)
- [X] T037 [US3] Crear página frontend `frontend/src/app/tesoreria/alertas/page.tsx`: listado de alertas con saldo/deficit/fecha, acciones (reprogramar/include) y estado
- [X] T038 [US3] Tests integración alertas completo: `backend/tests/integration/test_alertas_completo.py` — generar previsión con día negativo, verificar alerta, atender reprogramando un pago, regenerar previsión y comprobar que el bucket ya no es negativo
- [X] T039 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_alertas_tenant.py` — alerta de empresa A invisible para empresa B; intento de atenderla desde B → 404

**Checkpoint**: User Stories 1, 2 y 3 completas — previsión, EFE y alertas de liquidez.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación constitucional y robustez.

- [X] T040 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_cashflow.py` — verificar que todo saldo proyectado/EFE se calcula con `Decimal` (sin float); que el EFE cuadra con el diario balanceado; que ningún endpoint expone `empresa_id` en body/path; que la tabla `InformeEFE` formulada es inmutable (UPDATE/DELETE rechazado)
- [X] T041 [P] Hardening multi-tenant: `backend/tests/integration/test_cashflow_full_tenant.py` — escenario completo cross-empresa (previsión A, EFE B, alerta A atendida desde B → todos 404/403)
- [X] T042 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_cashflow.py` — reproducir los 5 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T043 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint usa `empresa_id` del body; verificar Decimal/NUMERIC(18,4) en saldos y EFE
- [X] T044 Validación de ejercicio cerrado: verificar que la formulación del EFE rechaza con 409 si el ejercicio está cerrado o ya formulada (SPEC-004)
- [X] T045 Limpieza y documentación: actualizar docstrings en servicios cashflow, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **US3 (Phase 5)**: Depende de Phase 2; requiere US1 para las alertas sobre la previsión (se recomienda US1 antes).
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Sin dependencias de US1/US3; usa Phase 2 completa; consume el diario (SPEC-002) y la conciliación (SPEC-013) en lectura.
- **US3 (P2)**: Sin dependencias de US2; depende de US1 (las alertas nacen al generar una previsión). Puede preparar los tests de detección en paralelo.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T011).
- Phase 3: tests [P] en paralelo (T012-T013).
- Phase 4: tests [P] en paralelo (T022-T023).
- Phase 5: tests [P] en paralelo (T031-T032).
- US1, US2 y US3 (parcial) pueden ejecutarse en paralelo por separado una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T012: "Test de proyección de vencimientos en backend/tests/unit/test_proyeccion_escenarios.py"
Task T013: "Test de exclusión de vencidos/cobrados en backend/tests/unit/test_exclusion_previstos.py"

# Servicios en paralelo:
Task T015: "Servicio recuperar_movimientos_proyectables en backend/src/services/cashflow/proyeccion.py"
Task T016: "Servicio generar_prevision en backend/src/services/cashflow/proyeccion.py (agrupación + saldo)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T012-T021. Verificar quickstart Escenarios 1 y 2.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP: previsión día/semana/mes).
3. + US2 → Test independiente → Deploy/Demo (informe EFE consolidado).
4. + US3 → Test independiente → Deploy/Demo (alertas de liquidez).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (proyección a partir de vencimientos).
   - Dev B: User Story 2 (informe EFE y clasificación por actividad).
   - Dev C: prepara tests de User Story 3 (detección de saldo negativo) y completa la integración cuando US1 entregue previsiones.
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- La previsión consume `Vencimiento` (SPEC-011) y `ReciboRemesa` (SPEC-020) en solo lectura; el saldo inicial proviene de SPEC-013 o del balance de SPEC-002 (research D1).
- El EFE se clasifica por grupo del plan de cuentas (SPEC-001) con override manual (research D4).
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.
---

## Estado real (implementacion 2026-09-26)

**Estado**: 45/45 tareas completadas. 27ª spec cerrada del proyecto.
Suite completa **1951 passed / 11 skipped** (SQLite; las 2 pruebas `test_suggest_perf`
verdes aisladas) y **9 passed** en el contrato PostgreSQL 18.6 real (instalación local) con las
migraciones 000-018 aplicadas sobre esquema limpio. `ruff` + `mypy` limpios
(363 fuentes), `tsc` + `eslint` + `next build` verdes con **95 rutas**
(4 nuevas: `/tesoreria/previsiones`, `/tesoreria/previsiones/[id]`,
`/tesoreria/efe`, `/tesoreria/alertas`).

### Modelos (`models/treasury/`)

- `prevision.py` (`PrevisionTesoreria`, `GranularidadPrevision`, `EstadoPrevision`),
  `movimiento_prevision.py` (`MovimientoPrevision` + 3 enums),
  `alerta_liquidez.py` (`AlertaLiquidez`, `EstadoAlertaLiquidez`,
  `AccionSugeridaLiquidez`) y `efe.py` (`InformeEFE` + `LineaEFE`, `BloqueEFE`,
  `EstadoInformeEFE`). Registrados en `models/treasury/__init__.py` y en
  `models/__init__.py` (resuelven las FKs compuestas cross-spec en `create_all`).
- **Columna anadida `PrevisionTesoreria.plan_manual` (JSON)**: el *plan* manual
  del usuario (pagos recurrentes, cobros estimados, ingresos creados al atender
  una alerta) es la **definicion** de la proyeccion, no su recorte temporal.
  Sin ella, regenerar con otro rango perderia los movimientos manuales y una
  reprogramacion (research D6) no se conservaria. Reconstruye la lista y los
  dicts en cada escritura: mutar en sitio un `JSON` sin `MutableList` no lo ve
  SQLAlchemy y el UPDATE se pierde en silencio (bug real detectado por T038).
- `MovimientoPrevision.motivo_exclusion`: persiste el codigo de exclusion
  (`vencido`, `cobrado`, `anulado`, `sin_fecha`) para que el detalle lo muestre
  sin recalcular. CHECK en ambos sentidos: excluido exige motivo, incluido lo prohibe.
- CHECK de saldo negativo en `AlertaLiquidez` (`saldo_proyectado < 0`) mas unicidad
  `(empresa_id, prevision_id, fecha)`: la garantia de "saldo cero no alerta" y de
  "una alerta por bucket" es del **modelo**, no solo del servicio (T032).

### Servicios (`services/cashflow/`)

- `utils.py` (puro), `clasificacion_actividad.py` (puro), `saldos.py`,
  `errores.py`, `proyeccion.py`, `efe.py`, `alertas.py`.
- `saldos.py` es un fichero **anadido** a los nominales: `saldo_tesoreria_inicial`
  (research D1, precedencia conciliacion > diario) lo usan US1 (`proyeccion.py`) y
  US2 (`efe.py`); mantenerlo duplicado habria creado dos versiones del calculo del
  saldo de tesorería.
- Los buckets se calculan en el GET a partir de `MovimientoPrevision` +
  `saldo_inicial` persistido, en vez de una tabla de lineas de bucket: el
  `data-model.md` no la define y asi la prevision y su detalle comparten una unica
  formula. El acumulado arranca en `saldo_inicial` (bug real detectado por T014:
  arrancaba en cero y `saldo_final` no cuadraba con la cabecera).
- Regenerar es un **refresco en el sitio** que conserva `numero_prevision`
  (constitucion IV: la correlatividad emitida no se altera). Reexpande el plan
  manual al nuevo rango y recalcula alertas.
- `leer_efe` devuelve el **snapshot formulado** si existe y el calculo provisional
  si no: un EFE formulado es un documento inmutable y releerlo debe devolver lo
  firmado, incluida la clasificacion overrideo, no un recalculo divergente.
- `generar_efe` **verifica** el cuadre contra la variacion real del grupo 5 del
  diario (`variacion_neta == variacion_tesoreria`) en vez de asumirlo, y excluye del
  cuadre tanto las cuentas del grupo 5 (derivan los saldos) como los asientos
  `OPENING` (ya reflected en `saldo_inicial`). Sin esas dos exclusiones el EFE
  duplicaria la variacion.

### API (`api/tesoreria.py`)

Modulo suelto bajo `/api/v1/tesoreria` (prefijo versionado, convencion de
`api/catalogo.py` y `api/presupuestos.py`), registrado en `main.py`. 12 rutas:
`GET/POST /previsiones`, `GET /previsiones/{id}`,
`POST /previsiones/{id}/regenerar`, `POST /previsiones/{id}/movimientos`,
`GET /alertas`, `POST /alertas/{id}/atender`, `POST /alertas/{id}/ignorar`,
`GET /efe`, `POST /efe/formular`.

### Migracion y triggers

- `018_cashflow.sql`: 5 tablas, 9 enums, unicidades, checks, indices, 4 FKs
  compuestas cross-tenant y los triggers append-only `informe_efe`/`linea_efe`
  (constitucion II). Registrada en `db/migrate.py` (`ORDEN_PREFERENTE`) y
  `test_migrations.ESPERADAS`; espejo SQLite en `db/triggers.py`.
- La FK a `Vencimiento` (SPEC-011, sin migracion propia) se anade dentro de un
  `IF to_regclass('public.vencimiento') IS NOT NULL`, **igual que `tercero` en
  `015_retenciones_irpf.sql`**: sin el guarda, `db.migrate` abortaba con
  `UndefinedTableError: relation "vencimiento" does not exist`. El modelo
  SQLAlchemy si la declara siempre y `create_all` la respeta en el esquema de pruebas.

### RBAC

Se reutiliza el modulo **`treasury`** del catalogo de SPEC-015 (no se creo un
modulo `tesoreria` ni `cashflow`), siguiendo lo ya hecho por SPEC-018/021/022.
Operaciones usadas: `ver`, `crear`, `editar`, `cerrar`. Ninguna ruta queda sin
bypass: `inventario_permisos` de `api/routes_registry.py` las cubre todas.

### Pruebas (300 nuevas)

- 152 unitarias: `test_cashflow_models` (24), `test_proyeccion_escenarios` (11),
  `test_exclusion_previstos` (16), `test_saldo_acumulado` (8),
  `test_clasificacion_actividad` (41), `test_efe_cuadre` (16),
  `test_efe_cruce_conciliacion` (8), `test_efe_ejercicio_cerrado` (6),
  `test_detectar_alertas` (10), `test_saldo_cero` (5), `test_accion_alerta` (16),
  `test_constitucion_cashflow` (21), `test_cashflow_review` (32),
  `test_migrations` (+1).
- 146 de integracion: `test_cashflow_tenant_isolation` (6),
  `test_prevision_completa` (15), `test_prevision_tenant` (15),
  `test_efe_completo` (12), `test_efe_tenant` (6), `test_alertas_completo` (15),
  `test_alertas_tenant` (6), `test_cashflow_full_tenant` (5),
  `test_quickstart_cashflow` (5, los 5 escenarios), `test_pg_schema` (+2).
- Helper compartido `tests/unit/cashflow_support.py` (`empresa`, `cuentas`,
  `tercero`, `vencimiento`, `plantar_cuenta`, `publicar_asiento`,
  `saldos_por_cuenta`) y fixture HTTP `cashflow_client` en `conftest.py`
  (empresas A=10/B=20, ADMIN/ACCOUNTANT/READ_ONLY con matriz RBAC, PGC base,
  helpers de asientos, cuentas, conciliacion y ejercicio cerrado).

### Desviaciones

- **Boundary ACID**: el autoritativo es `get_db` + `flush()`, no el literal
  `async with async_session.begin()` de T016/T043. `test_cashflow_review.py`
  verifica por AST que ningun servicio abre su propia transaccion.
- **Archivo nuevo `services/cashflow/saldos.py`** (ver arriba).
- **Bucket calculado, no persistido** (ver arriba).
- **Regeneracion en el sitio**, conservando `numero_prevision` y el plan manual.
- **Manual sin `fecha_prevista` se EXCLUYE con motivo `sin_fecha`**, no 422: el
  edge case del spec ("sin fecha quedan fuera de la proyeccion") es la regla mas
  especifica y la exige T013, mientras que el 422 generico del contrato solo
  cubre "movimientos sin fecha prevista" en la lista de errores. Se reporta en
  `excluidos` para que el usuario vea que tiene que datarlo.
- **Una alerta por periodo negativo**, no una por racha de deficit: SC-004 exige
  "el 100 % de los dias con saldo negativo generan una alerta" y el saldo es
  acumulado. `accion_sugerida` es `reprogramar_pago` solo si el bucket negativo
  tiene un pago propio; en los periodos siguientes de la racha ya no hay nada que
  reprogramar y se propone `incluir_ingreso`.
- **Frontend**: la prevision vive en `app/tesoreria/previsiones/` y
  `app/tesoreria/previsiones/[id]/`, no en `app/tesoreria/page.tsx`: esa pagina
  es el panel de efectos y cobros por medio de SPEC-021 y se conserva (se
  enlazan las cuatro rutas nuevas desde ahi y desde `app/page.tsx`).
- **Rutas anadidas al contrato**: `POST /previsiones/{id}/regenerar` (T019 lo pide
  como boton "regenerar" pero no estaba en `contracts/api-contracts.md`) y
  `POST /previsiones/{id}/movimientos` (alta manual de pago recurrente / cobro
  estimado, que `aplicar_movimiento_manual` implementa y que la accion
  `incluir_ingreso` reutiliza). En `RegenerarBody`, `movimientos_manuales = null`
  significa "conservar el plan" y una lista (incluso vacia) lo sustituye.
- **Checks SQLite y coma flotante**: el CHECK `diferencia = saldo_banco -
  saldo_libros` de SPEC-013 no admite decimales no representables en binario
  (SQLite guarda `NUMERIC` como REAL). Las pruebas de conciliacion usan
  diferencias con representacion exacta (0.50 en vez de 0.01); la precision
  decimal fina se verifica en el calculo del EFE, donde si importa.

### Lecciones reutilizables

- **Mutar en sitio un `JSON` sin `MutableList`/`flag_modified` no lo ve
  SQLAlchemy**: el `UPDATE` se pierde en silencio y el bug aparece como "no
  funciona" sin excepcion. Reconstruir lista y dicts.
- **`await` en las columnas de un `ScalarResult`**: `db.scalars(...)` hay que
  terminarla con `.all()`; `len(resultado)` falla.
- **Los tests async no pueden usar fixtures HTTP sincronos** que crean su propio
  event loop (`RuntimeError: Cannot run the event loop while another loop is
  running`): el test que llama a `cf.mutar(...)` desde dentro de una corrutina
  propia debe ser `def`, no `async def`.
- **El saldo acumulado debe arrancar en `saldo_inicial`**, no en cero: si no,
  `saldo_final` y la serie de buckets divergen en silencio.
- **Una columna JSON de definiciones sobrevive mejor a un refresco** que
  reconstruir el plan desde los movimientos ya proyectados (que se pierden al
  acortar el rango).
- **Los triggers SQLite se disparan al ejecutar el `UPDATE`/`DELETE` core**, no al
  `flush`; envolver el `execute` en `pytest.raises(IntegrityError)`.
- **Una FK a una tabla sin migracion propia** (`vencimiento` de SPEC-011,
  `tercero` de SPEC-008) debe ir dentro de un `IF to_regclass(...) IS NOT NULL`
  en el `.sql`, o `db.migrate` aborta con `UndefinedTableError`.
