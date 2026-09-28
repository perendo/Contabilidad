# AGENTS.md — Guía para agentes de IA (ContabilidadV1)

Guía de contexto para agentes que trabajan en este repositorio. Léela al inicio de
cada sesión; el estado completo se persiste en `specs/*/` y `.specify/memory/`.

## 1. Estado del proyecto

- **Fase**: nucleo contable completo. **30 specs terminadas** (001-030) con
  **1.432/1.432 tareas marcadas** y las puertas verificadas (pytest, ruff, mypy,
  PostgreSQL y `next build`).
- **30 feature specs** con artefactos completos (`specs/*/`), cada una con `spec.md`,
  `research.md`, `data-model.md`, `quickstart.md`, `plan.md`, `tasks.md` y `contracts/`.
- **Pendientes**: ninguna spec disenada sin implementar.
- La ultima feature cerrada del Spec Kit es `specs/030-documentos-asiento`.
- **Ultima spec cerrada**: `specs/030-documentos-asiento` (documentos adjuntos al
  asiento), 48/48 tareas el 2026-09-27. Ver seccion 45.

- Artefactos de todas las specs verificados/consolidados el 2026-09-16 (remediaciones
  R1–R4 aplicadas y verificadas: endpoints `/api/v1`, trazabilidad FR↔US, sección
  Dependencias, terminología multitenancy).
- **Ultima sesion (2026-09-27)**: cerrada **SPEC-029 Exportacion integral del tenant
  y enlace SII** (52/52, 29a spec); **2.503 passed / 19 skipped** en SQLite y
  **2.521 passed / 1 skipped** sobre **PostgreSQL 18.6 real** con las migraciones
  000-020; 245 pruebas nuevas, **16 passed** en el contrato de esquema, ruff + mypy
  limpios (393 fuentes) y `next build` con **103 rutas** (3 nuevas). El unico fallo de
  la corrida SQLite fue `test_suggest_perf` (flaky conocido bajo carga de SPEC-001),
  **2 passed** aislado. Detalle en SS43.
- **Ultima sesion (2026-09-26, cont.)**: cerrada **SPEC-028 Cierre intermedio y
  reapertura controlada** (57/57, 28ª spec); **2280 passed / 13 skipped** en SQLite y
  **2293 passed / 0 skipped** sobre **PostgreSQL 18.6 real** con las migraciones
  000–019; 276 pruebas nuevas, **11 passed** en el contrato de esquema, ruff + mypy
  limpios (377 fuentes) y `next build` con **100 rutas** (5 nuevas). La única falla de
  la corrida fue `test_suggest_perf` (flaky conocido bajo carga de SPEC-001),
  **2 passed** aislado. Detalle en §42.
- **Última sesión (2026-09-26, cont.)**: cerrada **SPEC-027 Previsión de tesorería**
  (45/45, 27ª spec); **1951 passed / 11 skipped**, con las 2 pruebas
  `test_suggest_perf` verdes aisladas; 300 pruebas nuevas, PostgreSQL 18.6 real
  **9 passed** para migración/triggers 018, ruff + mypy limpios (363 fuentes) y
  `next build` con **95 rutas** (4 nuevas). La corrida completa sobre **PostgreSQL 18.6 real** da **1962 passed / 0 skipped**. Detalle en §41.
- **Última sesión (2026-09-26, cont.)**: cerrada **SPEC-026 Presupuestos y desviaciones**
  (42/42, 26ª spec); **1651 passed / 9 skipped**, con las 2 pruebas `test_suggest_perf`
  verdes aisladas; 164 pruebas nuevas, PostgreSQL 16 real **7 passed** para
  migración/triggers 017, ruff + mypy limpios (350 fuentes) y `next build` con
  **92 rutas** (3 nuevas). Detalle en §40.
- **Última sesión (2026-09-26)**: cerrada **SPEC-025 Catálogo versionado del plan de
  cuentas** (47/47, 25ª spec); **1497 passed / 8 skipped**, con las 2 pruebas
  `test_suggest_perf` verdes aisladas; 88 pruebas nuevas, PostgreSQL 16 real
  **6 passed** para migración/triggers 016, ruff + mypy limpios (337 fuentes) y
  `next build` con **89 rutas** (4 nuevas). Detalle en §39.
- **Última sesión (2026-09-25)**: cerrada **SPEC-024 Retenciones IRPF / Modelos
  111/115/190** (48/48, 24ª spec); **1410 passed / 7 skipped**, con las 2 pruebas
  `test_suggest_perf` verdes aisladas; 56 pruebas nuevas, PostgreSQL 16 real **5 passed**
  para migración/triggers 015, ruff + mypy limpios (324 fuentes) y `next build` con
  **85 rutas** (4 nuevas). Detalle en §38.
- **Última sesión (2026-09-24, anterior)**: cerrada **SPEC-023 Impuesto sobre Sociedades / Modelo 200**
  (44/44, 23ª spec); suite completa **1354 passed / 5 skipped** con `test_suggest_perf`
  flaky bajo carga y **2 passed** aislado; 49 pruebas nuevas, PostgreSQL 16 real
  **4 passed** para migración/triggers 014, ruff + mypy limpios (312 fuentes) y
  `next build` con **80 rutas** (4 nuevas). Detalle en §37.
- **Última sesión (2026-09-24, anterior)**: cerrada **SPEC-022 Anticipos, fondos a cuenta y cesión
  de cobros** (48/48, 22ª spec); pytest **1304 passed / 5 skipped** (SQLite;
  `test_suggest_perf` flaky bajo carga, verde aislado), ruff + mypy limpios (303 fuentes),
  `next build` **78 rutas** (6 nuevas). Migración `013_anticipos.sql`. Detalle en §36.
- **Última sesión (2026-09-23, cont.)**: cerrada **SPEC-021 Medios de pago y efectos**
  (44/44, 21ª spec); pytest **1261 passed / 5 skipped** (SQLite; `test_suggest_perf`
  flaky bajo carga, verde aislado), ruff + mypy limpios (294 fuentes), `next build`
  **72 rutas** (6 nuevas: `/efectos`, `/efectos/nuevo`, `/efectos/[id]`, `/tesoreria`,
  `/tesoreria/cobros`). Migración `012_efectos.sql` + triggers
  `trg_efecto_final_immutable_update/_delete` (estados finales inmutables). Detalle en §35.
- **Última sesión (2026-09-23)**: cerrada **SPEC-019 Gestión ONG (subvenciones, libros
  oficiales y caja)** (53/53, 20ª spec); pytest **1171 passed / 5 skipped** (SQLite;
  `test_suggest_perf` flaky bajo carga, verde aislado), ruff + mypy limpios (285 fuentes),
  `next build` **66 rutas** (5 nuevas, `/ong/subvenciones`, `/ong/subvenciones/[id]`,
  `/ong/libros`, `/ong/caja`, `/ong/caja/[id]`). Migración `011_ngo.sql` + trigger
  `trg_journal_entry_legalizado_insert` (FR-007 a nivel DB). Detalle en §34.
- **Última sesión (2026-09-22, cont.)**: cerrada **SPEC-017 Centros de coste** (48/48, 18ª spec);
  pytest **1055 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky bajo carga,
  verde aislado), ruff + mypy limpios (251 fuentes), `next build` **57 rutas** (3 nuevas).
  Detalle en §32.
- **Última sesión (2026-09-22, cont.)**: cerrada **SPEC-018 Plantillas de asientos** (42/42, 19ª spec);
  pytest **1109 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky bajo carga,
  verde aislado), ruff + mypy limpios (263 fuentes), `next build` **61 rutas** (4 nuevas,
  `/plantillas`). Migración `010_templates.sql` verificada sobre PostgreSQL 16.4 real.
  Detalle en §33.
- **Última sesión (2026-09-22)**: cerrada **SPEC-016 Multi-divisa** (48/48, 17ª spec);
  pytest **965 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky bajo carga,
  verde aislado), ruff + mypy limpios (236 fuentes), `next build` **54 rutas** (5 nuevas).
  Detalle en §31.
- **Última sesión (2026-09-19)**: cerradas SPEC-001, 002, 003, 004, 005, 008, 011, 013 y
  020; verificadas sobre PostgreSQL 16.4 real (**571 passed, 0 skipped**). Detalle en §22
  y §23.
- **Última sesión (2026-09-20)**: cerradas **SPEC-009 Apertura del ejercicio** (37/37) y
  **SPEC-006 Asientos multilínea** (40/40); verificadas sobre PostgreSQL 16.4 real
  (**603 → 649 passed, 0 skipped**, migraciones 000–006). Detalle en §24 y §25.
- **Última sesión (2026-09-20, cont.)**: cerrada **SPEC-007 Facturación operativa** (56/56,
  12ª spec); pytest **696 passed / 5 skipped** (SQLite), ruff + mypy limpios (152 fuentes),
  `next build` **36 rutas**. Detalle en §26.
- **Última sesión (2026-09-20, cont.)**: cerrada **SPEC-010 Cuentas anuales** (45/45, 13ª spec);
  pytest **738 passed / 5 skipped** (SQLite) y **743 passed / 0 skipped** (PostgreSQL 16.4 real),
  ruff + mypy limpios (167 fuentes), `next build` **40 rutas**. Detalle en §27.
- **Última sesión (2026-09-20, cont.)**: cerrada **SPEC-012 Libros de IVA y modelos fiscales**
  (56/56, 14ª spec); pytest **771 passed / 5 skipped** (SQLite) y **776 passed / 0 skipped**
  (PostgreSQL 16.4 real), ruff + mypy limpios (191 fuentes), `next build` **43 rutas**.
  Detalle en §28.
- **Última sesión (2026-09-21)**: cerrada **SPEC-015 Matriz de permisos por rol**
  (48/48, 16ª spec); pytest **890 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky
  bajo carga, verde aislado), ruff + mypy limpios (219 fuentes), `next build` **49 rutas**.
  Detalle en §30.

## 2. Documentos que condicionan todo

| Documento | Rol |
|---|---|
| `.specify/memory/constitution.md` | **NO NEGOCIABLE**. Cuenta con principios I–V, stack, criterios de aceptación y gobernanza (versión fija 1.0.0). Cualquier código/spec en conflicto queda sin efecto. |
| `plan.md` (raíz) | Plan técnico autoritativo de SPEC-001 (PGC). Fuente de la convención de endpoints `/api/v1`. Usa `tenant_id`. |
| `specs/*/plan.md` | Plan por feature (29 restantes). Usan `empresa_id`. |
| `specs/*/tasks.md` | Lista de tareas `T###` por fase/US con trazabilidad FR. |

## 3. Reglas de la constitución (resumen operativo)

- **I · Partida doble estricta**: `SUM(Debe) == SUM(Haber)` siempre. Validación en backend en el punto más cercano a la persistencia, NUNCA solo en UI.
- **II · Inmutabilidad**: los `POSTED` son inmutables (no UPDATE/DELETE, ni API ni DB). Corrección → `REVERSAL`/`ADJUSTMENT` enlazado. Auditoría inmutable (WORM) escrita en la misma transacción ACID (usuario, UTC, IP, operación, payload).
- **III · Multi-tenancy estricto**: toda consulta/mutación filtra por la empresa activa de sesión (nunca data del cliente); `empresa_id`/`tenant_id` en claves/índices/filtros. Verificar con tests de integración cross-empresa.
- **IV · Correlatividad**: numeración sin saltos por (empresa, ejercicio) con `SELECT ... FOR UPDATE` atómico.
- **V · Pruebas obligatorias (NON-NEGOTIABLE)**: ninguna tarea está finalizada sin pytest que verifique (a) balance estricto y (b) aislamiento multi-tenant. Además: typecheck + lint antes de declarar completa.
- **Regla fiscal**: `Decimal` en Python / `NUMERIC(18,4)` en PostgreSQL para importes. **PROHIBIDO `float`** para dinero.
- **Transacciones**: el boundary ACID está en `get_db` (`backend/src/database.py`) y su override en tests (`backend/tests/conftest.py`): commit al final de la petición y rollback ante excepción, equivalente a `async with async_session.begin()`. Los servicios reciben la sesión y hacen `flush()` dentro de ese boundary; cabecera+líneas indivisibles.
- **Timestamps**: UTC (`TIMESTAMPTZ`).

## 4. Stack

- **Backend**: Python 3.11+ · FastAPI (async) · SQLAlchemy 2.x async + asyncpg · Pydantic v2 · PostgreSQL 16+.
- **Frontend**: Next.js (App Router) + TypeScript.
- **Tests**: pytest, en `backend/tests/{unit,integration}` (PostgreSQL opt-in vía `TEST_DATABASE_URL`).
- **Estructura backend prevista**: `backend/src/models`, `backend/src/services`, `backend/src/api`, `frontend/src/app`.

## 5. Convenciones

- **Endpoints**: siempre `/api/v1/...`; la empresa activa se deriva de la sesión/cabecera autenticada, NUNCA del path/body. (`rg "/api/\{" specs` debe dar 0 coincidencias.)
- **Terminología**: `empresa_id` en las 30 specs funcionales; `tenant_id` solo en SPEC-001/`plan.md` raíz (alineado con él, no cambiar).
- **Tareas**: formato `- [ ] T### [P?] [USn] descripción... ruta de archivo`. `[P]` = ejecutable en paralelo (archivos distintos, sin dependencias). TDD: tests antes de implementación.
- **Orden por spec**: Setup → Foundational (bloqueante) → US1/US2/US3 (paralelas entre sí tras Foundational) → Polish.
- Sin comentarios en código salvo que se pidan; sin archivos de documentación salvo que se pidan; commits solo si el usuario lo pide explícitamente.

## 6. Trazabilidad necesaria

Cada spec tiene en su `tasks.md` una tabla **Trazabilidad FR ↔ User Story** y una sección **Dependencias** (deps cross-spec). Antes de implementar una spec, lee su sección Dependencias y respeta las specs de las que depende (p. ej. SPEC-002 motor de asientos es base de casi todas).

## 7. Comandos / scripts

- `.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireSpec -RequireTasks` — estado de la feature activa (usado por `/speckit.*`).
- `.specify/scripts/powershell/setup-plan.ps1` y `setup-tasks.ps1` — ligados a `feature.json` (feature activa = `specs/030-documentos-asiento`). **No hay `setup-analyze.ps1`**.

```powershell
# Validación (desde backend/)
..\.venv\Scripts\python.exe -m pytest                       # 2659 passed, 21 skipped; perf verde aislado
..\.venv\Scripts\python.exe -m ruff check src tests         # lint
..\.venv\Scripts\python.exe -m mypy -p api -p models -p services -p database -p base -p db -p main -p config   # typecheck (406 fuentes)
```

- mypy está configurado en `backend/mypy.ini` (`mypy_path = src`). Ejecutarlo siempre desde `backend/` con targets por módulo vía `-p` (`-p api -p models -p services -p database -p base -p db`) para evitar el duplicado `src.*` vs `*` (mypy >= 2.3 no resuelve nombres desnudos como módulos).
- Sobre Windows PowerShell 5.1: no usar `&&`; encadenar con `cmd1; if ($?) { cmd2 }`.
- Escribir siempre en UTF-8; al editar desde PowerShell usar `[System.IO.File]::ReadAllText`/`WriteAllText` con `UTF8Encoding($false)` para preservar acentos (evita mojibake/CJK).

## 8. Git / GitHub

- Repo aún **no inicializado** como git (no es repo git todavía). `.gitignore` ya existe (Python/Node/secrets). Si el usuario pide subirlo: `git init`, commit inicial y `gh repo create` / push a GitHub.
- Comprobar siempre `.env` y secretos: nunca commitear credenciales.

## 9. Notas de contexto para continuar

- La siguiente sesión puede arrancar leyendo solo `constitución.md` + `specs/001/spec.md` + `specs/001/tasks.md` (o el punto de inicio elegido); NO es necesario cargar el historial completo de conversación.
- Inicio de implementación recomendado: Phase 1 Setup y Phase 2 Foundational de specs base (001 Plan General Contable, 002 Motor de Asientos, 003 Multiempresa RBAC).
- Desglose de tareas por bloque (verificado): Setup 117 · Foundational 197 · US1 317 · US2 245 · US3 272 · US4 43 · Polish 187 · Convergence 6.

## 10. Implementación realizada (SPEC-020 · Phase 1 Setup)

Completadas **T001–T004** (`specs/020-remesas-sepa-cobros/tasks.md`):

- **T001** — estructura de paquetes del módulo treasury: `backend/src/models/treasury/__init__.py`, `backend/src/services/remittance/{__init__,sepa_dd,csb_1919,refund_r19}.py`, `backend/src/services/discount.py`, `backend/src/api/treasury/__init__.py` (+ `__init__.py` de los paquetes padre `models`, `services`, `api`).
- **T002** — `backend/src/api/treasury/routes.py`: router con `prefix="/api/v1"` y `dependencies=[Depends(get_empresa_id)]`.
- **T003** — estructura frontend: `frontend/src/app/{remesas,devoluciones,terceros/condiciones}/` y `frontend/src/components/treasury/` (con `.gitkeep`).
- **T004** — `backend/src/api/treasury/deps.py`: `get_empresa_id()` deriva la empresa de `request.state` (sesión autenticada) y responde **401** si falta o es inválida; nunca acepta la empresa del cliente (constitución III).

Tests (33, pytest) en `backend/tests/unit/`:
`test_treasury_setup.py` (estructura/imports), `test_session_deps.py` (401 sin sesión, valores inválidos) y `test_treasury_router.py` (prefijo versionado + dependency de sesión).

Configuración añadida: `backend/pytest.ini` (`pythonpath=src`, `asyncio_mode=auto`), `requirements.txt`, `.gitignore`.

```powershell
# Ejecutar la suite (desde backend/)
..\.venv\Scripts\python.exe -m pytest
```

> Los servicios `discount.py`, `sepa_dd.py`, `csb_1919.py` y `refund_r19.py` son **stubs**; su lógica se implementa en Phase 3+ (T016–T050).

## 11. Implementación realizada (SPEC-020 · Phase 2 Foundational)

Completadas **T005–T013** (`specs/020-remesas-sepa-cobros/tasks.md`):

- **Infraestructura**: `backend/src/base.py` (`DeclarativeBase` con naming convention) y `backend/src/database.py` (`DATABASE_URL` vía `os.getenv`, `create_async_engine` asyncpg, `async_session_factory`, `get_db` con commit/rollback ACID).
- **T005–T010** — modelos fundacionales en `backend/src/models/treasury/`:
  `remesa.py` (Remesa, único `(empresa_id, ejercicio, numero_remesa)`, `importe_total` NUMERIC(18,4) > 0), `recibo_remesa.py` (ReciboRemesa con FK compuesta `(empresa_id, remesa_id)`, índice único parcial `(empresa_id, vencimiento_id)` para remesas activas), `condicion_pronto_pago.py` (índice único parcial vigente por `(empresa_id, tercero_id)`), `mandato_sepa.py`, `devolucion.py` (DevolucionRecibo + Reclamacion, `identificador_externo` único por empresa, `importe_gastos` DEFAULT 0), `blob_fichero.py` (contenido `LargeBinary` → BYTEA en PG, `sha256` CHAR(64)). Todos con `empresa_id` en PK/índices/FKs (constitución III) y exportados en `models/treasury/__init__.py`.
- **T011** — CRUD de `CondicionProntoPago` y `MandatoSepa`: `backend/src/services/tercero_amend.py` (crear/actualizar con desactivación del vigente previo, validar B2B firmado, ref única por tercero) y `backend/src/api/treasury/tercero_amend.py` (POST/PATCH `/api/v1/terceros/{id}/condiciones` y `/terceros/{id}/mandatos`), router anidado en `routes.py`.
- **T012/T012a/T013** — tests (27 nuevos, suite total 60): `backend/tests/unit/test_treasury_models.py` (unicidad remesa, vigente único, FK compuesta, NUMERIC(18,4)), `backend/tests/integration/test_treasury_tenant_isolation.py` (remesa de empresa A invisible desde B), `backend/tests/integration/test_tercero_amend_routes.py` (CRUD endpoints + 404 cross-tenant + 409 mandato duplicado + desactivación vigente). Fixtures SQLite in-memory en `backend/tests/conftest.py` (`aiosqlite`, `PRAGMA foreign_keys=ON`, `StaticPool`).

```powershell
# Ejecutar la suite (desde backend/)
..\.venv\Scripts\python.exe -m pytest          # 60 passed
..\.venv\Scripts\python.exe -m ruff check src tests   # All checks passed
```

> Pendiente: Phase 3 (US1), Phase 4 (US2), Phase 5 (US3), Phase 6 (Polish, incluye T051–T056) y Phase 7 (Convergence, T057–T062). El modelo integra FKs cross-spec (vencimiento, tercero, factura, asiento) como columnas UUID; las constraints reales se añaden al implementar SPEC-002/008/011.

## 12. Implementación realizada (SPEC-020 · Phase 3 US1)

Completadas **T014–T030a** (21 tareas) según `specs/020-remesas-sepa-cobros/tasks.md`:

- **Scaffolds cross-spec** (soporte mínimo de SPEC-020, NO implementación completa de SPEC-002/008/011): `backend/src/models/ar/tercero.py`, `backend/src/models/ar/vencimiento.py` (Vencimiento con estado/ejercicio/fecha/importe), `backend/src/models/acct/journal.py` (JournalEntry inmutable POSTED + JournalEntryLine con FK compuesta y checks `debe/haber >= 0`), `backend/src/models/treasury/secuencia_remesa.py` (correlatividad por (empresa, ejercicio)), `backend/src/models/treasury/cobro_conciliado.py` (idempotencia por (empresa, movimiento_id)), `backend/src/models/audit/audit_log.py` (WORM en la misma transacción).
- **Servicios**: `services/remittance/seleccion.py` (selección por empresa+fecha/cliente/banco, `ejercicio_cerrado`, correlatividad con `SELECT ... FOR UPDATE`), `services/remittance/sepa_dd.py` (PAIN.008.001.02 con `CtrlSum` 2 decimales, validación CORE D-2 / B2B D-1 hábiles, agrupación multi-fecha), `services/remittance/csb_1919.py` (registros 1/2/3/5 de 120 chars, importes en céntimos, ISO-8859-15), `services/remittance/emision.py` (`crear_remesa` con exclusión atómica y 422/`excluidos`, `emitir_remesa` con `BlobFichero`+sha256 y B2B obliga mandato firmado, `confirmar_cobro` y `conciliar_cobro` idempotente), `services/accounting.py` (`verificar_balance`, `construir_asiento_cobro` 572↔430), `services/audit.py`.
- **API** `backend/src/api/treasury/remesas.py`: `POST /api/v1/remesas` (201/422), `POST .../{id}/emitir` (200/409/422), `GET /api/v1/remesas` (paginación + filtros estado/formato), `GET .../{id}`, `GET .../{id}/fichero` (descarga), `POST .../{id}/recibos/{recibo_id}/cobrar` y `/conciliar` (idempotente, `movimiento_id`). `empresa_id` SIEMPRE vía `Depends(get_empresa_id)` (nunca query/body — constitución III).
- **Frontend**: `frontend/src/components/treasury/api.ts` (helper tipado + `ApiError`), `frontend/src/app/remesas/page.tsx` (T026 listado paginado con filtros), `frontend/src/app/remesas/nueva/page.tsx` (T024 selección/vista previa/envío), `frontend/src/app/remesas/[id]/page.tsx` (T025 detalle + emitir/descargar/cobrar).
- **Detalle clave**: construcción de asientos con `default=uuid.uuid4` en `id`: el default se aplica en el flush, por lo que `construir_asiento_cobro` asigna `asiento.id` antes de enlazar las líneas (evita `journal_entry_id NULL`).

```powershell
# Ejecutar la suite (desde backend/)
..\.venv\Scripts\python.exe -m pytest          # 87 passed (60 previos + 27 nuevos)
..\.venv\Scripts\python.exe -m ruff check src tests   # All checks passed
```

