# Tasks: Export Integral del Tenant (Backup y Portabilidad) (SPEC-029)

**Input**: Design documents from `/specs/029-export-integral/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests incluidos; la constitución V exige pytest obligatorio en cada tarea finalizada (huella verificable + aislamiento multi-tenant + precisión decimal).

**Organization**: Organizado por user story para implementación y test independientes.

**Stack**: Python 3.11+ / FastAPI async / SQLAlchemy 2.x async + asyncpg / PostgreSQL 16+ / Next.js. Importes: `Decimal`/`NUMERIC(18,4)` serializados como strings en JSON, prohibido `float`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Ejecutable en paralelo (distintos archivos, sin dependencias)
- **[Story]**: User story a la que pertenece (US1, US2, US3)
- Incluir ruta exacta del archivo en la descripción

---

## Trazabilidad FR ↔ User Story

| Requisito | Descripción breve | User Story |
|---|---|---|
| FR-001 | Exportación completa del tenant con inventario de bloques | US1 |
| FR-002 | Huella verificable y manifiesto de integridad | US2 |
| FR-003 | Excluir datos de otras empresas, solo empresa activa | US1 |
| FR-004 | Incluir bloques: cuentas, asientos, terceros, vencimientos | US1 |
| FR-005 | Filtrar por rango de ejercicios antes de exportar | US1 |
| FR-006 | Incluir datos SII AEAT, presentación opcional | US3 |
| FR-007 | Cumplir constitución en flujo completo | US1 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar el módulo `export/` en backend y frontend según plan.md.

- [X] T001 [P] Crear estructura del módulo export: `backend/src/models/export/__init__.py`, `backend/src/models/export/config_sii.py`, `backend/src/models/export/exportacion.py`, `backend/src/models/export/manifiesto.py`, `backend/src/models/export/blob_exportacion.py`
- [X] T002 [P] Crear servicios: `backend/src/services/export/__init__.py`, `backend/src/services/export/bloques.py`, `backend/src/services/export/recopilar.py`, `backend/src/services/export/manifiesto.py`, `backend/src/services/export/zip_generator.py`, `backend/src/services/export/persistir.py`, `backend/src/services/export/verificar.py`, `backend/src/services/export/sii.py`
- [X] T003 [P] Configurar router: crear `backend/src/api/export.py` registrar endpoints bajo `/api/v1/exportaciones` con dependency de sesión autenticada `get_empresa_id()`
- [X] T004 [P] Crear estructura frontend: `frontend/src/app/exportaciones/page.tsx`, `frontend/src/app/exportaciones/nueva/`, `frontend/src/app/exportaciones/[id]/`, `frontend/src/components/export/`, ampliar `frontend/src/services/client.ts` con métodos de exportación (crear, listar, detalle, descargar, verificar)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelos de datos base y validaciones constitucionales que toda user story requiere.

**CRITICAL**: Ningún trabajo de user story puede empezar hasta completar esta fase.

- [X] T005 Crear modelo `ConfigSii` en `backend/src/models/export/config_sii.py`: empresa_id UNIQUE, obligado_sii BOOLEAN DEFAULT false, sin_anexo BOOLEAN DEFAULT false, clave_regimen VARCHAR(10), entidad_representante_id UUID NULL, fecha_alta DATE, created_at
- [X] T006 Crear modelo `Exportacion` en `backend/src/models/export/exportacion.py`: empresa_id BIGINT NOT NULL, anio_creacion INT, numero_exportacion BIGINT, tipo ENUM(INTEGRAL/SII), ejercicio_desde INT NULL, ejercicio_hasta INT NULL, estado ENUM(en_proceso/lista/fallida), creado_por UUID, created_at, completado_at NULL, blob_id UUID NULL, sha256 CHAR(64) NULL, tamano_bytes BIGINT, n_bloques INT, mensaje_error TEXT NULL; UNIQUE(empresa_id, anio_creacion, numero_exportacion); trigger DB `chk_exportacion_immutable` que impide UPDATE/DELETE sobre una exportación `lista`
- [X] T007 Crear modelos `ManifiestoExportacion` y `ManifiestoBloque` en `backend/src/models/export/manifiesto.py`: cabecera empresa_id, exportacion_id FK UNIQUE, formato_version VARCHAR(20), fecha_generacion TIMESTAMPTZ, tenant_id BIGINT, n_bloques INT, sha256_fichero CHAR(64); línea empresa_id, manifiesto_id FK, bloque VARCHAR(64), entidades_exportadas VARCHAR(100), conteo_registros BIGINT, sha256 VARCHAR(64) NULL, fecha_min/fecha_max DATE NULL, ejercicio_min/ejercicio_max INT NULL; FK compuesta empresa_id
- [X] T008 Crear modelo `BlobExportacion` en `backend/src/models/export/blob_exportacion.py`: empresa_id, exportacion_id FK UNIQUE, contenido BYTEA, sha256 CHAR(64), tamano_bytes BIGINT, created_at
- [X] T009 Implementar el catálogo de bloques `BLOQUES` en `backend/src/services/export/bloques.py`: función `bloques_registro()` devuelve lista ordenada de bloques (plan_cuentas, plan_cuentas_versiones, asientos, apuntes, terceros, facturas, lineas_factura, vencimientos, cobros_pagos, remesas, devoluciones, amortizaciones, cierres, presupuestos, previsiones, libros_iva, configuracion) con su función query, nombre de fichero y si aplica filtro por ejercicio
- [X] T010 Tests unitarios de modelos: `backend/tests/unit/test_manifiesto.py` (parte 1) — verificar UNIQUE(empresa_id, anio_creacion, numero_exportacion), FK compuesta empresa_id, UNIQUE manifiesto por exportación, trigger inmutable de exportación
- [X] T011 Tests de aislamiento multi-tenant modelos: `backend/tests/integration/test_export_tenant_isolation.py` (parte 1: modelos) — crear exportación en empresa A, verificar que empresa B no la ve en ninguna consulta ni puede acceder a su blob (404)

**Checkpoint**: Foundation ready — user story implementation puede empezar en paralelo.

---

## Phase 3: User Story 1 — Exportar el tenant completo (Priority: P1) ← MVP — cubre FR-001, FR-003, FR-004, FR-005, FR-007

**Goal**: El usuario genera un archivo descargable con todos los datos de contabilidad de la empresa activa, consistente, con inventario de bloques y huella verificable.

**Independent Test**: Exportando un tenant, el archivo contiene todos los bloques de datos de la empresa activa y su huella (hash) permite verificar la integridad; ningún dato de otra empresa está presente.

### Tests for User Story 1

- [X] T012 [P] [US1] Test catalogo de bloques: `backend/tests/unit/test_manifiesto.py` (parte 2) — iterar catálogo `BLOQUES` y verificar que cada bloque tiene nombre, función query, fichero y booleano de filtro por ejercicio; los 17 bloques obligatorios están presentes
- [X] T013 [P] [US1] Test generación ZIP: `backend/tests/unit/test_zip_layout.py` — generar ZIP en memoria; verificar estructura determinista (bloques/ + manifest.json en raíz, orden alfabético de rutas), compresión, y que el binario es reproducible para un estado idéntico
- [X] T014 [P] [US1] Test manifiesto: `backend/tests/unit/test_manifiesto.py` (parte 3) — verificar que `manifest.json` interior contiene `formato_version`, `fecha_generacion`, `tenant_id`, lista de bloques con conteos correctos y `sha256_fichero`; verificar tensión tenant_id==empresa_id
- [X] T015 [P] [US1] Test precisión decimal: `backend/tests/unit/test_precision_decimal_export.py` — verificar que todos los importes en los registros JSON son strings con 4 decimales (`"123.4500"`); ningún valor numérico float para importes; `Decimal('123.4500')` parseable sin pérdida
- [X] T016 [US1] Test aislamiento US1: `backend/tests/integration/test_export_tenant_isolation.py` (parte 2) — empresa A genera exportación completa; verificar que el ZIP de A contiene 0 registros de empresa B en todos los bloques; empresa B no puede descargar la exportación de A → 404
- [X] T017 [US1] Test rango de ejercicios: `backend/tests/integration/test_export_rango_ejercicio.py` — exportación con `ejercicio_desde=ejercicio_hasta=2025`; verificar que bloques temporales solo contienen registros de 2025 y bloques atemporales se exportan completos; verificar `ejercicio_min/ejercicio_max` en el manifiesto

### Implementation for User Story 1

- [X] T018 [US1] Implementar servicio `recopilar_bloque` en `backend/src/services/export/recopilar.py`: función genérica que ejecuta la query del bloque con filtro `empresa_id` (derivado de sesión) y filtro opcional de ejercicio; devolver registros paginados en lotes de 10.000 como generador async; calcula conteo y `ejercicio_min/max`
- [X] T019 [US1] Implementar servicio `generar_manifiesto` en `backend/src/services/export/manifiesto.py`: construir el dict del `manifest.json` con formato, fecha UTC, tenant_id, bloques con conteos y huella (se completa al final con el hash del ZIP)
- [X] T020 [US1] Implementar generador ZIP en `backend/src/services/export/zip_generator.py`: crear el ZIP en memoria/módulo `zipfile` con orden determinista de rutas (`sorted`), escribir `manifest.json` y los ficheros de cada bloque; calcular `sha256` del binario del ZIP completo; límite de tamaño razonable (< 100 MB MVP)
- [X] T021 [US1] Implementar servicio `persistir_exportacion` en `backend/src/services/export/persistir.py`: asignar `numero_exportacion` correlativo por `(empresa_id, anio_creacion)` con `SELECT ... FOR UPDATE`; INSERT `Exportacion(estado=en_proceso)` → generar ZIP → INSERT `BlobExportacion` + `ManifiestoExportacion` + `ManifiestoBloque` → actualizar `Exportacion(estado=lista, sha256, tamano_bytes, n_bloques, blob_id)` → audit log `GENERAR_EXPORTACION`; todo en UNA transacción ACID `async with async_session.begin()`
- [X] T022 [US1] Implementar service de generación síncrona en `backend/src/services/export/persistir.py`: función orquestadora `exportar_tenant(empresa_id, tipo, ejercicio_desde, ejercicio_hasta)` que recorre bloques, recopila, serializa con `DecimalEncoder`, genera ZIP, persiste y devuelve resumen; si falla → `Exportacion(estado=fallida, mensaje_error)` y 500/422
- [X] T023 [US1] Implementar endpoints en `backend/src/api/export.py`: POST `/api/v1/exportaciones` (201, body `tipo/ejercicio_desde/ejercicio_hasta`, sin empresa_id), GET `/api/v1/exportaciones` (listado paginado), GET `/api/v1/exportaciones/{id}` (detalle con manifiesto), GET `/api/v1/exportaciones/{id}/descarga` (200 application/zip)
- [X] T024 [US1] Crear página frontend `frontend/src/app/exportaciones/nueva/page.tsx`: formulario de nueva exportación (tipo, rango de ejercicios opcional), llamada al API, indicación de progreso
- [X] T025 [US1] Crear página frontend `frontend/src/app/exportaciones/page.tsx`: listado paginado de exportaciones con estado, huella, tamaño y enlace a detalle
- [X] T026 [US1] Crear página detalle `frontend/src/app/exportaciones/[id]/page.tsx`: detalle con manifiesto de bloques, botones descargar y verificar
- [X] T027 [US1] Tests integración exportación completa: `backend/tests/integration/test_export_completo.py` — crear tenant A con datos en todos los módulos; generar exportación INTEGRAL; descomprimir y verificar que cada bloque contiene los registros esperados; verificar SHA-256 del ZIP y conteos del manifiesto; incluir caso tenant con bloques vacíos (conteos 0)
- [X] T028 [US1] Tests contract API: `backend/tests/contract/test_export_api_contracts.py` (parte 1) — verificar 201/422/401/403 del POST; 200/404 del GET detalle; 409 del GET descarga para exportación no `lista`

**Checkpoint**: User Story 1 completa — exportación integral funcional con inventario y huella. MVP desplegable.

---

## Phase 4: User Story 2 — Verificar la integridad de la exportación (Priority: P2) — cubre FR-002

**Goal**: El usuario verifica que la exportación no ha sido alterada y está completa, consultando el manifiesto y la huella del archivo.

**Independent Test**: Verificando la exportación, la huella del archivo coincide con la del manifiesto; un archivo manipulado se detecta como inconsistente.

### Tests for User Story 2

- [X] T029 [P] [US2] Test hash coincide: `backend/tests/unit/test_hash_integridad.py` (parte 1) — generar ZIP, calcular SHA-256 dos veces → igual; comparar con `sha256_fichero` del manifiesto → coinciden
- [X] T030 [P] [US2] Test detección de alteración: `backend/tests/unit/test_hash_integridad.py` (parte 2) — modificar un solo byte del binario del ZIP (simular manipulación) → SHA-256 difiere → `integro=false` y `diferencias` lista el bloque afectado (según recomputación del conteo)
- [X] T031 [P] [US2] Test conteo bloques: `backend/tests/unit/test_manifiesto.py` (parte 4) — verificar que el conteo de registros por bloque en `ManifiestoBloque` coincide con los registros serializados en cada JSON del ZIP
- [X] T032 [US2] Test aislamiento US2: `backend/tests/integration/test_export_tenant_isolation.py` (parte 3) — empresa B intenta verificar la exportación de A → 404; B verifica la suya → `integro=true`

### Implementation for User Story 2

- [X] T033 [US2] Implementar servicio `verificar_exportacion` en `backend/src/services/export/verificar.py`: leer `BlobExportacion` de la exportación de la empresa activa; calcular SHA-256; comparar con `sha256_fichero` del manifiesto almacenado; validar `tenant_id`; validar conteos por bloque contra los JSON del ZIP; devolver `{integro, sha256_calculado, sha256_manifiesto, bloques[], diferencias[]}`; registrar audit log `VERIFICAR` en la misma transacción ACID
- [X] T034 [US2] Implementar endpoint POST `/api/v1/exportaciones/{id}/verificar` en `backend/src/api/export.py` (200, errores 404/409)
- [X] T035 [US2] Crear componente frontend `frontend/src/components/export/ManifiestoEstado.tsx`: tabla de bloques con conteos esperados/encontrados y estado de integridad
- [X] T036 [US2] Tests integración verificación completa: `backend/tests/integration/test_verificar_integridad.py` — exportar, verificar `integro=true`; manipular ZIP, reintentar verificación del blob original (inmutable) → `integro=true` (el blob no cambia); verificar rutina contra un ZIP alterado simulado → `integro=false`
- [X] T037 [US2] Tests contract API verificación: `backend/tests/contract/test_export_api_contracts.py` (parte 2) — verificar 200 con `integro` true/false; 404 cross-tenant; 422 si exportación no existe

**Checkpoint**: User Stories 1 y 2 completas — exportación + verificación de integridad funcionales.

---

## Phase 5: User Story 3 — Enlazar con el SII de la AEAT (Priority: P2, opcional) — cubre FR-006

**Goal**: El usuario puede subir la exportación al SII de la AEAT si tiene autorización, o usar el archivo como fuente para preparar el enlace; la presentación telemática es opcional.

**Independent Test**: El archivo exportado de tipo SII contiene los datos necesarios para el SII y puede subirse manualmente.

### Tests for User Story 3

- [X] T038 [P] [US3] Test campos SII AEAT: `backend/tests/unit/test_config_sii.py` (parte 1) — verificar que los registros del bloque SII contienen los campos AEAT requeridos: NIF, NombreRazon, TipoFactura, FechaOperacion, FechaExpedicion, NumeroFactura, ClaveRegimen, BaseImponible, TipoImpositivo, CuotaRepercutida, ImporteTotal, EstadoCuadre
- [X] T039 [P] [US3] Test consistencia decimal SII: `backend/tests/unit/test_precision_decimal_export.py` (parte 2) — BaseImponible, CuotaRepercutida e ImporteTotal como strings de 4 decimales y consistentes con las facturas (Base * Tipo/100 = Cuota, Base + Cuota = Total, redondeo Decimal exacto)
- [X] T040 [US3] Test aislamiento US3: `backend/tests/integration/test_export_tenant_isolation.py` (parte 4) — empresa A genera SII; empresa B no ve el bloque SII de A ni su configuración SII → 404/422
- [X] T041 [US3] Test bloque SII en ZIP: `backend/tests/integration/test_bloque_sii.py` — generar exportación `tipo=SII` para empresa obligada; verificar que `bloques/datos_sii/facturas_emitidas.json` y `facturas_recibidas.json` existen y contienen registros; empresa sin `ConfigSii.obligado_sii` → 422

### Implementation for User Story 3

- [X] T042 [US3] Implementar servicio `generar_bloque_sii` en `backend/src/services/export/sii.py`: subconjunto de facturas (SPEC-007) y libros IVA (SPEC-012) de la empresa activa con los campos AEAT exigidos (ver [contracts/export-layout.md](contracts/export-layout.md) sección 4); construir registros con `DecimalEncoder`; calcular `EstadoCuadre` por factura
- [X] T043 [US3] Integrar bloque SII en la exportación en `backend/src/services/export/bloques.py` y `persistir.py`: cuando `tipo=SII` o `ConfigSii.obligado_sii=true`, añadir los ficheros `datos_sii/facturas_emitidas.json` y `datos_sii/facturas_recibidas.json` al ZIP y al manifiesto
- [X] T044 [US3] Implementar endpoint GET `/api/v1/exportaciones/{id}/sii` en `backend/src/api/export.py` (200 con config + registros; 422 si no es tipo SII; 404 cross-tenant)
- [X] T045 [US3] Crear página frontend `frontend/src/app/exportaciones/nueva/page.tsx` (parte 2): selector de tipo `INTEGRAL`/`SII`, aviso de configuración SII, botón crear; mostrar estado de bloque SII tras generar
- [X] T046 [US3] Tests contract API SII: `backend/tests/contract/test_export_api_contracts.py` (parte 3) — verificar 200/422 del GET /sii; verificar 201/422 del POST tipo=SII según configuración de la empresa

**Checkpoint**: User Stories 1, 2 y 3 completas — exportación integral, verificación y bloque SII funcionales.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Refinamiento transversal, validación y robustez.

- [X] T047 [P] Validar constitución V en todos los flujos: `backend/tests/unit/test_constitucion_export.py` — verificar que los importes de todos los bloques son strings decimales con 4 decimales (sin float); verificar que la Exportacion homologada es inmutable (trigger rechaza UPDATE/DELETE); verificar aislamiento empresa_id en todas las tablas export; verificar que cada generación y verificación queda auditada
- [X] T048 [P] Hardening multi-tenant completo: `backend/tests/integration/test_export_tenant_isolation.py` (escenario final) — empresa A exporta los 17 bloques + SII; empresa B no accede a ninguna parte (ZIP, manifiesto, blob, verificación) → 404; el ZIP de A contiene exactamente 0 filas de B
- [X] T049 Ejecutar escenarios quickstart: `backend/tests/integration/test_quickstart_export.py` — reproducir los 6 escenarios de `quickstart.md` y verificar resultados esperados
- [X] T050 [P] Code review transversal: verificar que todos los servicios export usan `async with async_session.begin()` (transacción ACID); verificar que ningún endpoint recibe `empresa_id` del request body; verificar `DecimalEncoder` en toda serialización; verificar que el ZIP es determinista y el SHA-256 calculado sobre el binario completo
- [X] T051 Límites y volúmenes: probar tenant grande (10.000 asientos + plan 150 cuentas + 1.000 terceros) y verificar generación < 30 s y descarga < 500 ms; verificar `mensaje_error` y estado `fallida` ante fallo de serialización
- [X] T052 Limpieza y documentación: actualizar docstrings en servicios export; verificar type hints; ejecutar lint/typecheck (`ruff check`, `mypy`); ejecutar `pytest` completo del módulo

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sin dependencias — empieza inmediatamente.
- **Foundational (Phase 2)**: Depende de Phase 1 — BLOQUEA todas las user stories.
- **US1 (Phase 3)**: Depende de Phase 2 completa.
- **US2 (Phase 4)**: Depende de Phase 2; usa la exportación persistida de US1 como datos de prueba.
- **US3 (Phase 5)**: Depende de Phase 2; se apoya en US1 (persistencia de exportaciones y bloques).
- **Polish (Phase 6)**: Depende de las user stories deseadas estar completas.

### User Story Dependencies

- **US1 (P1/MVP)**: Sin dependencias de otras stories; usa Phase 2 completa.
- **US2 (P2)**: Depende de US1 (necesita una exportación persistida para verificar); conceptualmente independiente.
- **US3 (P2)**: Depende de US1 (persistencia de exportaciones); reutiliza el catálogo de bloques y la integración de bloques de US1.

### Within Each User Story

- Tests ANTES de la implementación (TDD constitución V).
- Modelos antes de servicios (ya creados en Phase 2; este story solo referencia).
- Servicios antes de endpoints.
- Endpoints antes de frontend.
- Integración y aislamiento multi-tenant al final.

### Parallel Opportunities

- Phase 1: todos los [P] en paralelo (T001-T004).
- Phase 2: modelos [P] en paralelo (T005-T008); tests modelos [P] (T010-T011).
- Phase 3: tests [P] en paralelo (T012-T015).
- Phase 4: tests [P] en paralelo (T029-T031).
- Phase 5: tests [P] en paralelo (T038-T040).
- US2 y US3 pueden empezar en paralelo una vez US1 (Phase 3) esté en un estado estable que persista exportaciones (dependen de la capa de persistencia de US1).

---

## Parallel Example: User Story 1

```bash
# Tests en paralelo:
Task T012: "Catálogo bloques en backend/tests/unit/test_manifiesto.py"
Task T013: "Generación ZIP en backend/tests/unit/test_zip_layout.py"
Task T014: "Manifiesto en backend/tests/unit/test_manifiesto.py"
Task T015: "Precisión decimal en backend/tests/unit/test_precision_decimal_export.py"

