# Tasks: Remesas SEPA y Soporte Magnético (SPEC-020)

**Input**: Design documents from `/specs/020-remesas-sepa-cobros/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Trazabilidad FR ↔ User Story

| Requisito | Descripción breve | User Story |
|---|---|---|
| FR-001 | Aislar remesas, recibos y devoluciones por empresa | US1 |
| FR-002 | Seleccionar recibos pendientes y agrupar en remesa | US1 |
| FR-003 | Generar fichero domiciliación SEPA DD y CSB 19.19 | US1 |
| FR-004 | Fecha cargo igual vencimiento, validar plazos SEPA | US1 |
| FR-005 | Descuento pronto pago con asiento 432/662 vs 430 | US2 |
| FR-006 | Gestionar devoluciones R19/C19 con reversión | US3 |
| FR-007 | Confirmar cobro recibo remesado manual o conciliación | US1 |
| FR-008 | Rechazar remesas/devoluciones en ejercicio cerrado | US1 |
| FR-009 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo `treasury` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo treasury: `backend/src/models/treasury/__init__.py`, `backend/src/services/remittance/__init__.py`, `backend/src/services/discount.py`, `backend/src/services/remittance/sepa_dd.py`, `backend/src/services/remittance/csb_1919.py`, `backend/src/services/remittance/refund_r19.py`, `backend/src/api/treasury/__init__.py`
- [X] T002 [P] Configurar router treasury: registrar prefijo `/api/v1` en `backend/src/api/treasury/routes.py` con dependency de sesión autenticada `empresa_id`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/remesas/`, `frontend/src/app/devoluciones/`, `frontend/src/app/terceros/condiciones/`, `frontend/src/components/treasury/`
- [X] T004 [P] Crear utils de sesión: `backend/src/api/treasury/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `Remesa` en `backend/src/models/treasury/remesa.py`: campos empresa_id (PK), numero_remesa (BIGINT), ejercicio (INT), fecha_emision, fecha_cargo, formato (SEPA_DD/CSB_19_19), tipo_adeudo (CORE/B2B), importe_total NUMERIC(18,4), estado (borrador/emitida/devuelta), fichero_id UUID NULL; constraint unicidad (empresa_id, ejercicio, numero_remesa)
- [X] T006 [P] Crear modelo `ReciboRemesa` en `backend/src/models/treasury/recibo_remesa.py`: empresa_id, remesa_id FK, vencimiento_id FK UNIQUE por remesa, tercero_id, iban VARCHAR(34), importe NUMERIC(18,4), descuento_id NULL, estado (pendiente/remesado/cobrado/devuelto), asiento_cobro_id NULL; FK compuesta empresa_id
- [X] T007 [P] Crear modelo `CondicionProntoPago` en `backend/src/models/treasury/condicion_pronto_pago.py`: empresa_id, tercero_id FK, plazo_dias INT, porcentaje NUMERIC(5,2), vigente BOOLEAN, override_factura_id NULL; constraint único empresa_id+tercero_id+vigente=true
- [X] T008 [P] Crear modelo `MandatoSepa` en `backend/src/models/treasury/mandato_sepa.py`: empresa_id, tercero_id FK, mandato_ref VARCHAR(35), fecha_firma DATE, tipo (CORE/B2B), estado (firmado/caducado/revocado)
- [X] T009 [P] Crear modelos `DevolucionRecibo` y `Reclamacion` en `backend/src/models/treasury/devolucion.py`: DevolucionRecibo con empresa_id, recibo_remesa_id FK, codigo VARCHAR(10), identificador_externo único por empresa, motivo, fecha_registro, importe NUMERIC(18,4), importe_gastos NUMERIC(18,4) DEFAULT 0, asiento_reversal_id FK, estado_reclamacion; Reclamacion con empresa_id, devolucion_id FK, fecha, estado, observaciones
- [X] T010 [P] Crear modelo `BlobFichero` en `backend/src/models/treasury/blob_fichero.py`: empresa_id, tipo ENUM (remesa_sepa/remesa_csb1919/r19/c19), contenido BYTEA, sha256 CHAR(64), created_at
- [X] T011 Implementar CRUD de `CondicionProntoPago` y `MandatoSepa` en `backend/src/services/tercero_amend.py` (endpoints POST/PATCH en `backend/src/api/treasury/tercero_amend.py`)
- [X] T012 [P] Tests de modelos fundacionales: `backend/tests/unit/test_treasury_models.py` — verificar unicidad (empresa_id,ejercicio,numero_remesa), constraint vigente único por tercero, FK compuesta empresa_id
- [X] T012a [P] Tests de claves tenant: ampliar `backend/tests/unit/test_treasury_models.py` — verificar índices únicos y FKs compuestas con `empresa_id` en remesa, recibo, devolución, mandato y condición
- [X] T013 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_treasury_tenant_isolation.py` — crear remesa en empresa A, verificar que empresa B no la ve en ninguna consulta

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Emitir remesa (Priority: P1) ?? MVP — cubre FR-001, FR-002, FR-003, FR-004, FR-007, FR-008, FR-009

