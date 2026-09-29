# Tasks: Libros de IVA y Modelos Fiscales (SPEC-012)

**Input**: Design documents from `/specs/012-libros-iva-fiscal/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitucion V exige pytest obligatorio en cada tarea finalizada (partida doble + aislamiento multi-tenant).

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)`, prohibido `float`.

**Alcance**: los modelos solo se calculan y exportan; la presentacion telematica es externa o se cubre en SPEC-029 (solo se declara la interfaz SII aqui). FR-012 (cumplimiento constitucion) se valida en cada fase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3, US4)
- Incluir ruta exacta del archivo en la descripcion

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar modulos `fiscal` y `vat` en backend y frontend segun plan.md.

- [X] T001 [P] Crear estructura de modulos: `backend/src/models/fiscal/__init__.py`, `backend/src/services/vat/__init__.py`, `backend/src/services/vat/libros_iva.py`, `backend/src/services/vat/periodo.py`, `backend/src/services/vat/modelos.py`, `backend/src/services/vat/exportacion.py`, `backend/src/services/vat/recargo_equivalencia.py`, `backend/src/services/vat/criterio_caja.py`, `backend/src/services/vat/sii.py`, `backend/src/api/fiscal/__init__.py`, `backend/src/api/fiscal/routes.py`
- [X] T002 [P] Configurar routers fiscal: registrar prefijos `/api/v1/libros-iva`, `/api/v1/modelos`, `/api/v1/exportaciones`, `/api/v1/regimenes`, `/api/v1/sii` en `backend/src/api/fiscal/routes.py` con dependency de sesion autenticada `empresa_id`
- [X] T003 [P] Crear estructura frontend: `frontend/src/app/libros-iva/`, `frontend/src/app/modelos/`, `frontend/src/app/exportaciones/`, `frontend/src/components/vat/`
- [X] T004 [P] Crear utils de sesion: `backend/src/api/fiscal/deps.py` con `get_empresa_id()` que extrae `empresa_id` del contexto de sesion y bloquea acceso cross-tenant

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base (periodo, exportacion, configuracion) y reglas transversales que toda user story requiere.