# Servicios en paralelo (distintos archivos):
Task T018: "Recopilar bloques en backend/src/services/export/recopilar.py"
Task T019: "Generar manifiesto en backend/src/services/export/manifiesto.py"
Task T020: "Generador ZIP en backend/src/services/export/zip_generator.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRITICAL — bloquea todo).
3. Completar Phase 3: User Story 1.
4. **PARAR y VALIDAR**: Ejecutar T012-T028. Verificar quickstart Scenario 1 y Scenario 4 (aislamiento).
5. Desplegar/demo si listo.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independiente → Deploy/Demo (MVP! exportación integral con hash).
3. + US2 → Test independiente → Deploy/Demo (verificación de integridad).
4. + US3 → Test independiente → Deploy/Demo (bloque SII opcional).
5. + Polish → Validación constitucional completa.

### Parallel Team Strategy

Con varios desarrolladores:
1. Equipo completa Setup + Foundational juntos.
2. Una vez Foundational lista:
   - Dev A: User Story 1 (catálogo de bloques, ZIP, manifiesto, persistencia ACID).
   - Dev B: espera a US1 para verificar sobre blobs ya persistidos, y luego implementa US2.
   - Dev C: prepara en paralelo la configuración SII (ConfigSii) y el bloque SII de US3 sin tocar la persistencia de US1.
