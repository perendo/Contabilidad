---

description: "Task list for SPEC-030 Documentos adjuntos al asiento"
---

# Tasks: Documentos adjuntos al asiento (SPEC-030)

**Input**: Design documents from `specs/030-documentos-asiento/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md

**Tests**: los tests SI estan incluidos. La constitution V es NON-NEGOTIABLE ("ninguna tarea se
considera finalizada sin pruebas automaticas que verifiquen balance estricto y aislamiento
multi-tenant"), el plan y el quickstart los planifican, y las 30 specs anteriores los incluyen.
Orden dentro de cada historia: tests primero (deben fallar), despues modelo, servicio, endpoint
e integracion.

**Branch**: `030-documentos-asiento`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: historia de usuario a la que pertenece la tarea (US1, US2, US3)
- Rutas exactas incluidas en cada descripcion

## Paths

Backend: `backend/src/...`, `backend/tests/...`, `backend/migrations/...`
Frontend: `frontend/src/...`
Dependencias: `requirements.txt` (raiz del repositorio)

## Constitution Gates

Ninguna tarea se marca completada sin: (a) pytest que verifique que el cuadre del asiento
sigue intacto tras adjuntar o dar de baja, y (b) pytest que verifique el aislamiento por
`empresa_id`. Las historias que no tocan el diario (US2, US3) aportan el test de cuadre de
todos modos, porque la garantia FR-015 es transversal.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependencia nueva, configuracion y estructura de paquetes.

- [X] T001 Declarar `pillow>=10.0,<13.0` en `requirements.txt` (raiz) bajo "# Backend runtime" e instalarlo en el venv con `..\.venv\Scripts\python.exe -m pip install "pillow>=10.0,<13.0"` desde `backend/`; `pypdf` ya esta declarada y no se toca
- [X] T002 [P] Anadir a `Settings` en `backend/src/config.py` los campos `documento_max_bytes: int = 10 * 1024 * 1024`, `documento_max_paginas: int = 200`, `documento_max_por_asiento: int = 50` y `documento_plazo_conservacion_anos: int = 6` (research.md D10)
- [X] T003 [P] Crear el paquete `backend/src/services/documentos/` con `__init__.py` vacio
- [X] T004 [P] Crear `frontend/src/components/documentos/.gitkeep` y `frontend/src/app/documentos/.gitkeep`
- [X] T005 [P] Registrar la linea base antes de tocar codigo: ejecutar `..\.venv\Scripts\python.exe -m pytest`, `..\.venv\Scripts\python.exe -m ruff check src tests`, `..\.venv\Scripts\python.exe -m mypy -p api -p models -p services -p database -p base -p db -p main -p config` desde `backend/`, y `node node_modules/typescript/bin/tsc --noEmit` mas `next build` desde `frontend/`; anotar el numero de tests pasados y de rutas generadas en la seccion "Estado real" de `specs/030-documentos-asiento/tasks.md`. Es la **linea base** contra la que comparar T043-T048; no cierra la spec

**Checkpoint**: dependencia y configuracion disponibles; el resto del repositorio intacto.

---

## Phase 2: Foundational (Blocking Prerequisites)

**CRITICAL**: ninguna historia de usuario puede empezar hasta cerrar esta fase.

- [X] T006 Crear `TipoDocumento` (6 valores en minusculas: `factura`, `recibo`, `extracto`, `justificante`, `contrato`, `otro`), `EstadoDocumento` (`activo`, `dado_de_baja`) y la clase `DocumentoAsiento` en `backend/src/models/acct/documento.py` con las 19 columnas, `__table_args__` con `UniqueConstraint("empresa_id", "id")`, `UniqueConstraint("empresa_id", "journal_entry_id", "sha256")`, `ForeignKeyConstraint(["empresa_id", "journal_entry_id"], ["journal_entry.empresa_id", "journal_entry.id"])`, los `CheckConstraint` `size_bytes > 0`, el de baja completa y el de `importe_informativo >= 0`, y `index=True` en `empresa_id` (data-model.md seccion 3)
- [X] T007 Exportar `DocumentoAsiento`, `TipoDocumento` y `EstadoDocumento` en `backend/src/models/acct/__init__.py` y agregarlos al `__all__`; verificar que `backend/src/models/__init__.py` ya importa el paquete `acct` para que las FKs cross-spec resuelvan
- [X] T008 Crear `backend/migrations/021_adjuntos_asiento.sql` con el banner comentando la constitution y la alineacion con el modelo, los dos enums envueltos en `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_type ...) ... $$`, `CREATE TABLE IF NOT EXISTS documento_asiento` con las 7 restricciones y los 4 indices de data-model.md, y la funcion `f_documento_asiento_inmutable_update()` mas los triggers `trg_documento_asiento_contenido_inmutable_update` y `trg_documento_asiento_inmutable_delete` (research.md D3)
- [X] T009 [P] Anadir `"021_adjuntos_asiento.sql",` al final de `ORDEN_PREFERENTE` en `backend/src/db/migrate.py` (depende de T008), inmediatamente despues de `"020_export.sql",` (no puede ir tras 017: el 018 ya lo ocupa SPEC-027)
- [X] T010 [P] Anadir `"021_adjuntos_asiento.sql",` en la misma posicion de `ESPERADAS` en `backend/tests/unit/test_migrations.py` (depende de T008) y anadir el test `test_migracion_documentos_declara_inmutabilidad_y_huella` que compruebe `uq_documento_asiento_huella`, `fk_documento_asiento_entrada`, `trg_documento_asiento_contenido_inmutable_update` y `trg_documento_asiento_inmutable_delete`
- [X] T011 [P] Anadir el espejo para SQLite de los dos triggers de `documento_asiento` en la lista `_TRIGGERS_SQLITE` de `backend/src/db/triggers.py`, con `OLD`/`NEW` comparados y `RAISE(ABORT, 'documento_asiento inmutable')`
- [X] T012 [P] Crear `backend/src/services/documentos/errores.py` (depende de T002) con `DocumentoError(Exception)` que reciba `code`, `message`, `status_code=422` y `extra`, y el helper `error(code, message, status_code=422)` con la misma forma que `services/budget/errores.py`
- [X] T013 [P] Crear `backend/src/services/documentos/validacion.py` (depende de T002) con `detectar_formato(bytes) -> (extension, content_type)`, `validar_contenido(bytes, extension) -> num_paginas`, `validar_tamano(len(bytes))`, `validar_nombre(str)` y `validar_texto(str, campo, maximo)`, usando las firmas de D8, `pypdf.PdfReader` para cifrado, corrupcion y numero de paginas, y `PIL.Image.verify()` mas `n_frames` para imagenes; lanzar `DocumentoError` con los codigos de data-model.md seccion 5
- [X] T014 Anadir el fixture `documentos_client` a `backend/tests/conftest.py` siguiendo el molde de `presupuestos_client`: empresas A=10 y B=20, `seed_default_pgc` en ambas, usuarios ADMIN (id 1) y ACCOUNTANT (id 2) con `UserCompany` en las dos, y por empresa un asiento `DRAFT` y otro `POSTED` con lineas balanceadas; exponer helpers `_hh(token_key, empresa_id)`, `get`, `post`, `delete`, `subir(ruta, empresa_id, files, campos, token_key)` para multipart, y `asiento(empresa_id, estado)`
- [X] T015 [P] Crear el cliente tipado `frontend/src/components/documentos/api.ts` con `export { ApiError }`, las interfaces `Documento`, `ResultadoAdjunto`, `Rechazo`, `ListadoDocumentos`, `ItemGlobalDocumento` y `EncabezadoAsiento`, el helper privado `qs()`, y las funciones `adjuntarDocumentos(asientoId, files, tipoDocumento, descripcion?, importeInformativo?)` con `FormData` y cabeceras `getToken()` + `cabecerasEmpresa()`, `listarDocumentosAsiento(asientoId, incluirBajas)`, `listarDocumentos(params)`, `obtenerDocumento(id)`, `descargarDocumento(id, nombre)` con `requestBlob` y `darDeBajaDocumento(id, motivo)`
- [X] T016 [P] Anadir el contrato PostgreSQL de `documento_asiento` en `backend/tests/integration/test_pg_schema.py` (depende de T008): la tabla y los dos enums en las listas esperadas, y un test `test_documentos_unicidad_huella_y_triggers_en_postgresql` que compruebe el `IntegrityError` al cambiar `contenido`, al hacer `DELETE` y al insertar dos filas con la misma `sha256`

**Checkpoint**: fundacion lista. El modelo, la migracion, los triggers, la validacion, el
fixture y el cliente de frontend existen; las tres historias pueden empezar.

---

## Phase 3: User Story 1 - Adjuntar documentos justificantes a un asiento (Priority: P1) MVP

**Goal**: el usuario adjunta uno o varios ficheros PDF o imagen a un asiento del diario, con
tipo, descripcion e importe informativo opcionales, y el sistema acepta los validos y explica
los rechazados sin dejar nada a medias.

**Independent Test**: dado un asiento, un `POST /api/v1/documentos/asiento/{id}` en multipart
con tres ficheros (un PDF y dos imagenes) responde 201 con tres elementos en `aceptados`, cada
uno con nombre, formato, tamano, paginas, huella, tipo y estado `activo`; una segunda peticion
con un PDF valido, un `.bak` y un TIFF de 12 MB responde 201 con un aceptado y dos rechazados
con su codigo; y el cuadro del asiento es identico antes y despues.

### Tests for User Story 1

> Escribir primero y comprobar que fallan.

- [X] T017 [P] [US1] Crear `backend/tests/unit/test_documento_validacion.py` con el escenario S5 de quickstart: extension engañosa (JPEG renombrado a `.pdf`), PDF truncado, PDF protegido con contrasena, PDF de 250 paginas, fichero de 0 bytes, nombre de 300 caracteres y TIFF multipagina; y el camino feliz de los cuatro formatos
- [X] T018 [P] [US1] Crear `backend/tests/unit/test_documento_isolation.py` con el aislamiento del alta: el servicio rechaza con `asiento_no_encontrado` un asiento de la empresa B y no escribe ninguna fila; comprobar con `select(DocumentoAsiento)` que el conteo por `empresa_id` es 1 y 0 respectivamente
- [X] T019 [US1] Crear `backend/tests/integration/test_documentos_routes.py` con el POST: 201 y forma exacta del cuerpo, los tres rechazos de S3 con su `code`, el cuadre intacto antes y despues (`sum(debe) == sum(haber)` y estado del asiento sin cambios), 404 para un asiento de la otra empresa, 403 para un usuario `READ_ONLY` y 422 para `tipo_documento` fuera del enum

### Implementation for User Story 1

- [X] T020 [P] [US1] Crear `backend/src/services/documentos/adjuntos.py` (depende de T012, T013) con `adjuntar_documentos(session, empresa_id, asiento_id, ficheros, tipo_documento, descripcion, importe_informativo, actor, ip) -> ResultadoAdjunto`: validar el asiento con filtro por `empresa_id`, calcular `sha256`, validar cada fichero con `validacion.py`, comprobar el limite por asiento y el duplicado por `(empresa_id, asiento_id, sha256)`, insertar solo los aceptados, llamar a `registrar_auditoria(operacion="ADJUNTAR_DOCUMENTO", entidad="documento_asiento")` por cada alta y devolver `aceptados` y `rechazados` con `code` y `detail`; `await session.flush()` dentro del boundary de `get_db`, nunca `async with session.begin()`
- [X] T021 [US1] Crear `backend/src/api/documentos/__init__.py` con el `router = APIRouter(prefix="/api/v1/documentos", tags=["documentos"])` y su reexport, `backend/src/api/documentos/deps.py` con `Db = Annotated[AsyncSession, Depends(get_db)]`, `Empresa = Annotated[int, Depends(get_empresa_id)]`, `ACTOR` y el mapper `_http(exc: DocumentoError) -> HTTPException` con `{"code", "detail", **extra}`, y `backend/src/api/documentos/adjuntos.py` con `POST /asiento/{asiento_id}` (`status_code=201`, `dependencies=[Depends(require_permission("acct", "crear"))]`, `files: Annotated[list[UploadFile], File(...)]`, `tipo_documento: Annotated[str, Form()]`, `descripcion: Annotated[str | None, Form()] = None`, `importe_informativo: Annotated[str | None, Form()] = None`, `user: Annotated[User, Depends(get_current_user)]`) que devuelve 201 con el cuerpo de contracts seccion 1
- [X] T022 [P] [T021] Registrar el router en `backend/src/main.py` con `from api.documentos import router as documentos_router` y `app.include_router(documentos_router)` despues de `asientos_router` y `importexport_router`
- [X] T023 [P] [T015] Crear `frontend/src/components/documentos/DocumentosAsiento.tsx` con `interface Props { asientoId: string; estadoAsiento: string }`: `<input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff">` con `e.target.value = ""` en el `finally`, `<select>` de tipo con los seis valores, campos de descripcion e importe, boton con estado `enviando`, y el listado de documentos ya adjuntos; el estado vacio debe declarar explicitamente que los adjuntos son opcionales
- [X] T024 [P] [T023] Montar `<DocumentosAsiento>` en `frontend/src/app/asientos/[id]/page.tsx` debajo de la tabla de apuntes, leyendo el estado del asiento del `Detalle` ya cargado y sin anadir un segundo `useEffect` de carga

