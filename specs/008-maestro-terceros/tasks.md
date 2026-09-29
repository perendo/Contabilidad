# Tasks: Maestro de Terceros (Clientes y Proveedores) (SPEC-008)

**Input**: Design documents from `/specs/008-maestro-terceros/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

**Nota**: Esta spec incluye la ampliación T-08/FR-009 (IBAN/banco y condiciones de pronto pago) que alimentan a SPEC-020.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo `thirdparty`/`ar` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo: `backend/src/models/ar/__init__.py`, `backend/src/models/ar/tercero.py`, `backend/src/models/ar/tercero_subcuenta.py`, `backend/src/models/ar/condicion_pronto_pago.py`, `backend/src/services/thirdparty/__init__.py`
- [X] T002 [P] Crear estructura de servicios: `backend/src/services/thirdparty/validacion_nif.py`, `backend/src/services/thirdparty/alta.py`, `backend/src/services/thirdparty/saldo.py`, `backend/src/services/thirdparty/retirada.py`, `backend/src/services/thirdparty/bancos.py`, `backend/src/services/thirdparty/condiciones_pronto_pago.py`, `backend/src/services/thirdparty/subcuentas.py`
- [X] T003 [P] Crear router API: `backend/src/api/thirdparty.py` con prefijo `/api/v1/terceros`, dependency de sesión autenticada `empresa_id`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/thirdparty/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant
- [X] T005 [P] Crear estructura frontend: `frontend/src/app/terceros/`, `frontend/src/app/terceros/[id]/`, `frontend/src/app/terceros/[id]/condiciones/`, `frontend/src/components/thirdparty/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos base y validaciones que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T006 [P] Crear modelo `Tercero` en `backend/src/models/ar/tercero.py`: empresa_id (PK), nif VARCHAR(9) UNIQUE por empresa, razon_social, es_cliente BOOLEAN, es_proveedor BOOLEAN, direcciones JSONB, telefono, correo, iban VARCHAR(34) NULL, banco, autofactura BOOLEAN DEFAULT FALSE, activo BOOLEAN DEFAULT TRUE, created_at/updated_at; constraint al menos uno de es_cliente/es_proveedor es TRUE
- [X] T007 [P] Crear modelo `TerceroSubcuenta` en `backend/src/models/ar/tercero_subcuenta.py`: empresa_id, tercero_id FK, tipo ENUM (CLIENTE/PROVEEDOR), cuenta_codigo VARCHAR(20) FK SPEC-001, fecha_asignacion; constraint único (empresa_id, tercero_id, tipo)
- [X] T008 [P] Crear modelo `CondicionProntoPago` en `backend/src/models/ar/condicion_pronto_pago.py`: empresa_id, tercero_id FK, plazo_dias INT CHECK > 0, porcentaje NUMERIC(5,2) CHECK 0 < % <= 100, vigente BOOLEAN, override_factura_id UUID NULL; constraint único (empresa_id, tercero_id, vigente=true) cuando vigente=TRUE
- [X] T009 [P] Implementar validación de NIF/CIF en `backend/src/services/thirdparty/validacion_nif.py`: función `validar_nif(nif: str) -> bool` con algoritmo español (letra control personas físicas, CIF jurídicas, NIE letras iniciales); función `normalizar_nif(nif: str) -> str` (normaliza a mayúsculas, elimina espacios)
- [X] T010 [P] Implementar validación de IBAN en `backend/src/services/thirdparty/bancos.py`: función `validar_iban(iban: str) -> bool` con MÓDULO 97 ISO 13616 (reordenación + comprobación)
- [X] T011 [P] Tests de validación NIF: `backend/tests/unit/test_validacion_nif.py` — NIF personas físicas válido e inválido, CIF válido e inválido, NIE válido, normalización de formato
- [X] T012 [P] Tests de validación IBAN: `backend/tests/unit/test_validacion_iban.py` — IBAN español válido (ES9121000418450200051332), IBAN inválido, IBAN de otro país
- [X] T013 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_tercero_tenant_isolation.py` — crear tercero en empresa A, verificar que empresa B no lo ve

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Alta y gestión de terceros (Priority: P1) ?? MVP

**Goal**: El usuario da de alta clientes y proveedores con NIF, razón social, direcciones, IBAN/banco; el sistema valida NIF, crea la ficha y asigna subcuentas 430/410 automáticamente.

**Independent Test**: Alta de un tercero crea su ficha y sus subcuentas por empresa; el NIF se valida contra duplicados.

### Tests for User Story 1

- [X] T014 [P] [US1] Test alta completa: `backend/tests/unit/test_alta_tercero.py` — crear tercero cliente+proveedor, verificar que las 2 subcuentas (430 y 410) se crean automáticamente, verificar NIF normalizado
- [X] T015 [P] [US1] Test unicidad NIF por empresa: `backend/tests/unit/test_nif_unicidad.py` — mismo NIF en la misma empresa → 409; mismo NIF en otra empresa → 201 (fichas aisladas)
- [X] T016 [P] [US1] Test NIF inválido: `backend/tests/unit/test_nif_invalido.py` — NIF mal formado → 422; verificar que no se crea ni la ficha ni las subcuentas
- [X] T017 [P] [US1] Test IBAN: `backend/tests/unit/test_iban_tercero.py` — IBAN válido se guarda; IBAN inválido → 422; sin IBAN se permite
- [X] T018 [P] [US1] Test subcuentas en el plan correcto: `backend/tests/unit/test_subcuentas_plan.py` — verificar que la subcuenta asignada está en el plan de cuentas de la empresa activa y es de clase 4

### Implementation for User Story 1

- [X] T019 [US1] Implementar servicio `crear_tercero` en `backend/src/services/thirdparty/alta.py`: validar NIF (formato + unicidad), validar IBAN si está presente (MÓDULO 97), crear `Tercero` en `async with async_session.begin()`, llamar a `asignar_subcuentas` para crear `TerceroSubcuenta` automática, registrar audit log en la misma transacción
- [X] T020 [US1] Implementar servicio `asignar_subcuentas` en `backend/src/services/thirdparty/subcuentas.py`: generar código de subcuenta secuencial bajo 430 (cliente) y 410 (proveedor) en el plan de cuentas de la empresa activa; crear `TerceroSubcuenta` por cada rol activo
- [X] T021 [US1] Implementar endpoints en `backend/src/api/thirdparty.py`: POST crear tercero (201), GET listar (paginación), GET detalle (con subcuentas e IBAN)
- [X] T022 [US1] Crear página frontend `frontend/src/app/terceros/nuevo/page.tsx`: formulario de alta con campos NIF, razón social, roles, direcciones, IBAN/banco
- [X] T023 [US1] Crear listado frontend `frontend/src/app/terceros/page.tsx`: tabla paginada de terceros con filtros (rol, activo, búsqueda por NIF/razón social)
- [X] T024 [US1] Crear página frontend `frontend/src/app/terceros/[id]/page.tsx`: ficha del tercero con datos, IBAN, subcuentas y saldo pendiente
- [X] T025 [US1] Tests integración alta completa: `backend/tests/integration/test_alta_tercero_completa.py` — crear tercero vía endpoint, verificar ficha, subcuentas, NIF e IBAN validados, auditoría registrada
- [X] T026 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_alta_tercero_tenant.py` — empresa A crea tercero, empresa B no lo ve (mismo NIF → fichas separadas)