3. Usar la capa de persistencia de US1 (T021) como contrato de integración para US2 y US3.
4. Polish al final con todas las stories completas.

---

## Notes

- [P] = archivos distintos, sin dependencias.
- [Story] = trazabilidad con user story del spec.
- Cada user story debe ser completable y testeable independientemente.
- Verificar tests fallen antes de implementar (TDD).
- Commit tras cada tarea o grupo lógico.
- Parar en cada checkpoint para validar story independientemente.
- Constitución V: ninguna tarea se considera finalizada sin pytest de huella/integridad + aislamiento multi-tenant + precisión decimal.
- La exportación es de solo lectura (importación/restore fuera de alcance de esta versión): el módulo exportar NUNCA escribe en tablas de negocio, solo crea `Exportacion`, `Manifiesto*` y `BlobExportacion` con su auditoría.
- La exportación persistida es inmutable (trigger `chk_exportacion_immutable`); su blob puede re-descargarse las veces necesarias siempre con el mismo binario.
- El SHA-256 se calcula sobre el binario completo del ZIP (datos + manifiesto); `manifest.json` interior repite `sha256_fichero` para verificación autónoma sin API.

---

## Estado real (implementación 2026-09-27)

Spec cerrada **52/52** (29ª spec). Módulo `export` en backend y frontend,
migración `020_export.sql`, módulo RBAC propio `export` y 245 pruebas nuevas.