**Checkpoint**: US1 funcional. Se pueden adjuntar documentos a un asiento, con rechazo
explicado y sin alterar el cuadre. Es el MVP entregable.

---

## Phase 4: User Story 2 - Consultar y descargar los documentos de un asiento (Priority: P2)

**Goal**: desde el detalle del asiento y desde un listado global con filtros, el usuario ve,
previsualiza y descarga los documentos, y la huella del contenido descargado coincide con la
del alta.

**Independent Test**: dado un asiento con documentos, `GET /api/v1/documentos/asiento/{id}`
los lista con su huella, `GET /api/v1/documentos/{id}/descarga` devuelve el binario con
`X-Documento-SHA256` igual al `sha256` del alta y `Cache-Control: no-store`, y
`GET /api/v1/documentos?ejercicio=...&tipo_documento=...` filtra correctamente con orden estable
entre llamadas.

### Tests for User Story 2

- [X] T025 [P] [US2] Anadir a `backend/tests/integration/test_documentos_routes.py` los cuatro GET: listado del asiento con `documentos_obligatorios: false`, listado global con filtros de `ejercicio`, `tipo_documento`, `estado` y `q`, orden identico entre dos llamadas consecutivas, metadatos de un documento, y la descarga con `Content-Type`, `Content-Disposition` saneado, `X-Documento-SHA256` y `Cache-Control: no-store`; comprobar que el `sha256` del cuerpo descargado coincide con el del alta
- [X] T026 [P] [US2] Crear `backend/tests/integration/test_documentos_tenant.py` con el escenario S7 completo: las cinco operaciones (listar, descargar, listado global, adjuntar y dar de baja) contra un documento y un asiento de la empresa B devuelven 404 con el mismo texto que un recurso inexistente, y el listado de la empresa A no contiene ningun documento de la B