> Pendiente: Phase 4 (US2, T031–T038), Phase 5 (US3, T039–T050), Phase 6 (Polish, T051–T056) y Phase 7 (Convergence, T057–T062). Los scaffolds `models/ar|acct|audit` son exclusivos de SPEC-020; su ampliación a SPEC-002/008/011/013 queda fuera de esta feature.

## 13. Implementación realizada (SPEC-020 · Phase 4 US2)

Completadas **T031–T038** (8 tareas) según `specs/020-remesas-sepa-cobros/tasks.md`:

- **Modelo**: `Vencimiento.fecha_factura` (DATE nullable) añadido al scaffold SPEC-011; la ventana del descuento usa `fecha_factura` y cae a `fecha_vencimiento` si es NULL.
- **Servicios** `services/discount.py`: `calcular_descuento` (neto = importe × (1 − %) cuantizado a 4 decimales, neto nunca negativo, edge neto=0 con %=100), `en_plazo` (fecha_pago − fecha_factura <= plazo_dias), `condicion_para_vencimiento` (vigente del tercero o override por factura; decretado por descuento solo hay un vigente), `aplicar_pronto_pago`, `liquidar_con_descuento` (asiento ACID: Debe 572 neto + 432/662 descuento | Haber 430 total; sin descuento solo 572 vs 430 tipo COBRO; estado → cobrado recibo+vencimiento; `descuento_id` enlazado si procede; auditoría LIQUIDAR). Excepciones con código `recibo_no_encontrado`/`vencimiento_no_encontrado`/`liquidacion_estado_no_valido`/`condicion_no_encontrada`.
- **API** `api/treasury/recibos.py`: `POST /api/v1/recibos/{recibo_id}/liquidar` (body `{fecha_pago, cuenta="572", override_condicion_id?}`; 200 devuelve `importe_neto`/`descuento` a 4 decimales + `asiento_id`; 409 si ya liquidado). Añadido `GET /api/v1/terceros/{id}/condiciones` a `tercero_amend.py` para listado/edición frontend.
- **Frontend**: `frontend/src/app/terceros/condiciones/page.tsx` (T036): listar condiciones por tercero, crear vigente y desactivar.
- **Detalle clave**: `f"{Decimal(0):0.4f}"` (no `:f`) para devolver importes/descuentos con formato uniforme de 4 decimales. Un único `CondicionProntoPago` vigente por (empresa, tercero): al crear uno nuevo con `vigente=true` se desactiva el anterior, incluido el caso override-por-factura.

```powershell
# Ejecutar la suite (desde backend/)
..\.venv\Scripts\python.exe -m pytest          # 103 passed (87 previos + 16 nuevos)
..\.venv\Scripts\python.exe -m ruff check src tests   # All checks passed
```

> Pendiente: Phase 5 (US3, T039–T050), Phase 6 (Polish, T051–T056) y Phase 7 (Convergence, T057–T062).

## 14. Implementación realizada (SPEC-020 · Phase 5 US3)

Completadas **T039–T050** (14 tareas) según `specs/020-remesas-sepa-cobros/tasks.md`:

- **Parser** `services/remittance/refund_r19.py`: `parsear_retorno_aeb19` para R19/C19 y alias compatible `parsear_retorno_r19` (AEB cuaderno 19, registros tipo 3 de 97+ chars, ISO-8859-15, ignorar cabeceras/cierres), `normalizar_codigo` (≤ 10 chars, `MD01`/`AC04`/`R-CUST`, mayúsculas), `resolver_recibo_por_ref`. El tipo R19/C19 forma parte del identificador externo para la idempotencia por empresa.
- **Servicio** `procesar_devolucion`: valida recibo `cobrado` y `importe <= recibo.importe`; crea `DevolucionRecibo`; genera asiento **REVERSAL** (Debe 430 + 626 si gastos | Haber 572; `original_id` enlazado, original intacto — constitución II); recibo → `devuelto`, vencimiento → `pendiente`; auditoría REVERSAR. `gestionar_reclamacion`: acciones `abrir`/`en_curso`/`resolver`/`desestimar`, una única activa por devolución, estados reflejados en `DevolucionRecibo.estado_reclamacion`. Excepciones con códigos `recibo_no_encontrado`/`devolucion_no_encontrada`/`retorno_ya_procesado`/`recibo_no_cobrado`/`importe_invalido`/`ejercicio_cerrado`/`formato_retorno_invalido`/`reclamacion_activa`/`reclamacion_estado_no_valido`.
- **API** `api/treasury/devoluciones.py` (registrado en `routes.py`): `POST /api/v1/devoluciones/import` (fichero multipart **o** JSON vía `Request` — no mezclar `File`+`Body` pydantic: FastAPI lo trata como multipart y el JSON llega como `None`; devuelve `{procesadas, rechazadas[{motivo,code}], total}`), `GET .../devoluciones` (filtro código) y `GET .../{id}` (con recibo + reclamaciones), `POST .../{id}/reclamaciones`.
- **Frontend**: `frontend/src/components/treasury/api.ts` (+`Devolucion`, `listarDevoluciones`, `obtenerDevolucion`, `importarFicheroR19`, `importarDevolucionesJson`, `crearReclamacion`), `frontend/src/app/devoluciones/page.tsx` (T046 import + listado), `frontend/src/app/devoluciones/[id]/page.tsx` (T047 detalle + reclamaciones).
- **Detalles clave**: `date.strptime` NO existe en `datetime.date` — usar `datetime.strptime(...).replace(tzinfo=timezone.utc).date()` (cumple DTZ007). `_FileNone = File(default=None)` para validar B008. La fecha_cargo_original de la devolución es `recibo.fecha_cargo` (fecha de cargo, no la del cobro).

```powershell
# Ejecutar la suite (desde backend/)
..\.venv\Scripts\python.exe -m pytest          # 128 passed (103 previos + 25 nuevos)
..\.venv\Scripts\python.exe -m ruff check src tests   # All checks passed
```

> Pendiente: Phase 6 (Polish, T051–T056) y Phase 7 (Convergence, T057–T062).

> **Estado vigente**: ver §22 (2026-09-19). Las notas históricas de §10–§17 describen
> hitos anteriores y se conservan solo como referencia.

## 15. Correcciones de verificación (2026-09-17)

La verificación real de SPEC-020 detectó que, aunque las 69 tareas estaban marcadas `[X]`, las tres puertas fallaban. Corregido:

- **C1 (bloqueaba pytest)**: `ForeignKey` suelto en `__table_args__` → `ForeignKeyConstraint` en `backend/src/models/acct/account_plan.py` y `backend/src/models/iam/user_company.py`. Además `backend/src/models/__init__.py` (antes vacío) importa `acct, ar, audit, iam, treasury` para registrar todas las tablas y resolver FKs cross-spec.
- **C2 (ruff, 21 errores)**: `Annotated[...]` en lugar de `Depends()` en defaults (B008) en `api/deps.py`, `api/auth/auth.py`, `api/companies.py`, `api/acct/accounts.py`; `except (jwt.InvalidTokenError, ValueError, TypeError)` (BLE001); imports y variables sin usar.
- **C3 (mypy, 6 errores)**: guarda de `exponent` no entero en `services/journal/money.py`; retorno `tuple[...]` de `_validar_lineas`; `empresa_id: int | None` en `services/audit.py` y `writer.py` (login fallido audita sin empresa).

## 16. Inmutabilidad a nivel DB (SPEC-020 · H2)

- `backend/migrations/000_audit_log.sql`: tabla `audit_log` + trigger WORM `trg_audit_log_immutable`.
- `backend/migrations/004_iam.sql`: `companies`, `users`, `user_companies` + enum `user_company_rol` + índice único parcial de empresa por defecto.
- `backend/migrations/001_account_plan.sql`: tabla `account_plan` multi-tenant + índices + `pg_trgm` + triggers `chk_account_plan_structure`, `sync_account_plan_selectable` y `chk_account_plan_protected`.
- `backend/migrations/002_seed_pgc.sql`: función `seed_default_pgc(p_tenant_id)` (7 grupos + subgrupos/cuentas/subcuentas) + trigger `trg_companies_seed` AFTER INSERT ON companies.
- `backend/migrations/003_journal.sql`: `journal_entry`/`journal_entry_line` + FK compuesta multi-tenant + triggers de inmutabilidad, apuntabilidad y balance diferido `trg_journal_entry_balance`/`trg_journal_entry_line_balance` (§5.d).
- `backend/migrations/005_fiscal_invoice.sql`: `fiscal_year` e `invoice` (SPEC-004, modelos aún sin implementar) con FK compuesta a `journal_entry`.
- `backend/src/db/triggers.py`: triggers equivalentes para SQLite, instalados en `backend/tests/conftest.py` tras `create_all` → la inmutabilidad es verificable en CI sin PostgreSQL.
- `backend/src/db/migrate.py`: runner de `migrations/*.sql`. El orden numérico no coincide con las dependencias FK: `ORDEN_PREFERENTE` aplica `000 → 004 → 001 → 002 → 003 → 005` porque `account_plan`/`seed` referencian `companies` (004) y `fiscal_year`/`invoice` referencian `journal_entry` (003). Desde `backend/`: `$env:PYTHONPATH="src"; ..\.venv\Scripts\python.exe -m db.migrate`.
- Tests: `backend/tests/unit/test_db_immutability.py` (8), `backend/tests/unit/test_migrations.py` (4) y `backend/tests/integration/test_pg_schema.py` (6, opt-in con `TEST_DATABASE_URL`).
- Desviaciones documentadas: (a) se omite `uq_account_plan_tenant_name` porque los nombres del PGC se repiten entre niveles (`Proveedores` 40/400, `Clientes` 43/430, `Caja` 58/570) y el seed fallaría; se eliminó también del modelo `account_plan.py`; (b) `005` usa FK `UUID` (no `BIGINT`) para alinear con el PK real de `journal_entry`.
- Verificado sobre PostgreSQL 16.4 real (ver §19): las 6 migraciones se aplican, el seed crea 7/28/22/16 cuentas sin huérfanos, y los triggers rechazan UPDATE/DELETE de asientos POSTED y de `audit_log`, y apuntes sobre cuentas no apuntables.
- Corregido: el seed del plan raíz insertaba niveles 2 y 3 **sin `parent_id`** (el trigger `chk_account_plan_structure` lo rechaza) y faltaban los subgrupos padre `32` (cuenta `325`) y `79` (cuenta `790`); corregido en `002_seed_pgc.sql` y en `services/acct/seed.py`.
- Resuelto: trigger de balance diferido `chk_journal_entry_balance` añadido en `003_journal.sql`, con prueba PostgreSQL real; T062 sigue abierta por la verificación global pendiente.

## 17. Frontend Next.js (SPEC-020 · H1)

- Scaffolding: `frontend/package.json` (Next 15 + React 19 + TS + Tailwind 3), `tsconfig.json`, `next.config.mjs` (proxy `/api/v1/*` → `BACKEND_URL`, por defecto `http://localhost:8000`), `postcss.config.mjs`, `tailwind.config.ts`, `eslint.config.mjs`, `next-env.d.ts`, `src/app/{layout.tsx,page.tsx,globals.css}`.
- Contexto de empresa activa: `src/components/treasury/empresa.ts` (store en `localStorage` + `cabecerasEmpresa()`), `EmpresaActiva.tsx` (selector en el layout) y cabecera `X-Empresa-Activa` en todas las llamadas de `api.ts`. `descargarFichero()` descarga autenticada vía blob (una `<a href>` plana daría 403).
- Verificación: `tsc --noEmit`, `eslint src` y `next build` (8 rutas) en verde.
- Pendiente: página de login (hoy la empresa se fija manualmente en el selector), invalidación de caché al cambiar de empresa y `frontend/src/services/` del plan (el cliente vive en `components/treasury/api.ts`).

## 18. Comandos de verificación actualizados

```powershell
# Backend (desde backend/)
..\.venv\Scripts\python.exe -m pytest                    # 2659 passed, 21 skipped (SQLite; migraciones 000-021 sobre PG)
..\.venv\Scripts\python.exe -m ruff check src tests      # All checks passed
..\.venv\Scripts\python.exe -m mypy -p api -p models -p services -p database -p base -p db -p main -p config
# Servidor
$env:PYTHONPATH="src"; ..\.venv\Scripts\python.exe -m uvicorn main:app --reload

# Frontend (desde frontend/)
npm install
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js src
$env:NEXT_TELEMETRY_DISABLED="1"; node node_modules/next/dist/bin/next build   # 104 rutas
```

## 19. PostgreSQL local (verificación real de migraciones)

**PostgreSQL 18.6 instalado** en `C:\Program Files\PostgreSQL\18` como servicio Windows
`postgresql-x64-18` (puerto **5432**, `scram-sha-256`). Ya no se usa el cluster portable
del temp: se limpió y hay que reinstalar/reextraerlo si se vuelve a necesitar. La
constitución pide 16+, así que 18 es válido y verifica la instalación real.

- Credenciales en `backend/.env` (`DATABASE_URL` y `TEST_DATABASE_URL`). `config.py` lo
  lee vía `env_file = ".env"`, y `.gitignore` cubre `.env`/`.env.*` salvo `.env.example`.
  **Nunca** commitear `.env`; la plantilla sin secretos es `backend/.env.example`.
- `psql` **debe** llevar `-w` (no interactivo): sin él se queda esperando el prompt de
  contraseña y la sesión parece colgada. Lo mismo con cualquier cliente que pida auth.

```powershell
# servicio
Get-Service postgresql-x64-18
# cliente (OJO: -w evita el prompt interactivo)
$env:PGPASSWORD = "<la de .env>"; & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -w -p 5432 -U postgres -h 127.0.0.1 -d contabilidad
# recrear la base antes de aplicar migraciones
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -w -p 5432 -U postgres -h 127.0.0.1 -d postgres -c "DROP DATABASE IF EXISTS contabilidad;" -c "CREATE DATABASE contabilidad;"
```

Migraciones y tests contra PostgreSQL (desde `backend/`):

```powershell
$env:PYTHONPATH="src"; ..\.venv\Scripts\python.exe -m db.migrate   # lee DATABASE_URL de backend\\.env (idempotente)
# `db.migrate` debe correr ANTES de la suite completa contra PG: tests como
# `test_cierre_concurrente` insertan en `companies` y asumen el esquema migrado.
$env:PYTHONPATH="src"; $env:TEST_DATABASE_URL="postgresql+asyncpg://postgres:<password>@localhost:5432/contabilidad"; ..\.venv\Scripts\python.exe -m pytest   # 2678 passed, 1 skipped
```

- El runner usa el protocolo simple de asyncpg (`raw.driver_connection.execute`) porque cada `.sql` contiene varios comandos y asyncpg no admite multi-comando en prepared statements.
- `TEST_DATABASE_URL` **no** la lee `config.py`: hay que exportarla en el proceso para que
  `test_pg_schema.py` no se salte (con solo `DATABASE_URL` esos tests aparecen como skipped).
- Si se vacía el temp y hay que recuperar el cluster portable, `initdb` deja directorios
  vacíos que PostgreSQL no crea: recrear `pg_logical/{mappings,snapshots}`,
  `pg_multixact/{members,offsets}` y `pg_wal/archive_status` o el arranque falla con
  `could not open directory`.

## 20. Estado real por spec (auditoría 2026-09-26)

`tasks.md` marca **1.432/1.432**, con **30 specs completas** (tasks marcadas + puertas
verificadas) y ninguna diseñada sin implementar. Cada spec afectada lleva al final de su
`tasks.md` una sección **"Estado real (implementación 2026-09-2X)"** con desviaciones
documentadas.

| Spec | Marcadas/total | Código real | Estado |
|---|---|---|---|
| 001 PGC | 42/42 | `account_plan`, `plan_tree`, `account_service`, seed, migraciones 000/001/002, frontend cuentas | 🟢 completa |
| 002 Motor asientos | 43/43 | `journal`, `journal_sequence`, `money`, `sequence`, `entry_service`, `reversal`, `journal_query`, migración 003, frontend asientos | 🟢 completa |
| 003 Multiempresa RBAC | 36/36 | `iam`, `auth` login/me/switch, `api/deps.py`, `companies`, `company_service`, migración 004, frontend login+switch | 🟢 completa |
| 004 Informes/cierre | 53/53 | `models/acct/fiscal_year`, `models/ar/invoice`, `reports/{trial_balance,ledger,common}`, `closing/close_year`, `invoicing`, `api/reports`, migración 005, frontend informes+cierre | 🟢 completa |
| 005 Import/export | 43/43 | `services/importexport/{parseador,validador,importador,exportador}`, `api/importexport`, frontend drag-and-drop | 🟢 completa |
| 008 Terceros | 50/50 | `models/ar/{tercero,tercero_subcuenta}`, `services/thirdparty/*`, `api/thirdparty`, frontend terceros | 🟢 completa |
| 011 Cobros/pagos | 45/45 | `models/ar/vencimiento` (extendido), `models/treasury/cobro_pago`, `services/treasury/{cobros_pagos,antiguedad}`, `api/treasury/{vencimientos,antiguedad}`, frontend vencimientos/cobros/antigüedad | 🟢 completa |
| 013 Conciliación | 54/54 | `models/treasury/{extracto,movimiento,conciliacion,periodo_conciliado,alerta}`, `services/reconciliation/*`, `api/reconciliation`, fixtures norma 43, frontend conciliación | 🟢 completa |
| 020 Remesas SEPA | 69/69 | backend + frontend + migraciones | 🟢 completa |
| 009 Apertura ejercicio | 37/37 | `models/fiscal/ejercicio`, `services/cycle/{validacion_previa,apertura}`, `api/ciclo`, migración 006, frontend apertura | 🟢 completa |
| 006 Asientos multilínea | 40/40 | `services/journal/{validador_multilinea,motor,anulador}`, `api/journal/asientos`, `frontend/src/components/journal/line-editor.tsx`, `app/contabilidad/asientos/nuevo` | 🟢 completa |
| 007 Facturación | 56/56 | `models/invoice/{serie_factura,factura,factura_linea}`, `services/invoicing/{numeracion,calculo_impuestos,recargo_equivalencia,criterio_caja,asiento_factura,emision,rectificacion}`, `api/invoicing/{deps,routes,series,facturas}`, `components/invoicing/api.ts`, `app/facturacion/*` | 🟢 completa |
| 010 Cuentas anuales | 45/45 | `models/reporting/{configuracion,formulacion,control_efe}`, `services/reporting/{saldos,agrupacion,comparativo,pyg,efe,formulacion}`, `api/cuentas_anuales/{deps,routes,config}`, `components/reporting/*`, `app/{cuentas-anuales,balance,pyg,efe}` | 🟢 completa |
| 012 Libros IVA | 56/56 | `models/fiscal/{periodo_fiscal,exportacion_modelo,configuracion_sii,configuracion_fiscal,iva_diferido_caja}`, `services/vat/{periodo,configuracion_cuentas,libros_iva,modelos,exportacion,recargo_equivalencia,criterio_caja,sii}`, `api/fiscal/*`, `components/vat/api.ts`, `app/{libros-iva,modelos,exportaciones}` | 🟢 completa |
| 014 Amortizaciones | 49/49 | `models/inmovilizado/{activo,plan_amortizacion,amortizacion_generada,baja_activo}`, `services/inmovilizado/{plan,activo,generacion,baja}`, `api/inmovilizado/{deps,activos,amortizaciones}`, `components/inmovilizado/api.ts`, `app/inmovilizado/{page,alta,amortizaciones,[id]}` | 🟢 completa |
| 015 Matriz permisos | 48/48 | `models/rbac/*`, `services/security/{catalogo,autorizacion,auditoria_acceso,matriz}`, `api/deps.require_permission`, `api/rbac.py`, `api/routes_registry.py`, migración 007, `components/rbac/{api.ts,permisos-table.tsx}`, `app/permisos/*` | 🟢 completa |
| 016 Multi-divisa | 48/48 | `models/monedas/*`, `services/forex/{conversion,monedas,cuentas,tipos,asiento_divisa,valoracion}`, `api/forex/{deps,routes}`, migración 008, `components/forex/api.ts`, `app/divisas/*` | 🟢 completa |
| 017 Centros de coste | 48/48 | `models/costcenters/{centro_coste,jerarquia,imputacion}`, `services/costcenters/{centros,imputacion,informes}`, `api/costcenters/*`, migración 009, `components/costcenters/{api.ts,CentroSelect}`, `app/centros/*`, `app/informes/costes` | 🟢 completa |
| 018 Plantillas asientos | 42/42 | `models/templates/*`, `services/templates/*`, `api/templates/*`, migración 010, `components/templates/{api.ts,TemplateEditor.tsx}`, `app/plantillas/*` | 🟢 completa |
| 019 Gestión ONG | 53/53 | `models/ngo/*` (subvencion, gasto_imputado, libros, caja, arqueo), `services/ngo/{subvenciones,justificacion,libros_pdf,legalizacion,caja,arqueo,saldo_570}`, `api/ngo/*`, migración 011, `components/ngo/*`, `app/ong/*` | 🟢 completa |
| 021 Medios pago/efectos | 44/44 | `models/treasury/{efecto,cobro_medio,comision}`, `services/treasury/{common,efecto,cartera,cobro_medio}`, `api/treasury/{efectos,cobros_medio}`, migración 012, `components/treasury/api.ts`, `app/{efectos,tesoreria}` | 🟢 completa |
| 022 Anticipos/cesión | 48/48 | `models/treasury/{anticipo,liquidacion_anticipo,cesion,notificacion_cesion}`, `services/treasury/{anticipo,liquidacion,cesion}`, `api/treasury/{anticipos,cesiones}`, migración 013, `components/treasury/api.ts`, `app/{anticipos,cesiones}` | 🟢 completa |
| 023 Impuesto sociedades | 44/44 | `models/fiscal/{calculo_is,ajuste_extracontable,modelo_200,configuracion_fiscal}`, `services/fiscal/{impuesto_sociedades,modelo_200_gen}`, `api/fiscal/{calculos_is,modelo_200}`, migración 014, `components/fiscal/api.ts`, `app/fiscal/*` | 🟢 completa |
| 024 Retenciones IRPF | 48/48 | `models/fiscal/{retencion,liquidacion_retenciones,modelo_111,modelo_115,modelo_190}`, `services/fiscal/{retenciones,liquidacion_retenciones,modelo_111_gen,modelo_115_gen,modelo_190_gen}`, `api/fiscal/retenciones.py`, migración 015, `app/fiscal/{retenciones,modelos/190}` | 🟢 completa |
| 025 Catálogo versionado | 47/47 | `models/catalog/{catalogo_version,catalogo_cuenta,mapeo_cuenta,reclasificacion_saldo}`, `services/catalog/{_comun,versiones,importacion_catalogo,mapeo,reclasificacion_saldos}`, `api/catalogo.py`, migración 016 + trigger de vigencia, `components/catalog/api.ts`, `app/catalogo/{page,[id],importar,reclasificar}` | 🟢 completa |
| 026 Presupuestos/desviaciones | 42/42 | `models/budget/{presupuesto,periodo_seguimiento,desviacion}`, `services/budget/{errores,utils,periodos,presupuesto_service,desviaciones,informe_desviacion,cierre_periodo}`, `api/presupuestos.py`, migración 017 + triggers append-only, `components/budget/api.ts`, `app/presupuestos/{page,seguimiento,informes}` | 🟢 completa |
| 027 Previsión tesorería | 45/45 | `models/treasury/{prevision,movimiento_prevision,alerta_liquidez,efe}`, `services/cashflow/{utils,clasificacion_actividad,saldos,proyeccion,efe,alertas,errores}`, `api/tesoreria.py`, migración 018 + triggers, `components/cashflow/api.ts`, `app/tesoreria/{previsiones,previsiones/[id],efe,alertas}` | 🟢 completa |
| 028 Cierre intermedio/reapertura | 57/57 | `models/closing/{periodo_cerrado,balanza_periodo,cierre_ejercicio,solicitud_reapertura,secuencia_reapertura}`, `services/closing/{errores,reglas_cierre,balanza,periodo,cierre_anual,reapertura,secuencia}`, `api/closing.py`, migración 019 + trigger `chk_journal_entry_fecha_abierta`, `components/closing/{api.ts,BalanzaTabla.tsx}`, `app/cierres/{page,intermedio,anual,reaperturas,[id]}` | 🟢 completa |
| 029 Exportacion integral | 52/52 | `models/export/*`, `services/export/{bloques,recopilar,serializacion,manifiesto,zip_generator,persistir,verificar,sii}`, `api/export.py`, migracion 020 + trigger de inmutabilidad del snapshot, `components/export/{api.ts,ManifiestoEstado.tsx,DescargaExport.tsx}`, `app/exportaciones/{page,nueva,[id]}` | COMPLETA |
| 030 Documentos adjuntos | 48/48 | `models/acct/documento.py`, `services/documentos/{errores,validacion,_serializacion,adjuntos,consulta,bajas}`, `api/documentos/{__init__,deps,adjuntos,consulta,bajas}`, migracion 021 + 2 triggers, `components/documentos/{api.ts,DocumentosAsiento.tsx,VisorDocumento.tsx}`, `app/documentos/{page}` + montaje en `app/asientos/[id]/page.tsx` | COMPLETA |