**CRITICAL**: Ningun trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 [P] Crear modelo `PeriodoFiscal` en `backend/src/models/fiscal/periodo_fiscal.py`: empresa_id, ejercicio, tipo_periodo ENUM TRIMESTRE/MES, numero_periodo INT, fecha_inicio/fecha_fin, estado ENUM (pendiente/exportado); constraint unicidad (empresa_id, ejercicio, tipo_periodo, numero_periodo)
- [X] T006 [P] Crear modelo `ExportacionModelo` en `backend/src/models/fiscal/exportacion_modelo.py`: empresa_id, ejercicio, modelo ENUM, numero_exportacion BIGINT, periodo_id FK NULL, fecha_exportacion, usuario_id, contenido_hash CHAR(64), fichero_json JSONB, estado ENUM (generado/regenerado/anulado); constraint unicidad (empresa_id, ejercicio, modelo, numero_exportacion)
- [X] T007 [P] Crear modelo `ConfiguracionSII` en `backend/src/models/fiscal/configuracion_sii.py`: empresa_id PK, habilitado BOOLEAN, obligatorio BOOLEAN, identificador_emisor, endpoint_ejecucion TEXT NULL, updated_at
- [X] T008 [P] Crear modelo `IVADiferidoCaja` en `backend/src/models/fiscal/iva_diferido_caja.py`: empresa_id, factura_id FK, vencimiento_id FK, cuota_diferida NUMERIC(18,4), fecha_devengo_real DATE NULL, estado ENUM (diferido/liquidado)
- [X] T009 [P] Implementar servicio de configuracion de cuenta IVA en `backend/src/services/vat/configuracion_cuentas.py`: leer cuentas 472/477 y cuenta de recargo por empresa (SPEC-001) para clasificar operaciones (deducible/no deducible/recargo)
- [X] T010 [P] Tests de modelos fundacionales: `backend/tests/unit/test_fiscal_models.py` — verificar unicidades, constraint de estado, cierre de periodos exportados
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_fiscal_tenant_isolation.py` — periodo/exportacion/configuracion SII en empresa A no visibles ni mutables desde B

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Generar los libros de IVA automaticamente (Priority: P1) — MVP

**Goal**: Los libros de IVA (emitidas, recibidas, intracomunitarias) se construyen automaticamente desde las facturas y sus asientos, sin entrada manual.

**Independent Test**: Efectuando facturas e IVA, los libros reflejan exactamente esas operaciones sin entradas manuales.

### Tests for User Story 1

- [X] T012 [P] [US1] Test derivacion del libro: `backend/tests/unit/test_libros_derivacion.py` — crear facturas+asientos (SPEC-007/002), verificar que cada linea del libro tiene base/cuota/tipo correctos y que la suma de cuotas coincide con los asientos (472/477)
- [X] T013 [P] [US1] Test exclusion sin asiento: `backend/tests/unit/test_libros_exclusion.py` — factura sin asiento vinculado no aparece en el libro hasta que exista su asiento (edge case)
- [X] T014 [P] [US1] Test asentamiento intracomunitario: `backend/tests/unit/test_libros_intracomunitarias.py` — operaciones intracomunitarias aparecen en el libro correspondiente

### Implementation for User Story 1

- [X] T015 [US1] Implementar `construir_libro_emitidas` en `backend/src/services/vat/libros_iva.py`: recorrer facturas emitidas (SPEC-007) con asiento POSTED, extraer base/cuota/tipo de lineas 477, aplicar configuracion de recargo (cuenta separada) y criterio de caja (incluir_303=false si diferido)
- [X] T016 [US1] Implementar `construir_libro_recibidas` en `backend/src/services/vat/libros_iva.py`: recorrer facturas recibidas con asiento POSTED, extraer base/cuota deducible (472) segun configuracion de cuentas (deducible/no deducible)
- [X] T017 [US1] Implementar `construir_libro_intracomunitarias` en `backend/src/services/vat/libros_iva.py`: filtrar operaciones de bienes/servicios intracomunitarios segun configuracion del tercero (SPEC-008)
- [X] T018 [US1] Implementar endpoint GET `/api/v1/libros-iva/{tipo_libro}` en `backend/src/api/fiscal/routes.py` (200; 409 ejercicio/periodo no definidos)
- [X] T019 [US1] Tests integracion libros completo: `backend/tests/integration/test_libros_completo.py` — crear facturas+asientos, construir libros, verificar totales contra asientos
- [X] T020 [US1] Tests aislamiento multi-tenant US1: `backend/tests/integration/test_libros_tenant.py` — empresa B no ve las operaciones de A en ningun libro

**Checkpoint**: User Story 1 completa — libros de IVA funcionales. MVP desplegable parcial.

---

## Phase 4: User Story 2 — Calcular el modelo 303 (IVA trimestral) (Priority: P2)

**Goal**: El 303 del periodo cuadra con los libros (devengado - deducible = resultado; incluye recargo separado e IVA de caja diferido).

**Independent Test**: Calculando el 303 de un trimestre, el resultado coincide con la diferencia devengado - deducible de los libros del periodo.

### Tests for User Story 2

- [X] T021 [P] [US2] Test cuadre 303 con libros: `backend/tests/unit/test_303_cuadre.py` — devengado - deducible == resultado; sin descuadres (422 descuadre_libros si el calculo difiere de libros)
- [X] T022 [P] [US2] Test 303 intracomunitarias: `backend/tests/unit/test_303_intracomunitarias.py` — las cuotas de intracomunitarias se reflejan en el 303 (y preparan el 349)
- [X] T023 [P] [US2] Test periodo exportado impide recalculo: `backend/tests/unit/test_303_periodo_exportado.py` — si el periodo esta exportado, el recalculado se marca regenerado con advertencia (nunca memoria silenciosa)

### Implementation for User Story 2

- [X] T024 [US2] Implementar `calcular_303` en `backend/src/services/vat/modelos.py`: agregar cuotas por tipo desde libros del periodo, aplicar rectificativas, calcular resultado (a ingresar/compensar), verificar cuadre con libros en backend
- [X] T025 [US2] Implementar `resumen_periodico` en `backend/src/services/vat/modelos.py`: resumen trimestral/mensual de cuotas por tipo (T-02 del spec) alimentado por los libros
- [X] T026 [US2] Implementar endpoint GET `/api/v1/modelos/303` en `backend/src/api/fiscal/routes.py` (200; 422 descuadre_libros; 409 periodo no definido/exportado)
- [X] T027 [US2] Tests integracion 303 completo: `backend/tests/integration/test_303_completo.py` — ventas 21% + compras 21%, resultado correcto y cuadre con libros del periodo
- [X] T028 [US2] Tests aislamiento multi-tenant US2: `backend/tests/integration/test_303_tenant.py` — el 303 de A no ve ni mezcla operaciones de B

**Checkpoint**: User Stories 1 y 2 completas — libros y 303 funcionales.

---

## Phase 5: User Story 3 — Exportar modelos e informe de operaciones con terceros (Priority: P2)

**Goal**: El usuario exporta el 303/349 y prepara el resumen anual 347 en formato legible, con trazabilidad del periodo.

**Independent Test**: Exportando los modelos de un periodo, el fichero incluye el periodo correcto y agrega las operaciones por tercero.

### Tests for User Story 3

- [X] T029 [P] [US3] Test exportacion 303 identifica periodo: `backend/tests/unit/test_exportacion_303_periodo.py` — fichero con ejercicio/periodo/NIF y totales del trimestre; hash sha256
- [X] T030 [P] [US3] Test 347 limite legal: `backend/tests/unit/test_347_limite.py` — solo terceros con importe > 3005.06 agregados por NIF/clave
- [X] T031 [P] [US3] Test 349 agrupacion: `backend/tests/unit/test_349_intracomunitarias.py` — operaciones intracomunitarias del periodo agregadas por NIF

### Implementation for User Story 3

- [X] T032 [US3] Implementar `preparar_347` en `backend/src/services/vat/modelos.py`: agregar operaciones por NIF y clave operacional del ejercicio, aplicar limite 3005.06 con Decimal exacto
- [X] T033 [US3] Implementar `preparar_349` en `backend/src/services/vat/modelos.py`: agregar operaciones intracomunitarias por NIF del periodo
- [X] T034 [US3] Implementar generadores de fichero en `backend/src/services/vat/exportacion.py`: CSV/XML/JSON con los totales del modelo (formato segun `contracts/modelos-fiscales.md`), redondeo legal a 2 decimales solo en el fichero
- [X] T035 [US3] Implementar `registrar_exportacion` en `backend/src/services/vat/exportacion.py`: calcular modelo con cuadre previo, generar fichero, asignar numero_exportacion correlativo por (empresa, ejercicio, modelo) con `SELECT ... FOR UPDATE`, calcular hash, persistir `ExportacionModelo` en transaccion ACID con audit log; si el periodo ya fue exportado -> estado `regenerado` con advertencia
- [X] T036 [US3] Implementar endpoints en `backend/src/api/fiscal/routes.py`: POST `/exportaciones` (201), GET `/exportaciones/{id}/descargar` (200), GET `/exportaciones` (paginado), GET `/modelos/347`, GET `/modelos/349`
- [X] T037 [US3] Tests integracion exportacion completo: `backend/tests/integration/test_exportacion_completo.py` — exportar 303, descargar fichero, verificar contenidos/periodo y trazabilidad; re-exportar -> regenerado con numeracion correlativa
- [X] T038 [US3] Tests aislamiento multi-tenant US3: `backend/tests/integration/test_exportacion_tenant.py` — empresa B no puede descargar las exportaciones de A (404) ni ver su 347/349

**Checkpoint**: User Stories 1, 2 y 3 completas — libros, 303, 347/349 y exportacion funcionales.

---

## Phase 6: User Story 4 — Gestionar recargo de equivalencia e IVA de criterio de caja (Priority: P2)

**Goal**: El recargo de equivalencia se trata como cuota separada y el criterio de caja difiere el IVA hasta el cobro/pago, cuadrando en libros y 303.

**Independent Test**: Un periodo con operaciones de recargo y de caja cuadra sus cuotas en libros y 303 sin mezclar importes.

### Tests for User Story 4

- [X] T039 [P] [US4] Test recargo cuota separada: `backend/tests/unit/test_recargo_separado.py` — cuota de recargo en campo y cuenta distintos del IVA; el 303 la presenta en su casilla; suma no mezclada
- [X] T040 [P] [US4] Test criterio caja diferido: `backend/tests/unit/test_criterio_caja_diferido.py` — cuota diferida (incluir_303=false) no entra en el 303 hasta el cobro/pago; `IVADiferidoCaja` pasa a liquidado con fecha de devengo real
- [X] T041 [P] [US4] Test cuadre con ambos regimenes: `backend/tests/unit/test_303_recargo_caja.py` — periodo con recargo y caja cuadra exactamente (libros vs 303) sin mezclar

### Implementation for User Story 4

- [X] T042 [US4] Implementar `aplicar_recargo` en `backend/src/services/vat/recargo_equivalencia.py`: detectar operaciones de minoristas segun configuracion, registrar recargo_cuota separado en libros y en el 303 con cuenta diferenciada
- [X] T043 [US4] Implementar `aplicar_criterio_caja` en `backend/src/services/vat/criterio_caja.py`: marcar IVA diferido ligado al vencimiento (SPEC-011); al saldarse el vencimiento, actualizar `IVADiferidoCaja` a liquidado y re-incluir la cuota en el periodo de devengo real
- [X] T044 [US4] Implementar `sincronizar_con_vencimientos` en `backend/src/services/vat/criterio_caja.py`: listener/servicio que consume el estado de los vencimientos de SPEC-011 para activar el devengo por criterio de caja
- [X] T045 [US4] Implementar endpoints en `backend/src/api/fiscal/routes.py`: GET `/regimenes/estado`, POST `/regimenes/recargo-equivalencia`, POST `/regimenes/criterio-caja` (validacion de cuenta de recargo configurada)
- [X] T046 [US4] Tests integracion regimenes completo: `backend/tests/integration/test_regimenes_completo.py` — factura con recargo y factura de caja cobrada en periodo posterior; verificar que el 303 del periodo del cobro recoge la cuota y que los libros cuadran
- [X] T047 [US4] Tests aislamiento multi-tenant US4: `backend/tests/integration/test_regimenes_tenant.py` — la configuracion de recargo/caja y los diferidos de A no afectan a B

**Checkpoint**: User Stories 1, 2, 3 y 4 completas — fiscal funcional con regimenes especiales.

---

## Phase 7: Interfaz SII (declarada, sin envio) + Polish & Cross-Cutting Concerns

**Purpose**: Declarar la interfaz SII habilitable por empresa y el refinamiento transversal.

- [X] T048 [P] Implementar `configurar_sii` en `backend/src/services/vat/sii.py`: habilitar/deshabilitar por empresa, ajustar periodicidad 303 a MES con advertencia, validar identificador de emisor (NIF)
- [X] T049 [P] Implementar generador XML SII en `backend/src/services/vat/sii.py`: mapear libros del periodo a `SuministroLrFacturasEmitidas/Recibidas` segun `contracts/sii-xml.md`, calcular hash, SIN envio (interfaz para SPEC-029)
- [X] T050 [P] Critica constitucional FR-012: `backend/tests/unit/test_constitucion_fiscal.py` — todo asiento que sustenta libros cumple Debe==Haber; ninguna exportacion muta asientos; aislamiento empresa_id en todas las tablas fiscales
- [X] T051 Hardening multi-tenant: `backend/tests/integration/test_fiscal_full_tenant_isolation.py` — escenario completo cross-empresa (libros A, 303 B, exportacion A descargada desde B -> 404)
- [X] T052 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_fiscal.py` — reproducir los 7 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T053 [P] Code review: verificar que todos los servicios usan `async with async_session.begin()` (transaccion ACID); verificar que ningun endpoint expone `empresa_id` del request body; verificar Decimal/NUMERIC(18,4) en todos los importes
- [X] T054 Crear pagina frontend `frontend/src/app/libros-iva/page.tsx`: selector de tipo (emitidas/recibidas/intracomunitarias) y periodo, tabla de operaciones con base/cuota/recargo
- [X] T055 [P] Crear paginas frontend `frontend/src/app/modelos/page.tsx` y `frontend/src/app/exportaciones/page.tsx`: calculo de 303/347/349 con flags de cuadre y descarga de ficheros con trazabilidad
- [X] T056 Limpieza y documentacion: actualizar docstrings en servicios vat, verificar type hints, ejecutar lint/typecheck

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2 y US1 (el 303 se alimenta de los libros).
- **US3 (Phase 5)**: Depende de Phase 2 y US2 (exporta modelos calculados); el 347/349 dependen de US1 (libros).
- **US4 (Phase 6)**: Depende de Phase 2 y US1 (integrado en libros); usa los vencimientos de SPEC-011.
- **SII + Polish (Phase 7)**: Depende de las user stories completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Depende de US1 (el 303 cuadra con los libros).
- **US3 (P2)**: Depende de US2 (303) y de US1 (347/349); comparte la logica de modelos.
- **US4 (P2)**: Depende de US1 (recargo/caja se registran en libros); integra SPEC-011 (vencimientos).