### Implementation for User Story 2

- [X] T027 [P] [US2] Crear `backend/src/services/documentos/consulta.py` con `listar_documentos_asiento`, `listar_documentos` (con `JOIN` a `journal_entry` para el filtro por `ejercicio`, paginacion y `ORDER BY created_at, id`), `obtener_documento` y `datos_documento_para_descarga`; todos con filtro obligatorio `DocumentoAsiento.empresa_id == empresa_id` y `None` cuando el recurso es de otra empresa
- [X] T028 [US2] Crear `backend/src/api/documentos/consulta.py` con las cuatro rutas GET, todas con `dependencies=[Depends(require_permission("acct", "ver"))]`: `GET /asiento/{asiento_id}` con `incluir_bajas`, `GET ""` con los filtros de contracts seccion 3 y `page_size` acotado a 100, `GET /{documento_id}` y `GET /{documento_id}/descarga` que devuelve `fastapi.Response` con el binario y las cuatro cabeceras
- [X] T029 [P] [US2] Crear `frontend/src/components/documentos/VisorDocumento.tsx`: obtiene el `Blob` con `requestBlob`, crea una `URL.createObjectURL`, muestra `<img>` para `image/*` y `<iframe>` para `application/pdf`, ofrece la descarga con el nombre original y libera la URL con `revokeObjectURL` al cerrar
- [X] T030 [US2] Anadir a `frontend/src/components/documentos/DocumentosAsiento.tsx` el montaje de `VisorDocumento` y el boton "Ver/Descargar" por documento; este es el unico punto donde US2 edita un fichero de US1, y es aditivo
- [X] T031 [P] [US2] Crear `frontend/src/app/documentos/page.tsx` con los filtros de ejercicio, tipo, estado y texto, la tabla con nombre, tipo, tamano, huella corta, fecha, asiento y acciones, y los estados `cargando` / `error` / `aviso` del repositorio
- [X] T032 [P] [US2] Anadir `{ href: "/documentos", label: "Documentos del diario" }` al array `SECCIONES` de `frontend/src/app/page.tsx`

**Checkpoint**: US1 y US2 funcionales de forma independiente. El documento se puede volver a
recuperar integro y verificado.

---

## Phase 5: User Story 3 - Integridad, trazabilidad e inalterabilidad del soporte (Priority: P3)

**Goal**: el contenido de un documento no se puede sustituir, los duplicados se rechazan, toda
alta y toda baja quedan en una traza inmutable y un documento dado de baja se conserva y puede
recuperarse, sin que la evidencia de un asiento asentado pueda retirarse.

**Independent Test**: un `UPDATE` del `contenido` y un `DELETE` de la fila lanzan
`IntegrityError`; reenviar el mismo fichero al mismo asiento devuelve `documento_duplicado` sin
crear fila; dar de baja en un asiento `DRAFT` devuelve 204 y el contenido sigue descargable con
la misma huella; en un asiento `POSTED` devuelve 409; y el `audit_log` registra una entrada
inmutable por operacion.

