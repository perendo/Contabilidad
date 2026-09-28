# Tasks: Matriz de Permisos por Rol (SPEC-015)

**Input**: Design documents from `/specs/015-permisos-por-rol/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant — en este módulo sin asientos, el aislamiento empresa×rol es el criterio central).

**Organization**: Organizado por user story para implementación y test independientes. Se apoya en SPEC-003 (identidad, sesión, empresa activa, roles base), que no se duplica.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Sin importes monetarios en este módulo. Endpoints bajo `/api/v1/...` con empresa activa en cabecera de sesión (SPEC-003/015), nunca en path ni body.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Trazabilidad FR ↔ User Story

| Requisito | Descripción breve | User Story |
|---|---|---|
| FR-001 | Matriz de permisos por módulo, operación y rol | US1 |
| FR-002 | Denegar por defecto operación no concedida | US2 |
| FR-003 | Verificar autorización en cada operación sin bypass | US2 |
| FR-004 | Comprobar empresa activa y su matriz antes de operar | US2 |
| FR-005 | Auditar intentos denegados y concedidos | US3 |
| FR-006 | Configuración restringida a matriz de configuración | US1 |
| FR-007 | Cumplir constitución en flujo completo | US2 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar el módulo `rbac`/`security` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo `security`: `backend/src/models/rbac/__init__.py`, `backend/src/services/security/__init__.py`, `backend/src/api/rbac.py`, `backend/src/api/deps.py` (dependency `require_permission` — punto único de autorización)
- [X] T002 [P] Configurar router `rbac`: registrar prefijo `/api/v1` en `backend/src/api/rbac.py` con dependencies de SPEC-003 (sesión + empresa activa + rol)
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/permisos/`, `frontend/src/components/rbac/`, `frontend/src/services/client.ts` (cabecera de empresa activa)
- [X] T004 [P] Crear utils de autorización: `backend/src/api/deps.py` con `require_permission(modulo: str, operacion: str)` que solo consulta la matriz de la empresa activa y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `PermisoOperacion` en `backend/src/models/rbac/permiso_operacion.py`: id UUID PK, modulo VARCHAR(40), operacion ENUM (ver/crear/editar/aprobar/importar_exportar/configurar/baja/cerrar), descripcion VARCHAR(255), requiere_datos_contables BOOLEAN; UNIQUE (modulo, operacion)
- [X] T006 [P] Crear modelo `MatrizPermiso` en `backend/src/models/rbac/matriz_permiso.py`: id, empresa_id (PK compuesta), rol_id FK → SPEC-003 Rol, permiso_id FK → PermisoOperacion, concesion_id UUID NULL; UNIQUE (empresa_id, rol_id, permiso_id); índice de evaluación (empresa_id, rol_id, modulo(permiso), operacion)
- [X] T007 [P] Crear modelo `EventoAuditoriaAcceso` en `backend/src/models/rbac/evento_auditoria_acceso.py`: id, empresa_id, usuario_id FK → SPEC-003, rol_id FK → SPEC-003, modulo, operacion, resultado ENUM (allow/deny), motivo ENUM (sin_permiso/sin_rol/operacion_inexistente/sin_empresa/concedido), timestamp_utc TIMESTAMPTZ, ip VARCHAR(45); in-mutable (sin UPDATE/DELETE, trigger/constraint)
- [X] T008 [P] Semilla de catálogo: `backend/src/services/security/catalogo.py` — datos de `PermisoOperacion` para módulos acct, ar, treasury/bank, inmovilizado, divisas, rbac; y seed de matriz inicial por empresa (SPEC-003: ADMIN/ACCOUNTANT/READ_ONLY)
- [X] T009 [P] Tests de modelos fundacionales: `backend/tests/unit/test_rbac_models.py` — verificar UNIQUE (empresa_id, rol_id, permiso_id), UNIQUE (modulo, operacion), FK compuestas empresa_id, que no existe UPDATE/DELETE sobre EventoAuditoriaAcceso
- [X] T010 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_rbac_tenant_models.py` — matriz y eventos solo visibles por su empresa; las consultas de A nunca devuelven filas de B

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Definir la matriz de permisos por rol (Priority: P1) ?? MVP — cubre FR-001, FR-006

**Goal**: El administrador define, por módulo y operación, qué roles pueden ejecutarla en su empresa; la matriz se aplica de forma central.

**Independent Test**: Configurando una operación para un rol, solo los usuarios con ese rol pueden ejecutarla; el resto lo tiene denegado.

### Tests for User Story 1

- [X] T011 [P] [US1] Test concesión/denegación por matriz: `backend/tests/unit/test_matriz_evaluacion.py` — fila presente → allow solo para ese rol; sin fila → deny (ausencia = denegado); rol distinto → deny
- [X] T012 [P] [US1] Test catálogo cerrado: `backend/tests/unit/test_catalogo_operaciones.py` — operación no catálogo no puede concederse (422); concesión duplicada → 409
- [X] T013 [P] [US1] Test administración por matriz de configuración: `backend/tests/unit/test_configuracion_matriz.py` — solo quien tiene `rbac`/`configurar` en la empresa gestiona la matriz; READ_ONLY o sin fila → 403
- [X] T014 [P] [US1] Test aislamiento US1: `backend/tests/integration/test_matriz_tenant.py` — matriz de A no aplica en B; administrador de A no muta la matriz de B (404)

### Implementation for User Story 1

- [X] T015 [US1] Implementar servicio de catálogo en `backend/src/services/security/catalogo.py`: listado estático `PermisoOperacion` y validación de operaciones existentes
- [X] T016 [US1] Implementar servicio de matriz en `backend/src/services/security/matriz.py`: `conceder(empresa_id, rol_id, modulo, operacion)` (inserta fila + evento en una transacción ACID), `revocar(matriz_id)`, `reset(empresa_id)` (seed inicial), consulta de la matriz de la empresa activa
- [X] T017 [US1] Implementar endpoints en `backend/src/api/rbac.py`: `GET /api/v1/permisos/catalogo`, `GET /api/v1/permisos/matriz`, `POST /api/v1/permisos/matriz`, `DELETE /api/v1/permisos/matriz/{matriz_id}`, `POST /api/v1/permisos/matriz/reset`
- [X] T018 [US1] Implementar `GET /api/v1/permisos/mis-permisos` en `backend/src/api/rbac.py`: concesiones del rol del usuario en la empresa activa (para ocultar UI; la seguridad no depende de esto)
- [X] T019 [US1] Crear página frontend `frontend/src/app/permisos/page.tsx`: tabla matriz (rol × módulo × operación) para la empresa activa, alta/baja de concesiones, reset
- [X] T020 [US1] Crear componente frontend `frontend/src/components/rbac/permisos-table.tsx`: render condicionado de operaciones según `mis-permisos`
- [X] T021 [US1] Tests integración matriz completa: `backend/tests/integration/test_matriz_completa.py` — conceder → rol ejecuta; sin fila → 403; revocar → 403 inmediato; reset → seed; auditoría de concesión
- [X] T022 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_matriz_tenant.py` — escenario completo: A concede a su ACCOUNTANT; el mismo usuario (sesión en B) no lo tiene; B no ve la matriz de A