**Goal**: El usuario selecciona recibos, los agrupa en una remesa y genera el fichero SEPA/CSB; el cobro se confirma por marcado manual.

**Independent Test**: Crear remesa genera fichero válido y recibos pasan a `remesado`; marcado manual cambia a `cobrado` con asiento balanceado.

### Tests for User Story 1

- [X] T014 [P] [US1] Test correlatividad: `backend/tests/unit/test_correlatividad_remesa.py` — crear 3 remesas en el mismo ejercicio, verificar numero_remesa correlativo sin saltos; crear en ejercicio distinto → secuencia independiente
- [X] T015 [P] [US1] Test exclusión de recibos: `backend/tests/unit/test_exclusion_recibos.py` — intentar incluir recibo cobrado → excluido; sin IBAN → excluido; ejercicio cerrado → rechazo 409; verificación de que la lista de excluidos se devuelve al usuario

### Implementation for User Story 1

- [X] T016 [US1] Implementar `SeleccionRemesa` service en `backend/src/services/remittance/seleccion.py`: filtrar vencimientos pendientes por empresa_id + fecha/cliente/banco; validar IBAN, estado `pendiente`, ejercicio abierto; excluir cobrados
- [X] T017 [US1] Implementar servicio de correlatividad en `backend/src/services/remittance/seleccion.py`: asignar `numero_remesa` por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE` en secuencia bloqueada; calcular importe_total como suma de importes de recibos
- [X] T018 [US1] Implementar generador SEPA `PAIN.008.001.02` en `backend/src/services/remittance/sepa_dd.py`: cabecera (MsgId, CreDtTm, NbOfTxs, CtrlSum), pago (PmtInf con tipo_adeudo CORE/B2B, ReqdColltnDt, CdtrAcct), instrucción por recibo (EndToEndId, InstdAmt 2 decimales, MndtRltdInf); validación de plazos CORE D-2 / B2B D-1 hábiles
- [X] T019 [US1] Implementar generador CSB 19.19 en `backend/src/services/remittance/csb_1919.py`: registro tipo 1 (cabecera emisor, importe total en céntimos), tipo 3 (recibos con IBAN/datos deudor), tipo 5 (pie); encode ISO-8859-15
- [X] T020 [US1] Implementar servicio `emitir_remesa` en `backend/src/services/remittance/emision.py`: validar estado `borrador`, generar fichero SEPA o CSB según formato, persistir `BlobFichero` con sha256, cambiar estado a `emitida`, todo en transacción ACID con audit log; B2B requiere mandato `firmado`
- [X] T021 [US1] Implementar servicio `crear_remesa` en `backend/src/services/remittance/emision.py`: crear `Remesa` + `ReciboRemesa` (líneas) en una sola transacción ACID; validar que todos los recibos sean elegibles antes de insertar; si alguno no lo es, fallar la operación (atomicidad)
- [X] T022 [US1] Implementar endpoints en `backend/src/api/treasury/remesas.py`: POST crear (201), POST emitir (200), GET listar (paginación), GET detalle (con recibos), GET fichero (descarga), POST cobrar recibo (marcado manual)
- [X] T023 [US1] Implementar servicio `confirmar_cobro` en `backend/src/services/remittance/emision.py`: cambiar `ReciboRemesa.estado → cobrado`, crear asiento de cobro SPEC-011 (430 vs 572/570) balanceado, registrar audit log; en transacción ACID
- [X] T023a [US1] Implementar confirmación conciliada en `backend/src/services/remittance/emision.py` y `backend/src/api/treasury/remesas.py`: consumir evento de SPEC-013 con `movimiento_id`, usar clave idempotente por empresa y movimiento, devolver el asiento existente en reintentos y rechazar conflictos de estado
- [X] T023b [US1] Implementar agrupación multi-fecha en `backend/src/services/remittance/sepa_dd.py` y `backend/src/services/remittance/csb_1919.py`: generar un grupo por fecha de cargo y tipo de adeudo, con totales independientes y validación de plazos por grupo
- [X] T024 [US1] Crear página frontend `frontend/src/app/remesas/nueva/page.tsx`: formulario de selección de recibos con filtros (fecha/cliente/banco), vista previa, envío
- [X] T025 [US1] Crear página frontend `frontend/src/app/remesas/[id]/page.tsx`: detalle de remesa con lista de recibos, botón emitir, botón descargar fichero, botón cobrar individual
- [X] T026 [US1] Crear listado frontend `frontend/src/app/remesas/page.tsx`: tabla paginada con filtros (estado/ejercicio/formato), links a detalle
- [X] T027 [US1] Tests integración emisión SEPA: `backend/tests/integration/test_emision_sepa.py` — crear remesa, emitir, parsear XML con esquema PAIN.008, verificar NbOfTxs/CtrlSum/InstdAmt/EndToEndId
- [X] T027a [US1] Tests integración SEPA multi-fecha: `backend/tests/integration/test_emision_sepa_multifecha.py` — una remesa con dos fechas produce dos bloques `PmtInf`, totales y `ReqdColltnDt` correctos
- [X] T028 [US1] Tests integración emisión CSB: `backend/tests/integration/test_emision_csb.py` — verificar longitud registros tipo 1/3/5, importe total en céntimos, encode ISO-8859-15
- [X] T029 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_remesa_tenant.py` — empresa A crea remesa, empresa B no la ve en listado/detalle/fichero; intento de cobrar desde empresa B → 404
- [X] T030 [US1] Tests cobro manual: `backend/tests/unit/test_cobro_manual.py` — verificar cambio de estado, creación de asiento balanceado (430 vs 572), idempotencia (intentar cobrar dos veces → 409)
- [X] T030a [US1] Tests conciliación bancaria: `backend/tests/integration/test_cobro_conciliado.py` — movimiento de SPEC-013 confirma el recibo, un reintento devuelve el mismo asiento y manual+conciliación no duplican el cobro