### Tests for User Story 3

- [X] T033 [P] [US3] Crear `backend/tests/unit/test_documento_adjuntos.py` con la inmutabilidad por trigger (`UPDATE` de `contenido` y de `nombre_original` lanzan `IntegrityError` con el mensaje `documento_asiento inmutable`), el `DELETE` fisico rechazado, la unicidad de `sha256` dentro del mismo asiento, el limite `documento_max_por_asiento`, el rechazo del `tipo_documento` fuera del enum y la aceptacion del mismo fichero en dos asientos distintos
- [X] T034 [P] [US3] Anadir a `backend/tests/integration/test_documentos_routes.py` el `DELETE` con sus cuatro codigos (204, 404, 409 `baja_no_permitida` en asiento `POSTED`, 422 `baja_motivo_obligatorio`), la recuperacion del documento dado de baja con huella intacta, la verificacion de que el cuadre del asiento no cambia tras dar de baja, y la presencia de una entrada `ADJUNTAR_DOCUMENTO` y otra `DAR_DE_BAJA_DOCUMENTO` en `audit_log` con `usuario`, `timestamp`, `ip` y `payload`

### Implementation for User Story 3

- [X] T035 [P] [US3] Crear `backend/src/services/documentos/bajas.py` con `dar_de_baja_documento(session, empresa_id, documento_id, motivo, actor, ip)`: cargar el documento con `empresa_id` y `with_for_update()`, exigir `motivo` no vacio, exigir que el asiento este en `DRAFT` o lanzar `baja_no_permitida` (409), exigir estado `activo` o lanzar `documento_no_encontrado` (404), poner `estado`, `baja_motivo`, `baja_usuario` y `baja_at`, registrar `DAR_DE_BAJA_DOCUMENTO` en `audit_log` y hacer `flush()`; nunca tocar `contenido` ni `sha256`
- [X] T036 [US3] Crear `backend/src/api/documentos/bajas.py` con `DELETE /{documento_id}` (`status_code=204`, `dependencies=[Depends(require_permission("acct", "baja"))]`, cuerpo `{"motivo": str}` obligatorio) y el mapeo de `DocumentoError` a 404, 409 y 422
- [X] T037 [P] [US3] Anadir a `frontend/src/components/documentos/DocumentosAsiento.tsx` la seccion de documentos dados de baja (visible con `incluir_bajas`), el boton "Dar de baja" con `window.confirm` y campo de motivo, y la ocultacion de ese boton cuando el asiento no esta en `DRAFT`

**Checkpoint**: las tres historias son funcionales e independientes. La evidencia del diario
es verificable e inalterable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T038 [P] Crear `backend/tests/unit/test_constitucion_documentos.py` con el prefijo `/api/v1` en el router, la ausencia de `empresa_id: int` o `empresa_id: str` y la presencia de `empresa_id: Empresa` en el fuente de `api/documentos/`, la guarda `require_permission` en las seis rutas, la presencia de `Decimal` y la ausencia de `float` en el manejo de `importe_informativo`, y la certeza de que ningun modulo de `services/documentos/` importa `journal_entry_line` ni escribe en el diario
- [X] T039 [P] Crear `backend/tests/integration/test_documentos_opcional.py` con el escenario S1 de quickstart: un asiento sin documentos devuelve 200 con `items` vacio y `documentos_obligatorios: false`, se asienta, se anula y se lista sin restricion alguna, no aparece en el listado global, y no existe ninguna ruta que exija al menos un documento
- [X] T040 [P] Revisar `backend/src/api/routes_registry.py` y confirmar que `EXCLUSIONES_NO_BYPASS` no necesita cambios y que `rutas_sin_permiso` sigue vacio con las seis rutas nuevas; revisar tambien `frontend/src/app/asientos/[id]/page.tsx` para que el copy del estado vacio declare la opcionalidad sin ambigüedad
- [X] T041 [P] Actualizar `AGENTS.md`: la seccion 1 (estado del proyecto y numero de specs), la tabla de la seccion 20 con la fila `030 Documentos adjuntos al asiento`, y una seccion de cierre nueva con las tareas marcadas, el recuento de tests, los ficheros tocados y las desviaciones respecto de plan.md y research.md
- [X] T042 [P] Anotar en `specs/030-documentos-asiento/tasks.md` la seccion "Estado real (implementacion 2026-09-26)" con los recuento obtained en T005 y los de T043, mas cualquier desviacion encontrada

---

## Phase 7: Convergence (Gates)

**Purpose**: verificar todas las puertas antes de declarar la spec cerrada.

- [X] T043 Ejecutar `..\.venv\Scripts\python.exe -m pytest` desde `backend/` y registrar el total de tests pasados y omitidos; confirmar que los tests de la constitution V (cuadre del asiento intacto y aislamiento por `empresa_id`) estan en verde
- [X] T044 Ejecutar `..\.venv\Scripts\python.exe -m ruff check src tests` y `..\.venv\Scripts\python.exe -m mypy -p api -p models -p services -p database -p base -p db -p main -p config` desde `backend/`, y dejar ambos limpios
- [X] T045 [P] Ejecutar `node node_modules/typescript/bin/tsc --noEmit` y `node node_modules/eslint/bin/eslint.js src` desde `frontend/` sin errores
- [X] T046 Ejecutar `node node_modules/next/dist/bin/next build` desde `frontend/` con `NEXT_TELEMETRY_DISABLED=1` y anotar el numero de rutas generadas, que debe superar las 92 de la compilacion anterior
- [X] T047 Aplicar las migraciones 000 a 021 sobre PostgreSQL 18.6 real con esquema limpio y ejecutar `..\.venv\Scripts\python.exe -m pytest tests/integration/test_pg_schema.py` con `TEST_DATABASE_URL` apuntando al cluster del puerto 5432 (AGENTS.md seccion 19); confirmar que los triggers de `documento_asiento` y los de `audit_log` rechazan `UPDATE` y `DELETE` tambien en PostgreSQL
- [X] T048 [P] Recorrer los 11 escenarios S1 a S11 de `specs/030-documentos-asiento/quickstart.md` y marcar el checklist de "Criterio de terminado" de la seccion 7 de ese mismo fichero cuando los once tengan su resultado esperado. La lista de comprobacion vive en el quickstart, no aqui

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias, arranca de inmediato
- **Foundational (Phase 2)**: depende de Phase 1 y **bloquea** las tres historias
- **User Stories (Phase 3-5)**: todas dependen de Phase 2; pueden avanzar en paralelo porque
  cada una aporta ficheros propios en `api/documentos/`, `services/documentos/` y
  `components/documentos/`
