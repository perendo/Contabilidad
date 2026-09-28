# Tasks: Importación y Exportación Masiva de Asientos Contables (SPEC-005)

**Input**: Design documents from `/specs/005-import-export-asientos/`

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
| FR-001 | Aislar importación/exportación por empresa activa | US1 |
| FR-002 | Previsualización dry-run sin escritura en BD | US1 |
| FR-003 | Validar cuentas, partida doble y ejercicio abierto | US1 |
| FR-004 | Resumen con total, válidos, errores y detalle | US1 |
| FR-005 | Confirmar importación con re-validación atómica | US2 |
| FR-006 | Numeración secuencial por empresa y ejercicio | US2 |
| FR-007 | Auditoría de cada operación de importación | US2 |
| FR-008 | Exportar diario a CSV/Excel por rango de fechas | US3 |
| FR-009 | Precisión Decimal, prohibido float en import/export | US3 |
| FR-010 | Ver errores en previsualización y confirmar | US1 |
| FR-011 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar módulo de importación/exportación en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo: `backend/src/services/importexport/__init__.py`, `backend/src/services/importexport/parseador.py`, `backend/src/services/importexport/validador.py`, `backend/src/services/importexport/importador.py`, `backend/src/services/importexport/exportador.py`
- [X] T002 [P] Crear endpoint router: `backend/src/api/importexport.py` con prefijo `/api/v1/asientos/importar` y `/api/v1/asientos/exportar`, dependency de sesión autenticada `empresa_id`
- [X] T003 [P] Crear utils de sesión: `backend/src/api/importexport/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesión y bloquea acceso cross-tenant
- [X] T004 [P] Crear estructura frontend: `frontend/src/app/contabilidad/import-export/`, `frontend/src/components/importexport/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Utilidades de parseo de Decimal y parseo de archivos que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 Implementar utilidad de parseo de importes en `backend/src/services/importexport/parseador.py`: función `parse_decimal(valor_str: str) -> Decimal` que acepta coma o punto como separador decimal, elimina separadores de miles, valida que el resultado sea `Decimal` válido y no negativo para importes; lanza error claro si el parseo falla
- [X] T006 Implementar parseador CSV en `backend/src/services/importexport/parseador.py`: función `parsear_csv(file_bytes: bytes, empresa_id: int) -> list[FilaCruda]` que detecta encoding (UTF-8 BOM, ISO-8859-1), separador (auto: `;`, `,`, `\t`), valida cabeceras requeridas (fecha, numero_asiento, concepto, cuenta, debe, haber), devuelve lista de filas crudas normalizadas con agrupación por `numero_asiento`
- [X] T007 Implementar parseador XLSX en `backend/src/services/importexport/parseador.py`: función `parsear_xlsx(file_bytes: bytes, empresa_id: int) -> list[FilaCruda]` que lee la hoja activa, valida cabeceras, acepta celdas numéricas y de texto para importes, agrupa por `numero_asiento`
- [X] T008 [P] Tests de parseo: `backend/tests/unit/test_parseador_importes.py` — verificar `parse_decimal("1.250,50")` == Decimal("1250.50"), `parse_decimal("1250.50")` == Decimal("1250.50"), `parse_decimal("abc")` lanza error, `parse_decimal("-100")` lanza error
- [X] T009 [P] Tests de parseo CSV: `backend/tests/unit/test_parseador_csv.py` — verificar detección de encoding, separador, agrupación por numero_asiento, rechazo de cabecera incompleta, manejo de valores vacíos en debe/haber (interpretar como 0)
- [X] T010 Tests de aislamiento multi-tenant foundational: `backend/tests/integration/test_importexport_tenant_isolation.py` — verificar que el parseador no expone datos de otra empresa (cuentas de empresa B reportadas como no encontradas desde empresa A)

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Previsualizar la importación de asientos (Priority: P1) ?? MVP — cubre FR-001, FR-002, FR-003, FR-004, FR-010, FR-011

**Goal**: El contador sube un archivo CSV o Excel y el sistema realiza una pre-validación (dry-run) sin escritura, mostrando totales y errores detallados.

**Independent Test**: Subiendo un archivo mixto (válidos + erróneos), el resumen distingue válidos/erróneos y no se escribe ningún dato en el sistema.