### Within Each User Story

- Tests ANTES de la implementacion (TDD constitucion V).
- Modelos antes de servicios.
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integracion y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: todos los modelos [P] en paralelo (T005-T009).
- Phase 3: tests [P] en paralelo (T012-T014) y te vat servicios en paralelo (T015-T017).
- Phase 4: tests [P] en paralelo (T021-T023).
- Phase 5: tests [P] en paralelo (T029-T031).
- Phase 6: tests [P] en paralelo (T039-T041).
- US4 puede empezar cuando US1 este completo (lógica de libros); no depende de US2/US3.

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T012: "Test derivacion del libro en backend/tests/unit/test_libros_derivacion.py"
Task T013: "Test exclusion sin asiento en backend/tests/unit/test_libros_exclusion.py"

# Construccion de libros en paralelo:
Task T015: "Libro emitidas en backend/src/services/vat/libros_iva.py"
Task T016: "Libro recibidas en backend/src/services/vat/libros_iva.py"
Task T017: "Libro intracomunitarias en backend/src/services/vat/libros_iva.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1 (libros de IVA).
4. **PARAR y VALIDAR**: Ejecutar T012-T020. Verificar quickstart Scenario 1.
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP: libros de IVA).
3. + US2 → Test independiente → Deploy/Demo (modelo 303 cuadrado con libros).
4. + US3 → Test independiente → Deploy/Demo (exportacion y 347/349 con trazabilidad).
5. + US4 → Test independiente → Deploy/Demo (recargo de equivalencia y criterio de caja).
6. + SII/Polish → Interfaz SII declarada y validacion constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (libros de IVA).
   - Dev B: User Story 2 (modelo 303) — requiere US1 para el cuadre.
   - Dev C: User Story 3 (exportacion y 347/349) — tras US1.
   - Dev D: User Story 4 (recargo + caja) — tras US1, integra SPEC-011.