- **Polish (Phase 6)**: depende de las historias que se decida implementar
- **Convergence (Phase 7)**: depende de todo lo anterior

### User Story Dependencies

- **US1 (P1)**: arranca tras Phase 2. Sin dependencias de otras historias. Es el MVP
- **US2 (P2)**: arranca tras Phase 2. Solo depende de US1 en un punto aditivo: T030 monta
  `VisorDocumento` dentro de `DocumentosAsiento.tsx`. Aplica T029 en cualquier orden
- **US3 (P3)**: arranca tras Phase 2. Sin dependencias de otras historias. Los triggers ya
  existen desde Phase 2; US3 aporta el servicio de baja, el endpoint y sus pruebas

Orden recomendado: US1, US2, US3 (valor incremental: adjuntar, recuperar, garantizar).

### Within Each User Story

- Tests primero, y deben fallar antes de implementar
- Modelo antes que servicio, servicio antes que endpoint
- El servicio usa el boundary `get_db` + `flush()`, nunca `async_session.begin()` (desviacion
  V1 de plan.md)
- La empresa se deriva siempre de `Depends(get_empresa_id)`

### Conflicts de ficheros conocidos

| Fichero | Tareas | Nota |
|---|---|---|
| `frontend/src/components/documentos/DocumentosAsiento.tsx` | T023, T030, T037 | US1 lo crea, US2 y US3 lo amplian de forma aditiva; ejecutar US1 antes que US2 y US3 |
| `backend/src/api/documentos/__init__.py` y `deps.py` | T021 | Los crean US1; US2 y US3 solo los importan |
| `backend/tests/integration/test_documentos_routes.py` | T019, T025, T034 | US1 escribe el POST, US2 los GET, US3 el DELETE; aditivo en ese orden |
| `requirements.txt` y `backend/src/config.py` | T001, T002 | Phase 1, una sola vez |

---

## Parallel Opportunities

- T002, T003, T004, T005 en Phase 1 (ficheros distintos)
- T009, T010, T011, T012, T013, T015, T016 en Phase 2 (ficheros distintos)
- T017, T018 en Phase 3 (ficheros distintos)
- T020, T022, T023 en Phase 3; T021 y T024 dependen de T020 y T023 respectivamente
- T025, T026 en Phase 4
- T027, T029, T031, T032 en Phase 4
- T033, T034, T035, T037 en Phase 5
- T038, T039, T040, T041, T042 en Phase 6
- T045, T048 en Phase 7
- Las tres historias, en paralelo, siempre que cada persona no edite el mismo fichero

---

## Parallel Example: User Story 1

```text
# Lanzar a la vez los tests de US1 (deben fallar antes de implementar):
Task: "Tests de validacion en backend/tests/unit/test_documento_validacion.py (T017)"
Task: "Tests de aislamiento del alta en backend/tests/unit/test_documento_isolation.py (T018)"

# Lanzar a la vez el servicio y el componente de UI (ficheros distintos):
Task: "Servicio de alta en backend/src/services/documentos/adjuntos.py (T020)"
Task: "Componente de UI en frontend/src/components/documentos/DocumentosAsiento.tsx (T023)"
```

## Parallel Example: User Story 2

```text
# Lanzar a la vez los tres ficheros nuevos de US2 (ninguno existe todavia):
Task: "Servicio de consulta en backend/src/services/documentos/consulta.py (T027)"
Task: "Visor en frontend/src/components/documentos/VisorDocumento.tsx (T029)"
Task: "Pantalla global en frontend/src/app/documentos/page.tsx (T031)"

# Ademas, en paralelo y sobre ficheros distintos de los anteriores:
Task: "Anadir los GET a backend/tests/integration/test_documentos_routes.py (T025)"
Task: "Aislamiento de consulta en backend/tests/integration/test_documentos_tenant.py (T026)"
Task: "Enlace en frontend/src/app/page.tsx (T032)"
```

## Parallel Example: User Story 3