### Tests for User Story 1

- [X] T011 [P] [US1] Test previsualización sin escritura: `backend/tests/unit/test_previsualizacion_dryrun.py` — crear archivo con 3 asientos (2 válidos, 1 desbalanceado), llamar a previsualizar, verificar que total=3, validos=2, errores=1, tipo_error=desbalanceo; verificar que no se crea ningún JournalEntry en la BD
- [X] T012 [P] [US1] Test validación cuentas: `backend/tests/unit/test_previsualizacion_cuentas.py` — archivo con cuenta inexistente → tipo_error=cuenta_no_encontrada; archivo con cuenta no apuntable → tipo_error=cuenta_no_apuntable; archivo con fecha en ejercicio cerrado → tipo_error=ejercicio_cerrado
- [X] T013 [P] [US1] Test rechazo formato inválido: `backend/tests/unit/test_previsualizacion_formato.py` — archivo sin cabeceras requeridas → error 422 columnas faltantes; archivo binario corrupto → error 422 formato no soportado

### Implementation for User Story 1

- [X] T014 [US1] Implementar servicio `validar_asiento` en `backend/src/services/importexport/validador.py`: recibir lista de filas crudas agrupadas por asiento; por cada grupo: (a) validar que tiene al menos una línea al Debe y una al Haber, (b) validar existencia y apuntabilidad de cada cuenta contra `CuentaContable` de la empresa activa, (c) validar que la fecha pertenece a un ejercicio abierto, (d) calcular `Decimal(sum_debe) == Decimal(sum_haber)`, (e) devolver lista de errores por fila
- [X] T015 [US1] Implementar servicio `previsualizar_importacion` en `backend/src/services/importexport/importador.py`: recibir archivo subido, llamar a parseador (CSV o XLSX), llamar a validador, devolver `ResultadoImportacion` con totales y errores; **no escribir nada en la BD**
- [X] T016 [US1] Implementar endpoint POST `/api/v1/asientos/importar/previsualizar` en `backend/src/api/importexport.py`: recibir multipart file, llamar a `previsualizar_importacion`, devolver 200 con `ResultadoImportacion` o 422 con error de formato/tamaño
- [X] T017 [US1] Crear página frontend `frontend/src/app/contabilidad/import-export/page.tsx`: zona de drag-and-drop para subir archivo, tabla de resultados con totales y lista de errores resaltados, botón "Confirmar importación" habilitado solo si hay asientos válidos
- [X] T018 [US1] Tests integración previsualización completa: `backend/tests/integration/test_previsualizacion_completa.py` — subir archivo mixto vía endpoint, verificar respuesta 200 con totales correctos, verificar que no se creó ningún JournalEntry
- [X] T019 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_previsualizacion_tenant.py` — empresa A sube archivo con cuentas de B → cuentas reportadas como no encontradas; empresa B sube archivo con cuentas de A → mismo comportamiento

**Checkpoint**: User Story 1 completa — previsualización dry-run funcional. MVP desplegable.

---

## Phase 4: User Story 2 — Confirmar y ejecutar la importación definitiva (Priority: P1) — cubre FR-005, FR-006, FR-007

**Goal**: El contador confirma la importación; el sistema re-valida, importa únicamente los asientos válidos con transacciones atómicas por asiento, asigna numeración secuencial y registra en auditoría.

**Independent Test**: Confirmando la importación de un archivo mixto, solo los asientos válidos se registran, con numeración correlativa, y la operación queda auditada.

### Tests for User Story 2

- [X] T020 [P] [US2] Test importación atómica: `backend/tests/unit/test_importar_atomico.py` — importar 3 asientos válidos, verificar que los 3 existen con cabecera + líneas, verificar que la suma de debe y haber de cada uno cuadra
- [X] T021 [P] [US2] Test numeración correlativa: `backend/tests/unit/test_importar_correlatividad.py` — importar 5 asientos en el mismo ejercicio, verificar numero_asiento correlativo sin saltos; importar 2 en ejercicio distinto → secuencia independiente
- [X] T022 [P] [US2] Test omisión parcial: `backend/tests/unit/test_importar_omision_parcial.py` — importar archivo mixto, verificar que los válidos se importan y los erróneos se omiten sin afectar a los demás
- [X] T023 [P] [US2] Test auditoría importación: `backend/tests/unit/test_importar_auditoria.py` — importar asientos, verificar que se registra en audit log (empresa, usuario, acción, timestamp)

### Implementation for User Story 2

- [X] T024 [US2] Implementar servicio `importar_asientos` en `backend/src/services/importexport/importador.py`: recibir archivo, parsear, re-validar, para cada asiento válido: (a) obtener `numero_asiento` con `SELECT ... FOR UPDATE` sobre secuencia bloqueada por (empresa_id, ejercicio), (b) crear `JournalEntry` + `JournalEntryLine` en `async with async_session.begin()`, (c) registrar audit log en la misma transacción. Si un asiento falla, omitirlo y continuar. Devolver `ResultadoImportacionDefinitiva`
- [X] T025 [US2] Implementar servicio de correlatividad en `backend/src/services/importexport/importador.py`: función `siguiente_numero_asiento(empresa_id, ejercicio, session)` con `SELECT ... FOR UPDATE` sobre tabla de contadores o secuencia PostgreSQL por (empresa_id, ejercicio)
- [X] T026 [US2] Implementar endpoint POST `/api/v1/asientos/importar/confirmar` en `backend/src/api/importexport.py`: recibir multipart file, llamar a `importar_asientos`, devolver 201 con `ResultadoImportacionDefinitiva` o 422 si no hay asientos válidos
- [X] T027 [US2] Tests integración importación completa: `backend/tests/integration/test_importar_completa.py` — subir archivo mixto vía endpoint, verificar respuesta 201 con asientos_importados y numeración correlativa, verificar JournalEntries creadas con Debe==Haber
- [X] T028 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_importar_tenant.py` — importar en empresa A, verificar que empresa B no ve los asientos