### Ficheros creados

**Modelos** (`backend/src/models/export/`): `__init__.py`, `config_sii.py`
(`ConfigSii`, `UNIQUE(empresa_id)`), `exportacion.py` (`Exportacion` con
`UNIQUE(empresa_id, anio_creacion, numero_exportacion)`, CHECK de rango y
propiedades `nombre_fichero`/`descargable`/`por_megabytes`), `manifiesto.py`
(`ManifiestoExportacion` con `UNIQUE(empresa_id, exportacion_id)` + `tenant_id`
redundante, y `ManifiestoBloque`) y `blob_exportacion.py` (`BlobExportacion`
`BYTEA` con `UNIQUE(empresa_id, exportacion_id)`). Registrado en
`models/__init__.py`.

**Servicios** (`backend/src/services/export/`): `errores.py`
(`ExportError` + `error()`), `serializacion.py` (`DecimalEncoder`, `serializar`,
`cuatro_decimales` con ROUND_HALF_EVEN, `iso_utc`, `volcar_json`),
`bloques.py` (catálogo `BLOQUES` con los 17 bloques obligatorios + `datos_sii`
opcional; `Bloque.construir_consulta` es la "función query" del catálogo),
`recopilar.py` (`construir_consulta_bloque` con filtro de empresa y de rango,
`recopilar_bloque` en lotes de 10.000 con `db.stream()`), `manifiesto.py`
(`lineas_manifiesto`, `generar_manifiesto`, `contenido_digest`),
`zip_generator.py` (`escribir_zip` determinista con `ZipInfo` de fecha fija y
orden alfabético, `leer_manifiesto`, `rutas_zip`), `persistir.py`
(`asignar_numero`, `exportar_tenant`, `obtener_*`, `listar_exportaciones`,
`detalle_exportacion`), `verificar.py` (`verificar_contenido`,
`verificar_exportacion`) y `sii.py` (`config_efectiva`, `generar_bloque_sii`,
`entradas_sii`).