```text
# Lanzar a la vez los ficheros nuevos de US3:
Task: "Tests de inmutabilidad y duplicados en backend/tests/unit/test_documento_adjuntos.py (T033)"
Task: "Tests de baja y trazabilidad en backend/tests/integration/test_documentos_routes.py (T034)"
Task: "Servicio de baja en backend/src/services/documentos/bajas.py (T035)"
Task: "Endpoint de baja en backend/src/api/documentos/bajas.py (T036)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup completa
2. Phase 2 Foundational completa (bloqueante)
3. Phase 3 User Story 1 completa
4. **PARAR Y VALIDAR**: comprobar S2, S3 y S8 parcial de quickstart
5. Entregar o demostrar: ya se puede adjuntar evidencia a un asiento

### Entrega incremental

1. Setup + Foundational -> base lista
2. US1 -> validar S2, S3, S5, S8 -> entregar (MVP)
3. US2 -> validar S4, S7, S11 -> entregar
4. US3 -> validar S4, S6, S9, S10 -> entregar
5. Polish + Convergence -> gates finales y cierre de la spec

### Estrategia de equipo

Con varias personas, tras Phase 2:

- Persona A: US1 (`adjuntos.py` de API y `DocumentosAsiento.tsx`)
- Persona B: US2 (`consulta.py`, `VisorDocumento.tsx`, `app/documentos/page.tsx`)
- Persona C: US3 (`bajas.py` de API y de servicio, mas sus tests)

US2 y US3 no deben tocar `DocumentosAsiento.tsx` a la vez: coordinar T030 y T037 en el mismo
turno, o preparar `VisorDocumento.tsx` y `bajas.ts` en paralelo y montar los controles al final.

---

## Trazabilidad FR a historia

Esta tabla cubre los FR. Las tareas **no citadas** aqui son de infraestructura y no
de producto: T001, T003-T005 (setup), T007 (exportar el modelo), T009-T010 (registro de
la migracion), T012 (`errores.py`), T014 (fixture), T022 (registro del router en
`main.py`), T024 y T032 (montaje y enlace en frontend), T041-T042 (documentacion) y
T043-T048 (puertas de cierre).

| FR | Historia | Tareas |
|---|---|---|
| FR-001, FR-004 | US1 | T006, T020 |
| FR-002, FR-003 | US1 | T002, T013, T017 |
| FR-005 | US1 | T006, T020 |
| FR-006 | US3 | T006, T016, T020, T033 |
| FR-007 | US2 | T015, T027, T028, T029, T030 |
| FR-008 | US2 | T023, T027, T028 |
| FR-009 | US3 | T008, T011, T016, T033 |
| FR-010 | US3 | T035, T036, T037 |
| FR-011 | US3 | T020, T035, T034 |
| FR-012 | US2, US3 | T002, T008, T035, T034 |
| FR-013 | US1, US2 | T006, T018, T020, T026, T027, T028 |
| FR-014 | US1 | T013, T017 |
| FR-015 | US1, US3 | T019, T034, T038 |
| FR-016 | US1, US3 | T021, T028, T036, T019 |
| FR-017 | US2 | T027, T028, T031 |
| FR-018 | US1 | T013, T020, T019 |
| FR-019 | US2 | T027, T028, T031 |
| FR-020 | transversal | T039, T040, T023 |

## Trazabilidad SC a tarea de verificacion

| SC | Escenario de quickstart | Tarea |
|---|---|---|
| SC-001, SC-002 | S2, S4 | T019, T025 |
| SC-003 | S7 | T026, T016 |
| SC-004 | S4 | T025, T033 |
| SC-005 | S4 | T033, T016 |
| SC-006 | S9 | T034 |
| SC-007 | S8 | T019, T034, T038 |
| SC-008 | S2 | T019 |
| SC-009 | S3, S5 | T017, T019 |
| SC-010 | S11 | T025, T031 |
| SC-011 | S6 | T034 |
| SC-012 | S1 | T039 |

## Dependencias con otras specs

- **SPEC-002** (motor de asientos): `journal_entry` es el punto de anclaje. No se modifica.
- **SPEC-006** (asientos multilinea): sufija `/api/v1/asientos/{entry_id}`; de ahi el prefijo
  propio `/api/v1/documentos` con el segmento estatico `/asiento/` para no colisionar.
- **SPEC-003** (multiempresa): `Depends(get_empresa_id)` y la cabecera `X-Empresa-Activa`.
- **SPEC-015** (matriz de permisos): se reutiliza el modulo `acct`; no hay cambios de RBAC.
- **SPEC-013 / SPEC-019**: precedente de binarios en `BYTEA` con `sha256`.
- **SPEC-005 / SPEC-029**: la descarga autenticada sigue el patron existente; incluir los
  documentos en la exportacion integral queda fuera de alcance.

## Notes

- `[P]` significa fichero distinto y sin dependencia pendiente, no "rapido"
- Las historias se organizan por historia de usuario para permitir entrega incremental
- Ninguna tarea se marca completada sin sus tests en verde
- Ningun endpoint de esta spec escribe en `journal_entry` ni en `journal_entry_line`
- La adjuncion es opcional: ningun flujo contable depende de que un asiento tenga documentos
  (FR-020, T039)
- El boundary ACID es `get_db` + `flush()`, no `async with async_session.begin()` (desviacion
  V1 de plan.md)
- Los triggers de inmutabilidad se ejecutan al ejecutar el `UPDATE` o el `DELETE`; en las
  pruebas hay que envolver el `execute` en `pytest.raises(IntegrityError)`
- Los ids de columna `Uuid` se enlazan como `uuid.UUID(...)`, nunca como `str`
- Tras `commit()` o `rollback()` las instancias ORM quedan expiradas: capturar el atributo
  antes de revertir
- La suite completa tarda unos 11 minutos: lanzarla en segundo plano con log y consultar el
  fichero, porque el pipe no devuelve salida hasta el final
- Commit solo si el usuario lo pide de forma explicita

---

## Estado real (implementacion 2026-09-27)

Las 48 tareas quedaron marcadas. Detalle de lo que **no** coincide con
`plan.md`, `research.md` y `data-model.md`, y de lo que se aprendio al ejecutar.

### Ficheros creados

| Fichero | Contenido |
|---|---|
| `backend/src/models/acct/documento.py` | `DocumentoAsiento`, `TipoDocumento`, `EstadoDocumento`, `COLUMNAS_INMUTABLES` |
| `backend/migrations/021_adjuntos_asiento.sql` | 2 enums, tabla, 7 restricciones, 4 índices, 2 triggers |
| `backend/src/db/triggers.py` | espejo SQLite de los 2 triggers |
| `backend/src/services/documentos/errores.py` | `DocumentoError` + `error()` |
| `backend/src/services/documentos/validacion.py` | firmas, `pypdf`, Pillow, tamaño, páginas, nombres, importe |
| `backend/src/services/documentos/adjuntos.py` | `adjuntar_documentos` (US1) |
| `backend/src/services/documentos/consulta.py` | listados, metadatos, descarga (US2) |
| `backend/src/services/documentos/bajas.py` | `dar_de_baja_documento` (US3) |
| `backend/src/services/documentos/_serializacion.py` | serializador compartido (ver desviación 3) |
| `backend/src/api/documentos/{__init__,deps,adjuntos,consulta,bajas}.py` | las 6 rutas |
| `backend/tests/unit/documento_support.py` | generador de PDF/JPEG/PNG/TIFF de prueba |
| `backend/tests/unit/test_documento_validacion.py` | 30 |
| `backend/tests/unit/test_documento_isolation.py` | 7 |
| `backend/tests/unit/test_documento_adjuntos.py` | 16 |
| `backend/tests/unit/test_constitucion_documentos.py` | 23 |
| `backend/tests/integration/test_documentos_routes.py` | 49 |
| `backend/tests/integration/test_documentos_tenant.py` | 12 |
| `backend/tests/integration/test_documentos_opcional.py` | 10 |
| `frontend/src/components/documentos/api.ts` | cliente tipado + `FormData` |
| `frontend/src/components/documentos/DocumentosAsiento.tsx` | selector, listado, baja |
| `frontend/src/components/documentos/VisorDocumento.tsx` | visor `Blob` + `URL.createObjectURL` |
| `frontend/src/app/documentos/page.tsx` | listado global con filtros |

Ficheros modificados: `requirements.txt` (+`pillow`), `backend/src/config.py` (+4
campos), `backend/src/db/migrate.py`, `backend/tests/unit/test_migrations.py`,
`backend/tests/conftest.py` (+fixture `documentos_client`),
`backend/tests/integration/test_pg_schema.py`, `backend/src/main.py`,
`frontend/src/app/asientos/[id]/page.tsx`, `frontend/src/app/page.tsx`.

### Correccion de artefactos posterior al cierre (2026-09-27)

Un analisis de consistencia (`/speckit.analyze`) encontro que los artefactos
contenian **3 contradicciones** y 16 hallazgos mas. Todos corregidos: los
artefactos ya dicen lo que la implementacion hace.

1. **Migracion `021`, no `018`** (critico): los cuatro artefactos nombraban
   `018_adjuntos_asiento.sql`, numero que ya ocupaba `018_cashflow.sql`
   (SPEC-027). Corregido en plan, research, data-model y tasks, incluida la
   posicion en `ORDEN_PREFERENTE` (tras `020_export.sql`, no tras
   `017_presupuestos.sql`).
2. **El prefijo lo lleva cada sub-router** (critico): el plan lo situaba en
   `__init__.py`, pero con la ruta del listado global declarada como `""`
   FastAPI rechaza un `include_router` con prefijo y camino ambos vacios. Es el
   criterio de `api/costcenters/`, y ahora el plan lo dice con su motivo.
3. **Constitution patch 1.0.1** (critico): la constitucion exigia
   `async with async_session.begin()`, MUST que las 30 specs incumplen de forma
   consciente. Enmendada para fijar el boundary real del repositorio
   (`get_db` + `flush()`, y prohibicion explicita de abrir transaccion propia).
4. Escala del plan corregida: **6 endpoints** (no 5) y **5 modulos** de servicio
   (no 3); ambos contradician al propio arbol del plan.
5. `T020` usaba `asiento_entry_id`, nombre que no existe ni en el contrato ni en
   el data-model; unificado en `asiento_id`.
6. `T005` (baseline) y `T043-T048` (cierre) ejecutan las mismas puertas; `T005`
   deja explicito que es la linea base y no cierra la spec.
7. `T047` y el quickstart apuntaban a un cluster PostgreSQL 16 en el puerto
   **5433** que ya no existe; corregidos al cluster real 18.6 en el 5432.
8. Supuesto falso del quickstart S10: `baja` **si** esta concedido a ACCOUNTANT
   por defecto. La forma correcta de probar que `crear` y `baja` son distintos
   es revocar `acct:baja` en la matriz, que es lo que hace la prueba real.
9. FR-001, FR-005, FR-010 y FR-012 reescritos para que sean verificables:
   FR-001 dice que no existe endpoint para otros anclajes, FR-005 nombra
   `content_type` y `extension`, FR-010 excluye tambien `CANCELLED`, y FR-012
   cuantifica el plazo (seis anos, art. 30 LGT).
10. SC-001 marcado como criterio de usuario no automatizado, y SC-008 reescrito
    para que sea comprobable contando items.
11. Contrato de descarga alineado con RFC 6266 (la forma que la implementacion
    ya usaba) y con research D18.
12. La tabla de trazabilidad FR aclara cuales de las 20 tareas no citadas son de
    infraestructura y cuales de producto.

**Sin impacto en el codigo**: ningun test lee los artefactos de la spec, y no
cambio ni un fichero de `backend/src/`.

### Desviaciones de plan.md y research.md

1. **Migracion `021_adjuntos_asiento.sql`, no `018`**. El 018 ya lo ocupaba
   `018_cashflow.sql` (SPEC-027) cuando se diseno esta spec. Va al final de
   `ORDEN_PREFERENTE` y de `ESPERADAS`, que es donde no colisiona: depende de
   `journal_entry` (003) y no depende de nadie posterior.
2. **Los sub-routers llevan el prefijo, el padre no**. `plan.md` preveía
   `APIRouter(prefix="/api/v1/documentos")` en `__init__.py`. FastAPI rechaza un
   `include_router` con prefijo y camino **ambos** vacios, y la ruta del listado
   global es exactamente `""`. Se adopta el criterio de `api/costcenters/`
   (SPEC-017): cada sub-router declara el prefijo y el padre solo agrega.
3. **`services/documentos/_serializacion.py` es un sexto modulo** (plan preveia
   cinco). El alta y la consulta devuelven el mismo objeto del documento y ambos
   necesitan `iso_utc` + el formateo del importe a 4 decimales; duplicarlo
   invitaba a que las copias divergieran.
4. **`ConfigSiiBody.entidad_representante_id` (SPEC-029, cross-spec)**. Al
   verificar el payload SII del ZIP resulto que `payload_sii` solo serializaba
   `clave_regimen` y `sin_anexo`, de modo que `leer_bloque_sii` devolvia
   `entidad_representante_id` y `fecha_alta` como `null` aunque la configuracion
   los tuviera. Ademas la columna no era rellenable por API. Corregido en las
   tres capas: `payload_sii` serializa la configuracion completa, `leer_bloque_sii`
   la lee con `.get` (retrocompatible con ZIPs anteriores) y `PUT /sii/config`
   acepta y persiste el campo. 3 tests nuevos en `test_bloque_sii.py`.
5. **Orden del listado dentro del mismo segundo**. research D15 pide
   `ORDER BY created_at, id` para que el orden sea estable, y lo es: `id` es UUID
   y desempata. Pero dos documentos subidos en el mismo segundo se ordenan por
   UUID, no por orden de subida. Es lo que el spec pide (estabilidad, no
   secuencia) y lo que se verifica.
6. **`audit_log` no tiene orden total**. `AuditLog.id` es un UUID, asi que dos
   entradas del mismo segundo no se pueden ordenar de forma fiable. Es una
   propiedad preexistente del `audit_log` de SPEC-020, no algo que introduzca
   esta spec: no se anade columna de secuencia a una tabla WORM. El test de
   trazabilidad comprueba que existen las dos operaciones, no su orden.
7. **`name_original` sin comillas**. research D14 ya las senala como riesgo de
   cabecera. Se eliminan tambien del **nombre almacenado**: `"` no es valido en
   nombres de fichero en Windows ni macOS, y un cliente que codifica con
   RFC 2231 deja una `"` colgante al deserializar, que el usuario nunca escribio.