**Checkpoint**: User Story 1 completa — alta de terceros funcional. MVP desplegable.

---

## Phase 4: User Story 2 — Consultar histórico y saldo de un tercero (Priority: P2)

**Goal**: El usuario consulta la ficha del tercero con su histórico de facturas, cobros/pagos, movimientos de asiento y saldo pendiente, todo derivado de la empresa activa.

**Independent Test**: Consultando un tercero se obtienen sus movimientos y saldo de la empresa activa, nunca los de otra empresa.

### Tests for User Story 2

- [X] T027 [P] [US2] Test saldo derivado: `backend/tests/unit/test_saldo_derivado.py` — crear vencimientos y facturas para un tercero, consultar saldo, verificar que es la suma exacta (Decimal) de vencimientos no liquidados
- [X] T028 [P] [US2] Test histórico solo empresa activa: `backend/tests/unit/test_historico_aislamiento.py` — crear movimientos en empresa A y B para mismo NIF, consultar desde A → solo movimientos de A

### Implementation for User Story 2

- [X] T029 [P] [US2] Implementar servicio `consultar_saldo` en `backend/src/services/thirdparty/saldo.py`: función que dado tercero_id + empresa_id, agrega: (a) facturas emitidas (SPEC-007) del tercero, (b) journal_lines de la subcuenta (SPEC-002), (c) vencimientos (SPEC-011) del tercero; devuelve saldo_pendiente en `Decimal` y desglose de movimientos
- [X] T030 [US2] Implementar endpoint GET `/api/v1/terceros/{id}` con saldo en `backend/src/api/thirdparty.py`: consultar tercero, llamar a `consultar_saldo`, devolver 200 con ficha completa + saldo + histórico (facturas, movimientos, vencimientos)
- [X] T031 [US2] Tests integración ficha completa: `backend/tests/integration/test_ficha_tercero.py` — crear tercero, facturas y vencimientos, consultar ficha, verificar saldo_pendiente exacto
- [X] T032 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_saldo_tenant.py` — empresa A consulta tercero, empresa B no ve los movimientos de A ni afecta el saldo

**Checkpoint**: User Stories 1 y 2 completas — alta y consulta de terceros funcional.

---

## Phase 5: User Story 3 — Baja y retirada de terceros (Priority: P2)

**Goal**: El usuario retira un tercero; si tiene movimientos, solo permite inactivar (no borrar). Si no tiene movimientos, permite borrado físico.

**Independent Test**: Retirando un tercero sin movimientos se inactiva; con movimientos se bloquea la baja definitiva.

### Tests for User Story 3

- [X] T033 [P] [US3] Test protección baja con movimientos: `backend/tests/unit/test_baja_protegida.py` — tercero con facturas/asientos → DELETE devuelve 409 con mensaje "solo se puede inactivar"
- [X] T034 [P] [US3] Test inactivación conserva historial: `backend/tests/unit/test_inactivacion_historial.py` — inactivar tercero → activo=FALSE, facturas y asientos siguen existiendo
- [X] T035 [P] [US3] Test borrado sin movimientos: `backend/tests/unit/test_borrado_sin_movimientos.py` — tercero sin facturas/asientos/vencimientos → DELETE 204, tercero eliminado físicamente

### Implementation for User Story 3

- [X] T036 [P] [US3] Implementar servicio `verificar_movimientos` en `backend/src/services/thirdparty/retirada.py`: función que dado tercero_id + empresa_id, consulta si tiene facturas (SPEC-007), journal_lines (SPEC-002) o vencimientos (SPEC-011); devuelve `tiene_movimientos: bool` y motivo
- [X] T037 [US3] Implementar servicio `retirar_tercero` en `backend/src/services/thirdparty/retirada.py`: si no tiene movimientos → borrado físico (DELETE); si tiene → cambiar `activo = FALSE` (inactivación); en ambos casos, audit log
- [X] T038 [US3] Implementar endpoint POST `/api/v1/terceros/{id}/retirar` y DELETE `/api/v1/terceros/{id}` en `backend/src/api/thirdparty.py`: POST = inactivación; DELETE = borrado físico (solo sin movimientos → 204; con movimientos → 409)
- [X] T039 [US3] Tests integración retirada completa: `backend/tests/integration/test_retirada_completa.py` — crear tercero sin movimientos → DELETE OK; crear con movimientos → DELETE 409, POST retirar → activo=FALSE
- [X] T040 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_retirada_tenant.py` — empresa A retira tercero, empresa B no lo ve