### Bloqueantes transversales (no figuran en ninguna `tasks.md`)

- **G1**: ✅ **resuelto** — entrypoint `backend/src/main.py` (`FastAPI()`, CORS, lifespan
  con `engine.dispose()`, routers `auth`/`companies`/`accounts`/`journal`/`reports`/
  `fiscal`/`thirdparty`/`importexport`/`treasury`, `forex`, `GET /health`).
- **G2**: ✅ **resuelto** — `backend/src/config.py` (`Settings`); `database.py` lo consume.
- **G3**: ✅ **resuelto** — página de login (`frontend/src/app/login/page.tsx`) + selector
  de empresa (`components/rbac/CompanySwitch.tsx`); la empresa activa viaja en
  `X-Empresa-Activa`.
- **G4**: ✅ **resuelto** — cliente HTTP compartido en `frontend/src/services/client.ts`
  (JWT + cabecera de empresa); `services/acct/api.ts` para el plan.
- **G5**: ✅ **resuelto** — trigger de balance diferido `chk_journal_entry_balance`.
- **G6**: ✅ **resuelto** — `.github/workflows/ci.yml` con las puertas backend/frontend.

### Orden recomendado de continuacion

No queda ninguna spec pendiente: las 30 estan cerradas. Queda un solo trabajo
**transversal**: extraer un helper `sembrar_empresa_pgc` compartido en
`backend/tests/conftest.py`, hoy duplicado en mas de veinte fixtures de specs,
y mantener este recuento al dia.

## 21. Entrypoint FastAPI (G1/G2)

- `backend/src/main.py`: app FastAPI (`title`/`version` desde `config`), CORS desde `CORS_ORIGINS`, lifespan que libera el engine, routers `auth`, `companies`, `accounts` y `treasury` bajo `/api/v1`, y `GET /health`.
- `backend/src/config.py`: `Settings` (pydantic-settings) con `APP_NAME`, `APP_VERSION`, `DATABASE_URL`, `CORS_ORIGINS`; `database.py` usa `settings.database_url`.
- Arranque: `$env:PYTHONPATH="src"; ..\.venv\Scripts\python.exe -m uvicorn main:app --reload` (desde `backend/`).
- **Bug corregido**: coexistían `services/audit.py` (módulo) y `services/audit/` (namespace package sin `__init__.py`), de modo que `services.audit.writer` fallaba al importarse. Se consolidó `registrar_auditoria` en `services/audit/__init__.py` y se eliminó `services/audit.py`.
- Tests: `backend/tests/unit/test_app.py` (5).

## 22. Cierre de specs 001–005/008/011/020 (2026-09-19)

Sesión de verificación e implementación que cierra **8 specs** (381/1.384 tareas en ese
hito; SPEC-013 se cierra en §23). Puertas finales de ese hito: pytest **545 passed /
5 skipped** (SQLite) y **550 passed / 0 skipped** (PostgreSQL 16.4 real), `ruff` + `mypy`
(107 ficheros) limpios, `next build` **25 rutas**.

### SPEC-001 · PGC (42/42)
Creados en el cierre: `JournalEntryForm.tsx` (T022), `test_proteccion_integracion.py`
(T036), `test_suggest_perf.py` ~10k cuentas (T040). Desviación: `UNIQUE (tenant_id, name)`
omitido (nombres PGC repetidos entre niveles).

### SPEC-002 · Motor de asientos (43/43)
Barrido de verificación; creado `test_journal_tenant_isolation.py` (T011) y el frontend
`app/asientos/{nuevo,diario,[id]}`. Desviaciones: modelos en `models/acct/journal.py`
único; 4 tests viven en `integration/` en vez de `unit/`.

### SPEC-003 · Multiempresa RBAC (36/36)
Implementadas US1–US4 + Polish: login/JWT, switch-company, guards 403, alta de empresa
con seed atómico, matriz de roles, quickstart. Frontend `login`, `empresas/nueva`,
`rbac/CompanySwitch.tsx`, `services/client.ts`. **Guard compartido unificado**: los
routers `treasury` migraron del `request.state` local al `api.deps.get_empresa_id`
real (JWT + `X-Empresa-Activa`), corrigiendo que en producción devolvían 401.

### SPEC-004 · Informes y cierre (53/53)
Implementados desde casi cero (solo existía la migración 005): `Invoice`,
`fiscal_year`, `reports/trial_balance` + `ledger` (POSTED-only, Decimal), `closing/
close_year` (regularización 6/7→`1290`, salda balance, bloqueo atómico), `invoicing`
(precisión/numero/vínculo), `api/reports/{informes,fiscal}`, páginas informes/cierre.
Desviaciones: año inexistente = abierto; asientos de cierre `ADJUSTMENT`; regularización
contra subcuenta auto-creada `1290` (la `129` nivel 3 no es apuntable).

### SPEC-005 · Import/export asientos (43/43)
`services/importexport/{parseador,validador,importador,exportador}` +
`api/importexport` (`/api/v1/asientos/importar/{previsualizar,confirmar}`, `/exportar`) +
frontend drag-and-drop. Dry-run sin escritura; importación con `SAVEPOINT` por asiento
(omite inválidos), numeración vía `next_numero` de SPEC-002; export CSV (UTF-8 BOM, `;`)
y XLSX. **Dependencia nueva**: `openpyxl>=3.1,<4.0`.

### SPEC-008 · Maestro de terceros (50/50)
`Tercero` extendido (roles, NIF único/empresa, direcciones, IBAN/BIC/banco, activo),
`TerceroSubcuenta` (nivel 4 `430N`/`410N`), validadores NIF/CIF/NIE e IBAN (ISO 13616),
servicios `alta`/`saldo`/`retirada`, `api/thirdparty`, frontend terceros. Reutiliza el
CRUD de condiciones de SPEC-020.

### SPEC-011 · Cobros y pagos (45/45)
`Vencimiento` extendido (`tipo`, `acumulado`, `remesa_id`, estados `parcial`/`remesado`,
`saldo_pendiente` derivado) + `CobroPago`; `services/treasury/{cobros_pagos,antiguedad}`;
`api/treasury/{vencimientos,antiguedad}`; frontend vencimientos/cobros/antigüedad.
Cobros/pagos totales y parciales con asiento balanceado; no duplica remesas de SPEC-020.

### SPEC-020 · Remesas SEPA (69/69)
Cerradas T054 (review), T055 (ejercicios cerrados), T056 y T062 (puertas globales).
Corregido `test_correlatividad_concurrente` (pasaba `fecha` como string; requiere BD
limpia entre corridas).

### Lecciones reutilizables
- **Fixtures async en Windows**: `anyio.run()` deja el event loop policy sin loop para
  los tests `async def` posteriores; usar `asyncio.new_event_loop().run_until_complete()`
  + `with TestClient(...)`.
- **SQLite vs PG**: `BigInteger` PK no autoincrementa en SQLite → `BigInteger().with_variant(Integer, "sqlite")`.
- **Triggers SPEC-001**: `account_plan` exige `level == len(code)` y padre de nivel-1;
  las subcuentas de terceros se crean en `AccountPlan` (nivel 4) con el prefijo correcto.
- **`services/journal/entry_service.crear_borrador`** acepta `tipo=` (default `GENERAL`).

## 23. Cierre de SPEC-013 Conciliación Bancaria (2026-09-19)

Última spec de tesorería cerrada (54/54). Total del proyecto: **435/1.384** (9 specs).

- **Modelos** (`models/treasury/`): `extracto_bancario`, `movimiento_bancario`,
  `conciliacion` (+ `CruceConciliacion`), `periodo_conciliado`, `alerta_conciliacion`.
  Sin migración SQL dedicada (se crean vía `create_all` en tests, como el resto de ar).
- **Parser** `services/reconciliation/{layouts,parsers}.py`: layout de referencia norma
  43/19 de 100 chars (cabecera 01, operaciones 21/22, control 98) + CSV normalizado.
  Fixtures en `backend/tests/fixtures/extracto_43_19_*`.
- **Servicios**: `importacion` (sha256 + solape, cuádruple cuadre), `matching`
  (importe exacto + orientación; `propuesto` si coincide concepto, `candidato` si no),
  `cruce` (confirmar/deshacer + hook SPEC-020 que marca `ReciboRemesa.cobrado` sin
  segundo asiento), `saldos` (saldo_banco/libros/diferencia en `Decimal`), `cierre`
  (numero_periodo correlativo por empresa/ejercicio, solo diferencia `0.0000`).
- **API** `api/reconciliation.py`: extractos (POST/GET/detalle), conciliaciones
  (POST/GET/informe/propuestas/cruces/DELETE/cerrar/alertas), periodos archivados.
- **Frontend**: `app/conciliacion/{page,importar,[id],periodos}`.
- **Acoplamiento SPEC-020**: `confirmar_cruce` marca `ReciboRemesa.estado=cobrado`
  cuando el apunte cruce coincide con `asiento_cobro_id` (misma transacción).
- **Lección**: las tablas nuevas sin migración SQL se prueban solo en SQLite; la
  verificación PG real cubre las tablas migradas (000–005).

## 24. Cierre de SPEC-009 Apertura del Ejercicio (2026-09-20)

Primera spec del ciclo contable anual cerrada tras 019 (37/37). Total del proyecto:
**472/1.384** (10 specs).

- **Modelos**: `models/fiscal/ejercicio.py` (`EjercicioContable`: PK UUID con
  `UNIQUE(empresa_id, id)` + `UNIQUE(empresa_id, ejercicio)`, estados
  `abierto|cerrado|con_apertura`, `chk_..._rango`). `JournalEntry` ampliado con
  `tipo` `OPENING`/`OPENING_REVERSAL` y `referencia_cierre_id` (`models/acct/journal.py`).
- **Servicios** `services/cycle/`: `validacion_previa.py` (orden de validación: previo
  cerrado → destino con rango → sin solapamiento → sin OPENING activo; códigos
  `ejercicio_cerrado`, `ejercicio_ya_abierto`, `solapamiento_ejercicios`,
  `ejercicio_no_definido`; `estado_apertura` con `sin_apertura` 404) y `apertura.py`
  (`calcular_saldos_patrimoniales` = **grupos 1-3** netos del previo excluyendo solo
  `cierre_entry_id`; `generar_asiento_apertura` con numeración correlativa
  (`next_numero`), balance validado y auditoría APERTURA; `anular_apertura` = REVERSAL
  con líneas invertidas enlazado al original sin tocarlo + auditoría ANULAR_APERTURA;
  `regenerar_apertura`).
- **Migración** `backend/migrations/006_apertura.sql` (registrada en `ORDEN_PREFERENTE`
  tras 005; `ADD VALUE IF NOT EXISTS` para los enums) + `test_migrations.py` ampliado.
- **API** `api/ciclo/` (router versionado `/api/v1` + `Depends(get_empresa_id)`):
  `POST /ciclo/apertura` (201), `GET /ciclo/apertura/estado` (200), `POST .../anular`
  (200), `POST .../regenerar` (201) — montado en `main.py`.
- **Frontend**: `frontend/src/app/apertura/page.tsx` (estado, abrir, anular con
  confirmación, regenerar).
- **Verificación**: pytest **598 passed / 5 skipped** (SQLite) y **603 passed / 0
  skipped** (PostgreSQL 16.4 real con esquema limpio y migración 006), `ruff` + `mypy`
  limpios (131 fuentes), `tsc` + `eslint` + `next build` (30 rutas, incl. `/apertura`).
- **Lecciones reutilizables**:
  - `flush()` dentro del boundary `get_db` (patrón del proyecto); NUNCA
    `async with async_session.begin()` dentro del servicio.
  - La consulta de saldos excluye el asiento de cierre (no la regularización) para
    conservar `1290`; los grupos 1-3 deben cuadrar entre sí o la apertura se rechaza
    (`cuentas_patrimoniales_vacias`/`asiento_desbalanceado`).
  - `test_correlatividad_concurrente` (SPEC-002) falla si la BD PG no está limpia:
    entre corridas `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` + `db.migrate`.
  - El tool de escritura de archivos falla si el contenido lleva acentos → usar
    contenido ASCII al crearlo (o editar vía `[System.IO.File]::WriteAllText` con
    `UTF8Encoding($false)`).

## 25. Cierre de SPEC-006 Asientos multilínea (2026-09-20)

Décimo primera spec cerrada (40/40). Total del proyecto: **512/1.384** (11 specs).

- **Servicios** `services/journal/`: `validador_multilinea.py` (`validar_asiento_multilinea`:
  lado_vacio, desbalanceo, precisión >4, importe_negativo, cuenta inexistente/no apuntable,
  límite 100 líneas; cuentas repetidas admitidas; `MultilineaError` con `__first__` +
  `validation_errors`), `motor.py` (`crear_asiento_multilinea` = `crear_borrador` + `asentar`
  de SPEC-002 con numeración `next_numero`, echo `flush()` dentro del boundary `get_db`;
  `obtener_asiento`; `listar_asientos` paginado con filtros estado/fecha) y `anulador.py`
  (`anular_asiento` delega en `reversal.anular` y devuelve el contrato
  `{asiento_rectificativo, asiento_original_id}`).
- **API** `api/journal/asientos.py` (prefix `/api/v1/asientos` + `Depends(get_empresa_id)`):
  `POST /asientos` (201/422), `POST /asientos/{id}/anular` (201/404/409), `GET /asientos`,
  `GET /asientos/{id}`. Registrado en `main.py`; **`importexport_router` se mueve ANTES** de
  `asientos_router` para que las rutas estáticas `/exportar` e `/importar/*` (SPEC-005)
  ganen a la plantilla uuid `/{entry_id}`.
- **Frontend**: `components/journal/line-editor.tsx` (T128: filas dinámicas, Enter añade,
  Ctrl+Supr elimina, balance en tiempo real, autocomplete por código) y
  `app/contabilidad/asientos/nuevo/page.tsx` (T129/T002).
- **Desviaciones**: `reversal.anular` (SPEC-002) marca el original `POSTED → CANCELLED`
  (única transición permitida); "original intacto" = contenido sin cambios, estado pasa a
  CANCELLED por diseño. Import/export (T120/T121) = verificación, sin cambios: exportador
  ya emite una fila por `JournalEntryLine` y el parseador agrupa por `numero_asiento`.
- **Lección**: ORM `session.delete()` sobre SQLite aiosqlite dispara el DELETE antes de un
  `load_on_pk_identity` en contexto síncrono → `MissingGreenlet`; el trigger de
  inmutabilidad se prueba con `pytest.raises(IntegrityError)` y mensaje `inmutable` sin
  re-query posterior. Binding de UUID en tests: usar `uuid.UUID(...)` (la columna se
  almacena como 32-hex; `str` rompe con `.hex`).
- **Verificación**: pytest **644 passed / 5 skipped** (SQLite) y **649 passed / 0 skipped**
  (PostgreSQL 16.4 real, esquema limpio + migraciones 000–006), `ruff` + `mypy` limpios
  (135 fuentes), `tsc` + `eslint` + `next build` **31 rutas** (incl. `/contabilidad/asientos/nuevo`).

## 26. Cierre de SPEC-007 Facturación Operativa (2026-09-20)

Décimo segunda spec cerrada (56/56). Total del proyecto: **568/1.384** (12 specs).

- **Modelos** `models/invoice/`: `serie_factura.py` (`SerieFactura`,
  `UNIQUE(empresa_id, id)` + `UNIQUE(empresa_id, codigo)`, estado `activa|inactiva`,
  `siguiente_numero` como high-water global), `factura.py` (`Factura`, tipos
  `VENTA|COMPRA|RECTIFICATIVA`, estados `borrador|emitida|anulada`, importes
  `NUMERIC(18,4)`, FKs compuestas a serie/tercero/journal_entry/self, único
  `(empresa_id, serie_id, ejercicio, numero)`), `factura_linea.py` (checks `cantidad>0`,
  `precio>0`, descuento 0–100; IVA/recargo/IRPF). Exportados en `models/invoice/__init__.py`
  y registrados en `models/__init__.py`. **Sin migración SQL** (create_all en tests).
- **Servicios** `services/invoicing/`: `errores.py` (`InvoicingError` + `error()`),
  `calculo_impuestos.py` (redondeo línea a línea a 2 dec. y totales a 4 dec.),
  `recargo_equivalencia.py` (tipos 5,20/1,40/0,50; cuenta separada 4772/4722),
  `criterio_caja.py` (`regimen_caja=true`, `iva_devengado=false`, IVA diferido para
  SPEC-012), `numeracion.py` (CRUD series + `next_numero_factura` = `MAX(numero)+1` por
  `(empresa_id, serie_id, ejercicio)` bajo `SELECT ... FOR UPDATE`; serie inactiva → 409),
  `asiento_factura.py` (`construir_lineas` venta 4300 vs 7000+4770(+4772)-4750; compra
  6000+4720(+4722) vs 4100+4750; `crear_asiento_factura` vía motor de SPEC-002/006;
  `crear_asiento_reversal_factura` total invirtiendo el asiento original;
  `crear_asiento_rectificativa` parcial sobre las líneas del abono),
  `emision.py` (`crear_factura_borrador`, `emitir_factura` con número+asiento+POSTED,
  `listar_facturas`, `obtener_factura_detalle`, `eliminar_factura_borrador`,
  `anular_factura` exige rectificativa previa → 409 `sin_rectificativa`),
  `rectificacion.py` (`rectificar_factura`: `factura_original_id` a la raíz del
  encadenamiento, asiento REVERSAL sin tocar el original).
- **API** `api/invoicing/` (paquete, `Depends(get_empresa_id)`; NO `api/invoicing.py`):
  `POST/GET /api/v1/facturacion/series`, `PATCH .../series/{id}/estado`,
  `POST/GET /api/v1/facturacion/facturas`, `GET .../{id}`, `POST .../{id}/emitir|anular|rectificar`
  (anular 409), `DELETE .../{id}` (204). Registrado en `main.py` (facturas + series).
- **Frontend**: `components/invoicing/api.ts` (cliente tipado con JWT + empresa),
  `app/facturacion/facturas/{page,nueva,[id],[id]/rectificar}` y `app/facturacion/series`.
- **Lecciones reutilizables**:
  - Los campos `Numeric` de un objeto ORM recién creado contienen el valor Python asignado:
    asignar `Decimal(...)` (no `str`) o el `f"{factura.importe_total:0.4f}"` del response
    revienta con `ValueError: Unknown format code 'f'`.
  - Rectificación parcial: el REVERSAL debe construirse sobre las **líneas del abono**, no
    sobre el asiento original completo; para total, invertir el asiento original real. La
    `naturaleza` (VENTA/COMPRA) se resuelve subiendo por `factura_original_id` hasta la raíz.
  - Tests con UUID en `text()` crudo (SQLite) requieren `uuid.UUID(x).hex`; en queries ORM,
    `uuid.UUID(x)` (la columna guarda 32-hex).
  - `facturacion_client` (conftest) siembra cuentas fiscales ausentes del PGC base
    (`472/475/477` nivel 3 y `4720/4722/4750/4770/4772` nivel 4), terceros con subcuentas
    430/410 y una serie por empresa.
- **Verificación**: pytest **696 passed / 5 skipped** (SQLite), `ruff` + `mypy` limpios
  (152 fuentes), `tsc` + `eslint` + `next build` **36 rutas** (incl.
  `/facturacion/facturas/nueva` y `/facturacion/series`).

## 27. Cierre de SPEC-010 Cuentas Anuales (2026-09-20)

Décimo tercera spec cerrada (45/45). Total del proyecto: **613/1.384** (13 specs).

- **Modelos** `models/reporting/`: `configuracion.py` (`ConfiguracionInforme`, enum
  `InformeTipo`/`ActividadEfe`, único `(empresa_id, ejercicio, informe_tipo, agrupacion_codigo,
  cuenta_ini)`), `formulacion.py` (`FormulacionCuentasAnuales`, snapshot JSON + `contenido_hash`
  CHAR(64) + `numero_formulacion` correlativo, estado `formulada|anulada`), `control_efe.py`
  (`ClasificacionEfe`, override manual por línea). Sin migración SQL (create_all en tests).
- **Servicios** `services/reporting/`: `saldos.py` (`netos_por_cuenta` POSTED por ejercicio,
  excluyendo cierre/regularización), `agrupacion.py` (`resolver_masa` por rango, `"Otros"` sin
  config), `comparativo.py`, `pyg.py` (`generar_pyg`, coincide con la regularización 129),
  `efe.py` (`generar_efe` directo por contrapartida + `clasificar_movimiento`),
  `formulacion.py` (`generar_balance`, `formular`, `anular_formulacion`, `listar_formulaciones`).
- **API** `api/cuentas_anuales/` (paquete, `Depends(get_empresa_id)`; NO `api/cuentas_anuales.py`):
  `GET /{ejercicio}/{balance,pyg,efe}` (modo provisional|oficial), `PATCH /{ejercicio}/efe/clasificacion`,
  `POST /{ejercicio}/formular|anular-formulacion`, `GET /{ejercicio}/formulaciones`,
  `POST/PATCH /configuracion`. Registrado en `main.py`.
- **Frontend**: `components/reporting/{api.ts,BalanceView,PygView,EfeView}` +
  `app/cuentas-anuales/page.tsx` (pestañas + formular/anular/histórico) y
  `app/{balance,pyg,efe}/page.tsx`.
- **Lecciones reutilizables**:
  - El cierre (`_cerrar_saldos`) **salda todas las cuentas** del ejercicio; para reconstruir el
    balance/PyG de un ejercicio cerrado se excluye el asiento `cierre_entry_id` (y, en PyG, también
    el de regularización) para recuperar los saldos de gestión.
  - El seed PGC **no crea la cuenta 129**; el cierre la exige, así que la fixture `cuentas_client`
    la planta (nivel 3 bajo el subgrupo `12`) antes de cerrar.
  - El cuadre `Activo == Pasivo + Patrimonio` es estructural con partida doble (el resultado de
    gestión se incorpora al patrimonio); `422 balance_descuadrado` queda para datos no balanceados.
  - `modo=oficial` exige `FiscalYear.is_closed` (409 `ejercicio_no_cerrado`); la PyG oficial exige
    coincidencia con la regularización (409 `descuadre_cierre`).
- **Verificación**: pytest **738 passed / 5 skipped** (SQLite) y **743 passed / 0 skipped**
  (PostgreSQL 16.4 real), `ruff` + `mypy` limpios (167 fuentes), `tsc` + `eslint` + `next build`
  **40 rutas** (incl. `/cuentas-anuales`, `/balance`, `/pyg`, `/efe`).