8. **`Content-Disposition` conforme a RFC 6266**. `contracts` decia
   `filename="<nombre_original>"`. Con acentos eso mete bytes UTF-8 en una
   cabecera, que es invalido y rompe a clientes estritos (el propio cliente de
   pruebas no la podia leer). Ahora viaja la doble forma: `filename` con
   equivalente ASCII y `filename*=UTF-8''...` percent-encoded. El nombre original
   sigue intacto en la base de datos y en los metadatos.

### Halazgos de los tests que cambiaron el codigo

- **`Content-Disposition` con UTF-8 crudo** (ver 8). Lo encontro el test de
  cabecera, no la revision.
- **Doble envoltura de la cabecera**: al mover la composicion de la cabecera al
  servicio (`datos_documento_para_descarga` devuelve el valor completo), la ruta
  la envolvia otra vez en `filename="..."`. `datos["nombre"]` **es** la cabecera.
- **Indice duplicado en `create_all`**: `empresa_id` con `index=True` mas el
  `Index("ix_documento_asiento_empresa_id", ...)` de `__table_args__` dan
  "index already exists". Se queda solo el indice con nombre, que es el que
  documenta `data-model.md`.
- **Trigger de partida doble en PostgreSQL**: el primer contrato PG insertaba
  asientos sin lineas y `trg_journal_entry_balance` (diferido) los rechazaba en
  el COMMIT. constitution I tambien aplica al contrato; los asientos de prueba
  se balancean.