**Checkpoint**: User Stories 1, 2 y 3 completas — flujo completo de maestro funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación, condiciones de pronto pago y robustez.

- [X] T041 [P] Implementar CRUD de `CondicionProntoPago` en `backend/src/services/thirdparty/condiciones_pronto_pago.py`: POST crear (vigente única por tercero), GET listar, PATCH desactivar; validate porcentaje y plazo_dias
- [X] T042 [P] Implementar endpoints de condiciones en `backend/src/api/thirdparty.py`: POST `/{id}/condiciones` (201), GET `/{id}/condiciones` (200), PATCH `/{id}/condiciones/{cond_id}` (200); 409 si ya existe vigente al crear
- [X] T043 [P] Tests condiciones pronto pago: `backend/tests/unit/test_condiciones_pronto_pago.py` — crear vigente, segunda activa → 409, listar, desactivar
- [X] T044 [P] Implementar validación de cambio de NIF con movimientos: `backend/src/services/thirdparty/validacion_nif.py` — función `validar_cambio_nif(tercero_id, nif_nuevo, empresa_id, permiso_admin)` → requiere permiso_admin=TRUE si tiene movimientos; audit log del cambio con payload NIF anterior/nuevo
- [X] T045 [P] Implementar endpoint PATCH `/api/v1/terceros/{id}/nif` en `backend/src/api/thirdparty.py`: recibir nif_nuevo + justificacion + permiso_admin, validar, cambiar, audit log; 409 si sin permiso y con movimientos
- [X] T046 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_terceros.py` — verificar que toda tabla tiene empresa_id; verificar que no se borran asientos al inactivar tercero; verificar aislamiento empresa_id
- [X] T047 [P] Hardening multi-tenant: `backend/tests/integration/test_terceros_full_tenant_isolation.py` — escenario completo cross-empresa (A alta, B consulta → 404, B intenta borrar → 404)
- [X] T048 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_terceros.py` — reproducir los 7 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T049 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC en importes; verificar que el IBAN no se expone en listados sin autenticación
- [X] T050 Limpieza y documentación: actualizar docstrings en servicios thirdparty, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 3 (necesita terceros creados con movimientos para saldo).
- **US3 (Phase 5)**: Depende de Phase 3 (necesita terceros para retirar).
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Depende de US1 (necesita terceros con subcuentas para saldo derivado).
- **US3 (P2)**: Depende de US1 (necesita terceros para retirar).

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1 y 2: todos los [P] en paralelo.
- Phase 3: tests [P] en paralelo (T014-T018).
- Phase 5: tests [P] en paralelo (T033-T035), servicio [P] (T036).
- US2 y US3 pueden ejecutarse en paralelo una vez completada US1.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T014: "Test alta completa en backend/tests/unit/test_alta_tercero.py"
Task T015: "Test unicidad NIF en backend/tests/unit/test_nif_unicidad.py"
Task T016: "Test NIF inválido en backend/tests/unit/test_nif_invalido.py"
Task T017: "Test IBAN en backend/tests/unit/test_iban_tercero.py"
Task T018: "Test subcuentas en backend/tests/unit/test_subcuentas_plan.py"