**Checkpoint**: User Story 1 completa — matriz configurable y aplicada de forma central. MVP desplegable.

---

## Phase 4: User Story 2 — Denegación por defecto y restricción multiempresa (Priority: P1) — cubre FR-002, FR-003, FR-004, FR-007

**Goal**: Toda operación queda denegada por defecto salvo concesión, aplicada como el mínimo (empresa × rol × permiso); sin bypass.

**Independent Test**: Sin matriz explícita, cualquier intento es denegado; aun con rol global, la falta de acceso de la empresa deniega.

### Tests for User Story 2

- [X] T023 [P] [US2] Test denegación por defecto: `backend/tests/unit/test_denegacion_defecto.py` — operación sin fila → 403 en todos los módulos; se registra evento `sin_permiso`
- [X] T024 [P] [US2] Test mínimo empresa×rol×permiso: `backend/tests/unit/test_minimo_empresa_rol_permiso.py` — todos los combos auditador: (rol sin permiso, permiso sin rol en empresa, empresa sin matriz) → deny; solo la intersección concede
- [X] T025 [P] [US2] Test rol inexistente / permiso inexistente: `backend/tests/unit/test_permisos_inexistentes.py` — rol sin vínculo en la empresa → 403 `sin_rol`; concesión de operación no catálogo → 422; acceso con empresa sin rol → 403 `sin_empresa`
- [X] T026 [P] [US2] Test no-bypass (contrato): `backend/tests/contract/test_no_bypass_endpoints.py` — inventariar los routers registrados de los módulos con datos (acct, ar, treasury, bank, inmovilizado, divisas, rbac) y verificar que cada endpoint con datos usa `require_permission` (SC-004)
- [X] T027 [P] [US2] Test aislamiento US2: `backend/tests/integration/test_denegacion_empresa.py` — rol con permiso en A deniega en B; usuario de A nunca ve datos de B aun con rol global

