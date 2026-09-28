# Tasks: Multiempresa y Control de Acceso por Roles — RBAC (SPEC-003)

**Input**: Design documents from `/specs/003-multiempresa-rbac/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (aislamiento multi-tenant y acceso no autorizado → 403).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Founded : bcrypt/argon2 + JWT (python-jose o el fijado en research D10).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3, US4)
- Incluir ruta exacta del archivo en la descripción

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo `iam` y frontend de sesión.

- [X] T001 [P] Crear estructura del módulo iam: `backend/src/models/iam/__init__.py`, `backend/src/services/auth/__init__.py`, `backend/src/api/auth/__init__.py`
- [X] T002 [P] Configurar routers auth y companies: registrar en `backend/src/api/auth/auth.py` y `backend/src/api/companies.py` con dependency de sesión
- [X] T003 [P] Crear estructura frontend de sesión: `frontend/src/app/login/page.tsx`, `frontend/src/components/rbac/`, `frontend/src/services/client.ts`
- [X] T004 [P] Crear utils de contexto: `backend/src/api/deps.py` con `get_current_user()`, `get_empresa_id()` y `require_role()` (leída de la cabecera `X-Empresa-Activa`, 403 sin contexto)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos y guards constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `Company` en `backend/src/models/iam/company.py`: company_id PK BIGINT, nif, razon_social, is_active, created_at
- [X] T006 [P] Crear modelo `User` en `backend/src/models/iam/user.py`: id, email UNIQUE, password_hash, full_name, is_active, created_at
- [X] T007 [P] Crear modelo `UserCompany` en `backend/src/models/iam/user_company.py`: user_id FK, company_id FK, role ENUM (ADMIN/ACCOUNTANT/READ_ONLY), is_default, is_active; `UNIQUE (user_id, company_id)`; índice único parcial `UNIQUE (user_id) WHERE is_default`
- [X] T008 [P] Crear migración DDL en `backend/migrations/004_iam.sql`: tablas `companies`, `users`, `user_companies`, FKs a `companies(company_id)` (referenciada por `account_plan.tenant_id`), índice único parcial de la empresa por defecto
- [X] T009 [P] Implementar `security.py` en `backend/src/services/auth/security.py`: hash/verify de contraseñas (bcrypt/argon2) y emit/verify JWT (claims sub/exp/jti) — algoritmo y expiración según config
- [X] T010 [P] Implementar guards en `backend/src/api/deps.py`: `get_current_user` (401 si token inválido/usuario inactivo), `get_empresa_id` (403 sin cabecera o sin relación activa), `require_role(*roles)` y `require_write` (blocking READ_ONLY)
- [X] T011 [P] Tests unit de modelos RBAC: `backend/tests/unit/test_rbac_models.py` — unicidad (user_id, company_id), empresa por defecto única por usuario, roles válidos
- [X] T012 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_iam_tenant_isolation.py` — dos empresas con dos usuarios, verificar que el contexto de empresa de A jamás filtra datos de B

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Iniciar sesión y acceder a las empresas autorizadas (Priority: P1) ?? MVP

**Goal**: El usuario se autentica y obtiene su sesión con la lista de empresas accesibles y su empresa por defecto.

**Independent Test**: Autenticando a un usuario se obtienen su sesión, su lista de empresas y su empresa por defecto; sin credenciales válidas no se inicia sesión.

### Tests for User Story 1

- [X] T013 [P] [US1] Test login correcto: `backend/tests/unit/test_login_correcto.py` — login válido devuelve token + companies + default_company_id (FR-001)
- [X] T014 [P] [US1] Test login inválido: `backend/tests/integration/test_login_invalido.py` — credenciales incorrectas o usuario inactivo → 401 sin filtración de empresas; payload de log sin datos reveladores

### Implementation for User Story 1

- [X] T015 [US1] Implementar servicio `login()` en `backend/src/services/auth/session.py`: verificar credenciales y estado activo, emitir JWT, devolver empresas accesibles (filtradas por actividad) y `default_company_id`; auditar LOGIN/LOGIN_FAILED
- [X] T016 [US1] Implementar endpoint POST `/api/v1/auth/login` en `backend/src/api/auth/auth.py`: 200 con `{ token, user, companies, default_company_id }`; 401
- [X] T017 [US1] Crear página frontend `frontend/src/app/login/page.tsx`: formulario de acceso con manejo de errores y navegación al contexto de empresa por defecto

**Checkpoint**: User Story 1 completa — autenticación y primer contexto de empresa. MVP parcial.

---

## Phase 4: User Story 2 — Cambiar de empresa activa sin cerrar sesión (Priority: P1)

**Goal**: El usuario cambia de empresa desde el selector del Navbar; la sesión se actualiza y todas las operaciones pasan a ejecutarse bajo la nueva empresa.