## 28. Cierre de SPEC-012 Libros de IVA y modelos fiscales (2026-09-20)

Décimo cuarta spec cerrada (56/56). Total del proyecto: **669/1.384** (14 specs).

- **Modelos** `models/fiscal/`: `periodo_fiscal.py` (`PeriodoFiscal`, `TipoPeriodo`,
  `EstadoPeriodo`), `exportacion_modelo.py` (`ExportacionModelo`, `ModeloFiscal`,
  `EstadoExportacion`), `configuracion_sii.py` (`ConfiguracionSII`), `configuracion_fiscal.py`
  (`ConfiguracionFiscal`: recargo/criterio de caja + cuenta de recargo) e
  `iva_diferido_caja.py` (`IVADiferidoCaja`, `EstadoDiferido`). Sin migración SQL (create_all
  en tests).
- **Servicios** `services/vat/`: `periodo.py` (`rango_periodo`/`etiqueta_periodo`),
  `configuracion_cuentas.py` (cuentas 472/477 + recargo), `libros_iva.py` (emitidas/recibidas/
  intracomunitarias derivadas de `Factura`+`FacturaLinea` con asiento POSTED; facturas sin
  asiento excluidas), `modelos.py` (`calcular_303`, `resumen_periodico`, `preparar_347` con
  límite 3.005,06 €, `preparar_349`), `exportacion.py` (CSV/XML/JSON, sha256, correlativo),
  `recargo_equivalencia.py`, `criterio_caja.py` (`aplicar_criterio_caja`, `liquidar_diferido`,
  `sincronizar_con_vencimientos`) y `sii.py` (config + XML sin envío).
- **API** `api/fiscal/` (paquete, `Depends(get_empresa_id)`): `GET /libros-iva/{tipo_libro}`,
  `GET /modelos/{303,347,349}`, `POST/GET /exportaciones` y `GET /exportaciones/{id}/descargar`,
  `GET /regimenes/estado` + `POST /regimenes/{recargo-equivalencia,criterio-caja}`,
  `GET/POST /sii/configuracion` y `GET /sii/operaciones/{tipo}`. Registrado en `main.py`.
- **Frontend**: `components/vat/api.ts` + `app/libros-iva/page.tsx`, `app/modelos/page.tsx` y
  `app/exportaciones/page.tsx`.
- **Lecciones reutilizables**:
  - El asiento de SPEC-007 siempre añadía la línea de IVA; para operaciones al 0 %
    (intracomunitarias) genera una línea 0/0 que el validador multilínea rechaza → `construir_lineas`
    ahora omite la línea de IVA cuando la cuota es 0.
  - La clasificación intracomunitaria se resuelve por NIF/VAT (dos letras de país ≠ `ES`) o IBAN no
    español, al no existir flag en SPEC-008.
  - `servicios` de IVA consumen `Factura` (SPEC-007) y solo computan facturas `emitida` con
    `asiento_id`; el `flash()` va dentro del boundary `get_db`.
- **Verificación**: pytest **771 passed / 5 skipped** (SQLite; `test_suggest_perf` es flaky bajo
  carga y pasa aislado) y **776 passed / 0 skipped** (PostgreSQL 16.4 real), `ruff` + `mypy` limpios
  (191 fuentes), `tsc` + `eslint` + `next build` **43 rutas** (incl. `/libros-iva`, `/modelos`,
  `/exportaciones`).

## 29. Cierre de SPEC-014 Amortizaciones del Inmovilizado (2026-09-21)

Décimo quinta spec cerrada (49/49). Total del proyecto: **718/1.384** (15 specs).

- **Modelos** `models/inmovilizado/`: `activo.py` (`ActivoInmovilizado`: `UNIQUE(empresa_id, id)`
  + `UNIQUE(empresa_id, numero_activo)`, coste > 0, vida > 0, método `lineal|regresivo`,
  `porcentaje_regresivo` NUMERIC(5,2) requerido si regresivo, estado `en_uso|dado_de_baja`, FKs
  cuenta/gasto/acumulada nivel 4), `plan_amortizacion.py` (`PlanAmortizacion`,
  `UNIQUE(empresa_id, activo_id, ejercicio, periodo)`, estado `pendiente|amortizado`),
  `amortizacion_generada.py` (`AmortizacionGenerada`, **UNIQUE parcial
  `(empresa_id, activo_id, ejercicio, periodo)` WHERE `reabierta = false`** + `reapertura_de`
  UUID NULL + `created_at`) y `baja_activo.py` (`BajaActivo`, `UNIQUE(empresa_id, activo_id)`,
  precio >= 0, tipo `venta|retirada`). Sin migración SQL (create_all en tests).
- **Servicios** `services/inmovilizado/`: `plan.py` (`calcular_plan(coste, vida_util, metodo,
  porcentaje, fecha_alta, prorrateo="mensual"|"dias")` devuelve filas con `cuota`/`acumulado`
  como **strings de 4 decimales**; ajuste de última cuota; regresivo = simulación natural hasta
  residual 0 con `LIMITE_ROWS_REGRESIVO=1200`; `replanear_pendientes` tras PATCH),
  `activo.py` (`dar_de_alta` valida nivel 4 2xx apuntables, deriva acumulada
  `CUENTA_ACUMULADA_PREFIJO + code[1:3]` → 2100→2810, 2180→2818; `editar_activo` recalcula el plan
  futuro con `_replanear` mutando por `del`), `generacion.py` (`generar_amortizacion` balanceado
  681/281 con numeración `next_numero`; 409 `periodo_ya_amortizado`; `reabrir_amortizacion` crea
  REVERSAL propio **sin cambiar el estado del original** — desviación de `reversal.anular` que
  marca CANCELLED) y `baja.py` (`dar_de_baja(prorrateo=...)` con `fraccion_cuota_baja(fecha_baja,
  prorrateo)`; asiento Debe 281X+5720 (+6710/7710 resultado) | Haber 21X; 422 `fecha_baja_invalida`
  si fecha anterior al alta).
- **API** `api/inmovilizado/` (paquete, `Depends(get_empresa_id)`; NO `api/inmovilizado.py`):
  `activos.py` (`POST /activos`, `POST /activos/plan/calcular`, `GET /activos`, `GET|PATCH
  /activos/{id}`, `POST /activos/{id}/baja`) y `amortizaciones.py` (`POST /amortizaciones/generar`,
  `GET /amortizaciones`, `POST /amortizaciones/{id}/reabrir`). Registrado en `main.py`.
- **Frontend**: `components/inmovilizado/api.ts` + `app/inmovilizado/{page,alta/,[id]/}` y
  `app/inmovilizado/amortizaciones/page.tsx` (listado + reapertura). El detalle `[id]` muestra el
  plan en lectura (los plan rows no llevan `generada_id`; la reapertura se hace desde la página de
  amortizaciones). `app/page.tsx` enlaza a `/inmovilizado`.
- **Lecciones reutilizables**:
  - `AccountPlan` se consulta por `tenant_id` (columna SPEC-001); la empresa activa SIEMPRE vía
    `Depends(get_empresa_id)` (los tests unitarios de API pasan `empresa_id` real de la sesión).
  - Rebind vs `del` en listas: `_replanear` debe borrar con `del pendientes[n:]` porque el caller
    conserva la misma lista (PATCH plan futuro).
  - Los miembros de enum no admiten anotación de tipo (`pendiente: str` → mypy error); el default
    de fixture cae a cuenta 2180 (con `get("2100") or ["2180"]`) porque `_cuentas` no incluye 2100.
  - `listar_amortizaciones`: `select(AmortizacionGenerada).where(*filtros).order_by(...)` (evitar
    NameError de variables sueltas `base`).
- **Verificación**: pytest **820 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky bajo carga,
  verde aislado) y **825 passed / 0 skipped** (PostgreSQL 16.4 real), `ruff` + `mypy` limpios
  (207 fuentes), `tsc` + `eslint` + `next build` **47 rutas** (incl. `/inmovilizado`,
  `/inmovilizado/alta`, `/inmovilizado/[id]`, `/inmovilizado/amortizaciones`). Detalle de
  desviaciones en el **"Estado real"** de `specs/014-amortizaciones-inmovilizado/tasks.md`.

## 30. Cierre de SPEC-015 Matriz de permisos por rol (2026-09-21)

Décimo sexta spec cerrada (48/48). Total del proyecto: **766/1.384** (16 specs).

- **Modelos** `models/rbac/`: `permiso_operacion.py` (`PermisoOperacion`, UNIQUE
  `(modulo, operacion)`, `requiere_datos_contables`), `rol.py` (`Rol`, UNIQUE
  `(empresa_id, id)` y `(empresa_id, nombre)`), `matriz_permiso.py` (`MatrizPermiso`,
  FK compuesta `(empresa_id, rol_id)` → `roles`, UNIQUE `(empresa_id, rol_id, permiso_id)`,
  `concesion_id` UUID sin FK) y `evento_auditoria_acceso.py` (`EventoAuditoriaAcceso`
  inmutable; `operacion` `VARCHAR(40)`, no enum, para auditar operaciones arbitrarias).
- **Servicios** `services/security/`: `catalogo.py` (`CATALOGO` de 10 módulos × operaciones,
  `_ops_por_rol`, `sembrar_catalogo`, `sembrar_seguridad` idempotente),
  `autorizacion.py` (`permiso_operacion`, `rol_de_empresa`, `concesion_activa`, `evaluar`),
  `auditoria_acceso.py` (`registrar(..., commit=False)`; `listar_eventos` con filtros y
  paginación) y `matriz.py` (`conceder`/`revocar`/`reset`/`matriz_empresa`/`mis_permisos`).
- **Guard central** `api/deps.require_permission(modulo, operacion)`: resuelve sesión →
  empresa activa → rol en la empresa → concesión; **deny por defecto**; los deny se
  **commitean antes del 403** y los allow con `requiere_datos_contables` hacen `flush()`
  (transacción única con la operación). Marca `_rbac_permiso` para introspección.
- **API** `api/rbac.py` (`/api/v1/permisos`): catálogo/matriz/auditoría (`rbac/ver`),
  matriz POST/DELETE/reset (`rbac/configurar`; `reset` exige `confirm=true` → 422),
  `mis-permisos` sin guard (excluido). `GET /matriz` devuelve `matriz_id` para revocar.
- **Sin bypass**: `api/routes_registry.py` (`EXCLUSIONES_NO_BYPASS`, `guard_de_ruta`,
  `inventario_permisos`, `rutas_sin_permiso`); recorre routers incluidos
  (`_IncludedRouter.original_router`). Se reemplazó `require_write` por
  `require_permission` en todos los routers de datos y se añadieron guards a las lecturas.
- **Inmutabilidad + seed a nivel DB**: `db/triggers.py` (SQLite) y `migrations/007_rbac.sql`
  (PostgreSQL; `seed_seguridad_empresa` `RETURNS TRIGGER`). **Clave**: el trigger SQLite
  genera ids con `lower(hex(randomblob(16)))` porque `hex()` devuelve mayúsculas y SQLite
  compara texto case-sensitive (rompía la FK compuesta y las búsquedas de la matriz).
- **Frontend**: `components/rbac/{api.ts,permisos-table.tsx}` + `app/permisos/{page,auditoria}`
  (matriz editable condicionada por `mis-permisos`, reset y log de accesos con filtros).
- **Fixtures**: `rbac_client` en `tests/conftest.py` (A=10/B=20, ADMIN/ACCOUNTANT/READ_ONLY
  con vínculo en ambas empresas, PGC sembrado, routers rbac+accounts+journal).
- **Lecciones reutilizables**:
  - `rol_id`/`matriz_id` en el cuerpo/path deben tiparse `uuid.UUID` (con `object`, un str
    con guiones llega a `db.get()` y revienta al serializar el `Uuid` de SQLite).
  - En FastAPI reciente `app.routes` contiene `_IncludedRouter` (perezoso): la
    introspección debe bajar por `original_router.routes`.
  - Los endpoints `DELETE` que delegan en servicios con errores propios deben capturar
    `MatrizError` y mapear a 404/409/422 (si no, 500).
  - Las cuentas nuevas en tests deben colgar de un padre de nivel 3 (`430`) con código
    `430X` (nivel 4) y prefijo correcto; el árbol (`/accounts/tree`) es anidado.
  - `test_suggest_perf` es flaky bajo carga; `test_migrations.ESPERADAS` debe incluir cada
    migración nueva (`007_rbac.sql`).
- **Verificación**: pytest **890 passed / 5 skipped** (SQLite; `test_suggest_perf` aislado
  verde), `ruff` + `mypy` limpios (219 fuentes), `tsc` + `eslint` + `next build` **49 rutas**
  (incl. `/permisos`, `/permisos/auditoria`). Desviaciones en el **"Estado real"** de
  `specs/015-permisos-por-rol/tasks.md`.
## 31. Cierre de SPEC-016 Multi-divisa (2026-09-22)

Décimo séptima spec cerrada (48/48). Total del proyecto: **814/1.384** (17 specs).

- **Modelos** `models/monedas/`: `moneda.py` (`Moneda`, una solo funcional por
  empresa — índice parcial único—, `UNIQUE(empresa_id, codigo_iso)`, código ISO
  4217), `tipo_cambio.py` (`TipoCambio`, `UNIQUE(empresa, divisa, fecha)`, ratio
  NUMERIC(18,8), CHECK `sellado = (usos_posteados > 0)`, sellado inmutable por
  triggers), `asiento_divisa.py` (`AsientoDivisa` 1:1 con `JournalEntry`,
  también `LineaDivisa` con `es_linea_redondeo`), `diferencia_cambio.py`
  (`DiferenciaCambio`, `UNIQUE(empresa, ejercicio, fecha_valoracion, cuenta,
  divisa)` — corregido en esta sesión—, inmutable append-only). Migración
  `008_forex.sql` (triggers sellado + valoración inmutable).
- **Servicios** `services/forex/`: `errores.py`, `conversion.py`
  (`convertir` ROUND_HALF_EVEN a 4 decimales), `monedas.py` (`moneda_funcional`
  EUR perezoso, `registrar_divisa`), `cuentas.py` (`cuenta_diferencia_cambio`
  con Lado y cadena 6680/7690), `tipos.py` (`registrar_tipo`, `corregir_tipo`,
  resolución de tipo por fecha con prioridad: explícito → exacta → ratio del
  body → última anterior, `sellar_tipo`, `obtener_historial_asiento`,
  `historial_tipos` con filtros), `asiento_divisa.py` (`registrar_asiento_divisa`
  con cuadre doble divisa/funcional + línea de redondeo, asiento vía motor de
  SPEC-002, `LineaDivisa` y sellado en la misma transacción; `detalle`),
  `valoracion.py` (saldos vivos por cuenta en divisa, tipo de cierre, asiento
  ADJUSTMENT 668/769 balanceado, `DiferenciaCambio` por período, listado con
  filtros) y `audit` en todas las mutaciones.
- **API** `api/forex/` (paquete, `Depends(get_empresa_id)`; NO `api/forex.py`):
  `GET/POST /api/v1/divisas`, `POST/PATCH/GET /api/v1/tipos-cambio`,
  `GET /api/v1/tipos-cambio/historial` (por asiento, divisa, rango, sellado),
  `POST /api/v1/asientos-divisa`, `GET /api/v1/asientos-divisa/{id}`,
  `POST /api/v1/valoraciones`, `GET /api/v1/diferencias-cambio`. El ratio
  explícito del asiento viaja en `tipo_ratio_explicito: {ratio}`. Todos con
  guards `require_permission("divisas", *)`.
- **Frontend**: `components/forex/api.ts` + `app/divisas/{page,tipos,
  tipos/historial,asientos/nuevo,valoracion}` y enlace en `app/page.tsx`.
  El editor de asiento divide/autocompleta cuentas (`/accounts/suggest`),
  previsualiza el equivalente funcional y avisa del remanente de redondeo.
- **Tests (75 nuevos)**: unit + integration cubriendo T010–T047 (conversión,
  cuadre doble, modelos, aislamiento US1/US2/US3, historial, inmutabilidad,
  constitución, isolación completa, quickstart y batería de redondeo).
- **Lecciones reutilizables**:
  - `sqlite_where`/`postgresql_where` de índices parciales deben usar
    `text(...)`, no string cruda (`_compiler_dispatch`).
  - UUID de SQLite se almacenan como 32-hex: enlazar `uuid.UUID(...)` en
    consultas ORM, nunca `str`.
  - `sum(Decimal)` de líneas: verificar que al valorar un ejercicio abierto sin
    tipos de cierre la API responde 422 `sin_tipo_cierre` antes de crear nada.
  - El fixture `forex_client` (backend) siembra USD para ambas empresas y
    4300/5720; la funcional EUR aparece perezosamente en `moneda_funcional`
    para ambas.
- **Desviaciones**: paquete `api/forex/` vs citado `api/forex.py`; patrón ACID
  del proyecto (`get_db` + flush) en vez de `async with async_session.begin()`
  de la tarea; `PATCH /tipos-cambio` no expone `auditado`; tests T045/T047 en
  `tests/integration/` en vez de `tests/unit/`. Detalle en el "Estado real" de
  `specs/016-multi-divisa/tasks.md`.
- **Verificación**: pytest **965 passed / 5 skipped** (SQLite; `test_suggest_perf`
  flaky bajo carga, verde aislado), `ruff` + `mypy` limpios (236 fuentes),
  `tsc` + `eslint` + `next build` **54 rutas** (incl. `/divisas`,
  `/divisas/tipos`, `/divisas/tipos/historial`, `/divisas/asientos/nuevo`,
  `/divisas/valoracion`).

## 32. Cierre de SPEC-017 Centros de coste (2026-09-22)

Décimo octava spec cerrada (48/48). Total del proyecto: **862/1.384** (18 specs).

- **Modelos** `models/costcenters/`: `centro_coste.py` (`CentroCoste`, tipos
  `departamento|proyecto|subvencion|delegacion`, estados `activo|inactivo`,
  `UNIQUE(empresa_id, codigo)`, FK compuesta `(empresa_id, parent_id)`), `jerarquia.py`
  (`JerarquiaCentro`, closure table con `profundidad` y PK compuesta), `imputacion.py`
  (`ImputacionCentro`, traza append-only por línea, UNIQUE `(empresa_id, asiento_id,
  linea_id)`, `periodo`). `JournalEntryLine.centro_coste_id` en `models/acct/journal.py`.
- **Servicios** `services/costcenters/`: `centros.py` (CRUD + closure con
  `_insertar_closure_nodo`/`_reinsertar_closure_reasignado`, detección de ciclos,
  `estado_duplicado`, `arbol_centros` con profundidad por closure), `imputacion.py`
  (`imputar_linea`, `quitar_imputacion`, `listar_imputaciones`, `rectificar_imputacion`
  → asiento ADJUSTMENT sin tocar el original; líneas POSTED/CANCELLED → 409) e
  `informes.py` (`informe_costes` con subtotales por closure en `Decimal` a 4 decimales,
  `exportar_informe` CSV `;`/UTF-8-BOM y JSON).
- **Migración** `backend/migrations/009_costcenters.sql` (cierre + triggers de
  inmutabilidad de `imputacion_centro` y borrado protegido de `centro_coste`); triggers
  SQLite equivalentes en `db/triggers.py`.
- **API** `api/costcenters/` (paquete; router en `__init__.py`, re-export en `routes.py`):
  `POST|GET /api/v1/centros`, `GET /api/v1/centros/arbol`, `GET|PATCH /api/v1/centros/{id}`,
  `POST .../{id}/inactivar|reactivar`, `POST .../asientos/{id}/lineas/{lid}/imputar`,
  `DELETE .../imputar`, `GET /api/v1/imputaciones`, `GET /api/v1/informes/costes`,
  `GET /api/v1/informes/costes/exportar`. `empresa_id` siempre vía `Depends(get_empresa_id)`.
- **RBAC**: SPEC-017 añade el módulo `centros` al catálogo `services/security/catalogo.py`
  (10→11 módulos, +13 concesiones: ADMIN 8 + ACCOUNTANT 4 + READ_ONLY 1); la migración
  `007_rbac.sql`/trigger SQLite y los recuentos de tests RBAC se actualizaron.
- **Frontend**: `components/costcenters/{api.ts,CentroSelect.tsx}`,
  `app/centros/{page,nuevo}`, `app/informes/costes`, selector de centro en
  `components/journal/line-editor.tsx`.
- **Tests (90 nuevos)**: unit `test_costcenter_models`, `test_centro_arbol`,
  `test_centro_restricciones`, `test_centro_subvencion`, `test_imputacion_balance`,
  `test_imputacion_inmutable`, `test_imputacion_inmutable_db`, `test_imputacion_centro_valido`,
  `test_constitucion_costcenters`, `test_informe_{agregacion,subtotales,periodo}`;
  integration `test_costcenter_tenant_isolation`, `test_centro_arbol_integration`,
  `test_centro_tenant`, `test_imputacion_{completa,tenant}`,
  `test_informe_{completo,tenant}`, `test_costcenters_full_tenant_isolation`,
  `test_quickstart_costcenters`. Fixture `costcenters_client` en `tests/conftest.py`.
- **Lecciones reutilizables**:
  - Los servicios devuelven `id` como `str`; al pasarlo a otra función de servicio hay que
    convertirlo con `uuid.UUID(...)` (un `str` en un bind de columna `Uuid` revienta con
    `'str' object has no attribute 'hex'`).
  - Los `text()` con parámetros UUID usan el hex de 32 chars (`x.id.hex`, sin guiones);
    `rollback()` expira las instancias ORM, así que hay que capturar `id.hex` antes de
    revertir.
  - `db.scalars(select(a, b, c))` devuelve solo la primera columna; para varias columnas usar
    `db.execute(...).all()`.
  - `func.count().select_from(...)` no existe: es `select(func.count()).select_from(...)`.
  - Cuentas PGC apuntables del seed: 1110/1320/2100/2500/2810/3000/4000/4100/4300/4700/
    5720/6000/6210/6400/6810/7000 (la 570 nivel 3 NO es apuntable).
  - Tests de triggers SQLite deben esperar `sqlalchemy.exc.IntegrityError`, no `Exception`.
- **Verificación**: pytest **1055 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky
  bajo carga, verde aislado), `ruff` + `mypy` limpios (251 fuentes),
  `tsc` + `eslint` + `next build` **57 rutas** (incl. `/centros`, `/centros/nuevo`,
  `/informes/costes`).
## 33. Cierre de SPEC-018 Plantillas de asientos (2026-09-22)

Décimo novena spec cerrada (42/42). Total del proyecto: **904/1.384** (19 specs).

- **Modelos** `models/templates/`: `plantilla.py` (`PlantillaAsiento`, UNIQUE
  `(empresa_id, id)` y `(empresa_id, nombre)`, estado `activa|inactiva`,
  `version_actual`), `variable.py` (`VariablePlantilla`, tipo `importe`), `linea.py`
  (`LineaPlantilla`, CHECK fijo/variable excluyente y FK compuesta a `account_plan`) y
  `asiento_generado.py` (traza inmutable, PK `(empresa_id, asiento_id)`,
  `variables_aportadas` JSON).
- **Servicios** `services/templates/`: `errores.py` (`TemplateError`), `plantillas.py`
  (CRUD con validación de líneas D1 y cuentas del plan SPEC-001; `actualizar_plantilla`
  incrementa `version_actual` solo si cambian líneas/variables) y `generacion.py`
  (`generar_asiento` resuelve variables por id o nombre, omite variables opcionales
  vacías y delega en `crear_asiento_multilinea` de SPEC-006; `listar_generados`).
- **Migración** `backend/migrations/010_templates.sql` (registrada en `ORDEN_PREFERENTE`
  y `test_migrations.ESPERADAS`): tablas + enums + triggers `asiento_generado`
  append-only y `plantilla_asiento` sin borrado con generados; triggers SQLite en
  `db/triggers.py`.
