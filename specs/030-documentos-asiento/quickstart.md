# Quickstart: Validacion de Documentos adjuntos al asiento (SPEC-030)

**Feature**: `specs/030-documentos-asiento/spec.md` · **Date**: 2026-09-26

Guia de validacion de extremo a extremo. Cada escenario es un caso de prueba con su resultado
esperado. Los detalles de campos y codigos de error estan en
[contracts/api-contracts.md](contracts/api-contracts.md) y las restricciones de persistencia en
[data-model.md](data-model.md).

---

## 0. Prerrequisitos

```powershell
# Raiz del repositorio: la dependencia nueva
#   + pillow>=10.0,<13.0
#   pypdf ya estaba declarada. Sin dependencias nuevas de frontend.

# PostgreSQL opcional, solo para el contrato de migracion (ver seccion 6)
#   Cluster real en el puerto 5432 (AGENTS.md seccion 19). `db.migrate` lee
#   DATABASE_URL de backend\.env, asi que basta con exportarla para el runner.
Get-Service postgresql-x64-18
```

## 1. Puertas de calidad

```powershell
# Backend, desde backend/
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check src tests
..\.venv\Scripts\python.exe -m mypy -p api -p models -p services -p database -p base -p db -p main -p config

# Frontend, desde frontend/
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js src
$env:NEXT_TELEMETRY_DISABLED="1"; node node_modules/next/dist/bin/next build
```

## 2. Migracion

```powershell
# Desde backend/
$env:PYTHONPATH="src"; ..\.venv\Scripts\python.exe -m db.migrate
```

**Esperado**: `021_adjuntos_asiento.sql` aplicada sin error. Verificar que la migracion esta
registrada en los dos sitios exactos, o falla `test_orden_por_dependencias`:

- `backend/src/db/migrate.py` -> `ORDEN_PREFERENTE`, anadida tras `017_presupuestos.sql`.
- `backend/tests/unit/test_migrations.py` -> `ESPERADAS`, misma posicion.

## 3. Escenarios de validacion

### S1. La adjuncion es opcional (FR-020, SC-012) — el escenario ancla

Un asiento sin documentos recorre su ciclo de vida completo sin restricciones.

1. Crear y contabilizar un asiento con lineas balanceadas.
2. `GET /api/v1/documentos/asiento/{id}` -> **200** con
   `{"items": [], "total": 0, "documentos_obligatorios": false}`. Nunca 404.
3. Asentar, anular y volver a listar el asiento -> ninguna operacion falla ni exige documentos.
4. Consultar el listado global de documentos -> el asiento no aparece y la consulta no falla.

**Esperado**: ningun flujo contable depende de la existencia de documentos.

### S2. Adjuntar varios documentos de una vez (US1, FR-001..FR-005)

1. `POST /api/v1/documentos/asiento/{id}` en multipart con `files` = [factura.pdf, foto.jpg,
   escaneo.png] y `tipo_documento=factura`.
2. Comprobar `sum(SDebe) == sum(SHaber)` del asiento antes y despues.
3. Consultar `GET /api/v1/documentos/asiento/{id}`.

**Esperado**: 201 con 3 elementos en `aceptados` y `rechazados` vacio. Cada item trae nombre,
extension, `content_type`, `size_bytes`, `num_paginas`, `sha256`, tipo, descripcion, estado
`activo`, autor y `created_at`. El cuadre del asiento es identico antes y despues.

### S3. Rechazos con motivo, sin dejar nada a medias (FR-018, SC-009)

1. En una sola peticion, enviar [factura.pdf valida, captura.png.bak, escaneo.tif de 12 MB].
2. Comprobar el cuerpo de `rechazados`.

**Esperado**: 201. `aceptados` contiene la factura. `rechazados` contiene
`captura.png.bak` con `code=formato_no_admitido` y `escaneo.tif` con
`code=documento_demasiado_grande`. El listado del asiento muestra 1 documento, no 2 ni 0.

### S4. Integridad verificable y duplicados (FR-006, FR-009, SC-004, SC-005)

1. Descargar el documento con `GET /api/v1/documentos/{id}/descarga`.
2. Calcular `sha256` del binario recibido y compararlo con `X-Documento-SHA256` y con el
   `sha256` del alta.