3. Cada story se integra y prueba independientemente (con US1 como base).
4. SII y Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Cada user story debe ser completable y testeable independientemente (US2/US3/US4 dependen de US1: los modelos se alimentan de los libros).
- Verificar tests fallen antes de implementar.
- Commit tras cada tarea o grupo logico.
- Parar en cada checkpoint para validar story independientemente.
- Constitucion V: ninguna tarea se considera finalizada sin pytest de balance + aislamiento multi-tenant.
- FR-012: todas las fases validan la constitucion; T050 lo verifica explicitamente.
- El envio SII real y la presentacion telematica se integran con SPEC-029; aqui solo se declara la interfaz.

---

## Estado real (implementación 2026-09-20)

56/56 tareas completadas. Puertas en verde: pytest **771 passed / 5 skipped** (SQLite) y
**776 passed / 0 skipped** (PostgreSQL 16.4 real, esquema migrado 000–006); `ruff` + `mypy`
limpios (191 fuentes); `tsc` + `eslint` + `next build` **43 rutas**
(incl. `/libros-iva`, `/modelos`, `/exportaciones`).

### Desviaciones documentadas

1. **T002/T004 (estructura API)**: implementado como paquete `backend/src/api/fiscal/`
   (`__init__.py`, `deps.py`, `comun.py`, `routes.py`, `libros_iva.py`, `modelos.py`,
   `exportaciones.py`, `regimenes.py`, `sii.py`) en lugar del módulo único; `deps.py`
   re-exporta `api.deps.get_empresa_id` (JWT + `X-Empresa-Activa`).