**API** `backend/src/api/export.py` (8 endpoints bajo `/api/v1/exportaciones`),
registrado en `main.py`.

**Migración** `backend/migrations/020_export.sql` + espejo SQLite en
`db/triggers.py` + `db/migrate.py` (`ORDEN_PREFERENTE`) y
`test_migrations.ESPERADAS`.

**Frontend**: `components/export/{api.ts,ManifiestoEstado.tsx,DescargaExport.tsx}`
y `app/exportaciones/{page.tsx,nueva/page.tsx,[id]/page.tsx}`; `put` añadido a
`services/client.ts`; enlace en `app/page.tsx`. **103 rutas** (3 nuevas).

**Tests** (245 nuevos): `tests/unit/{test_manifiesto,test_zip_layout,
test_hash_integridad,test_precision_decimal_export,test_config_sii,
test_constitucion_export,test_export_review}.py` (unitarias),
`tests/integration/{test_export_completo,test_export_rango_ejercicio,
test_export_tenant_isolation,test_verificar_integridad,test_bloque_sii,
test_quickstart_export,test_export_limites}.py`,
`tests/contract/test_export_api_contracts.py`, 5 pruebas nuevas en
`tests/integration/test_pg_schema.py` y el helper `tests/unit/export_support.py`
con la fixture `export_client` (empresas A=10/B=20, tres roles con matriz RBAC,
PGC, facturas, asientos de 2025 y 2026, `ConfigSii` solo en A).