3. Reenviar el mismo fichero al mismo asiento.
4. Intentar `PATCH`/`PUT` sobre el contenido del documento.

**Esperado**: las tres huellas coinciden. El reenvio produce `documento_duplicado` (409) y no
crea una segunda fila. No existe endpoint para sobrescribir el contenido, y el trigger
`trg_documento_asiento_contenido_inmutable_update` rechaza el `UPDATE` con `IntegrityError`
cuando se intenta por via directa.

### S5. Contenido incoherente con el formato (FR-014)

1. Renombrar un JPEG a `factura.pdf` y adjuntarlo.
2. Adjuntar un PDF truncado.
3. Adjuntar un PDF protegido con contrasena.
4. Adjuntar un PDF de 250 paginas.
5. Adjuntar un fichero de 0 bytes.

**Esperado**: `documento_ilegible`, `documento_ilegible`, `documento_protegido`,
`documento_paginas_excedidas` y `documento_vacio`, respectivamente. Ninguno se persiste.

### S6. Baja logica y su impossibility en un asiento asentado (FR-010, FR-012, SC-011)

1. Con un asiento en `DRAFT`, `DELETE /api/v1/documentos/{id}` con `{"motivo": "..."}`.
2. Intentar borrar fisicamente la fila con `session.execute(delete(...))`.
3. Descargar el documento dado de baja.
4. Con un asiento `POSTED`, intentar `DELETE` de un documento suyo.

**Esperado**: (1) 204 y estado `dado_de_baja` con motivo, responsable y fecha.
(2) `IntegrityError` del trigger `trg_documento_asiento_inmutable_delete`.
(3) 200 con el contenido intacto y la misma huella: la baja es logica.
(4) 409 `baja_no_permitida`.

### S7. Aislamiento multi-empresa (constitution III, FR-004, FR-013, SC-003)

Con empresas A = 10 y B = 20, cada una con su asiento y sus documentos:

1. `GET /asiento/{id_de_B}` desde la sesion de A.
2. `GET /{documento_id_de_B}/descarga` desde A.
3. `GET /documentos?ejercicio=...` desde A y comprobar que no aparece ningun documento de B.
4. `POST /asiento/{id_de_B}` con un fichero desde A.
5. `DELETE /{documento_id_de_B}` desde A.

**Esperado**: las cinco operaciones devuelven 404 con el mismo texto que un recurso
inexistente. El listado de A solo contiene documentos de A. El `Cache-Control: no-store` esta
presente en todas las descargas.

### S8. Cuadre intacto (constitution I y V, FR-015, SC-007)

1. Registrar `sum(SDebe)` y `sum(SHaber)` del asiento.
2. Adjuntar tres documentos y despues dar de baja uno (en un asiento `DRAFT`).
3. Volver a calcular ambas sumas y el `estado` del asiento.

**Esperado**: sumas identicas, cuadre exacto y `estado` sin cambios. Ninguna ruta de esta spec
escribe en `journal_entry` ni en `journal_entry_line`.

### S9. Trazabilidad inmutable (constitution II, FR-011, SC-006)

1. Adjuntar un documento y dar de baja otro.
2. Consultar `audit_log` filtrando `entidad = 'documento_asiento'`.
3. Intentar `UPDATE` o `DELETE` sobre esas filas de auditoria.

**Esperado**: una entrada por operacion con `usuario`, `timestamp` UTC, `ip`, `operacion`
(`ADJUNTAR_DOCUMENTO` / `DAR_DE_BAJA_DOCUMENTO`), `entidad_id` y `payload` con `sha256`,
`nombre_original` y `size_bytes`. Los triggers WORM `trg_audit_log_immutable_update` y
`_delete` rechazan la modificacion.

### S10. Permisos diferenciados (FR-016)

Con un usuario `READ_ONLY` y otro `ACCOUNTANT` en la misma empresa:

1. `READ_ONLY` intenta adjuntar -> 403 `sin_permiso`.
2. `READ_ONLY` intenta listar y descargar -> 200.
3. `ACCOUNTANT` adjunta -> 201.
4. `ACCOUNTANT` intenta dar de baja -> 403 `sin_permiso`. **Ojo**: el catalogo por defecto
   si concede `baja` a ACCOUNTANT, asi que el supuesto original era falso. La forma
   correcta de probar que `crear` y `baja` son distintos es **revocar `acct:baja`** en la
   matriz de la empresa y comprobar que el alta sigue funcionando mientras la baja da 403.

**Esperado**: exactamente esa separacion. Confirma que `acct:crear` y `acct:baja` son permisos
distintos y no intercambiables.

### S11. Listado global y localizacion (FR-017, FR-019, SC-010)

1. Adjuntar documentos en asientos de dos ejercicios distintos.
2. `GET /documentos?ejercicio=2025` y `GET /documentos?tipo_documento=factura`.
3. `GET /documentos?q=<texto parcial del nombre>`.
4. Repetir la misma consulta dos veces y comparar el orden.

**Esperado**: los filtros devuelven solo lo que corresponde, y el orden es identico entre
llamadas (desempate estable por `id`).

## 4. Cobertura de pruebas prevista

| Suite | Fichero | Cubre |
|---|---|---|
| Unit | `test_documento_validacion.py` | Firmas, pypdf, Pillow, tamano, paginas, nombres largos |
| Unit | `test_documento_adjuntos.py` | Alta, duplicados, limite por asiento, listado, baja, inmutabilidad del trigger |
| Unit | `test_documento_isolation.py` | Filtro por `empresa_id` en toda consulta |
| Unit | `test_constitucion_documentos.py` | Prefijo `/api/v1`, `empresa_id` nunca en body ni ruta, guard en las 6 rutas, `Decimal` |
| Unit | `test_migrations.py` | Presencia y contenido de `021_adjuntos_asiento.sql` |
| Integration | `test_documentos_routes.py` | Los 6 endpoints con sus codigos |
| Integration | `test_documentos_tenant.py` | S7 completo |
| Integration | `test_documentos_opcional.py` | S1, el escenario ancla de FR-020 |
| Contract | `test_pg_schema.py` | Tabla, enum, unicidades, FKs compuestas y ambos triggers sobre PostgreSQL 16 |

Fixture nuevo en `backend/tests/conftest.py`: `documentos_client`, con empresas A = 10 y
B = 20, PGC sembrado, usuarios ADMIN y ACCOUNTANT, y un asiento `DRAFT` y otro `POSTED` por
empresa.

## 5. Validacion de frontend

1. `next build` compila las rutas nuevas: `/documentos` y el detalle del asiento.
2. En `/asientos/[id]`, la seccion de documentos muestra el estado vacio declarando que los
   adjuntos son opcionales.
3. Adjuntar dos ficheros: aparece un selector multiple con `accept` de PDF e imagenes.
4. Descargar un documento: el `Blob` llega con `sha256` coincidente.
5. Previsualizar un JPEG y un PDF desde la URL de objeto.
6. Cambiar de empresa con `CompanySwitch`: el listado y el detalle se recalculan y no muestran
   documentos de la empresa anterior.

## 6. Verificacion sobre PostgreSQL 16 real (opcional pero recomendada)

```powershell
# Desde backend/
$env:PYTHONPATH="src"
$env:TEST_DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/contabilidad"
..\.venv\Scripts\python.exe -m pytest tests/integration/test_pg_schema.py
```

**Esperado**: los tests de `documento_asiento` en verde, entre ellos los que comprueban que
`UPDATE` del contenido y `DELETE` Raises `IntegrityError` en PostgreSQL real, no solo en el
espejo SQLite.

## 7. Criterio de terminado

- [ ] Todas las tareas de `tasks.md` marcadas y las puertas de la seccion 1 en verde.
- [ ] Los 11 escenarios de la seccion 3 con su resultado esperado.
- [ ] Migracion `018` aplicada y registrada en los dos listas, en el mismo orden.
- [ ] `next build` verde con las rutas nuevas.
- [ ] Ninguna ruta de esta spec escribe en el diario (verificable por inspeccion del modelo).
- [ ] Confirmado explicitamente que un asiento sin documentos opera con normalidad (S1).