- **API** `api/templates/` (`prefix=/api/v1/plantillas`, `Depends(get_empresa_id)` y
  guards `require_permission` del módulo `treasury`): POST/GET, GET/PATCH `{id}`,
  POST `{id}/activar|inactivar|generar`, GET `{id}/generados`. Registrado en `main.py`.
- **Frontend**: `components/templates/{api.ts,TemplateEditor.tsx}` (editor de líneas con
  autocompletado de cuentas, posición, fijo/variable y alta de variables),
  `app/plantillas/{page,nueva,[id],[id]/generar}` (generación con vista previa, balance
  en vivo y confirmación; atajo Ctrl+Enter).
- **Tests (54, 51 nuevos)**: unit e integración de alta, restricciones, generación
  (balance/variables/cuentas/ejercicio), inmutabilidad, estados, aislamiento multi-tenant
  (US1–US3), constitución, quickstart (6 escenarios) y correlatividad. Fixture
  `templates_client` en `tests/conftest.py`.
- **Lecciones reutilizables**:
  - `actualizar_plantilla` necesita `flush()` tras reinsertar variables y antes de las
    líneas; en caso contrario la FK compuesta de `linea_plantilla` falla en SQLite.
  - Los binds de columnas `Uuid` y `obtener_asiento` exigen `uuid.UUID(...)` (un `str`
    revienta con `'str' object has no attribute 'hex'`).
  - Next.js 15 (App Router) obliga a leer `params` con `useParams<{ id: string }>()` en
    páginas dinámicas cliente; la firma `{ params }` como objeto rompe `next build`.
  - El borrado físico de una plantilla sin generados exige borrar antes líneas y
    variables (FK); con `AsientoGenerado` está prohibido por trigger.
- **Desviaciones**: guards sobre el módulo `treasury` (no se creó un módulo `templates`);
  la generación llama a `crear_asiento_multilinea` (SPEC-006) en vez de `journal_engine`
  nominal; `PlantillaAsiento.id` es UUID (no BIGINT del data-model).
- **Verificación**: pytest **1109 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky
  bajo carga, verde aislado), `ruff` + `mypy` limpios (263 fuentes), `tsc` + `eslint` +
  `next build` **61 rutas** (4 nuevas: `/plantillas`, `/plantillas/nueva`, detalle y
  `/generar`). Migración 010 aplicada sobre PostgreSQL 16.4 real; 5 tests opt-in en verde.

## 34. Cierre de SPEC-019 Gestión ONG (2026-09-23)

Vigésima spec cerrada (53/53). Total del proyecto: **957/1.384** (20 specs).

- **Modelos** `models/ngo/`: `subvencion.py` (`Subvencion`, `SubvencionEstado`, UNIQUE
  `(empresa_id, referencia)`, `partidas` JSON `Mapped[list[str] | None]`), `gasto_imputado.py`
  (FK compuesta a subvención, duplicado por `(empresa_id, asiento_id, linea_id)` SIN
  subvencion_id → una línea por subvención), `libros.py` (`LibroOficial` BYTEA+sha256, tipo
  `diario|mayor|balance|pyg`; `Legalizacion` con rango/huella/fichero y índice parcial
  `(empresa_id, ejercicio)` WHERE valido), `caja.py` (`Caja` con 570 única por empresa +
  `MovimientoCaja` traza del diario), `arqueo.py` (`Arqueo`, diferencia = efectivo − saldo).
- **Migración** `backend/migrations/011_ngo.sql` + triggers SQLite en `db/triggers.py`:
  inmutabilidad de `libro_oficial`/`movimiento_caja`/`legalizacion` y
  `trg_journal_entry_legalizado_insert` (**FR-007 a nivel DB**: bloquea INSERT de asientos en
  ejercicio legalizado; verificado en contrato con `IntegrityError` y en motor con 422).
- **Servicios** `services/ngo/`: `subvenciones.py` (CRUD + transiciones, `asiento_rectificativo_id`
  obligatorio al reintegrar), `justificacion.py` (`imputar_gasto` valida línea de la empresa y
  tipo gasto 6xx, `SELECT ... FOR UPDATE`, disponibles por línea/subvención; **desimputación =
  DELETE auditado, NO append-only**; informe con canon + huella sha256; export CSV BOM/JSON),
  `libros_pdf.py` (canon 4 decimales + PDF reportlab con pie `Debe = … | Haber = …`,
  sha256 libro == huella legalización), `legalizacion.py` (fichero `.txt` 11 líneas `LEGALIZACION
  V1`, re-emisión solo huella idéntica), `caja.py` (`saldo_570` derivado del diario,
  `registrar_movimiento` crea asiento motor 572↔570 ACID, ejercicio cerrado → 409),
  `arqueo.py` (auto-aprobación si cuadra; aprobar con diferencia exige asiento de ajuste que
  cuadra la 570; archivar = pendiente visible).
- **API** `api/ngo/` (paquete; `deps.get_empresa_activa` desde sesión + `require_permission`
  módulo `ngo`): subvenciones/gastos/informes, libros (±generar/descarga), legalizaciones
  (±descarga), cajas (±movimientos/inactivar), arqueos (±aprobar/archivar). **Mapeo HTTP**:
  `subvencion_no_encontrada`/`caja_no_encontrada` → 404; conflictos → 409; `ejercicio_invalido`
  → 422.
- **RBAC**: módulo `ngo` añadido al catálogo (11→12 módulos, 147 items); migración `007_rbac.sql`
  actualizada.
- **FR-007** (refuerzo motor): `entry_service._validar_ejercicio` orden `ejercicio_invalido` →
  `_ejercicio_cerrado` (FY inexistente = abierto) → `_ejercicio_legalizado`; `api/journal/
  asientos.py` mapea `ejercicio_cerrado/invalido` → 400 y `ejercicio_legalizado` → 422.
- **Frontend**: `components/ngo/{api.ts,CuentaPicker.tsx}` + `app/ong/{subvenciones,
  subvenciones/[id],libros,caja,caja/[id]}`; enlace en `app/page.tsx`. **66 rutas** (5 nuevas).
  Páginas dinámicas con `useParams<{ id: string }>()`.
- **Tests (62 SPEC-019)**: 34 unit + 17 integration + 11 contract. Contratos verificados con
  pypdf (extracción del PDF: encabezado/pie por página, 4 decimales, cierre sumas) y formato
  del fichero de legalización (líneas exactas, HUELLA recalculable). FR-007 probado motor + DB.
- **Lecciones reutilizables**:
  - Fixture `ngo_client`: `get(empresa_id, ruta, **params)` (empresa PRIMERO) vs
    `post/patch/delete(ruta, empresa_id=10)`; `_run` crea event loop nuevo por llamada →
    resolver ids de cuenta FUERA de `ns.run(ns.mutar(...))`.
  - `Mapped[dict | None]` en una columna JSON que guarda listas rompe mypy al asignar
    `list[str]` → tipar `Mapped[list[str] | None]`.
  - La inmutabilidad WORM de una tabla no debe aplicarse a filas que se deshacen con
    intención (gasto imputado): uso DELETE + auditoría, no trigger.
  - La empresa/fecha en los stores no deben pasar en body/path (constitución III): los tests
    de tenant aislamiento validan 404 cross-empresa en cada endpoint.
  - `test_suggest_perf` sigue flaky bajo carga (verde aislado); no es un fallo de SPEC-019.
- **Verificación**: pytest **1171 passed / 5 skipped** (SQLite; `test_suggest_perf` verde
  aislado), `ruff` + `mypy` limpios (285 fuentes), `tsc` + `eslint` + `next build` **66 rutas**
  (5 nuevas: `/ong/subvenciones`, `/ong/subvenciones/[id]`, `/ong/libros`, `/ong/caja`,
  `/ong/caja/[id]`).
- **Desviaciones** (detalle en "Estado real" de `specs/019-gestion-ong-libros-caja/tasks.md`):
  frontend agrupado en `app/ong/*`; multi-tenant/quickstart/correlatividad sin archivos
  dedicados con los nombres nominales (cubiertos en los tests de aislamiento/justificación);
  `GastoImputado` no es inmutable (DELETE auditado); FR-007 en `entry_service` (motor) no en
  `acct/journal_engine.py`; `TestClient` del contrato usa el router ngo completo.

## 35. Cierre de SPEC-021 Medios de pago y efectos (2026-09-23, cont.)

Vigésima primera spec cerrada (44/44). Total del proyecto: **1.001/1.384** (21 specs).

- **Modelos** `models/treasury/`: `efecto.py` (`Efecto`; `TipoEfecto` CHEQUE/PAGARE/LETRA;
  `EstadoEfecto` emitido/cobrado/impagado; checks importe>0 y `fecha_vencimiento >=
  fecha_emision`; UNIQUE `(empresa_id, tercero_id, tipo_efecto, numero_documento)`; índices
  `(empresa_id, estado, fecha_vencimiento)` y `(empresa_id, tercero_id)`),
  `cobro_medio.py` (`CobroMedio`, `MedioCobro` de 6 valores; checks `comision <= total`,
  `neto >= 0`; índices por empresa/fecha y empresa/medio), `comision.py` (`ComisionBancaria`,
  `TipoComision` TPV/TRANSFERENCIA/CHEQUE/CAJA/OTRA; FK compuesta
  `(empresa_id, cobro_medio_id)`; `cuenta_contable` DEFAULT `'626'`).
- **Migración** `backend/migrations/012_efectos.sql` (enums + 3 tablas + índices + triggers
  `trg_efecto_final_immutable_update/_delete` que bloquean UPDATE/DELETE de efectos en estado
  final). Registrada en `db/migrate.py` (`ORDEN_PREFERENTE`) y `test_migrations.ESPERADAS`;
  espejo SQLite en `db/triggers.py`.
- **Servicios** `services/treasury/`: `common.py` (`TesoreriaError`, constantes de cuenta
  430/431/400/401/572/570/626 y `ejercicio_abierto`), `efecto.py` (`registrar_efecto`,
  `cobrar_efecto` COBRO 572↔431, `impagar_efecto` REVERSAL 431(+626)↔572 con reapertura de
  vencimientos del tercero), `cartera.py` (`consultar_cartera`, `agrupar_cartera`,
  `detalle_efecto`), `cobro_medio.py` (`registrar_cobro_medio` Debe 572 neto + 626 comisión |
  Haber 430; `listar_cobros_medio`, `detalle_cobro_medio`).
- **API** `api/treasury/{efectos,cobros_medio}.py` (registrados en `routes.py`), todos con
  `Depends(get_empresa_id)` + `require_permission("treasury", …)`: `POST/GET /api/v1/efectos`,
  `GET /efectos/{id}`, `POST …/cobrar`, `POST …/impago`; `POST/GET /api/v1/cobros-medio`,
  `GET /cobros-medio/{id}`. Errores con `detail={code, detail}`.
- **Frontend**: `components/treasury/api.ts` (+tipos y helpers), `app/efectos/{page,nuevo,[id]}`,
  `app/tesoreria/{page,cobros}`, enlaces en `app/page.tsx`. **72 rutas** (6 nuevas).
- **Tests (90 SPEC-021)**: unit `test_efecto_models`, `test_efecto_services` (T011–T013),
  `test_cobro_medio_services` (T024–T025), `test_cartera` (T031–T032),
  `test_constitucion_efectos` (T039); integration `test_efecto_routes` (T021–T023),
  `test_cobro_medio_routes` (T029–T030), `test_efectos_full_tenant_isolation`
  (T010/T023/T030/T037/T038/T040) y `test_quickstart_efectos` (6 escenarios, T041).
  Fixture `efectos_client` (A=10/B=20, PGC, tercero y 2 vencimientos pendientes por empresa,
  usuario ADMIN y `FiscalYear` 2025 cerrado por empresa).
- **Lecciones reutilizables**:
  - Al validar que el **tercero pertenece a la empresa activa** (`tercero_no_encontrado`, 404)
    hay que sembrar el `Tercero` en los tests unitarios: los ids de `Tercero` son **PK global
    (single-column)**, así que dos empresas no pueden compartir el mismo UUID.
  - `f"{Decimal(0):0.4f}"` para importes; patrón `^\d+(\.\d{1,4})?$` en el body.
  - Los triggers SQLite de inmutabilidad se disparan al **ejecutar** el `UPDATE` core (no al
    `flush`); envolver el `execute` en `pytest.raises(IntegrityError)`.
  - Tras `commit()`/`rollback()` las instancias ORM quedan expiradas: capturar el atributo
    (p. ej. `asiento_id`) **antes** de commitear para evitar `MissingGreenlet`.
  - En fixtures HTTP, `_body(...)` con `empresa_id=10` por defecto puede usar el tercero de la
    empresa equivocada; pasar siempre `empresa_id` explícito en el segundo tenant.
- **Desviaciones** (detalle en "Estado real" de `specs/021-medios-pago-efectos/tasks.md`):
  reapertura de vencimientos *best-effort* por tercero (el modelo no tiene `vencimiento_id`);
  asientos construidos a bajo nivel (no `crear_asiento_multilinea`); nombres de test agrupados;
  boundary ACID del proyecto (`get_db` + `flush`) en vez de `async with async_session.begin()`.
- **Verificación**: pytest **1261 passed / 5 skipped** (SQLite; `test_suggest_perf` flaky bajo
  carga, verde aislado), `ruff` + `mypy` limpios (294 fuentes), `tsc` + `eslint` + `next build`
  **72 rutas** (6 nuevas: `/efectos`, `/efectos/nuevo`, `/efectos/[id]`, `/tesoreria`,
  `/tesoreria/cobros`).

## 36. Cierre de SPEC-022 Anticipos, fondos a cuenta y cesión de cobros (2026-09-24)

Vigésimo segunda spec cerrada (48/48). Total del proyecto: **1.049/1.384** (22 specs).

- **Modelos** `models/treasury/`: `anticipo.py` (`Anticipo`, tipos `CLIENTE|PROVEEDOR`,
  estados `pendiente|parcialmente_aplicado|totalmente_aplicado`, `TipoAnticipo`
  `CLIENTE|PROVEEDOR`; `saldo_pendiente >= 0`, `importe` y `saldo_pendiente`
  `NUMERIC(18,4)`), `liquidacion_anticipo.py` (`LiquidacionAnticipo` con
  CheckConstraint `importe_aplicado > 0`), `cesion.py` (`CesionCobro` +
  `CesionCobroDetalle` con UNIQUE `(empresa_id, cesion_id, vencimiento_id)`;
  `TipoComisionCesion` `IMPORTE_FIJO|PORCENTAJE`; `EstadoCesion`
  `activa|saldada|cancelada`), `notificacion_cesion.py` (`MedioNotificacion`
  `EMAIL|CORREO|REGISTRO`). `EstadoVencimiento.cedido` añadido. Migración
  `backend/migrations/013_anticipos.sql` + `db/migrate.py` + `test_migrations.py`
  actualizados.
- **Servicios** `services/treasury/`: `common.py` (constantes `CUENTA_ACREEDORES_SERVICIOS`
  410, `CUENTA_ANTICIPOS_CLIENTES` 438, `CUENTA_ANTICIPOS_PROVEEDORES` 407,
  `CUENTA_ACREEDORES_PENDIENTES_FACTURA` 408, `CUENTA_INTERESES_DEUDAS` 662),
  `anticipo.py` (`registrar_anticipo`: CLIENTE Debe 572 | Haber 438, PROVEEDOR
  Debe 407/408 | Haber 572, `ejercicio_abierto`, auditoría `REGISTRAR_ANTICIPO`;
  listado/detalle con liquidaciones), `liquidacion.py` (`liquidar_anticipo`:
  Debe 430/410 | Haber 438/407 según tipo; **422 `importe_supera_saldo` si una
  aplicación individual excede el saldo; 409 `saldo_insuficiente` si la suma
  acumulada lo excede**; actualiza estado y saldo; auditoría `LIQUIDAR_ANTICIPO`),
  `cesion.py` (`registrar_cesion` Debe 572 neto + 662 comisión | Haber 430 total,
  validación de vencimientos `pendientes`, 409 `vencimiento_no_pendiente`,
  422 `sin_vencimientos`; `registrar_notificacion` valida `cliente_no_asociado`;
  `saldar_cesion` 409 `cesion_no_activa`; listado/detalle con vencimientos y
  notificaciones; `contar_vencimientos`).
- **Endpoints** `api/treasury/{anticipos,cesiones}.py` (registrados en `routes.py`):
  `POST/GET /api/v1/anticipos`, `GET /{id}`, `GET /{id}/liquidaciones`,
  `POST /{id}/liquidar`; `POST/GET /{id}/cesiones`, `GET /{id}`,
  `POST /{id}/notificar`, `POST /{id}/saldar`. Todos con `get_empresa_id` +
  `require_permission("treasury", ...)` y respuesta `{code, detail}`.
- **Fix cross-spec**: `api/treasury/vencimientos.py::_raise` mapea ahora
  `vencimiento_cedido` → **409** (quickstart SC4 exige 409; antes caía al 422 genérico).
- **Frontend**: `components/treasury/api.ts` (+tipos/funciones anticipos/cesiones/
  vencimientos), `app/anticipos/{page,nuevo,[id]}`, `app/cesiones/{page,nueva,[id]}`,
  enlaces en `app/page.tsx`. **78 rutas** (6 nuevas).
- **Tests (44 SPEC-022)**: unit `test_anticipo_models` (T011), `test_anticipo_{cliente
  _balance,liquidacion_cliente_balance,exceso}` (T013–T015), `test_anticipo_{proveedor
  _balance,liquidacion_proveedor_balance}` (T024–T025), `test_cesion_{balance,
  doble_cobro,vencimientos_pendientes}` (T031–T033), `test_constitucion_anticipos`
  (T043); integration `test_anticipo_tenant_isolation` (T012), `test_anticipo_{cliente
  _completo,tenant}` (T022–T023), `test_anticipo_{proveedor_completo,prov_tenant}`
  (T029–T030), `test_cesion_{completa,tenant}` (T041–T042),
  `test_anticipos_full_tenant_isolation` (T044), `test_quickstart_anticipos`
  (SC1–SC6, T045), `test_anticipos_ejercicios_cerrados` (T047). Helper compartido
  `tests/unit/anticipo_support.py` (`sembrar_base`, `sumas`, `cuentas`, constantes
  `CLIENTE`/`PROVEEDOR` con ids únicos). Fixture `anticipos_client` en conftest
  (A=10/B=20, PGC, FY2025 cerrado, terceros cliente+proveedor, serie, factura
  venta/compra, vencimientos, usuario ADMIN).
- **RBAC**: todos los endpoints bajo el módulo `treasury` existente (no se creó un
  módulo `anticipos`/`cesiones` nuevo).
- **Lecciones reutilizables**:
  - En tests, UUIDs **string** en bodies JSON (si no, `TypeError: Object of type UUID is
    not JSON serializable`); al filtrar/bindear columnas `Uuid` → `uuid.UUID(str(...))`
    (si no, `AttributeError: 'str' object has no attribute 'hex'`); callbacks de
    `api.consultar`/`api.mutar` `async def` (si no, `coroutine' object has no attribute
    'all'`).
  - `Vencimiento` exige `iban` en test (`"ES9121000418450200051332"`) y el `Tercero`
    tiene PK global: dos empresas no pueden compartir el mismo UUID → en aislamiento
    pasar `cliente_id`/`proveedor_id` distintos.
  - Tras `rollback()` el objeto recién creado desaparece (rollback de la transacción):
    para probar inmutabilidad basta con el `IntegrityError` del trigger con mensaje
    `inmutable`; no re-query del asiento.
  - `sembrar_base` parametrizable con `n_vencimientos`, `cliente_id`, `proveedor_id`.
- **Desviaciones** (detalle en "Estado real" de `specs/022-anticipos-cesion-cobros/
  tasks.md`): las FK a `factura`/`tercero`/`vencimiento` en la migración PG
  `013_anticipos.sql` son columnas UUID planas (sin constraint FK; los modelos
  SQLAlchemy sí las declaran para SQLite create_all); boundary ACID del proyecto
  (`get_db` + `flush`) en vez de `async with async_session.begin()` del texto de T046;
  guards sobre el módulo `treasury`; `TipoAnticipo`/`EstadoAnticipo` en `anticipo.py`.
- **Verificación**: pytest **1304 passed / 5 skipped** (SQLite; `test_suggest_perf`
  flaky bajo carga, verde aislado), ruff + mypy limpios (303 fuentes), `tsc` +
  `eslint` + `next build` **78 rutas** (6 nuevas: `/anticipos`, `/anticipos/nuevo`,
  `/anticipos/[id]`, `/cesiones`, `/cesiones/nueva`, `/cesiones/[id]`).

## 37. Cierre de SPEC-023 Impuesto sobre Sociedades / Modelo 200 (2026-09-24)

Vigésimo tercera spec cerrada (44/44). Total del proyecto: **1.093/1.384** (23 specs).

- **Modelos**: `CalculoIS` (Decimal/`NUMERIC(18,4)`, tipo `NUMERIC(5,2)`, estados
  `borrador|calculado|contabilizado`, índice parcial único por empresa/ejercicio para
  definitivos), `AjusteExtracontable` y `Modelo200`; `ConfiguracionFiscal` amplía
  `tipo_is` y vigencia. Todos usan UUID + `UNIQUE(empresa_id,id)`, FKs compuestas y
  `empresa_id` en índices/filtros.
- **Migración `014_impuesto_sociedades.sql`**: crea/alinea configuración y tablas del IS,
  añade el seed PGC 63/630/6300/473/4730/475/4752/4709 y triggers de cálculo final
  inmutable, ajustes bloqueados tras contabilizar y Modelo 200 append-only. Espejo
  SQLite en `db/triggers.py`; aplicada y verificada sobre PostgreSQL 16 real.
- **Servicios** `services/fiscal/impuesto_sociedades.py`: cálculo desde asientos POSTED
  6/7, exclusión de regularización/cierre y asientos IS, pagos netos 473, ajustes
  positivos/negativos/deducciones, tipo vigente, cálculo provisional/definitivo,
  listados tenant-scoped y configuración fiscal. Las mutaciones auditan usuario, IP,
  UTC, operación y payload decimal en la misma transacción.
- **Contabilización**: asiento POSTED correlativo y balanceado con hojas reales
  `6300/4730/4752/4709`; a pagar `6300 | 4730 + 4752`, a devolver
  `6300 + 4709 | 4730`, y cero diferencial `6300 | 4730`. El original queda inmutable.
- **Modelo 200** `services/fiscal/modelo_200_gen.py`: exige cálculo contabilizado,
  valida las cuatro ecuaciones, genera exactamente cinco bloques, JSON canónico,
  SHA-256, persistencia append-only y descarga CSV UTF-8 autenticada.
- **API**: `api/fiscal/{calculos_is,modelo_200}.py` bajo `/api/v1/fiscal/is`, con
  `get_empresa_id` + RBAC `fiscal`, listados, ajustes, contabilización, configuración y
  modelos; errores 404/409/422 con `{code,detail}`. Nunca acepta `empresa_id` del cliente.
- **Frontend**: `components/fiscal/api.ts` y páginas `/fiscal/impuesto-sociedades`
  (listado), `/nuevo`, `/[id]` y `/fiscal/modelo-200`; importes siempre como strings
  de cuatro decimales y descarga autenticada por blob. **80 rutas** en total.
- **Pruebas**: 49 pruebas backend SPEC-023 verdes (modelos, US1/US2/US3, quickstart,
  constitución, aislamiento y RBAC) + **4 passed** del contrato PostgreSQL 16 para
  migración 014. Fixture `is_client` con empresas 10/20, PGC, P&L, pagos 473 y
  ejercicios 2025 cerrado / 2026 abierto.