2. **Modelos**: `PeriodoFiscal` se define y `obtener_o_crear_periodo` existe, pero los
   endpoints no persisten periodos (el período se identifica por `ejercicio`/`periodo`/
   `tipo_periodo`); `ExportacionModelo.periodo_id` queda NULL y el período se guarda en
   `fichero_json.etiqueta_periodo`. Se añade `ConfiguracionFiscal` (recargo/criterio de caja),
   no previsto en el data-model, para la cuenta de recargo y los regímenes.
3. **Sin migración SQL**: las tablas `periodo_fiscal`, `exportacion_modelo`,
   `configuracion_sii`, `configuracion_fiscal` e `iva_diferido_caja` se crean vía
   `Base.metadata.create_all` en tests (precedente de `models/ar`/`treasury`/`reporting`);
   no se añadió `migrations/007_*.sql`.
4. **US1 intracomunitarias**: como SPEC-008 no expone un flag de operador intracomunitario,
   el tercero se clasifica por NIF/VAT (dos letras de país distintas de `ES`) o IBAN no
   español; las líneas se derivan de `Factura`/`FacturaLinea` con asiento POSTED.
5. **US2 (303)**: `cuadre_libros` se calcula desde los mismos libros del período (es
   estructuralmente verdadero con asientos balanceados); `422 descuadre_libros` queda como
   guarda defensiva y los códigos `ejercicio_no_definido`/`periodo_no_definido` no se
   disparan (el rango inválido devuelve 409 `periodo_fuera_de_rango`).