### Implementation for User Story 2

- [X] T028 [US2] Implementar dependency `require_permission(modulo, operacion)` completa en `backend/src/api/deps.py`: (1) sesión SPEC-003 → (2) empresa activa → (3) rol en la empresa → (4) fila en MatrizPermiso → (5) allow/deny con evento de auditoría en la transacción (deny sin transacción de negocio: una transacción ACID del evento)
- [X] T029 [US2] Exponer inventario de rutas para el test: `backend/src/api/routes_registry.py` — lista de `(ruta, modulo, operacion)` registrada; el test de contrato lo recorre
- [X] T030 [US2] Aplicar `require_permission` a routers de módulos base: `backend/src/api/acct/...`, `backend/src/api/ar/...`, `backend/src/api/treasury/...`, `backend/src/api/reconciliation.py`, `backend/src/api/inmovilizado.py`, `backend/src/api/forex.py` (cada endpoint con datos de negocio usa la dependency con su par módulo/operación)
- [X] T031 [US2] Tests integración denegación en endpoints reales: `backend/tests/integration/test_denegacion_endpoints.py` — READ_ONLY frente a crear/editar/aprobar/importar de un módulo real → 403; ACCOUNTANT con concesión → 200
- [X] T032 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_denegacion_empresa.py` — escenario completo: permiso en A deniega en B con el mismo rol y cuenta; datos de A invisibles desde B en todo módulo

**Checkpoint**: User Stories 1 y 2 completas — denegación por defecto central sin bypass y aislamiento estricto.

---

## Phase 5: User Story 3 — Auditar las comprobaciones de permiso (Priority: P2) — cubre FR-005

**Goal**: El sistema registra en el log de auditoría cada intento denegado y cada permiso concedido que afecte a datos contables, con usuario, empresa y operación.

**Independent Test**: Denegando una operación o concediéndola, el evento queda registrado con actor, empresa y operación.

### Tests for User Story 3

- [X] T033 [P] [US3] Test auditoría de denegados: `backend/tests/unit/test_auditoria_denegado.py` — deny genera `EventoAuditoriaAcceso` con usuario, empresa, módulo, operación, motivo, timestamp UTC, IP; sin pérdida si la operación principal falla (misma transacción)
- [X] T034 [P] [US3] Test auditoría de concedidos: `backend/tests/unit/test_auditoria_concedido.py` — allow sobre operación con `requiere_datos_contables=true` genera evento con payload (strings decimales si aplica)
- [X] T035 [P] [US3] Test inmutabilidad del evento: `backend/tests/unit/test_auditoria_evento_inmutable.py` — UPDATE/DELETE sobre `EventoAuditoriaAcceso` → rechazo a nivel de base de datos (constitución II aplicada a la auditoría)
- [X] T036 [P] [US3] Test aislamiento US3: `backend/tests/integration/test_auditoria_tenant.py` — la auditoría de A no la ve B; B no puede consultar los eventos de A

### Implementation for User Story 3

- [X] T037 [US3] Implementar servicio `auditoria_acceso` en `backend/src/services/security/auditoria_acceso.py`: función `registrar(empresa_id, usuario_id, rol_id, modulo, operacion, resultado, motivo, payload, ip)` que persiste el evento en la misma transacción ACID de la operación (o de la denegación); in-mutable
- [X] T038 [US3] Integrar `auditoria_acceso` dentro de `require_permission` en `backend/src/api/deps.py`: allow sobre datos contables y deny de cualquier operación emiten evento; el event se persiste con `async with async_session.begin()`
- [X] T039 [US3] Implementar endpoint `GET /api/v1/permisos/auditoria` en `backend/src/api/rbac.py`: filtros resultado/modulo/operacion/usuario/fecha y paginación (requiere `rbac`/`ver`)
- [X] T040 [US3] Crear frontend `frontend/src/app/permisos/auditoria/page.tsx`: log de accesos con filtros y detalle del evento (actor, empresa, operación, resultado, motivo, IP, UTC)
- [X] T041 [US3] Tests integración auditoría: `backend/tests/integration/test_auditoria_completa.py` — denegar y conceder; verificar eventos consultables con todos los campos; verificar atomicidad (si el evento no puede persistir, la transacción revierte)
- [X] T042 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_auditoria_tenant.py` — escenario completo: A deniega y concede; B no ve los eventos de A y sus propias denegaciones no se mezclan