**Checkpoint**: User Story 1 completa — remesas SEPA/CSB funcionales con cobro manual. MVP desplegable.

---

## Phase 4: User Story 2 — Liquidación con descuento (Priority: P2) — cubre FR-005

**Goal**: El usuario liquida un recibo aplicando pronto pago si procede; genera asiento balanceado (432/662 contra 430) con `Decimal`.

**Independent Test**: Liquidar con pronto pago genera asiento Debe==Haber con 432/662; sin pronto pago genera solo 430 vs 572.

### Tests for User Story 2

- [X] T031 [P] [US2] Test cálculo descuento: `backend/tests/unit/test_descuento_pronto_pago.py` — dentro del plazo aplica %, neto>=0; fuera del plazo no aplica; neto nunca negativo; edge neto=0
- [X] T032 [P] [US2] Test balance asiento descuento: `backend/tests/unit/test_asiento_descuento.py` — Debe==Haber siempre; 432 + 572 = 430; precision 4 decimales sin error de redondeo

### Implementation for User Story 2

- [X] T033 [P] [US2] Implementar servicio `aplicar_pronto_pago` en `backend/src/services/discount.py`: recibir vencimiento + fecha_pago; buscar `CondicionProntoPago` vigente del tercero (o override factura); calcular neto = importe × (1 - porcentaje/100); validar neto>=0; si fecha_pago - fecha_factura > plazo_dias → no aplica
- [X] T034 [US2] Implementar servicio `liquidar_con_descuento` en `backend/src/services/discount.py`: calcular pronto pago, crear asiento atomico Debe 572 (neto) + 432/662 (descuento) | Haber 430 (total), en transacción ACID; si no hay descuento, solo crear 572 vs 430
- [X] T035 [US2] Implementar endpoint POST `/api/v1/recibos/{recibo_id}/liquidar` en `backend/src/api/treasury/recibos.py`: recibir fecha_pago y cuenta; ejecutar liquidar_con_descuento; devolver importe_neto, descuento, asiento_id
- [X] T036 [US2] Crear página frontend `frontend/src/app/terceros/condiciones/page.tsx`: formulario para crear/editar condiciones de pronto pago por tercero
- [X] T037 [US2] Tests integración liquidación completa: `backend/tests/integration/test_liquidacion_completa.py` — crear vencimiento con descuento, liquidar, verificar asiento balanceado (432/662 vs 430), verificar cambio de estado del vencimiento; liquidar sin descuento → asiento 572 vs 430
- [X] T038 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_descuento_tenant.py` — empresa A liquida con descuento, empresa B no ve el asiento ni la condición

**Checkpoint**: User Stories 1 y 2 completas — remesas + liquidación con pronto pago.

---

## Phase 5: User Story 3 — Devoluciones R19/C19 (Priority: P2) — cubre FR-006

**Goal**: Procesar devoluciones bancarias: revertir cobro con asiento `REVERSAL`, reabrir vencimiento, registrar devolución y reclamación.

**Independent Test**: Al importar R19, el vencimiento vuelve a `pendiente` y se crea un asiento REVERSAL balanceado (inmutabilidad II); reclamación queda registrada.

### Tests for User Story 3

- [X] T039 [P] [US3] Test balance REVERSAL: `backend/tests/unit/test_reversal_balance.py` — Debe==Haber siempre; con gastos: Debe 430+626 | Haber 572; sin gastos: Debe 430 | Haber 572; asiento original NO modificado
- [X] T040 [P] [US3] Test reapertura vencimiento: `backend/tests/unit/test_reapertura_vencimiento.py` — al procesar devolución, ReciboRemesa.estado → devuelto, vencimiento (SPEC-011) → pendiente

### Implementation for User Story 3

- [X] T041 [P] [US3] Implementar parser R19/C19 en `backend/src/services/remittance/refund_r19.py`: parsear fichero AEB cuaderno 19, extraer código (MD01/MD06/AC04 etc.), motivo, importe, importe_gastos, recibo_id asociado
- [X] T041a [P] [US3] Normalizar códigos bancarios en `backend/src/services/remittance/refund_r19.py`: aceptar códigos de hasta 10 caracteres (`MD01`, `MD06`, `AC04`, `R-CUST`) y conservar el código externo original para trazabilidad e idempotencia
- [X] T042 [US3] Implementar servicio `procesar_devolucion` en `backend/src/services/remittance/refund_r19.py`: crear `DevolucionRecibo`, generar asiento `REVERSAL` del cobro (Debe: 430 (+ 626 si gastos), Haber: 572), cambiar `ReciboRemesa.estado → devuelto`, reapertura de `Vencimiento` (SPEC-011) a pendiente; todo en transacción ACID, audit log, sin modificar asiento original
- [X] T043 [US3] Implementar servicio `gestionar_reclamacion` en `backend/src/services/remittance/refund_r19.py`: crear/avanzar `Reclamacion` (abrir → en_curso → resuelta/desestimada), validar que solo una reclamación activa por devolución
- [X] T044 [US3] Implementar endpoint POST importar devoluciones en `backend/src/api/treasury/devoluciones.py`: recibir fichero multipart o JSON; llamar a procesar_devolucion; devolver procesadas/rechazadas
- [X] T045 [US3] Implementar endpoint POST reclamación en `backend/src/api/treasury/devoluciones.py`: recibir devolucion_id + acción + observaciones; llamar a gestionar_reclamacion
- [X] T046 [US3] Crear página frontend `frontend/src/app/devoluciones/page.tsx`: formulario de importación de fichero R19/C19 y listado de devoluciones
- [X] T047 [US3] Crear página frontend `frontend/src/app/devoluciones/[id]/page.tsx`: detalle de devolución con su asiento REVERSAL y formulario de reclamación
- [X] T048 [US3] Tests integración devolución completa: `backend/tests/integration/test_devolucion_completa.py` — importar R19, verificar REVERSAL balanceado, verificar reapertura de vencimiento, verificar cambio de estado del recibo; verificar que asiento original no fue modificado
- [X] T049 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_devolucion_tenant.py` — empresa A importa R19, empresa B no ve la devolución ni el REVERSAL
- [X] T049a [US3] Tests de códigos e idempotencia: ampliar `backend/tests/integration/test_devolucion_completa.py` — aceptar códigos de cuatro caracteres, rechazar reprocesado del mismo retorno y verificar que gastos 626 forman parte del REVERSAL balanceado
- [X] T050 [US3] Tests integración reclamación: `backend/tests/integration/test_reclamacion.py` — crear reclamación, avanzar estados, intentar crear segunda activa → rechazo