- **Desviaciones**: boundary ACID real del proyecto (`get_db` + `flush`) en lugar del
  `async_session.begin()` literal de T042; cuentas apuntables de nivel 4 representadas
  por hojas 6300/4730/4752/4709; dirección no disponible en `Company` se exporta como
  `null`; el definitivo exige ejercicio cerrado y su contabilización usa el servicio
  fiscal explícito con validación de partida doble, dado que el motor genérico rechaza
  ejercicios cerrados.
- **Verificación**: suite completa **1354 passed / 5 skipped**; el único fallo de la
  corrida fue `test_suggest_perf` (flaky conocido), **2 passed** aislado. Ruff + mypy
  limpios (312 fuentes), `tsc` + ESLint + `next build` verdes; migración 000–014 aplicada
  sobre PostgreSQL 16 real.

## 38. Cierre de SPEC-024 Retenciones IRPF y Modelos 111/115/190 (2026-09-25)

Vigésima cuarta spec cerrada (48/48). Total del proyecto: **1.141/1.384** (24 specs).

- **Modelos**: `RetencionPeriodo`, `LiquidacionRetenciones`, `Modelo111`, `Modelo115`
  y `Modelo190`; UUID + `UNIQUE(empresa_id,id)`, FKs compuestas, uniques por trimestre,
  `NUMERIC(18,4)` y estado final. `FacturaLinea` incorpora categoría IRPF y dirección
  de inmueble para separar profesionales, arrendamientos, obras y otros.
- **Migración `015_retenciones_irpf.sql`**: tablas, checks, unicidades, FKs cross-tenant,
  triggers append-only y de liquidación final, backfill/seed de 4751 y trigger para nuevas
  empresas. Espejo SQLite en `db/triggers.py`; aplicada sobre PostgreSQL 16 real.
- **Acumulación** `services/fiscal/retenciones.py`: facturas con asiento del trimestre
  natural,signo negativo para rectificativas, agrupación por tercero/categoría/tasa,
  excluye borradores, conserva el snapshot de facturas, audita y hace `flush()` dentro del
  boundary `get_db`.
- **Modelos 111/115/190**: cuatro bloques contractuales, totales cuadrados, JSON canónico,
  SHA-256, persistencia append-only y CSV UTF-8 BOM descargable con autenticación. El 190
  agrupa Q1–Q4 y bloquea la generación si falta o no es válido algún NIF.
- **Liquidación**: `contabilizar_liquidacion` bloquea la fila, valida estado/total/cuentas y
  crea un asiento POSTED correlativo `Debe 4751 | Haber cuenta bancaria`; marca la liquidación
  como final y audita en la misma ACID. Doble contabilización devuelve 409.
- **API**: `/api/v1/fiscal/retenciones` con `get_empresa_id` + RBAC `fiscal`; liquidaciones,
  retenciones, contabilización, modelos 111/115/190, validación NIF, listados y descargas.
  Todos los cuerpos devuelven importes con cuatro decimales y nunca aceptan `empresa_id`.
- **Frontend**: `components/fiscal/api.ts` ampliado y páginas `/fiscal/retenciones`,
  `/fiscal/retenciones/nueva`, `/fiscal/retenciones/[id]` y `/fiscal/modelos/190`, con
  descarga autenticada por blob. **85 rutas** en total.
- **Pruebas**: **56 nuevas** para modelos, US1/US2/US3, cuadre exacto, auditoría, inmutabilidad,
  rectificativas, API, aislamiento y los seis escenarios quickstart. PostgreSQL 16:
  **5 passed** para migración 015, seed 4751, unicidades y triggers.
- **Desviaciones**: el boundary ACID autoritativo es `get_db` + `flush()`; PostgreSQL aún
  no migra `factura_linea`/`tercero` de SPEC-007/008, por lo que la FK y columnas se crean
  condicionalmente cuando existan; las categorías legacy se infieren por porcentaje solo
  cuando la línea no trae clasificación explícita; el 190 exporta `null` para domicilio
  desestructurado no disponible.
- **Verificación**: **1410 passed / 7 skipped** (las 2 pruebas `test_suggest_perf` verdes
  aisladas), PostgreSQL **5 passed**, ruff + mypy limpios (324 fuentes), `tsc` + ESLint +
  `next build` verdes.

## 39. Cierre de SPEC-025 Catálogo versionado del plan de cuentas (2026-09-26)

Vigésima quinta spec cerrada (47/47). Total del proyecto: **1.188/1.384** (25 specs).

- **Modelos** `models/catalog/`: `catalogo_version.py` (`CatalogoVersion` con estados
  `borrador|activa|anulada`, `es_migracion` para la reserva PGC 2025 y unicidad
  `(empresa_id, numero_version)`), `catalogo_cuenta.py` (`CatalogoCuenta`: proyección por
  versión con `codigo_version`/`nombre_version`, estado `igual|renombrada|suprimida|nueva`,
  unicidades `(empresa_id, version_id, account_id)` y `(…, codigo_version)` y FKs
  compuestas), `mapeo_cuenta.py` (`MapeoCuenta` origen/destino con `tipo_movimiento`,
  `requiere_reclasificacion` y `origen` `manifiesto|autogenerado`) y
  `reclasificacion_saldo.py` (`ReclasificacionSaldo` con `importe NUMERIC(18,4)`, estado
  `borrador|contabilizado|cuadrado` y `asiento_id` a `journal_entry`). Todos con UUID,
  `UNIQUE(empresa_id, id)` y `empresa_id` en índices/FKs (constitución III).
- **Migración `016_catalogo.sql`**: 4 tablas, enums, unicidades, checks e índices
  multi-tenant + función y trigger **`trg_catalogo_version_vigencia`** (BEFORE
  INSERT/UPDATE) que rechaza el **solape de vigencia por empresa** (FR-006) en el punto
  más cercano a la persistencia; el servicio replica la regla para devolver 422 legible.
  Registrada en `db/migrate.py` (`ORDEN_PREFERENTE`) y `test_migrations.ESPERADAS`;
  espejo SQLite en `db/triggers.py`; aplicada y verificada sobre PostgreSQL 16 real.
- **Servicios** `services/catalog/`: `_comun.py` (proyección de la versión a partir de
  `account_plan`, helpers `validar_codigo`/`cuentas_plan`/`obtener_version`),
  `versiones.py` (`registrar_version` correlativa por empresa, `activar_version` con
  reserva de vigencia y 409 si queda alguna `borrador`, `version_vigente` por fecha),
  `importacion_catalogo.py` (manifiesto CSV/JSON con `alta|renombrado|baja`, `previsualizar`
  y `confirmar`, mapeo automático por código y reporte de `pendientes_mapeo`),
  `mapeo.py` (versión anterior y mapeos de una versión) y `reclasificacion_saldos.py`
  (`previsualizar` tenant-scoped sobre saldos POSTED y `confirmar_reclasificacion` con
  asientos `ADJUSTMENT` correlativos y balanceados vía motor de SPEC-002, sin tocar los
  asientos históricos). Auditoría y `flush()` dentro del boundary `get_db`.
- **API** `api/catalogo.py` (registrado en `main.py`): `POST/GET /api/v1/catalogo/versiones`,
  `POST .../activar`, `GET .../vigente?fecha=`, `GET .../cuentas`, `GET .../mapeos`,
  `POST .../importar/preview`, `POST .../importar/confirmar` (multipart) y
  `POST .../reclasificar/{preview,confirmar}`, todo con `get_empresa_id` y guards
  `require_permission("catalogos", …)`; errores `404/409/422` con `{code, detail}` y
  `empresa_id` **nunca** en body ni path.
- **RBAC**: módulo `catalogos` añadido al catálogo de `services/security/catalogo.py` y a
  la migración `007_rbac.sql`.
- **Frontend**: `components/catalog/api.ts` y páginas `/catalogo` (listado con filtro de
  estado), `/catalogo/[id]` (detalle, activar, versión vigente en fecha, cuentas y
  mapeos con código de origen), `/catalogo/importar` (fichero + pendientes de mapeo) y
  `/catalogo/reclasificar` (preview, confirmación y asientos enlazados a
  `/asientos/[id]`), más el enlace en `app/page.tsx`. **89 rutas** en total.
- **Pruebas (88 nuevas)**: 59 unitarias (`test_catalogo_models`, `test_catalogo_versiones`,
  `test_catalogo_importacion`, `test_catalogo_mapeo`, `test_catalogo_reclasificacion`,
  `test_catalogo_constitucion`, `test_catalogo_rbac`, …) y 29 de integración
  (`test_catalogo_tenant_isolation`, `test_resolucion_integration`, `test_catalogo_tenant_us1`,
  `test_import_completa`, `test_import_tenant`, `test_reclasificacion_apertura`,
  `test_reclasificacion_tenant`, `test_catalogo_full_tenant`, `test_quickstart_catalogo`).
  PostgreSQL 16: **6 passed** (migración 016, trigger de vigencia, unicidades y rango).
- **Lecciones reutilizables**:
  - `MapeoVersion.cuenta_origen_id` es el **id de la fila `CatalogoCuenta`** de la versión
    origen, no de `account_plan`: para mostrar códigos hay que cargar también esa versión.
  - La proyección de una versión excluye las cuentas `renombrada`/`suprimida`, por lo que
    una cuenta ya renombrada en una versión anterior conserva su nombre y **no puede
    renombrarse de nuevo** (comportamiento aceptado y documentado en el quickstart).
  - Los enums de la migración 016 son **en minúsculas** (`'borrador'`, `'activa'`, …); en
    los contratos PG hay que respetar las minúsculas.
  - La versión PGC 2025 se crea por código de reserva (`es_migracion`); las versiones de
    normativa arrancan en el número 2.
  - Si el temp del usuario borra directorios vacíos del cluster portable, PostgreSQL no
    arranca (`could not open directory "pg_logical/mappings"`): recrear
    `pg_logical/{mappings,snapshots}`, `pg_multixact/{members,offsets}` y
    `pg_wal/archive_status` con `New-Item -ItemType Directory`.
  - La suite completa tarda ~11 min: lanzarla en segundo plano con log y consultar el
    fichero, porque el pipe no devuelve salida hasta el final.
- **Desviaciones**: el boundary ACID autoritativo es `get_db` + `flush()` (no
  `async with async_session.begin()`); `api/catalogo.py` es un módulo suelto (no paquete)
  por seguir la convención de `api/rbac.py`; los tests T045/T047 viven en `tests/unit/`
  y el contrato PostgreSQL en `tests/integration/test_pg_schema.py`.
- **Verificación**: **1497 passed / 8 skipped** (las 2 pruebas `test_suggest_perf` verdes
  aisladas), PostgreSQL 16 **6 passed**, ruff + mypy limpios (**337 fuentes**), `tsc` +
  ESLint + `next build` verdes con migraciones `000`–`016` aplicadas sobre PostgreSQL real.

## 40. Cierre de SPEC-026 Presupuestos y Desviaciones (2026-09-26, cont.)

Vigésima sexta spec cerrada (42/42). Total del proyecto: **1.230/1.384** (26 specs).

- **Modelos** `models/budget/`: `presupuesto.py` (`Presupuesto` por combinación
  cuenta-centro-ejercicio; unicidad FR-005 mediante **dos** indices parciales UNIQUE
  `uq_presupuesto_sin_centro`/`uq_presupuesto_con_centro`, porque `centro_coste_id`
  es NULLABLE y NULL no colisiona en un UNIQUE normal),
  `periodo_seguimiento.py` (`PeriodoSeguimiento` con `numero_periodo` correlativo
  por (empresa, ejercicio) e indice parcial `uq_periodo_seguimiento_abierto` para el
  "solo un periodo abierto por ejercicio"; transición única `abierto -> cerrado` con
  `fecha_cierre`/`cerrado_por`) y `desviacion.py` (`Desviacion` snapshot append-only,
  `desviacion_relativa NUMERIC(7,4)`, mismos dos indices parciales). Todos con
  `UNIQUE(empresa_id, id)`, FKs compuestas por `empresa_id` y `empresa_id` en índices.
- **Migración `017_presupuestos.sql`**: 3 tablas, 2 enums, unicidades, checks,
  índices parciales, 4 FKs compuestas cross-tenant y función `f_desviacion_append_only()`
  con los triggers `trg_desviacion_append_only_update/_delete` (constitución II en el
  punto más cercano a la persistencia). Registrada en `db/migrate.py` (`ORDEN_PREFERENTE`)
  y `test_migrations.ESPERADAS`; espejo SQLite en `db/triggers.py`.
- **Servicios** `services/budget/`: `errores.py` (`PresupuestoError` con `code` +
  `status_code`), `utils.py` (convención de signos D2 `calcular_real`, desviación
  absoluta/relativa, cuantización `c4`/`c4_ratio` a 4 decimales, `cuenta_grupo`),
  `periodos.py` (correlatividad con `SELECT ... FOR UPDATE`, `asegurar_periodo`,
  `crear_periodo`, `cerrar_periodo`), `presupuesto_service.py` (`guardar_presupuesto`
  idempotente por combinación, `importar_presupuesto` atómico, `listar_presupuestos`),
  `desviaciones.py` (`calcular_desviaciones` agrega `SUM(Debe)`/`SUM(Haber)` del diario
  POSTED por combinación y solo grupos 6/7, `obtener_periodo_actual`,
  `desviaciones_de_periodo`), `informe_desviacion.py` (`generar_informe_desviacion` con
  totales, subtotales por centro y lectura opcional desde el snapshot;
  `filas_desde_snapshot`) y `cierre_periodo.py` (`cerrar_periodo_desviaciones` persiste
  el snapshot e invierte el periodo en la misma transacción, `listar_snapshots`).
- **API** `api/presupuestos.py` (módulo suelto, prefijo `/api/v1/presupuestos`):
  `POST/GET ""`, `POST /importar` (multipart CSV/JSON), `GET/POST /periodos`,
  `GET /seguimiento`, `GET /seguimiento/periodo`, `GET /seguimiento/snapshot`,
  `GET /informes/desviacion`, `POST /informes/cerrar`. Todos con
  `Depends(get_empresa_id)` y guards `require_permission("presupuestos", ...)`;
  errores como `{"code", "detail"}` con 404/409/422; `empresa_id` **nunca** en body ni path.
- **RBAC**: módulo `presupuestos` añadido al catálogo de `services/security/catalogo.py`,
  a la migración `007_rbac.sql` y al trigger SQLite `trg_companies_rbac_seed`
  (12 módulos de negocio, 98 permisos, 160 concesiones por empresa). Recuentos de
  `test_matriz_evaluacion`, `test_rbac_tenant_models` y `test_quickstart_rbac` actualizados.
- **Frontend**: `components/budget/api.ts` (cliente tipado + `formatearImporte`/
  `formatearPorcentaje`), `app/presupuestos/page.tsx` (listado + alta + importación CSV),
  `app/presupuestos/seguimiento/page.tsx` (tabla comparativa con filtros
  ejercicio/mes/cuenta/centro) y `app/presupuestos/informes/page.tsx` (totales, subtotales
  por centro, tabla de cierre y botón "Cerrar periodo" con confirmación, más apertura de
  un periodo nuevo). Enlace en `app/page.tsx`. **92 rutas**.
- **Pruebas (164 nuevas)**: 74 unitarias (`test_budget_models` 12, `test_presupuesto_duplicado` 5,
  `test_cuenta_inapunteable` 8, `test_desviacion_absoluta` 12, `test_desviacion_relativa` 9,
  `test_sin_presupuesto` 7, `test_informe_desviacion_completo` 5, `test_cierre_snapshot` 7,
  `test_cierre_bloqueo` 9, `test_constitucion_presupuestos` 15; helper compartido
  `tests/unit/budget_support.py`) y 90 de integración (`test_budget_tenant_isolation` 5,
  `test_importar_presupuesto` 12, `test_presupuesto_tenant` 6, `test_seguimiento_completo` 11,
  `test_seguimiento_tenant` 6, `test_cierre_completo` 7, `test_cierre_tenant` 5,
  `test_presupuestos_full_tenant` 6, `test_quickstart_presupuestos` 8 con los 5 escenarios
  del quickstart). Fixture `presupuestos_client` en `conftest.py` (empresas A=10/B=20, PGC,
  centro de coste, tres usuarios con matriz RBAC, helpers de asientos y ejercicio cerrado).
  PostgreSQL 16: `test_presupuestos_unicidad_y_snapshot_en_postgresql` en
  `tests/integration/test_pg_schema.py`.
- **Lecciones reutilizables**:
  - **NULL no colisiona en un UNIQUE**: para hacer efectiva la unicidad con una columna
    opcional hacen falta **dos** indices parciales UNIQUE (uno `WHERE col IS NULL` y otro
    `WHERE col IS NOT NULL`), en SQLite (`Index(..., sqlite_where=..., postgresql_where=...)`)
    y en PostgreSQL.
  - **El signo del real depende del grupo PGC**: la agregación necesita
    `account_plan.code` (grupo 6 = `SUM(Debe)`, 7 = `SUM(Haber)`), no solo `account_id`.
    Por eso el seguimiento se limita a los grupos 6 y 7: mezclar cuentas de balance
    anularía los totales del informe por partida doble.
  - `db.execute(select(Modelo))` devuelve tuplas (`.all()`), no instancias: usar
    `db.scalars(...)` cuando se filtran atributos de una entidad.
  - Al añadir un módulo RBAC hay que actualizar **los tres** sitios coherentes
    (`catalogo.py`, `007_rbac.sql`, trigger `trg_companies_rbac_seed`) y los recuentos
    de permisos/concesiones de los tests de SPEC-015.
  - Un test con el **mismo nombre de fichero** en `tests/unit/` y `tests/integration/`
    rompe la recolección de pytest (import mode `prepend` sin `__init__.py`).
  - Los triggers SQLite de inmutabilidad se disparan al ejecutar el `UPDATE`/`DELETE`
    core; envolver el `execute` en `pytest.raises(IntegrityError)`.
- **Desviaciones** (detalle en "Estado real" de `specs/026-presupuestos-desviaciones/tasks.md`):
  el boundary ACID autoritativo es `get_db` + `flush()` (no `async_session.begin()` literal
  de T032/T040); `cuenta_id` es `BIGINT` (el id real de `account_plan`), no `UUID` como
  dice el `data-model.md`; `desviacion_relativa` se satura al rango de `NUMERIC(7,4)`;
  solo los grupos 6/7 admiten presupuesto (`cuenta_no_presupuestable` 422);
  `guardar_presupuesto` es idempotente por combinación (el 422 `duplicado_identico` se
  reserva al POST simple con importe idéntico) y la importación acepta `permitir_identico`;
  el ejercicio de un CSV se deduce del nombre del fichero (`presupuesto_2026.csv`);
  se añaden `GET/POST /periodos` y `GET /seguimiento/snapshot` (necesarios para el ciclo
  abrir/cerrar y la consulta del snapshot, ausentes del contrato);
  T028 nombra `test_informe_completo.py`, que ya existe en `tests/integration/` de SPEC-017,
  por lo que el test vive en `tests/unit/test_informe_desviacion_completo.py`.
- **Verificación**: suite completa **1651 passed / 9 skipped** (`tests/unit` 918 passed,
  `tests/integration` 717 passed / 9 skipped, `tests/contract` 16 passed); el único fallo
  de la corrida fue `test_suggest_perf` (flaky conocido bajo carga de SPEC-001), **2 passed**
  aislado. PostgreSQL 16 real: migraciones 000–017 aplicadas sobre esquema limpio y
  **7 passed** en `test_pg_schema.py`. ruff + mypy limpios (**350 fuentes**), `tsc` +
  ESLint + `next build` verdes con **92 rutas**.

## 41. Cierre de SPEC-027 Previsión de Tesorería (2026-09-26, cont.)

Vigésima séptima spec cerrada (45/45). Total del proyecto: **1.275/1.384** (27 specs).

- **Modelos** `models/treasury/`: `prevision.py` (`PrevisionTesoreria` +
  `GranularidadPrevision`/`EstadoPrevision`), `movimiento_prevision.py`
  (`MovimientoPrevision` + `Origen`/`Tipo`/`Frecuencia`), `alerta_liquidez.py`
  (`AlertaLiquidez`, una por bucket con CHECK `saldo_proyectado < 0`) y `efe.py`
  (`InformeEFE` + `LineaEFE`, `BloqueEFE`, `EstadoInformeEFE`). Todos con
  `UNIQUE(empresa_id, id)`, FKs compuestas por `empresa_id` e importes
  `NUMERIC(18,4)`.
- **Columnas anadidas**: `PrevisionTesoreria.plan_manual` (JSON) y
  `MovimientoPrevision.motivo_exclusion`. La primera es el *plan* manual del
  usuario: sin ella, regenerar con otro rango perdía los pagos recurrentes y una
  reprogramación por alerta. La segunda persiste el código de exclusión
  (`vencido`/`cobrado`/`anulado`/`sin_fecha`) para el detalle, con CHECK en ambos
  sentidos (excluido exige motivo, incluido lo prohíbe).
- **Servicios** `services/cashflow/`: `utils.py` (cuantización, buckets,
  recurrencias), `clasificacion_actividad.py` (bloque por grupo PGC),
  `saldos.py` (saldo de tesorería del diario SPEC-002 y de la conciliación
  SPEC-013, research D1), `proyeccion.py` (US1), `efe.py` (US2), `alertas.py`
  (US3), `errores.py`.
- **Migración `018_cashflow.sql`**: 5 tablas, 9 enums, unicidades, checks,
  índices, 4 FKs compuestas cross-tenant y los triggers append-only
  `trg_informe_efe_*` / `trg_linea_efe_*`. Registrada en `db/migrate.py` y
  `test_migrations.ESPERADAS`; espejo SQLite en `db/triggers.py`.
- **API** `api/tesoreria.py` (prefijo `/api/v1/tesoreria`, `Depends(get_empresa_id)`
  + guards `require_permission("treasury", …)`), registrado en `main.py`:
  `GET/POST /previsiones`, `GET /previsiones/{id}`,
  `POST /previsiones/{id}/regenerar`, `POST /previsiones/{id}/movimientos`,
  `GET /alertas`, `POST /alertas/{id}/atender|ignorar`, `GET /efe`,
  `POST /efe/formular`.
- **Frontend** `components/cashflow/api.ts` y `app/tesoreria/{previsiones,
  previsiones/[id], efe, alertas}`, enlazados desde `app/tesoreria/page.tsx` y
  `app/page.tsx`. **95 rutas** (4 nuevas).
- **Pruebas (300 nuevas)**: 152 unitarias y 146 de integración, más 2 en el
  contrato PostgreSQL 16. Helper `tests/unit/cashflow_support.py` y fixture HTTP
  `cashflow_client` (A=10/B=20, tres roles con matriz RBAC, PGC, asientos,
  cuentas, conciliación y ejercicio cerrado). Los 5 escenarios de `quickstart.md`
  se reproducen en `test_quickstart_cashflow.py`.
- **RBAC**: se reutiliza el módulo **`treasury`** del catálogo (no se creó un
  módulo `tesoreria`), como en SPEC-018/021/022. Operaciones: ver/crear/editar/cerrar.
- **Constitución V**: `test_constitucion_cashflow.py` (21) verifica que ningún
  módulo del cashflow anota ni declara `float`, que las columnas de importe son
  `NUMERIC(18,4)`, que ninguna ruta acepta `empresa_id` del cliente, que el EFE
  cuadra contra el diario POSTED y que el snapshot formulado rechaza UPDATE/DELETE.
  `test_cashflow_review.py` (32) revisa por AST el boundary ACID, los type hints,
  los docstrings, la auditoría y la cobertura RBAC.