**Checkpoint**: User Stories 1 y 2 completas — importación completa con previsualización y confirmación.

---

## Phase 5: User Story 3 — Exportar el libro diario (Priority: P2) — cubre FR-008, FR-009

**Goal**: El contador exporta el libro diario a CSV o Excel por rango de fechas, con precisión de 4 decimales y solo los asientos de la empresa activa.

**Independent Test**: Exportando el diario por rango de fechas se obtiene un archivo descargable con los asientos de la empresa activa y montos de Debe/Haber exactos.

### Tests for User Story 3

- [X] T029 [P] [US3] Test exportación CSV: `backend/tests/unit/test_exportar_csv.py` — exportar diario con asientos, verificar encoding UTF-8 BOM, separador `;`, importes con 4 decimales exactos, solo asientos POSTED
- [X] T030 [P] [US3] Test exportación XLSX: `backend/tests/unit/test_exportar_xlsx.py` — exportar diario, verificar que el XLSX tiene hoja "Diario" con columnas correctas y formato decimal
- [X] T031 [P] [US3] Test aislamiento exportación: `backend/tests/unit/test_exportar_aislamiento.py` — crear asientos en empresa A y B, exportar desde A, verificar que no aparecen los de B

### Implementation for User Story 3

- [X] T032 [P] [US3] Implementar generador CSV en `backend/src/services/importexport/exportador.py`: función `generar_csv(asientos: list, empresa_id, fecha_desde, fecha_hasta) -> bytes` que genera CSV con encoding UTF-8 BOM, separador `;`, importes con 4 decimales exactos, ordenado por fecha+numero_asiento
- [X] T033 [P] [US3] Implementar generador XLSX en `backend/src/services/importexport/exportador.py`: función `generar_xlsx(asientos: list, empresa_id, fecha_desde, fecha_hasta) -> bytes` que genera XLSX con hoja "Diario", formatos de celda decimal con 4 decimales
- [X] T034 [US3] Implementar servicio `exportar_diario` en `backend/src/services/importexport/exportador.py`: consultar JournalEntry POSTED por empresa_id y rango de fechas, generar archivo en el formato solicitado, devolver bytes con metadata
- [X] T035 [US3] Implementar endpoint GET `/api/v1/asientos/exportar` en `backend/src/api/importexport.py`: recibir query params (fecha_desde, fecha_hasta, formato), llamar a `exportar_diario`, devolver archivo con Content-Disposition
- [X] T036 [US3] Tests integración exportación completa: `backend/tests/integration/test_exportar_completa.py` — importar asientos, exportar a CSV y XLSX, verificar contenido del archivo descargado
- [X] T037 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_exportar_tenant.py` — empresa A importa asientos, empresa B exporta → archivo vacío

**Checkpoint**: User Stories 1, 2 y 3 completas — flujo completo de importación/exportación funcional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T038 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_importexport.py` — verificar que todo asiento importado tiene Debe==Haber; verificar que no se actualiza/borra ningún JournalEntry; verificar aislamiento empresa_id en todas las operaciones
- [X] T039 [P] Hardening multi-tenant: `backend/tests/integration/test_importexport_full_tenant_isolation.py` — escenario completo cross-empresa (importación A, exportación B → vacío, previsualización B con archivo de A → cuentas no encontradas)
- [X] T040 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_importexport.py` — reproducir los 5 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T041 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes; verificar que no se usa `float` en ningún punto del parseo
- [X] T042 Validación de ejercicios cerrados: verificar que tanto previsualización como importación rechazan con 409 asientos con fecha en ejercicio cerrado
- [X] T043 Limpieza y documentación: actualizar docstrings en servicios importexport, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; puede empezar en paralelo con US1 (pero US2 requiere US1 para el mismo flujo, así que en la práctica va después).
- **US3 (Phase 5)**: Depende de Phase 2; puede empezar en paralelo con US1.
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P1)**: Usa servicios de US1 (parseador, validador); se implementa después de US1.
- **US3 (P2)**: Sin dependencias de US1/US2; usa Phase 2 completa.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: tests [P] en paralelo (T008-T009).
- Phase 3: tests [P] en paralelo (T011-T013).
- Phase 4: tests [P] en paralelo (T020-T023).
- Phase 5: tests [P] en paralelo (T029-T031), generadores CSV/XLSX [P] (T032-T033).
- US1, US3 pueden ejecutarse en paralelo una vez completada Phase 2.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T011: "Test previsualización dry-run en backend/tests/unit/test_previsualizacion_dryrun.py"
Task T012: "Test validación cuentas en backend/tests/unit/test_previsualizacion_cuentas.py"
Task T013: "Test rechazo formato en backend/tests/unit/test_previsualizacion_formato.py"

# Implementación secuencial después de tests:
Task T014: "Validador en backend/src/services/importexport/validador.py"
Task T015: "Servicio previsualizar en backend/src/services/importexport/importador.py"
Task T016: "Endpoint previsualizar en backend/src/api/importexport.py"
Task T017: "Frontend drag-and-drop en frontend/src/app/contabilidad/import-export/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T011-T019. Verificar quickstart Scenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP! previsualización dry-run).
3. + US2 → Test independiente → Deploy/Demo (importación definitiva).
4. + US3 → Test independiente → Deploy/Demo (exportación diario).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 + US2 (previsualización + importación, secuenciales).
   - Dev B: User Story 3 (exportación).
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
- Esta feature no crea tablas nuevas; consume JournalEntry (SPEC-002), CuentaContable (SPEC-001) y EjercicioContable (SPEC-004).

## Estado real (implementación 2026-09-19, 43/43)

- **Implementado**: `services/importexport/{parseador,validador,importador,exportador}.py` + `api/importexport.py` (`/api/v1/asientos/importar/previsualizar|confirmar`, `/exportar`) + frontend drag-and-drop.
- **Dependencia nueva**: `openpyxl>=3.1,<4.0` (añadido a `requirements.txt`) para XLSX.
- **Desviaciones**:
  - T003: no se crea `api/importexport/deps.py`; se reutiliza el guard compartido `api.deps.get_empresa_id`.
  - T024/T025: la numeración correlativa se delega en `services/journal/sequence.next_numero` (SPEC-002, `SELECT ... FOR UPDATE`); la importación usa `crear_borrador`+`asentar` por asiento dentro de un `SAVEPOINT` (`db.begin_nested()`), de modo que un asiento inválido se omite sin abortar el resto.
  - T008: `parse_decimal` interpreta el punto como decimal cuando no hay coma (`"1250.50"`); con coma, la coma es el separador decimal y el punto de miles.
- Puertas: 29 tests nuevos en verde; ruff + mypy limpios; `next build` con `/contabilidad/import-export`.