6. **US4 (criterio de caja)**: `aplicar_criterio_caja` es un servicio explícito (no se
   engancha automáticamente a la emisión de SPEC-007); `sincronizar_con_vencimientos`
   liquida el diferido cuando el `Vencimiento` de SPEC-011 está `cobrado` o su saldo es 0,
   activando `iva_devengado` para que la cuota entre en el 303 del período del cobro.
7. **US3 (exportación)**: el contenido del fichero se almacena en `fichero_json.contenido`
   (JSONB) con su `content_type`; la descarga reproduce ese contenido. El 347 es JSON y el
   349 XML; el 303 admite CSV/XML/JSON. Redondeo legal a 2 decimales solo en el fichero.
8. **SII**: XML simplificado (sin validación XSD) de `SuministroLF`/`SuministroLR`;
   `sii.obtener_configuracion_sii` + `configurar_sii` (ajuste a MES) + `generar_xml_sii`
   (409 `sii_no_habilitado`); sin envío, integrable con SPEC-029.
9. **Ficheros de test consolidados**: `tests/integration/test_fiscal_us{1,2,3,4}.py`,
   `test_fiscal_sii.py`, `test_quickstart_fiscal.py` y `tests/unit/test_constitucion_fiscal.py`;
   la fixture `fiscal_client` (`tests/conftest.py`) siembra PGC + cuentas `472/475/477` y
   subcuentas, terceros (ES e intracomunitario) y facturas emitidas/recibidas con asiento en
   A=10/B=20.
10. **T053 (transacción ACID)**: los servicios usan `flush()` dentro del boundary de `get_db`
    (patrón del proyecto), no `async with async_session.begin()` anidado; ningún endpoint
    acepta `empresa_id` del body/path y todos los importes son `Decimal`/`NUMERIC(18,4)`.
11. **Mejora colateral en SPEC-007**: `construir_lineas` omite la línea de IVA cuando la cuota
    es 0 (necesario para intracomunitarias al 0 %), evitando la línea 0/0 rechazada por el
    validador multilínea.


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

- `periodo_fiscal`
- `exportacion_modelo`
- `configuracion_sii`
- `iva_diferido_caja`
- `clasificacion_efe`

## Qué se ha hecho, y qué no

**Sí**: un guard nuevo en `tests/unit/test_migrations.py`,
`test_toda_tabla_del_orm_tiene_migracion`, que cruza los `__tablename__` de
`src/models/` con los `CREATE TABLE` de `migrations/`. Con él, **una tabla nueva sin
migración se ve al escribir el modelo**, y no meses después. Las 27 están inventariadas
en `TABLAS_SIN_MIGRACION`, con dos guards que impiden que la lista mienta en ninguna de
las dos direcciones.

**No**: la migración de estas 5 tablas. Es trabajo de un día por spec —DDL, enums,
índices, unicidades, FKs compuestas por `empresa_id`, triggers de inmutabilidad que
correspondan, el contrato en `test_pg_schema.py` y los tasks que lo nombren— y no cabe
en una corrección puntual. Lo que **no** hay que hacer es volver a dar la spec por
cerrada sin mirar este apartado: la spec está implementada y probada, y aun así su
funcionalidad no se puede usar.