- **Desviaciones** (detalle en "Estado real" de
  `specs/027-prevision-tesoreria/tasks.md`): el boundary ACID autoritativo es
  `get_db` + `flush()` (no el `async_session.begin()` literal de T016/T043);
  fichero nuevo `services/cashflow/saldos.py` (el saldo inicial lo usan US1 y US2);
  los buckets se calculan en el GET en vez de persistirse (el `data-model.md` no
  define tabla de líneas de bucket); regenerar es un refresco **en el sitio** que
  conserva `numero_prevision` y reexpande el plan manual; un movimiento manual sin
  fecha se **excluye con motivo** (edge case del spec) en lugar de 422; una alerta
  por **periodo negativo** (SC-004), no por racha; la prevision vive en
  `app/tesoreria/previsiones/` porque `app/tesoreria/page.tsx` es el panel de
  SPEC-021; se añaden `POST /previsiones/{id}/regenerar` y
  `POST /previsiones/{id}/movimientos` al contrato; la FK a `Vencimiento` (SPEC-011,
  sin migración propia) va dentro de `IF to_regclass(...) IS NOT NULL` como
  `tercero` en 015.
- **Lecciones reutilizables**:
  - **Mutar en sitio un `JSON` sin `MutableList`/`flag_modified` no lo ve
    SQLAlchemy**: el `UPDATE` se pierde en silencio. Reconstruir lista y dicts
    (bug real detectado por T038: la reprogramación no se conservaba).
  - **El saldo acumulado debe arrancar en `saldo_inicial`**, no en cero: si no,
    `saldo_final` y la serie de buckets divergen sin error (bug real de T014).
  - `db.scalars(...)` hay que terminarlo en `.all()`; `len(resultado)` falla.
  - Los tests `async def` no pueden usar fixtures HTTP síncronas que crean su
    propio event loop (`Cannot run the event loop while another loop is running`):
    el test que llama a `cf.mutar(...)` debe ser `def`.
  - Una FK a una tabla sin migración propia (`vencimiento` de SPEC-011, `tercero` de
    SPEC-008) debe ir dentro de un `IF to_regclass(...) IS NOT NULL` en el `.sql`:
    si no, `db.migrate` aborta con `UndefinedTableError`.
  - El CHECK `diferencia = saldo_banco - saldo_libros` de SPEC-013 no admite
    decimales no representables en binario (SQLite guarda `NUMERIC` como REAL):
    usar diferencias con representación exacta en los tests de migración.
- **Verificación**: suite completa **1951 passed / 11 skipped** (SQLite); el único
  fallo de la corrida fue `test_suggest_perf` (flaky conocido bajo carga de
  SPEC-001), **2 passed** aislado. PostgreSQL 18.6 real: migraciones 000–018 aplicadas
  sobre esquema limpio y **9 passed** en `test_pg_schema.py`; la suite completa contra PostgreSQL da **1962 passed / 0 skipped**. ruff + mypy limpios
  (**363 fuentes**), `tsc` + ESLint + `next build` verdes con **95 rutas**.

## 42. Cierre de SPEC-028 Cierre intermedio y reapertura controlada (2026-09-26, cont.)

Vigésima octava spec cerrada (57/57). Total del proyecto: **1.332/1.432** (28 specs).

- **Modelos** `models/closing/`: `periodo_cerrado.py` (`PeriodoCerrado` con clave
  natural `(empresa_id, ejercicio, tipo, periodo)` y estados
  `abierto/cerrado/reabierto_ajuste/cerrado_ajustado`), `balanza_periodo.py`
  (`BalanzaPeriodo` + `BalanzaPeriodoLinea`, snapshot inmutable con
  `sha256`), `cierre_ejercicio.py` (`CierreEjercicio`, `UNIQUE (empresa_id, ejercicio)`
  = idempotencia del cierre anual), `solicitud_reapertura.py`
  (`SolicitudReapertura` con índice parcial de una sola solicitud **activa** por
  periodo) y `secuencia_reapertura.py` (constitución IV).
- **Ampliación de `JournalEntry`**: al enum `tipo` se añaden `REGULARIZACION` y
  `CIERRE`; `REVERSAL`, `ADJUSTMENT` y `OPENING` ya existían. `reverses_id` y
  `cierre_id` del `data-model.md` **ya existían** como `original_id` y
  `referencia_cierre_id`, así que no se añadieron columnas. `crear_borrador`
  acepta ahora `original_id` para enlazar un rectificativo **al crearlo**
  (un POSTED es inmutable: asignarlo después lo rechaza el trigger).
- **Bloqueo de periodos (research D9, doble protección)**:
  `services/closing/reglas_cierre.py::validar_periodo_abierto`, invocado por
  `_persist_entrada` y `asentar` del motor de SPEC-002, y trigger
  `chk_journal_entry_fecha_abierta` (PostgreSQL + espejo SQLite). Solo bloquean
  los estados `cerrado` y `cerrado_ajustado`: un periodo en `reabierto_ajuste`
  admite el asiento rectificativo. Los tipos `REGULARIZACION`/`CIERRE`/
  `OPENING`/`OPENING_REVERSAL` están exentos porque el cierre anual se fecha el
  último día del ejercicio, dentro del último mes cerrado.
- **Servicios** `services/closing/`: `reglas_cierre.py` (calendario de periodos y
  habilitación de reaperturas que cruza SPEC-010/019/023), `balanza.py`
  (snapshot con cuadre estricto + huella SHA-256 canónica), `periodo.py`
  (cierre intermedio, listado y calendario), `cierre_anual.py`
  (regularización 6/7 → 129, cierre de saldos, bloqueo y apertura de SPEC-009),
  `reapertura.py` (solicitud/aprobación/rechazo/rectificación) y `secuencia.py`.
- **Migración `019_cierres.sql`**: 5 tablas, 5 enums, CHECK `total_debe =
  total_haber`, unicidad natural del periodo, unicidad de una solicitud activa
  por periodo (índice parcial), 2 CHECK de justificación y 6 triggers
  (4 append-only del snapshot, `no_delete` del cierre anual y el de bloqueo de
  fecha). Registrada en `db/migrate.py` (`ORDEN_PREFERENTE`) y
  `test_migrations.ESPERADAS`; espejo en `db/triggers.py`.
- **API** `api/closing.py` (`/api/v1/cierres`, 11 endpoints) con módulo RBAC
  propio **`cierres`** sembrado en los tres sitios coherentes
  (`catalogo.py`, `007_rbac.sql`, `trg_companies_rbac_seed`): 14 módulos, 106
  permisos y 173 concesiones por empresa. `aprobar` es exclusiva de ADMIN.
- **Frontend** `components/closing/{api.ts,BalanzaTabla.tsx}` y
  `app/cierres/{page,intermedio,anual,reaperturas,[id]}`; enlace en
  `app/page.tsx`. **100 rutas** (5 nuevas).
- **Pruebas (276 nuevas)**: 122 unitarias (`test_periodo_cerrado`,
  `test_balanza_cuadre`, `test_reglas_reapertura`, `test_cierre_anual_balance`,
  `test_reapertura_reversal_balance`, `test_constitucion_closing`,
  `test_closing_review`), 101 de integración/contrato
  (`test_closing_tenant_isolation`, `test_cierre_intermedio_flujo`,
  `test_cierre_anual_flujo`, `test_reapertura_flujo`, `test_quickstart_closing`,
  `test_closing_cross_modulo`, `test_closing_api_contracts`) y 2 en el contrato
  PostgreSQL. Helper `tests/unit/closing_support.py` y fixture HTTP
  `closing_client` (A=10/B=20, tres roles con matriz RBAC, PGC, cuenta 129
  plantada y ejercicios 2025–2027).
- **Desviaciones** (detalle en "Estado real" de
  `specs/028-cierre-intermedio/tasks.md`): el boundary ACID autoritativo es
  `get_db` + `flush()` (no `async_session.begin()` literal de T019/T032/T044/T046);
  `cerrado_por`/`usuario_solicitante` son `VARCHAR(120)` (el `User.id` es
  BIGINT); no hay tabla de calendario de periodos (research D2 la descarta) y el
  listado con `ejercicio`+`tipo` devuelve el calendario fusionado; `aprobar`
  deja la solicitud en `reabierta` en un paso (dos acciones de auditoría);
  `cuenta_id` de la balanza es `BIGINT`; `resultado_ejercicio` usa signo de
  beneficio; se añade `GET /reaperturas/{id}` y el periodo asociado se llama
  `periodo_cerrado` para no chocar con el número de `periodo`.
- **Lecciones reutilizables**:
  - `balanza_periodo` referencia `periodo_cerrado`: el periodo se inserta
    **antes** del snapshot o la FK compuesta falla.
  - Un `PeriodoCerrado` en `reabierto_ajuste` no es bloqueante, y por tanto su
    mes vuelve a contar como pendiente para el cierre anual (`meses_cubiertos`).
  - `original_id` de un rectificativo debe fijarse al crear el asiento: un
    UPDATE sobre un POSTED lo rechaza `trg_journal_entry_immutable_update`.
  - Un `tipo` de periodo desconocido lanzaba `ValueError` (HTTP 500); ahora se
    coacciona a 422 `tipo_periodo_invalido` (`tipo_periodo_de`).
  - `resultado_ejercicio` debe ser `ingresos - gastos`: con la suma bruta de

    `debe - haber` un beneficio salía negativo.
  - La apertura de SPEC-009 solo balancea si el **libro** tiene grupos 1-3
    autocuadrados: un dataset con toda la actividad en 4/5/6/7 produce una
    apertura de un solo lado y el ciclo la omite en silencio.
  - En los contratos PostgreSQL cada `pytest.raises` debe ir en su propia
    transacción **al nivel de función**: anidado dentro de la transacción de
    inserts abre otra conexión que no ve las filas sin confirmar y el trigger no
    llega a dispararse. Conviene además un `empresa_id` aleatorio por corrida
    para que el test sea re-ejecutable sin recrear la base.
  - Las pruebas de frontend y backend comparten nombre de campo: si la API
    renombra `periodo` a `periodo_cerrado`, hay que actualizar también los tests
    de integración que leen ese JSON.
- **Verificación**: suite completa **2280 passed / 13 skipped** (SQLite); el único
  fallo de la corrida fue `test_suggest_perf` (flaky conocido bajo carga de
  SPEC-001), **2 passed** aislado. PostgreSQL 18.6 real: migraciones 000–019
  aplicadas sobre esquema limpio y **11 passed** en `test_pg_schema.py`; la
  suite completa contra PostgreSQL da **2293 passed / 0 skipped**. ruff + mypy
  limpios (**377 fuentes**), `tsc` + ESLint + `next build` verdes con
  **100 rutas**.

## 43. Cierre de SPEC-029 Exportación integral del tenant y enlace SII (2026-09-27)

Vigésima novena spec cerrada (52/52). Total del proyecto: **1.384/1.432** (29 specs).

- **Modelos** `models/export/`: `exportacion.py` (`Exportacion` con
  `UNIQUE(empresa_id, anio_creacion, numero_exportacion)`, CHECK de rango,
  `ESTADOS_FINALES` y propiedades `nombre_fichero`/`descargable`/`por_megabytes`),
  `manifiesto.py` (`ManifiestoExportacion` con `UNIQUE(empresa_id, exportacion_id)` y
  `tenant_id` redundante para verificar la tensión; `ManifiestoBloque` con conteo,
  huella y `fecha_min/max` + `ejercicio_min/max`; `FORMATO_VERSION = "1.0.0"`),
  `blob_exportacion.py` (`BYTEA` con `UNIQUE(empresa_id, exportacion_id)`) y
  `config_sii.py` (`ConfigSii`, `UNIQUE(empresa_id)`, coexiste con la
  `ConfiguracionSII` de SPEC-012 y `sii.config_efectiva` la usa de respaldo).
  Registrados en `models/__init__.py`.
- **Servicios** `services/export/`: `errores.py` (`ExportError` con `code` +
  `status_code`, patrón de SPEC-026/027/028), `serializacion.py`
  (`DecimalEncoder`, `cuatro_decimales` con ROUND_HALF_EVEN, `iso_utc` con sufijo `Z`,
  `volcar_json` determinista, base64 para `LargeBinary`), `bloques.py` (el catálogo
  `BLOQUES` de los **17 bloques obligatorios** de FR-004 más la entrada opcional
  `datos_sii`; cada `TablaBloque` declara su `empresa_col` **obligatoria** —
  `tenant_id` en `account_plan`, `company_id` en `companies` —, su columna de
  ejercicio/fecha, su tabla padre y `filtra_rango`), `recopilar.py`
  (`construir_consulta_bloque` y `recopilar_bloque` con `db.stream()` y lotes de
  `LOTE_REGISTROS = 10.000`), `manifiesto.py` (`generar_manifiesto`,
  `contenido_digest`), `zip_generator.py` (`escribir_zip` con `ZipInfo` de
  `FECHA_ZIP = (1980,1,1,0,0,0)`, `external_attr` y `create_system` fijos, escritura
  `sorted()` y `LIMITE_BYTES = 100 MiB`), `persistir.py` (`asignar_numero` con
  `SELECT ... FOR UPDATE` + UNIQUE como red, `exportar_tenant` con SAVEPOINT y
  cabecera `fallida` auditada, `detalle_exportacion`), `verificar.py`
  (`verificar_contenido` devuelve `{integro, sha256_calculado, sha256_manifiesto,
  sha256_contenido, bloques[], diferencias[]}` y captura `BadZipFile`/`zlib.error`)
  y `sii.py` (`config_efectiva`, `generar_bloque_sii`, `entradas_sii`,
  `cuadra` para `EstadoCuadre`).
- **Migración `020_export.sql`**: 5 tablas (2 enums), unicidades, checks, índices,
  3 FKs compuestas cross-tenant, `chk_exportacion_immutable_*` (la exportación en
  `lista`/`fallida` rechaza UPDATE/DELETE; solo se admite `en_proceso → lista|fallida`)
  y los append-only de manifiesto y blob con `CREATE OR REPLACE TRIGGER`
  (PostgreSQL 14+: atómico e idempotente en una sentencia). Registrada en
  `db/migrate.py` (`ORDEN_PREFERENTE`) y `test_migrations.ESPERADAS`; espejo
  SQLite en `db/triggers.py`. **Idempotente**: dos pases seguidos de `db.migrate`
  sobre el mismo esquema.
- **API** `api/export.py` (prefijo `/api/v1/exportaciones`, `get_empresa_id` +
  `require_permission("export", …)`): `POST ""` (201), `GET ""`, `GET/PUT
  /sii/config`, `GET /{id}`, `GET /{id}/descarga` (409 si no está `lista`),
  `POST /{id}/verificar` y `GET /{id}/sii` (422 si no es tipo SII). Registrado en
  `main.py`; las rutas estáticas `/sii/config` se declaran antes que
  `/{exportacion_id}`.
- **RBAC**: módulo propio **`export`** con `ver`, `crear` y `configurar` sembrado en
  `catalogo.py`, `migrations/007_rbac.sql` y `trg_companies_rbac_seed`: **15 módulos,
  109 permisos y 179 concesiones** por empresa. Recuentos de SPEC-015 actualizados
  (`test_matriz_evaluacion`, `test_quickstart_rbac`, `test_rbac_tenant_models`).
- **Frontend** `components/export/{api.ts,ManifiestoEstado.tsx,DescargaExport.tsx}` y
  `app/exportaciones/{page.tsx,nueva/page.tsx,[id]/page.tsx}`; `put` añadido a
  `services/client.ts`; enlace en `app/page.tsx`. **103 rutas** (3 nuevas).
- **Pruebas (245 nuevas)**: 92 unitarias (`test_manifiesto` con las 4 partes,
  `test_zip_layout`, `test_hash_integridad`, `test_precision_decimal_export`,
  `test_config_sii`, `test_constitucion_export`, `test_export_review`), 99 de
  integración/contrato (`test_export_completo`, `test_export_rango_ejercicio`,
  `test_export_tenant_isolation` con las 4 partes + escenario final, T048,
  `test_verificar_integridad`, `test_bloque_sii`, `test_quickstart_export` con los 6
  escenarios, `test_export_limites`), 30 de contrato API
  (`tests/contract/test_export_api_contracts.py`) y 5 en el contrato PostgreSQL.
  Helper `tests/unit/export_support.py` y fixture `export_client` (A=10/B=20, tres
  roles con matriz RBAC, PGC, facturas de venta y compra, asientos de 2025 y 2026,
  vencimiento y `ConfigSii` solo en A; `TestClient(..., raise_server_exceptions=False)`
  para que un fallo de generación sea un 500 y no una excepción de test).
- **Desviaciones** (detalle en "Estado real" de
  `specs/029-export-integral/tasks.md`): boundary ACID `get_db` + `flush()` con
  SAVEPOINT; el `manifest.json` interior **no puede** contener el hash de sí mismo,
  así que lleva `sha256_contenido` y la huella del binario completo vive en la base de
  datos y la API; `creado_por` es `VARCHAR(120)` (`users.id` es BIGINT); numeración
  correlativa sin tabla de secuencia; el filtro de rango compara **fechas** (no
  `EXTRACT`, inexistente en SQLite) y `created_at` nunca filtra;
  `CREATE OR REPLACE TRIGGER` en la migración 020; `TestClient` con
  `raise_server_exceptions=False`; el test de volumen usa 300 asientos y 120 terceros
  en lugar de 10.000/1.000 para no alargar la suite.
- **Lecciones reutilizables**:
  - **El `manifest.json` no puede llevar el SHA-256 del propio ZIP.** Hay que
    separar `sha256_contenido` (dentro) y `sha256_fichero` (fuera, en la base de
    datos y la API). La Asumption del spec es imposible de fulfilment literalmente.
  - **`DROP TRIGGER IF EXISTS` + `CREATE TRIGGER` en un mismo lote multi-sentencia
    falla con `DuplicateObjectError` al reaplicar** (asyncpg simple protocol, un
    solo `execute` con todo el fichero). `CREATE OR REPLACE TRIGGER` lo resuelve.
  - **No importes un módulo de test desde otro test** (`from tests.unit.test_x
    import _y`): rompe la importación de pytest con el modo `prepend` y produce un
    `ImportError` con la línea equivocada. Usa un `*_support.py` (patrón ya
    existente en el repo).
  - **Filtrar por `created_at` es un bug silencioso**: `account_plan` (82 filas del
    PGC) se quedaba en 0 al filtrar por ejercicio. La columna técnica de auditoría
    no filtra; marca los maestros con `filtra_rango=False`.
  - **Las tablas hijas sin fecha propia** (`journal_entry_line`, `factura_linea`,
    `balanza_periodo_linea`, `desviacion`) se filtran con un `EXISTS` correlacionado
    sobre la tabla padre, declarada en el catálogo.
  - **`TestClient(app)` re-lanza las excepciones del servidor**: para probar el
    camino 500 de un servicio usa `raise_server_exceptions=False`.
  - **Un bloque con `una sola ROW` de la AEAT no cuadra si la rectificativa se
    clasifica por su propio tipo**: hay que subir por `factura_original_id` hasta la
    raíz (mismo criterio que SPEC-007).
  - La suite completa tarda ~19 min: lánzala en segundo plano con log y consulta el
    fichero, porque el pipe no devuelve salida hasta el final.
  - Contra PostgreSQL, `db.migrate` debe correr **antes** de la suite completa:
    `test_cierre_concurrente` (y otros) insertan en `companies` y asumen el esquema.
- **Verificación**: suite completa **2.503 passed / 19 skipped** (SQLite), sin
  fallos: las 2 pruebas `test_suggest_perf` (flaky conocido bajo carga de
  SPEC-001) pasaron tambien en la corrida completa. PostgreSQL 18.6 real: migraciones 000–020 aplicadas
  sobre esquema limpio e idempotentes y **16 passed** en `test_pg_schema.py`; la
  suite completa contra PostgreSQL da **2.521 passed / 1 skipped**. ruff + mypy
  limpios (**393 fuentes**), `tsc` + ESLint + `next build` verdes con **103 rutas**.

## 44. Corrección del secreto de firma JWT y desviaciones de SPEC-029 (2026-09-27)

Segunda tanda de trabajo sobre SPEC-029, ya cerrada, más un arreglo de seguridad
transversal detectado al revisar el `.env`.

### `SECRET_KEY` (transversal, SPEC-003)

- **Problema**: `services/auth/security.py` tenía el secreto de firma **como
  constante en el código** (`jwt_secret: str = "dev-only-secret-change-me-to-32-bytes-min"`,
  clase `AuthSettings` con prefijo `AUTH_`). Cualquiera que leyera el repo podía
  **forjar tokens de cualquier usuario**. El `SECRET_KEY` añadido a `backend/.env`
  **no se leía**: el nombre no coincide con `AUTH_JWT_SECRET` y el código no
  miraba `config.Settings`.
- **El valor del `.env` es correcto**: 64 caracteres hexadecimales (= 32 bytes,
  256 bits, propio de `secrets.token_hex(32)` o `openssl rand -hex 32`), sin
  espacios, 15 caracteres distintos y 3,62 bits de entropía por carácter
  (máximo teórico del hex = 4). No es el placeholder de desarrollo.
- **Cambios**:
  - `config.Settings` incorpora `secret_key`, `algorithm` y
    `access_token_expire_minutes` con `AliasChoices` (`SECRET_KEY` /
    `AUTH_JWT_SECRET`, `ALGORITHM` / `AUTH_JWT_ALGORITHM`, minutos /
    `AUTH_JWT_EXPIRE_MINUTES`; y `AUTH_JWT_EXPIRE_HOURS` como legado que solo
    aplica si los minutos no vienen explícitos, con `model_fields_set`).
  - `services/auth/security.py` ya **no declara ningún secreto por defecto**.
    Resuelve `secreto` desde `config.Settings`; si falta, es el placeholder, o
    mide menos de `LONGITUD_MINIMA_SECRETO = 32`, genera uno aleatorio de un
    solo proceso (`SECRET_EPHEMERAL = True`) y **avisa**; un secreto corto
    lanza `ValueError`. `ALGORITMOS_PERMITIDOS` es una lista blanca
    (HS256/384/512) que blinda frente a *algorithm confusion*.
  - `comprobar_configuracion()` devuelve los avisos y `main.lifespan` los
    registra al arrancar.
  - `backend/.env.example` declara `SECRET_KEY` / `ALGORITHM` /
    `ACCESS_TOKEN_EXPIRE_MINUTES` con el comando de generación. `.env` sigue
    cubierto por `.gitignore` (`!.env.example`).
  - Vencimiento: 30 min (antes 12 h).
- **Pruebas**: `backend/tests/unit/test_config_secreto.py` (23) cubre el entorno
  como fuente, el alias histórico, la precedencia minutos > horas, la lista
  blanca de algoritmos, el rechazo del placeholder y de secretos cortos, que un
  token firmado con otro secreto o sin `jti` se rechaza, que la plantilla no
  lleva secreto real y que el `.env` local no usa el placeholder.

### Desviaciones de SPEC-029 corregidas

1. **Colisión de rutas con SPEC-012** (la importante): `api/fiscal/exportaciones.py`
   ya ocupaba `/api/v1/exportaciones` y, al registrarse el router fiscal antes
   que `api/export.py`, **ocultaba `POST /api/v1/exportaciones`** de la
   exportación integral en la app real. Se movió SPEC-012 a
   `/api/v1/fiscal/exportaciones` y se añadieron dos guards de colisión en
   `tests/unit/test_app.py`.
2. `creado_por` pasó de la etiqueta fija `"api:api"` al `users.id` autenticado.
3. `GET /{id}/sii` lee el bloque del **blob inmutable** en vez de recalcularlo
   (si el tenant cambia, la API ya no puede discrepar del ZIP).
4. Eliminados los imports perezosos de `persistir.detalle_exportacion` y
   `api/export._lineas`.
5. T051 sube a 2.000 asientos + 1.000 terceros en la suite, con el volumen
   completo del plan (10.000 asientos, < 30 s) bajo `EXPORT_PERF_FULL=1`.

### Lo que NO se puede corregir