**Independent Test**: Seleccionando otra empresa con acceso se actualiza la sesión y los listados de cuentas/asientos devuelven exclusivamente los datos de la nueva empresa; sin acceso → 403.

### Tests for User Story 2

- [X] T018 [P] [US2] Test switch correcto: `backend/tests/unit/test_switch_company.py` — conmutar a empresa relacional y activa → 200; las consultas posteriores usan el nuevo contexto (FR-004)
- [X] T019 [P] [US2] Test switch sin acceso: `backend/tests/integration/test_switch_company_aislamiento.py` — conmutar a empresa sin relación → 403 y la empresa activa permanece sin cambios; empresa inactiva → 403 (FR-008)

### Implementation for User Story 2

- [X] T020 [US2] Implementar servicio `switch_company()` y endpoint POST `/api/v1/auth/switch-company` en `backend/src/services/auth/session.py` y `backend/src/api/auth/auth.py`: revalidar relación activa, devolver contexto nuevo, auditar SWITCH_COMPANY
- [X] T021 [US2] Crear componente frontend `frontend/src/components/rbac/CompanySwitch.tsx`: selector de empresa en el Navbar (lista solo de empresas accesibles), actualiza el estado global de empresa y reenvía la cabecera `X-Empresa-Activa` en todas las peticiones
- [X] T022 [US2] Actualizar `frontend/src/services/client.ts`: cliente HTTP que adjunta automáticamente el JWT y la cabecera `X-Empresa-Activa`; sincroniza con el cambio de empresa (SC-003 sin arrastre de estado anterior)

**Checkpoint**: User Stories 1 y 2 completas — conmutación fluida de empresa sin fugas.

---

## Phase 5: User Story 3 — Trabajar solo dentro de las empresas autorizadas (Priority: P1)

**Goal**: Cualquier operación sobre datos exige relación activa del usuario con la empresa; si no, HTTP 403 sin exponer información.

**Independent Test**: Enviando una petición con una empresa no autorizada se obtiene un rechazo y ningún dato de esa empresa.

### Tests for User Story 3

- [X] T023 [P] [US3] Test 403 cross-empresa cuentas/asientos: `backend/tests/integration/test_403_datos_cross_empresa.py` — operar en cuentas (SPEC-001) y asientos (SPEC-002) con empresa no autorizada → 403/404 sin filtrar datos (FR-003/FR-010)
- [X] T024 [P] [US3] Test 403 contexto ausente o malformado: `backend/tests/integration/test_403_contexto.py` — sin cabecera empresa → 403; proyecto `company_id` inexistente → 403 (sin distinguir "no existe" de "sin permiso"); usuario/empresa inactivos → 403 (FR-008)

### Implementation for User Story 3

- [X] T025 [US3] Aplicar guards en SI routers de datos: `backend/src/api/deps.py` (aplicar `get_empresa_id` + `require_write` en cuentas/asientos/informes para esta feature) y validar con los endpoints de SPEC-001/002 ya registrados
- [X] T026 [US3] Tests end-to-end de aislamiento: `backend/tests/integration/test_aislamiento_end_to_end.py` — usuario B contra recursos de A (árbol, suggest, alta, asiento, diario, anulación) → 404/403 en el 100 % de los casos (SC-001)

**Checkpoint**: User Stories 1, 2 y 3 completas — plataforma multiempresa con aislamiento garantizado y 403 sin fugas. Base desplegable.

---

## Phase 6: User Story 4 — Crear una nueva empresa (Priority: P2)

**Goal**: Un usuario con capacidad de administración crea una empresa con NIF y razón social; queda ADMIN y se inicializa la plantilla base del PGC.

**Independent Test**: Creando una empresa, el creador queda con rol ADMIN y aparece en su lista de empresas; sus cuentas parten de la plantilla base.

### Tests for User Story 4

- [X] T027 [P] [US4] Test creación y seed: `backend/tests/integration/test_crear_empresa_seed.py` — crear empresa → role ADMIN, empresa en la lista, PGC base sembrado (≥ 7 grupos) (FR-007/SC-005)
- [X] T028 [P] [US4] Test atomicidad seed: `backend/tests/integration/test_crear_empresa_atomicidad.py` — forzar fallo de seed → la empresa no persiste (transacción revertida completa)

### Implementation for User Story 4

- [X] T029 [US4] Implementar servicio `crear_empresa()` en `backend/src/services/auth/company_service.py`: insertar `companies` + `user_companies(ADMIN, is_default=true)` + invocar seed del PGC (SPEC-001) todo en `async with async_session.begin()`; auditar CREATE_COMPANY en la misma transacción
- [X] T030 [US4] Implementar endpoint POST `/api/v1/companies` en `backend/src/api/companies.py`: 201 con `{ company_id, nif, razon_social, role: "ADMIN", default_company_id }`; 422 por validación de cuerpo
- [X] T031 [US4] Crear página frontend `frontend/src/app/empresas/nueva/page.tsx`: formulario NIF + razón social, navegación a la nueva empresa tras el alta