### Desviaciones del plan documentado

1. **Boundary ACID**: el autoritativo es `get_db` + `flush()`, no el
   `async with async_session.begin()` literal de T021/T022. La generación
   corre dentro de un `SAVEPOINT` (`db.begin_nested()`) para que un fallo
   deshaga el trabajo a medias y deje una cabecera `fallida` con su
   `mensaje_error` (confirmada en su propia transacción, porque el `rollback`
   del `get_db` la borraría).
2. **Huella dentro del ZIP (imposibilidad lógica)**: un fichero no puede
   contener su propio SHA-256, así que el `manifest.json` interior lleva
   `sha256_contenido` (digest canónico `ruta|sha256` de cada bloque, verificable
   sin API) y la huella del **binario completo** vive en `Exportacion.sha256`,
   `BlobExportacion.sha256` y `ManifiestoExportacion.sha256_fichero`, que la API
   devuelve como `sha256` / `manifiesto.sha256_fichero`. La verificación manual
   de `contracts/api-contracts.md` sigue siendo válida: el hash del fichero
   descargado se compara con el de la API.
3. **`creado_por` es `VARCHAR(120)`**, no UUID: `users.id` es BIGINT en SPEC-003
   (mismo criterio que `journal_entry.created_by` y `cerrado_por` de SPEC-028).