**Checkpoint**: User Stories 1, 2 y 3 completas — matriz, denegación por defecto y auditoría de accesos funcionales.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación constitucional y robustez.

- [X] T043 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_rbac.py` — verificar aislamiento empresa_id en todas las tablas rbac (matriz y auditoría); verificar la inmutabilidad de los eventos de auditoría; verificar que ninguna concesión altera asientos (SPEC-002 intacto)
- [X] T044 [P] Hardening multi-tenant: `backend/tests/integration/test_rbac_full_tenant_isolation.py` — escenario completo cross-empresa (rol A que actúa en B → 403/404 en todos los módulos; evento de A invisible para B)
- [X] T045 [P] Test no-bypass consolidado: `backend/tests/contract/test_no_bypass_all_routers.py` — recorrer el inventario completo de routers (SPEC-001/002/011/013/014/016/020) y verificar `require_permission` en cada endpoint con datos (SC-004)
- [X] T046 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_rbac.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T047 [P] Code review: verificar que la evaluación de permisos no cachea concesiones revocables (D3 research); verificar que ningún endpoint de negocio omite `require_permission`; verificar Decimal/strings en payloads auditados cuando aplican
- [X] T048 Limpieza y documentación: actualizar docstrings en servicios `security`, verificar type hints, ejecutar lint/typecheck; confirmar semilla de catálogo con los módulos definitivos (D1 research)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1 (la dependency `require_permission` se integra después de que la matriz exista, pero su testing unit es independiente).
- **US3 (Phase 5)**: Depende de Phase 2; el servicio de auditoría se desarrolla en paralelo con US1/US2 y se integra al final de US2.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa y SPEC-003/SPEC-002 ya operativos.
- **US2 (P2)**: Depende de la matriz (US1) para la evaluación; sin dependencias de US3.
- **US3 (P2)**: Depende de US2 para la emisión de eventos desde `require_permission`; aunque el servicio de auditoría se crea antes.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios (catálogo → matriz → autorización) antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: modelos [P] en paralelo (T005-T007), semilla [P] (T008).
- Phase 3: tests [P] en paralelo (T011-T014), catalogo + matriz [P] (T015-T016).
- Phase 4: tests [P] en paralelo (T023-T027), dependency + inventario [P] (T028-T029).
- Phase 5: tests [P] en paralelo (T033-T036), auditoría [P] (T037).
- US1 define la base (matriz) sobre la que US2 integra la dependency; US3 se habilita desde US2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T011: "Test evaluación de matriz en backend/tests/unit/test_matriz_evaluacion.py"
Task T012: "Test catálogo cerrado en backend/tests/unit/test_catalogo_operaciones.py"

# Servicios en paralelo:
Task T015: "Catálogo en backend/src/services/security/catalogo.py"
Task T016: "Matriz en backend/src/services/security/matriz.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T011-T022. Verificar quickstart Scenario 1 y 3.
5. Desplegar/demo si listo (matriz configurable con denegación por defecto en la dependency).

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (matriz + dependency básica).
3. + US2 → Test independiente → Deploy/Demo (denegación por defecto sin bypass).
4. + US3 → Test independiente → Deploy/Demo (auditoría de accesos).
5. + Polish → Validación constitucional completa + control de no-bypass en todos los routers.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (matriz + catálogo + endpoints + UI).
   - Dev B: User Story 2 (dependency `require_permission` + integración en routers).
   - Dev C: User Story 3 (auditoría de accesos + endpoint de consulta).
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
- Constitución V: ninguna tarea se considera finalizada sin pytest de aislamiento multi-tenant (en este módulo, empresa×rol); no hay asientos propios, pero la integración con SPEC-002 verifica que no se altera el balance.
- La identidad, la sesión y la empresa activa vienen de SPEC-003; esta feature solo añade la capa de autorización por operación.

---

## Estado real (implementación 2026-09-21)

Las 48 tareas quedan cerradas. Puertas: pytest **890 passed / 5 skipped** (SQLite;
`test_suggest_perf` es flaky bajo carga y pasa aislado), `ruff` + `mypy` limpios
(219 fuentes) y `tsc` + `eslint` + `next build` **49 rutas**. Desviaciones:

- **Modelos**: `EventoAuditoriaAcceso.operacion` es `VARCHAR(40)` (no enum) para poder
  auditar operaciones arbitrarias sin romper el INSERT; `MatrizPermiso.concesion_id` es
  un UUID sin FK (enlace blando al evento de concesión). La inmutabilidad del log se
  implementa con triggers (`trg_evento_auditoria_acceso_immutable_*` en SQLite y
  `trg_evento_acceso_immutable_*` en PostgreSQL).
- **Seed**: los ids generados por los triggers SQLite usan `lower(hex(randomblob(16)))`
  para ser coherentes con los UUID que persiste SQLAlchemy (SQLite `hex()` devuelve
  mayúsculas; la comparación de texto es case-sensitive y rompía la FK). El trigger
  `trg_companies_rbac_seed` siembra catálogo + roles + matriz en cada alta de empresa
  (equivalente a `services/security/catalogo.sembrar_seguridad`, invocado también desde
  `services/auth/company_service.crear_empresa`).
- **Endpoint `GET /permisos/matriz`**: además de `permiso_id` devuelve `matriz_id`
  (el `concesion_id`) para que la UI pueda revocar; `GET /permisos/mis-permisos` queda
  fuera del guard (se autoconcede) junto con auth/companies/health.
- **`routes_registry`**: las versiones recientes de FastAPI envuelven `include_router`
  en `_IncludedRouter`; el inventario desciende por `original_router.routes`. El test de
  contrato recorre `main.app` y verifica 0 rutas de datos sin `require_permission`
  (123 rutas, 116 con guard).
- **Wiring**: se reemplazó `Depends(require_write)` por `require_permission(modulo,
  operacion)` en todos los routers de datos (`acct`, `ar`, `treasury`, `bank`,
  `inmovilizado`, `divisas`, `reporting`, `fiscal`, `invoicing`, `rbac`) y se añadieron
  guards a las rutas de lectura que no tenían ninguno. `require_write` se conserva
  exportado en `api/deps.py` por compatibilidad (sin uso).
- **Migración 007**: `seed_seguridad_empresa` es `RETURNS TRIGGER` y lee `NEW.company_id`;
  el trigger se invoca con `EXECUTE FUNCTION seed_seguridad_empresa()`. No se ejecutó
  contra PostgreSQL en esta sesión (la suite usa SQLite vía `db/triggers.py`).
- **Fixtures**: nuevo `rbac_client` en `backend/tests/conftest.py` (empresas A=10/B=20,
  ADMIN/ACCOUNTANT/READ_ONLY con vínculo en ambas, PGC sembrado, routers rbac+accounts+
  journal) usado por los tests de matriz, denegación y auditoría.
- **Operación no catalogada**: como el guard solo evalúa pares del catálogo, el 422 de
  "operación inexistente" se verifica contra `POST /permisos/matriz` (concesión), no
  contra un endpoint de negocio.