**Checkpoint**: User Stories 1, 2, 3 y 4 completas — ciclo de vida multiempresa completo.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T032 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_rbac.py` — ningún recurso accesible sin `X-Empresa-Activa` válida; READ_ONLY jamás escribe; matríz de roles coherente
- [X] T033 [P] Hardening multi-tenant: `backend/tests/integration/test_rbac_full_tenant_isolation.py` — escenario de dos empresas completas (cuentas+asientos) con cruces múltiples → todos 403/404; verificar ausencia de fuga en respuestas
- [X] T034 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_rbac.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T035 [P] Code review: verificar que `empresa_id` se deriva solo de la sesión; ningún endpoint expone `empresa_id` del body; hashes con bcrypt/argon2; `audit_log` en la misma transacción; `async with async_session.begin()` en todos los servicios
- [X] T036 Limpieza y documentación: actualizar docstrings en servicios auth/iam, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1 (guards listos en Phase 2).
- **US3 (Phase 5)**: Depende de Phase 2; puede empezar en paralelo con US1/US2, pero sus pruebas end-to-end requieren endpoints de SPEC-001/002 (se pueden probar con stubs o tras esas features).
- **US4 (Phase 6)**: Depende de Phase 2 y del seed del PGC (SPEC-001), invocado por trigger o por servicio.
- **Polish (Phase 7)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1/MVP)**: Sin dependencias de US1; usa Phase 2 completa (reusa guards).
- **US3 (P1/MVP)**: Sin dependencias de US1/US2; usa Phase 2 completa; las pruebas de datos reales integran con SPEC-001/002.
- **US4 (P2)**: Sin dependencias de US1-US3; usa Phase 2 completa y SPEC-001 (seed).

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos/migración/security [P] en paralelo (T005-T011).
- Phase 3: tests [P] en paralelo (T013-T014).
- Phase 4: tests [P] en paralelo (T018-T019).
- Phase 5: tests [P] en paralelo (T023-T024).
- Phase 6: tests [P] en paralelo (T027-T028).
- US1, US2, US3, US4 pueden iniciarse en paralelo una vez completada Phase 2.

---

## Parallel Example: User Story 2

```bash
# Tests en paralelo:
Task T018: "Test switch correcto en backend/tests/unit/test_switch_company.py"
Task T019: "Test switch sin acceso en backend/tests/integration/test_switch_company_aislamiento.py"

# Servicio y frontend en paralelo (archivos distintos):
Task T020: "session.py/auth.py (switch_company + endpoint)"
Task T021: "CompanySwitch.tsx (selector de empresa del navbar)"
```

---

## Implementation Strategy

### MVP First (User Story 1, 2 y 3)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo; guards + modelos).
3. Completar Phase 3: User Story 1 (login).
4. Completar Phase 4: User Story 2 (switch).
5. Completar Phase 5: User Story 3 (guards 403 en datos).
6. **PARAR y VALIDAR**: Ejecutar T013-T026. Verificar quickstart Scenarios 1, 3, 4, 6.
7. Desplegar/demo si listo (multiempresa con aislamiento ya funcional para SPEC-001/002).

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (login mínimo).
3. + US2 → Test independiente → Deploy/Demo (conmutación de empresa).
4. + US3 → Test independiente → Deploy/Demo (bloqueo 403 en datos — base de aislamiento).
5. + US4 → Test independiente → Deploy/Demo (alta de empresas con seed PGC).
6. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos (guards y modelos son críticos).
2. Una vez Foundational lista:
   - Dev A: User Story 1 (login) y User Story 4 (crear empresa).
   - Dev B: User Story 2 (switch).
   - Dev C: User Story 3 (guards y 403 en datos).
3. Cada story se integra y prueba independientemente.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Los guards de `backend/src/api/deps.py` (get_empresa_id/require_role) son consumidos por SPEC-001, SPEC-002 y SPEC-004; su estabilidad es crítica para el aislamiento.
- La empresa activa viaja en la cabecera `X-Empresa-Activa`; nunca en path/body.
- La tabla `companies` define el `company_id` que referencia `account_plan.tenant_id` (SPEC-001).
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de aislamiento multi-tenant + acceso no autorizado (403).

## Estado real (auditoría 2026-09-17)

Código creado como soporte de SPEC-020; las tareas siguen **sin marcar `[X]`** porque sus pruebas de la Constitución V están pendientes.

- **Implementado**: T001 (estructura `iam`/`auth`), T002/T004 (`api/deps.py`: `get_current_user`, `get_empresa_id`, `require_role`), modelos `Company`/`User`/`UserCompany`, `004_iam.sql`, `POST /auth/login` y `GET /auth/me`, `GET /companies`.
- **Pendiente**: US2 cambio de empresa (frontend), US4 alta de empresa, página de login, tests de la feature.