4. **Numeración correlativa sin tabla de secuencia**: `asignar_numero` usa
   `SELECT ... FOR UPDATE` sobre la última fila de `(empresa_id,
   anio_creacion)` con el UNIQUE como red final (research D10 no exige tabla
   auxiliar; SQLite no soporta `FOR UPDATE`).
5. **`ConfigSii` convive con `ConfiguracionSII`** de SPEC-012: la primera es la
   del data-model (obligación, anexos, régimen) y la segunda la configuración
   técnica de envío. `sii.config_efectiva` usa la primera y cae a la segunda.
6. **Bloque SII fuera del mecanismo genérico**: `datos_sii` se deriva de
   facturas + libros, no de una consulta de tabla, así que lo escribe
   `services.export.sii` como ficheros inyectados (`entradas_extra` de
   `escribir_zip`) y `zip_generator` los registra en el manifiesto con su conteo
   leído del propio JSON. `n_bloques` del manifiesto = 19 para una empresa
   obligada (17 + `datos_sii.facturas_emitidas` + `datos_sii.facturas_recibidas`)
   y 17 si no lo está.
7. **Filtro por rango sin `EXTRACT`**: la resolución del ejercicio se hace por
   columnas de fecha comparables (`>= date(desde,1,1)`) y por `EXISTS` sobre la
   tabla padre para las hijas sin fecha propia (`journal_entry_line`,
   `factura_linea`, `balanza_periodo_linea`, `desviacion`), de modo que la misma
   consulta funciona en PostgreSQL y en el SQLite de los tests. `created_at`
   **nunca** filtra (es una columna técnica): los maestros se exportan enteros.
   `TablaBloque.filtra_rango=False` marca los maestros cuya fecha es de alta
   (`tercero_subcuenta`) y las proyecciones de `catalogo_version`.
8. **Determinismo con `fecha_generacion` inyectable**: dos generaciones del
   mismo estado producen el mismo binario byte a byte si comparten instante
   (`escribir_zip(..., fecha_generacion=...)`); la API usa `created_at` con
   microsegundos a cero.
9. **`CREATE OR REPLACE TRIGGER`** en la migración 020 (PostgreSQL 14+) en vez
   de `DROP TRIGGER IF EXISTS` + `CREATE TRIGGER`: es atómico e idempotente en
   una sola sentencia, y evita depender del orden de dos comandos al reaplicar
   el lote. El resto de migraciones mantiene el patrón `DROP` + `CREATE`.