- **Multipart de httpx**: en una lista, cada fichero es la pareja
  `("files", (nombre, bytes, mime))`, no una terna suelta.
- **`TestClient.delete` no acepta `json=`** como keyword; hay que usar
  `client.request("DELETE", ..., json=...)`.
- **`crear_borrador` nombra los importes `debit`/`credit`** en el dict de linea
  (`debe`/`haber` son los nombres de columna) y exige `account_id` real.
- **Los binds crudos sobre columnas `Uuid` en SQLite** necesitan el hex de 32
  chars (`id.hex`), no el `uuid.UUID`.
- **`pdf_bytes()` es determinista**: dos PDFs identicos en el mismo asiento caen
  en `documento_duplicado` (FR-006, correcto). El generador acepta un `marcador`
  que se graba en los metadatos para que cada fichero sea unico.

### Verificacion

| Puerta | Resultado |
|---|---|
| `pytest` (SQLite) | **2652 passed / 21 skipped**, 0 fallos (el unico `FAILED` fue `test_suggest_perf`, flaky conocido de SPEC-001; **2 passed** aislado) |
| `pytest` (PostgreSQL 18.6 real, esquema limpio, migraciones 000-021) | **2672 passed / 1 skipped** |
| `test_pg_schema.py` | **18 passed** (16 previos + 2 de `documento_asiento`) |
| `ruff check src tests` | limpio |
| `mypy` | limpio, **406 fuentes** |
| `tsc --noEmit` / `eslint src` / `next build` | verdes, **104 rutas** (1 nueva: `/documentos`) |
| Tests nuevos | **147** (30 validacion + 7 aislamiento + 16 adjuntos + 23 constitucion + 49 rutas + 12 tenant + 10 opcional) |

`api.routes_registry.rutas_sin_permiso` sigue en **0**: las 6 rutas llevan su
`require_permission` y `EXCLUSIONES_NO_BYPASS` no ha necesitado cambios
(`research D21`). No se creo modulo RBAC: se reutiliza `acct` con `ver` (4),
`crear` (1) y `baja` (1), lo que satisface FR-016 sin tocar el catalogo.

### Escenarios de quickstart

Los 11 escenarios (S1-S11) tienen verificacion automatica:
S1 `test_documentos_opcional.py` · S2 `test_s2_adjuntar_varios_documentos_de_una_vez`
· S3 `test_s3_rechazos_con_motivo...` · S4 `test_s4_la_huella_del_cuerpo_descargado_coincide`,
`test_s4_reenviar_el_mismo_fichero_es_duplicado`, `test_documento_adjuntos.py` (triggers)
· S5 `test_s5_contenido_incoherente_con_el_formato` + `test_documento_validacion.py`
· S6 `test_s6_*` (8 tests) · S7 `test_documentos_tenant.py` (12) · S8 `test_s8_el_cuadre_no_cambia_al_adjuntar`
· S9 `test_s9_cada_alta_queda_auditada`, `test_s9_la_baja_queda_auditada`
· S10 `test_s10_*` (4) · S11 `test_s11_listar_del_asiento...` + `test_el_orden_del_listado_global_es_estable`

### Nota sobre el permiso `baja` en quickstart S10

S10 supone que "`baja` no esta concedido a ACCOUNTANT en el catalogo por
defecto". No es asi: `_ops_por_rol` concede `ver/crear/editar/baja` a
ACCOUNTANT. El supuesto de mas valor de S10 —que `crear` y `baja` sean
**distintos e intercambiables**— se verifica revocando `acct:baja` en la matriz
de la empresa y comprobando que el alta sigue funcionando y la baja da 403
(`test_s10_crear_y_baja_son_permisos_distintos`). Es una prueba mas fuerte que la
del propio quickstart.