- **`sha256_fichero` dentro del `manifest.json`**: un fichero no puede contener
  su propio hash. El manifiesto lleva `sha256_contenido` (digest canónico del
  contenido, verificable sin API) y la huella del binario completo vive en
  `Exportacion`/`BlobExportacion`/`ManifiestoExportacion` y en la API. Es una
  asunción imposible del spec, no un defecto de implementación.

## 45. Cierre de SPEC-030 Documentos adjuntos al asiento (2026-09-27)

Trigésima spec cerrada (48/48). Total del proyecto: **1.432/1.432 tareas**.

- **Modelos** `models/acct/documento.py`: `DocumentoAsiento` (19 columnas),
  `TipoDocumento` (6 valores en minusculas) y `EstadoDocumento`, mas
  `COLUMNAS_INMUTABLES`. FK compuesta `(empresa_id, journal_entry_id)` a
  `journal_entry` (constitucion III a nivel de BD) y
  `UNIQUE (empresa_id, journal_entry_id, sha256)` **sin** indice parcial
  (research D6: la baja es logica y la huella sigue ocupando su sitio).
- **Migracion `021_adjuntos_asiento.sql`** (no `018`, que ya ocupa
  `018_cashflow.sql` de SPEC-027): 2 enums, tabla, 7 restricciones, 4 indices y
  los triggers `trg_documento_asiento_contenido_inmutable_update` y
  `trg_documento_asiento_inmutable_delete`. Registrada en `db/migrate.py` y
  `test_migrations.py`; espejo SQLite en `db/triggers.py`.
- **research D3**: el contenido, su nombre y su huella **no** se reescriben
  nunca; lo unico que el trigger admite es el `UPDATE` de las cuatro columnas de
  la baja logica, y el `CHECK chk_documento_asiento_baja` exige que la baja venga
  completa. El `DELETE` fisico se rechaza siempre (FR-012).
- **Servicios** `services/documentos/`: `errores`, `validacion` (tres capas:
  firma, `pypdf` y Pillow), `adjuntos` (US1), `consulta` (US2), `bajas` (US3) y
  `_serializacion` (compartido, sexto modulo sobre los cinco de plan.md).
- **API** `api/documentos/` (paquete): 6 rutas bajo `/api/v1/documentos` con el
  segmento estatico `/asiento/{id}` (research D7, evita la colision con
  `GET /api/v1/asientos/{entry_id}`). `empresa_id` siempre via
  `Depends(get_empresa_id)`; `api.routes_registry.rutas_sin_permiso` sigue en 0.
- **RBAC**: sin modulo nuevo. Se reutiliza `acct` con `ver` (4 rutas), `crear`
  (1) y `baja` (1), lo que satisface FR-016 sin tocar el catalogo: **15
  modulos, 109 permisos** (sin cambios).
- **Frontend**: `components/documentos/{api.ts,DocumentosAsiento.tsx,VisorDocumento.tsx}`
  y `app/documentos/page.tsx`; montado en `app/asientos/[id]/page.tsx`. La
  previsualizacion usa `URL.createObjectURL` sobre el `Blob` autenticado, nunca
  una URL publica. **104 rutas** (1 nueva).
- **Pruebas (147 nuevas)**: 30 de validacion (S5 completo + los 4 formatos),
  7 de aislamiento del alta, 16 de inmutabilidad/duplicados/limites, 23 de
  constitucion, 49 de los seis endpoints (S2, S3, S4, S6, S8, S9, S10, S11),
  12 de aislamiento multi-empresa (S7) y 10 de opcionalidad (S1). Helper
  `tests/unit/documento_support.py` y fixture `documentos_client`.
- **Opcionalidad (FR-020, research D11)**: ninguna capa impone la presencia de
  documentos. Sin columna de recuento en `journal_entry`, sin `NOT NULL`, y
  `GET /asiento/{id}` devuelve 200 con `items: []` y
  `documentos_obligatorios: false`. Un asiento sin documentos recorre su ciclo
  de vida completo sin restriccion alguna.
- **Correccion del payload SII del ZIP (SPEC-029, cross-spec)**:
  `payload_sii` solo serializaba `clave_regimen` y `sin_anexo`, de modo que
  `leer_bloque_sii` —la via que respeta la inmutabilidad de la exportacion—
  devolvia `entidad_representante_id` y `fecha_alta` como `null`. Y la columna no
  era rellenable por API: `ConfigSiiBody` no tenia el campo. Corregido en las
  tres capas (payload completo, lectura con `.get` retrocompatible, y
  `PUT /sii/config` acepta y persiste el campo). 3 tests nuevos.
- **`Content-Disposition` conforme a RFC 6266**: `contracts` pedia
  `filename="<nombre_original>"`, lo que mete bytes UTF-8 en una cabecera cuando
  el nombre lleva acentos. Ahora viaja la doble forma: `filename` con equivalente
  ASCII y `filename*=UTF-8''...`. El nombre original sigue intacto en la base de
  datos, y `"` se elimina del nombre almacenado (no es valido en Windows ni
  macOS y un cliente RFC 2231 deja una colgante).
- **Desviaciones**: el boundary ACID es `get_db` + `flush()` (V1 de plan.md);
  el prefijo lo lleva cada sub-router y no el padre (un `include_router` con
  prefijo y camino ambos vacios es error de FastAPI, criterio de
  `api/costcenters/`); `_serializacion.py` es un sexto modulo; la migracion es
  `021` y no `018`. Detalle completo en el **"Estado real"** de
  `specs/030-documentos-asiento/tasks.md`.
- **Lecciones reutilizables**:
  - **Una cabecera HTTP solo admite ASCII.** `filename="<nombre con acentos>"`
    produce una cabecera que los clientes estricos no pueden ni leer. RFC 6266
    resuelve con `filename` + `filename*`.
  - **`TestClient.delete` no acepta `json=`**; hay que usar
    `client.request("DELETE", ...)`.
  - **httpx multipart en lista**: cada fichero es `("files", (nombre, bytes, mime))`.
  - **`crear_borrador` usa `debit`/`credit`** en el dict de linea y exige
    `account_id`; `debe`/`haber` son los nombres de columna.
  - **`index=True` + `Index(...)` con nombre en `__table_args__` rompe
    `create_all`** con "index already exists": elige uno.
  - **El trigger de partida doble tambien aplica a los contratos PG**: es
    diferido y revisa en el COMMIT, asi que un asiento de prueba sin lineas se
    rechaza.
  - **Un generador de ficheros determinista provoca falsos duplicados**: si
    `pdf_bytes()` devuelve siempre los mismos bytes, el segundo alta cae en
    `documento_duplicado` (correcto) y el test parece un fallo de negocio.
  - **`AuditLog.id` es un UUID**, asi que dos entradas del mismo segundo no
    tienen orden total. No se comprueba el orden de la traza; se comprueba que las
    operaciones existen.
  - Dentro de un here-string de PowerShell (`@"..."@`) se pierden las comillas
    dobles anidadas: para generar bloques de codigo con `"` usar un `.py`
    temporal y ejecutarlo.
- **Verificacion**: suite completa **2659 passed / 21 skipped** (SQLite), sin
  fallos salvo `test_suggest_perf` (flaky conocido de SPEC-001, **2 passed**
  aislado). PostgreSQL 18.6 real: migraciones 000-021 sobre esquema limpio y
  **18 passed** en `test_pg_schema.py`; la suite completa da **2678 passed /
  1 skipped**. ruff + mypy limpios (**406 fuentes**), `tsc` + ESLint +
  `next build` verdes con **104 rutas**.

## 46. Estado del proyecto tras SPEC-031

- **31 specs completas** (001-031), con las puertas verificadas.
- **1.506/1.506** tareas marcadas (1.432 de SPEC-001 a SPEC-030, mas 74 de SPEC-031).
- La spec activa ya no es SPEC-030: `specs/031-navegacion-superficies`. Ver seccion 49.
- La siguiente feature (SEG-032: seguridad, gestion de usuarios y autoria del apunte)
  esta disenada pero **no implementada**. Quedan tres huecos conocidos que alli
  deberían cerrarse: el backend escribe `"system"` como autor de los asientos creados
  por la API, el guard de sesion del frontend es optimista (no de seguridad), y las
  superficies no tienen gestion de altas ni de bajas de sus destinos.

## 47. Trabajo transversal: siembra de empresas en tests (2026-09-27)

Cierra el unico pendiente que quedaba tras SPEC-030 (§46). No es una spec: es
deuda tecnica que 30 specs fueron dejando atras.

### El problema

Dar de alta una empresa en un test repetia el mismo bloque en mas de cien
sitios, con variantes del NIF y de la razon social que **ningun test miraba**:
`"A00000001"`, `"Diez SL"`, `"Retenciones Diez SL"`, `"Tesorería Diez SL"`... mas
de trescientas construcciones de `Company` y cincuenta variantes distintas de
`add(Company(...))` + `flush()` + `seed_default_pgc(...)`. Cada spec nueva
copiaba el de la anterior, y copiar implicaba decidir otra vez si el sitio
necesitaba plan de cuentas o no.

### La solucion: cuatro funciones en un solo sitio

En `backend/tests/conftest.py`:

| Funcion | Que hace | Cuando |
|---|---|---|
| `crear_empresa(db, empresa_id, *, nif, razon_social, is_active)` | Empresa y `flush()`, **sin** PGC | el test planta su propio plan (`_plantar_pgc`) |
| `sembrar_empresa_pgc(db, empresa_id, ...)` | Empresa + seed del PGC de 7 grupos | el caso habitual |
| `crear_empresas(db, *ids, ...)` | Varias empresas sin PGC | el par A=10 / B=20 con plan propio |
| `sembrar_empresas_pgc(db, *ids, ...)` | Varias empresas con PGC | el par A=10 / B=20, el mas repetido |

Decisiones del diseno:

- **El NIF y la razon social se derivan de `empresa_id`** (`T00000010`,
  `E10 SL`), lo que hace que dos empresas en el mismo test no colisionen. Se
  pueden pasar explicitamente solo cuando un test **afirma** sobre el valor: hoy
  son tres casos, el declarante del Modelo 111 y la razon social que devuelve la
  API al cambiar de empresa.
- **`flush()` y nunca `commit()`**: el commit pertenece a quien llama. Sin el
  flush la fila no existe para el trigger que siembra el catalogo RBAC ni para las
  FKs del plan de cuentas.
- **`crear_empresas` NO siembra el PGC**, y es deliberado: sembrar el seed
  estandar y luego plantar cuentas a medida choca con
  `UNIQUE (tenant_id, code)`. Ese bug aparecio al migrar la primera vez y por eso
  las dos funciones estan separadas.

### La parte que lo sostiene: la cremalla

`backend/tests/unit/test_guard_siembra_empresa.py` (6 tests) impide que la
duplicacion vuelva:

1. `test_no_aparece_ningun_company_nuevo_a_mano` — un `Company(` fuera de la
   lista de pendientes **falla**. La lista `PENDIENTES` solo puede encogerse.
2. `test_la_lista_de_pendientes_no_tiene_ficheros_inventados` — si un fichero ya
   no construye `Company` pero sigue en la lista, falla: una lista que miente
   deja de ser una cremalla.
3. `test_el_helper_cubre_las_cuatro_formas` — la firma es la que leen los
   transformadores y esta seccion, asi que cambiarla rompe el test a proposito.
4. `test_el_nif_y_la_razon_social_se_derivan_del_id`
5. `test_crear_empresa_hace_flush_y_no_commit`
6. `test_crear_empresas_no_siembra_el_pgc`

**Estado real**: migrados los 23 fixtures de `conftest.py` y 57 sitios de test.
Quedan **67 ficheros** en `PENDIENTES`, y ahi sigue la verdad: la migracion
restante se hizo **a mano y uno por uno**, no con un transformador, porque cada
fichero tiene su forma y el riesgo de un cambio automatico mayor que el del
beneficio. La lista los nombra para que el proximo trabajo apunte a algo concreto.

### Lecciones reutilizables

- **Un refactor automatico necesita validar su propio resultado**: el
  transformador comprueba `ast.parse(texto)` antes de escribir y, si no parsea,
  descarta el fichero entero. Sin esa red, un `)` de mas deja 30 ficheros con
  sintaxis rota y el error aparece lejos de su causa.
- **Contar parentesis, no lineas**: distinguir el `)` que cierra `Company(` del
  que cierra `add(` con regex por linea es la causa clasica de estos fallos.
- **`ast.unparse` normaliza las comillas a simples**: un test que comprueba el
  codigo fuente con comillas dobles falla aunque el codigo sea correcto.
- **No abstraigas lo que es heterogeneo.** Se intento un helper mas potente que
  hacia tambien el cableado de `User`/`UserCompany`/roles, y se elimino: los
  roles por usuario y empresa no siguen un patron, y la matriz de RBAC depende
  de ellos. Es preferible un helper que cubre cuatro formas a uno que finge
  cubrir diez.
- **Un `seed_default_pgc` de mas rompe los tests de una forma confusa**:
  `UNIQUE constraint failed: account_plan.tenant_id, account_plan.code` no dice
  que el problema es una doble siembra.

### Verificacion

| Puerta | Resultado |
|---|---|
| `pytest` (SQLite) | **2659 passed / 21 skipped** (antes 2652; +6 del guard) |
| `pytest` (PostgreSQL 18.6 real, migraciones 000-021) | **2678 passed / 1 skipped** |
| `ruff check src tests` | limpio |
| `mypy` | limpio, **406 fuentes** |

Ficheros tocados: `backend/tests/conftest.py` (helper + 23 fixtures),
`backend/tests/unit/test_guard_siembra_empresa.py` (nuevo) y 57 ficheros de test
migrados. No se toco `backend/src/`.

## 48. Enmienda de la constitucion 1.0.1 y correccion de artefactos (2026-09-27)

Trabajo documental, **sin cambios en `backend/src/`**: ningun test lee los
artefactos de la spec, asi que las puertas no se ven afectadas.

### Enmienda PATCH de la constitucion (1.0.0 -> 1.0.1)

La constitucion exigia en su seccion de transacciones que "los servicios de
backend MUST usar bloques de transaccion atomicos
(`async with async_session.begin()`)". **Las 30 specs incumplen ese MUST de
forma consciente** desde SPEC-001, y cada una lo declara como desviacion V1 de
su plan. Segun el principio de gobernanza ("cualquier codigo, especificacion o
tarea en conflicto con esta constitucion queda sin efecto"), el patron
realmente establecido no tenia cobertura normativa.

La enmienda fija el boundary **por su propiedad** en vez de por su sintaxis, y
cierra ademas la puerta al error contrario:

> la indivisibilidad MUST garantizarse con un boundary de transaccion ACID unico
> y explicito. En este repositorio ese boundary es el generador de sesion de la
> capa de datos (`get_db`), que abre la transaccion al entrar, confirma al final
> de la peticion y revierte ante excepcion; los servicios MUST hacer `flush()`
> dentro de ese boundary y MUST NOT abrir su propia transaccion
> (`async with session.begin()`), porque eso romperia la atomicidad con la
> operacion que la invoca.

Version **1.0.1** (PATCH: aclaracion y correccion, sin eliminar ni redefinir
principios). Afecta a las 30 specs, no solo a SPEC-030.

**Consecuencia**: las desviaciones V1 de los 30 `plan.md` dejan de ser
desviaciones y quedan cubiertas por la norma. Los textos de "Estado real" de las
specs que las describen siguen siendo historicos y correctos como registro.

### Correccion de los artefactos de SPEC-030

Un analisis de consistencia (`/speckit.analyze`) sobre `spec.md`, `plan.md` y
`tasks.md` encontro **3 contradicciones** y 16 hallazgos mas. Los tres criticos
eran errores reales de los artefactos, no de la implementacion:

1. **Migracion `018_adjuntos_asiento.sql`**: los cuatro artefactos la nombraban,
   pero el 018 ya lo ocupaba `018_cashflow.sql` (SPEC-027). Aplicarla como
   escrito rompe `test_orden_por_dependencias`. Corregida a `021` en plan,
   research, data-model y tasks, con su posicion real en `ORDEN_PREFERENTE`.
2. **Reparto del prefijo**: el plan situaba
   `APIRouter(prefix="/api/v1/documentos")` en `__init__.py`, pero la ruta del
   listado global es exactamente `""` y FastAPI rechaza un `include_router` con
   prefijo y camino ambos vacios. El plan ahora dice que el prefijo lo lleva
   cada sub-router, con el motivo y el precedente (`api/costcenters/`).
3. **Conflicto con la constitucion** (arriba).

Ademas: 6 endpoints en vez de 5, 5 modulos de servicio en vez de 3,
`asiento_entry_id` unificado en `asiento_id`, `T005` marcada como linea base y
no cierre, `T047` y el quickstart apuntando al cluster real (PostgreSQL 18.6 en
el 5432) en vez de al cluster portable 5433, el supuesto falso del quickstart
S10 corregido, FR-001/005/010/012 reescritos para que sean verificables, SC-001
marcado como no automatizable, SC-008 comprobable, contrato de descarga
alineado con RFC 6266 y la tabla de trazabilidad FR aclarando las tareas
transversales.

Detalle completo en el "Estado real" de `specs/030-documentos-asiento/tasks.md`.

### Lecciones reutilizables

- **Una desviacion repetida 30 veces deja de ser una desviacion**: cuando el
  patron establecido contradice la norma, el problema no es la decima aplicacion sino que la norma nunca se alineo con la realidad.
- **Un analisis sobre una spec ya cerrada sigue siendo util**: los artefactos
  son la memoria del proyecto y una contradiccion entre ellos se propaga a
  quien los lea para continuar, aunque el codigo este bien.
- **Un supuesto equivocado en un quickstart se propaga al test que lo sigue**:
  S10 afirmaba que `baja` no estaba concedido a ACCOUNTANT, y la prueba
  correcta (revocar el permiso en la matriz) verifica algo mas fuerte.

## 49. Cierre de SPEC-031 Navegación y superficies (2026-09-28)

Trigésima primera spec cerrada. Total del proyecto: **1.506/1.506 tareas**.

- **Modelos** `models/navigation/favorito.py` (`FavoritoUsuario`: por usuario y
  empresa, `UNIQUE (empresa_id, usuario_id, destino)`, `UNIQUE (empresa_id, id)` y FK
  compuesta a `user_companies`).
- **Migración `022_favoritos.sql`**: 2 índices únicos, 2 CHECK y la FK de vínculo. Es
  constitution III a nivel de esquema: un favorito de una empresa a la que el usuario
  no está vinculado no es invisible, es **inválido**.
- **Servicios** `services/navigation/`: `contexto.py`, `ejercicio_activo.py`,
  `favoritos.py`, `resumenes.py`, `destinos.py`, `errores.py`. `destinos.py` es el
  catálogo de las 100 claves de destino, extraído de `surfaces.ts` y protegido por
  `test_destinos_en_sync.py` contra la deriva.
- **API** `api/navigation.py` con tres routers versionados: `GET /api/v1/contexto`,
  los cuatro de `/api/v1/favoritos` y `GET /api/v1/resumenes/{superficie}`. Ninguno
  acepta `empresa_id` del cliente; sale de la sesión.
- **Frontend** `components/navigation/` (10 componentes: `surfaces.ts`, `AppShell`,
  `DestinationRail`, `MobileNav`, `SurfacePanel`, `FavoritesBar`, `ResumenSuperficie`,
  `AjusteSii`, `ContextZone`, `SessionContext`), `src/middleware.ts` y las 7
  pantallas nuevas.
- **Pruebas**: **267** de SPEC-031 (126 en `unit/`, 141 en `integration/`), más 19
  del contrato PostgreSQL.

### La amidalla que hizo falta

`src/middleware.ts` es un guard **optimista**: comprueba que hay cookie de sesión y
redirige a `/login` si no. No es un control de seguridad, y no pretende serlo: la
frontera real es el **401** del backend, que ya funcionaba. Se dejó escrito en el
código para que nadie lo lea como lo que no es, y para que quien lo lea sepa que
**actualizar una superficie no autoriza nada**.

### Verificacion

- Suite completa **2942 passed / 23 skipped** (SQLite). El unico fallo es
  `test_suggest_perf` (flaky conocido de SPEC-001), **2 passed** aislado.
- PostgreSQL 18.6 real: migraciones 000-022, **19 passed** en `test_pg_schema.py`.
- `ruff` y `mypy` limpios en **416 fuentes**; `tsc`, ESLint y `next build` verdes con
  **110 paginas**.
- `p95` de `GET /api/v1/contexto` con 5.000 asientos: **16,7 ms** (opt-in con
  `PERF_NAV=1`).

### Lo que dejo pendiente, y es deliberate

Los diez recorridos del `quickstart.md` son **manuales**: describen lo que hay que
mirar en un navegador. Lo automatizable esta en
`tests/integration/test_quickstart_navegacion.py` y
`tests/unit/test_navegacion_accesibilidad.py`, y ambos enumeran en `MANUAL` lo que
queda a ojo. **No se ha comprobado a mano**: el orden real de tabulacion, que el foco
sea visible, la hoja de contexto en un movil real, y el recorrido R4 entero (que
crea asientos).

### Desviaciones que conviene tener presentes

- **La spec nacio como "reordenar pantallas y darles aspecto Material Design", y ha
  crecido.** El contexto de sesion, la cabecera de ejercicio y los favoritos
  persistidos no estaban en el encargo original. El contexto y la cabecera son los
  que hacen que un panel por superficie pueda decir "del ejercicio activo", asi que
  sirven al objetivo. Los favoritos son lo unico que se podria recortar si mas
  adelante se quisiera volver al alcance original.
- **De las 5 pantallas que US6 mandaba consolidar, 4 no eran duplicados** y se
  conservaron. `/tesoreria/efe` estaba ademas **fuera del mapa**: inalcanzable desde
  la navegacion. Ese era el defecto real, y la consolidacion lo ha arreglado. Detalle
  en el "Estado real" de `specs/031-navegacion-superficies/tasks.md`.
- **Un resumen es una lectura y admite ejercicios cerrados; la escritura no.** Se
  separo `validar_pertenencia` de `validar_solicitado` en
  `services/navigation/ejercicio_activo.py`. Con la regla de escritura, el resumen de
  un ano recien cerrado devolvia los numeros de otro ejercicio con el rotulo del
  cerrado, que es peor que un error.
- **El endpoint `GET /api/v1/resumenes/{superficie}` no estaba en el contrato.**
  T046 pedia un test de backend con aislamiento por empresa, y ese test necesita un
  endpoint con sujeto. Queda anotado como pieza anadida.

### Lecciones reutilizables

- **`tsc` no valida un contrato.** El bug de los permisos (`String(p).split(":")` sobre
  una respuesta de objetos) estaba bien tipado y hacia que el panel ocultara todos los
  destinos en silencio. Lo caza comparar la forma que declara el cliente con la que
  produce el servidor.
- **`next build` no comprueba que las rutas del mapa existan.** Con 101 destinos, un
  error de dedo es un 404 que solo ve quien lo pulsa.
- **Un guard que nunca falla no comprueba nada.** `PENDIENTES` de
  `test_guard_mapa_superficies.py` fallo al llegar a US6, con las siete rutas que ya
  existian. Se vacio.
- **Los guards leen prosa.** El guard de siembra busca `Company(` y fallo por un
  comentario que mencionaba `Company(...)`. Es el aviso de §47, cropsa.
- **`user_companies` es `(user_id, company_id)` en ese orden**, y con `company_id` de
  nombre. Cualquier FK compuesta ahi tiene que invertir el orden. El error sale como
  `no column named 'empresa_id'`, que senala una columna inexistente y no un orden.
- **Un `.next` obsoleto rompe `tsc` tras borrar una pagina.** Se borra `.next/types`.
- **El boundary ACID sigue siendo `get_db` + `flush()`** (constitucion 1.0.1, §48).
  Ningun servicio de esta feature abre transaccion ni hace commit, y
  `test_constitucion_navegacion.py` lo verifica.