10. **Módulo RBAC propio `export`** con tres operaciones (`ver`, `crear`,
    `configurar`); no expone `importar_exportar` porque el restore está fuera de
    alcance. Sembrado en los tres sitios coherentes (`catalogo.py`,
    `migrations/007_rbac.sql`, `trg_companies_rbac_seed`), lo que actualiza los
    recuentos de SPEC-015 a **15 módulos, 109 permisos y 179 concesiones**.
11. **Endpoints extra** no listados en el contrato, necesarios para US3:
    `GET /api/v1/exportaciones/sii/config` y `PUT .../sii/config` (declarados
    **antes** que `/{exportacion_id}` para que la ruta estática no choque con el
    UUID). El body del POST acepta `{}` (todo por defecto `INTEGRAL`) y
    descarta un `empresa_id` que venga del cliente (constitución III).
12. **Ficheros extra**: `services/export/errores.py` y
    `services/export/serializacion.py` (patrón `errores.py` de SPEC-026/027/028)
    y `tests/integration/test_export_limites.py` (T051, no nombra fichero).
13. **Volumen del test de rendimiento**: la suite usa 2.000 asientos y 1.000
    terceros (< 60 s de generación, < 5 s de descarga) y el volumen completo del
    plan (10.000 asientos, < 30 s) se ejecuta con `EXPORT_PERF_FULL=1`; ambos
    verificados en verde.
14. **`Tamano` se expone dos veces**: `tamano_bytes` (entero) y `tamano_mb`
    (cadena de 4 decimales) para no perder precisión.

### Verificación

- **pytest (SQLite)**: 2.470 passed / 13 skipped. El único fallo de la corrida
  completa fue `test_suggest_perf` (flaky conocido bajo carga de SPEC-001),
  **2 passed** aislado.
- **pytest (PostgreSQL 18.6 real)**: migraciones 000–020 aplicadas sobre esquema
  limpio e idempotentes (dos pases seguidos); los 16 tests de
  `test_pg_schema.py` verdes, 5 nuevos de SPEC-029.
- **ruff** y **mypy**: limpios (393 fuentes).
- **Frontend**: `tsc --noEmit`, `eslint src` y `next build` verdes con
  **103 rutas** (3 nuevas: `/exportaciones`, `/exportaciones/nueva`,
  `/exportaciones/[id]`).

### Correcciones posteriores al cierre (2026-09-27, 2.ª tanda)

1. **Colisión de rutas con SPEC-012 (corregida)**: `api/fiscal/exportaciones.py`
   (exportación de modelos AEAT de SPEC-012) ya usaba el prefijo
   `/api/v1/exportaciones`. Como el router fiscal se registra **antes** que
   `api/export.py` en `main.py`, sus rutas ocultaban las de la exportación
   integral: `POST /api/v1/exportaciones` devolvía 422 del modelo AEAT en la app
   real (los tests de contrato no lo detectaban porque su fixture solo incluye el
   router de SPEC-029). Se movió SPEC-012 a
   `/api/v1/fiscal/exportaciones` (recurso distinto, ruta distinta) y se
   actualizaron sus tres pruebas (`test_fiscal_us3`, `test_quickstart_fiscal`,
   `test_constitucion_fiscal`). Se añadieron a `tests/unit/test_app.py` los guards
   `test_no_hay_colisiones_de_ruta_en_la_app_real` y
   `test_las_dos_exportaciones_viven_en_rutas_distintas`.
2. **`creado_por` real (corregida)**: el router usaba la etiqueta fija
   `"api:api"`. Ahora `_actor(request, user)` toma `users.id` del usuario
   autenticado (`Depends(get_current_user)`), que es lo que pide el data-model.
3. **`GET /{id}/sii` lee el blob (corregida)**: recalculaba el bloque SII con el
   estado actual del tenant, de modo que tras cambiar las facturas la API
   mostraba algo distinto del ZIP exportado (research D9). Ahora lee
   `sii.leer_bloque_sii(contenido)` del binario inmutable; 422
   `bloque_sii_ausente` si el ZIP no lo contiene.
4. **Importes perezosos eliminados**: `detalle_exportacion` (en
   `services/export/persistir.py`) y `_lineas` (en `api/export.py`) ya no hacen
   `from ... import` dentro de la función.
5. **Volumen de T051 (corregida)**: el test de rendimiento pasa de 300 asientos
   y 120 terceros a **2.000 asientos y 1.000 terceros** en la suite normal, y el
   volumen completo del plan (10.000 asientos) se ejecuta con
   `EXPORT_PERF_FULL=1`. Verificado: el volumen completo genera y verifica en
   < 30 s.