**Checkpoint**: User Stories 1, 2 y 3 completas — flujo total de tesorería funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T051 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_treasury.py` — verificar que todo asiento (cobro, descuento, reversión) tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry confirmado; verificar aislamiento empresa_id en todas las tablas treasury
- [X] T052 [P] Hardening multi-tenant: `backend/tests/integration/test_treasury_full_tenant_isolation.py` — escenario completo cross-empresa (remesa A, devolución B, liquidación A desde B → todos 404)
- [X] T053 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_remesas.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T054 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [X] T055 Validación de ejercicios cerrados: verificar que remesas y devoluciones rechazan con 409 si el ejercicio está cerrado (SPEC-002/004)
- [X] T056 Limpieza y documentación: actualizar docstrings en servicios treasury, verificar type hints, ejecutar lint/typecheck

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
- **US2 (P2)**: Sin dependencias de US1/US3; usa Phase 2 completa.
- **US3 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa; integra con asientos de US1 al verificar que REVERSAL es independiente.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T010).
- Phase 3: tests [P] en paralelo (T014-T015), y modelos [P] de US1 en paralelo.
- Phase 4: tests [P] en paralelo (T031-T032).
- Phase 5: tests [P] en paralelo (T039-T040), parser + servicio [P] (T041).
- US1, US2, US3 pueden ejecutarse en paralelo por separado una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T014: "Test correlatividad en backend/tests/unit/test_correlatividad_remesa.py"
Task T015: "Test exclusión recibos en backend/tests/unit/test_exclusion_recibos.py"

# Generadores de fichero en paralelo:
Task T018: "Generador SEPA en backend/src/services/remittance/sepa_dd.py"
Task T019: "Generador CSB 19.19 en backend/src/services/remittance/csb_1919.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T014-T030. Verificar quickstart Scenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP!).
3. + US2 → Test independiente → Deploy/Demo (descuento por pronto pago).
4. + US3 → Test independiente → Deploy/Demo (devoluciones R19/C19).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (remesas + fichero SEPA/CSB).
   - Dev B: User Story 2 (descuento por pronto pago).
   - Dev C: User Story 3 (devoluciones R19/C19).
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

## Phase 7: Convergence

La evaluación de convergencia del 2026-09-16 encontró que `backend/`, `frontend/` y sus
pruebas aún no existían en el repositorio. Las tareas T057–T062 consolidan ese trabajo;
las tareas de verificación permanecen abiertas hasta validar cada criterio de forma
reproducible.

- [X] T057 CRITICAL Implementar la infraestructura y modelos fundacionales de treasury, incluyendo transacciones ACID, auditoría inmutable, índices/FKs con `empresa_id`, Decimal/NUMERIC(18,4) y aislamiento cross-tenant según Constitución I-V y Phase 1-2 (completada — T001–T013)
- [X] T058 CRITICAL Implementar el flujo P1 completo de remesas: selección de vencimientos, numeración correlativa, agrupación multi-fecha, generación SEPA/CSB, emisión, descarga y cobro manual/conciliado idempotente según FR-001..FR-004, FR-007..FR-008 y US1 (completada — T014–T030a)
- [X] T059 HIGH Implementar la liquidación con pronto pago, sus asientos balanceados y las condiciones/mandatos del maestro de terceros según FR-005, SC-003 y US2 (completada — T031–T038)
- [X] T060 HIGH Implementar devoluciones R19/C19, normalización de códigos, REVERSAL inmutable con gastos, reapertura de vencimientos y reclamaciones idempotentes según FR-006, SC-004 y US3 (completada — T039–T050)
- [X] T061 HIGH Crear las páginas y cliente frontend de remesas, devoluciones y condiciones de terceros, incluyendo contexto de empresa activa, estados de error y descarga de ficheros según el plan y los contratos API (completada — T024–T026, T036, T046–T047)
- [X] T062 CRITICAL Ejecutar y completar las pruebas unitarias, de integración y contractuales de balance estricto, aislamiento multi-tenant, correlatividad, formatos SEPA/CSB, conciliación sin duplicados, devoluciones y ejercicios cerrados; ejecutar typecheck y lint antes de cerrar la feature según Constitución V y SC-001..SC-007 (pendiente de verificación final)


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

- `remesa`
- `recibo_remesa`
- `secuencia_remesa`
- `mandato_sepa`
- `condicion_pronto_pago`
- `devolucion_recibo`
- `reclamacion`
- `blob_fichero`
- `cobro_conciliado`

## Qué se ha hecho, y qué no

**Sí**: un guard nuevo en `tests/unit/test_migrations.py`,
`test_toda_tabla_del_orm_tiene_migracion`, que cruza los `__tablename__` de
`src/models/` con los `CREATE TABLE` de `migrations/`. Con él, **una tabla nueva sin
migración se ve al escribir el modelo**, y no meses después. Las 27 están inventariadas
en `TABLAS_SIN_MIGRACION`, con dos guards que impiden que la lista mienta en ninguna de
las dos direcciones.

**No**: la migración de estas 9 tablas. Es trabajo de un día por spec —DDL, enums,
índices, unicidades, FKs compuestas por `empresa_id`, triggers de inmutabilidad que
correspondan, el contrato en `test_pg_schema.py` y los tasks que lo nombren— y no cabe
en una corrección puntual. Lo que **no** hay que hacer es volver a dar la spec por
cerrada sin mirar este apartado: la spec está implementada y probada, y aun así su
funcionalidad no se puede usar.