# Implementación secuencial:
Task T019: "Servicio crear_tercero en backend/src/services/thirdparty/alta.py"
Task T020: "Servicio asignar_subcuentas en backend/src/services/thirdparty/subcuentas.py"
Task T021: "Endpoints en backend/src/api/thirdparty.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T014-T026. Verificar quickstart Scenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP! alta con subcuentas automáticas).
3. + US2 → Test independiente → Deploy/Demo (historial y saldo).
4. + US3 → Test independiente → Deploy/Demo (retirada protegida).
5. + Polish (condiciones pronto pago + QUICKSTART) → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (alta + NIF + IBAN + subcuentas).
   - Dev B: Condiciones pronto pago (Phase 6 adelantada, sin dependencias de US2/US3).
3. Dev A completa US1; Dev B completa condiciones pronto pago.
4. Dev A: User Story 2 + US3 (historial/retirada, pueden ser paralelas internamente).
5. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.
- Dependencias externas: SPEC-001 (plan de cuentas con cuentas 430/431/410/411), SPEC-002 (asientos), SPEC-003/015 (permisos de administrador), SPEC-007 (facturas), SPEC-011 (vencimientos), SPEC-020 (remesas SEPA consumen IBAN y condiciones de pronto pago).
- La ampliación T-08/FR-009 (IBAN/banco + condiciones pronto pago) está integrada en US1 y Polish; su consumo se verifica en SPEC-020.

## Estado real (auditoría 2026-09-17)

- **Implementado**: scaffold mínimo `backend/src/models/ar/tercero.py` (campos usados por SPEC-020).
- **Pendiente**: resto de la feature (CRUD de terceros, IBAN, validaciones fiscales, endpoints, tests).

## Estado real (implementación 2026-09-19, 50/50)

Desviaciones documentadas:
- **T006**: `Tercero.nombre` es la razón social (no se renombra para no romper SPEC-020); `iban` pasa a NULLable (opcional, excluido de remesas SEPA). Campos `es_cliente/es_proveedor/direcciones/telefono/correo/banco/autofactura/activo/updated_at` añadidos.
- **T007**: `TerceroSubcuenta` en `models/ar/tercero_subcuenta.py`; subcuentas nivel 4 (`430N`/`410N`) creadas en `AccountPlan` (el seed ocupa `4300`, el primer tercero usa `4301`).
- **T008/T041-T043**: `CondicionProntoPago` y su CRUD viven en `models/treasury/` + `services/tercero_amend.py` (SPEC-020); se reutilizan. Al crear una vigente se **desactiva la anterior** (no 409, desviación vs quickstart).
- **T038**: `POST /retirar` = inactivación (sin body); `DELETE` = borrado físico (204/409). El body `{"eliminar"}` del quickstart no se implementa.
- **T045**: `PATCH /terceros/{id}/nif` con `permiso_admin`; 409 si tiene movimientos sin permiso.
- Puertas: 38 tests nuevos en verde (498 suite), ruff + mypy limpios, `next build` con `/terceros`, `/terceros/nuevo`, `/terceros/[id]`.


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

- `tercero`
- `tercero_subcuenta`

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
