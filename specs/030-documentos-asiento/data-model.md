# Data Model: Documentos adjuntos al asiento (SPEC-030)

**Feature**: `specs/030-documentos-asiento/spec.md` · **Date**: 2026-09-26
**Migracion**: `backend/migrations/021_adjuntos_asiento.sql` · **Modelos**: `backend/src/models/acct/documento.py`

Una sola entidad nueva. No hay tablas de trazabilidad, de configuracion ni de contadores: la
trazabilidad se apoya en el `audit_log` WORM ya existente (research.md D5) y los limites son
parametros de `Settings` (D10).

---

## 1. Enum `documento_tipo`

Lista **cerrada** de seis valores (research.md D17). El cliente no puede introducir valores
fuera del conjunto; un valor desconocido produce `tipo_documento_invalido` (422).

| Valor | Uso tipico |
|---|---|
| `factura` | Factura de proveedor o cliente que justifica el apunte |
| `recibo` | Recibo, justificante de cobro o de pago |
| `extracto` | Extracto bancario o certificado |
| `justificante` | Justificante generico sin forma administrativa reconocible |
| `contrato` | Contrato de arrendamiento o de prestacion de servicios |
| `otro` | Documento que no encaja en ninguna de las anteriores |

## 2. Enum `documento_estado`

| Valor | Significado |
|---|---|
| `activo` | Documento visible y descargable en el listado del asiento |
| `dado_de_baja` | Baja logica: el contenido se conserva pero deja de ofrecerse por defecto (FR-012) |

Transicion unica: `activo` -> `dado_de_baja`. No hay vuelta atras. La baja solo es posible
mientras el asiento este en `DRAFT` (FR-010).

## 3. Entidad `documento_asiento`

### Columnas

| Columna | Tipo SQL | Tipo Python | Null | Notas |
|---|---|---|---|---|
| `id` | `UUID` | `uuid.UUID` | no | PK, `default=uuid.uuid4` en el modelo |
| `empresa_id` | `BIGINT` | `int` | no | Tenant activo de la sesion; indexado (constitution III) |
| `journal_entry_id` | `UUID` | `uuid.UUID` | no | Asiento ancla; parte de la FK compuesta |
| `contenido` | `BYTEA` | `bytes` | no | Binario integro; nunca se reescribe (FR-009) |
| `sha256` | `VARCHAR(64)` | `str` | no | `hashlib.sha256(contenido).hexdigest()` |
| `nombre_original` | `VARCHAR(255)` | `str` | no | Tal cual lo subio el usuario; validado antes de insertar (D18) |
| `content_type` | `VARCHAR(100)` | `str` | no | MIME derivado de la firma detectada, no del header |
| `extension` | `VARCHAR(10)` | `str` | no | Sin punto y en minusculas: `pdf`, `jpg`, `png`, `tif` |
| `size_bytes` | `BIGINT` | `int` | no | `CHECK (size_bytes > 0)` |
| `num_paginas` | `INTEGER` | `int \| None` | si | Solo para PDF; `NULL` en imagenes |
| `tipo_documento` | `documento_tipo` | `TipoDocumento` | no | Ver seccion 1 |
| `descripcion` | `VARCHAR(500)` | `str \| None` | si | Texto libre del usuario |
| `importe_informativo` | `NUMERIC(18,4)` | `Decimal \| None` | si | Solo referencia visual; nunca altera el asiento (D19) |
| `estado` | `documento_estado` | `EstadoDocumento` | no | `DEFAULT 'activo'` |
| `baja_motivo` | `VARCHAR(500)` | `str \| None` | si | Obligatorio si `estado = 'dado_de_baja'` |
| `baja_usuario` | `VARCHAR(120)` | `str \| None` | si | Quien ejecuto la baja |
| `baja_at` | `TIMESTAMPTZ` | `datetime \| None` | si | UTC |
| `created_by` | `VARCHAR(120)` | `str \| None` | si | Quien adjunto el documento |
| `created_at` | `TIMESTAMPTZ` | `datetime` | no | `server_default=func.now()`; UTC |

### Restricciones

| Nombre | Tipo | Definicion | Proposito |
|---|---|---|---|
| `pk_documento_asiento` | PK | `(id)` | Identificador global |
| `uq_documento_asiento_empresa_id` | UNIQUE | `(empresa_id, id)` | Clave tenant que consume la FK compuesta |
| `uq_documento_asiento_huella` | UNIQUE | `(empresa_id, journal_entry_id, sha256)` | Deteccion de duplicados (FR-006, D6) |
| `fk_documento_asiento_entrada` | FK | `(empresa_id, journal_entry_id)` -> `journal_entry (empresa_id, id)` | Aislamiento cross-tenant (constitution III) |
| `chk_documento_asiento_tamano` | CHECK | `size_bytes > 0` | Rejecta ficheros vacios |
| `chk_documento_asiento_baja` | CHECK | `(estado = 'activo' AND baja_motivo IS NULL AND baja_usuario IS NULL AND baja_at IS NULL) OR (estado = 'dado_de_baja' AND baja_motivo IS NOT NULL AND baja_usuario IS NOT NULL AND baja_at IS NOT NULL)` | Una baja siempre esta completa y trazada |
| `chk_documento_asiento_importe` | CHECK | `importe_informativo IS NULL OR importe_informativo >= 0` | Sin importes negativos |

### Indices

| Nombre | Columnas | Proposito |
|---|---|---|
| `ix_documento_asiento_empresa_id` | `(empresa_id)` | Filtro de tenant en toda consulta |
| `ix_documento_asiento_entrada` | `(empresa_id, journal_entry_id, created_at, id)` | Listado del asiento en orden determinista (D15) |
| `ix_documento_asiento_ejercicio` | `(empresa_id, created_at)` | Listado global por ejercicio (FR-017) |
| `ix_documento_asiento_tipo` | `(empresa_id, tipo_documento)` | Filtro por tipo de documento (FR-017) |

`created_at` e `id` forman el par de ordenacion D15; `id` es UUID y actua de desempate
estable, de modo que dos documentos con la misma marca de tiempo mantienen el orden entre
peticiones.

### Triggers

| Trigger | Momento | Efecto |
|---|---|---|
| `trg_documento_asiento_contenido_inmutable_update` | `BEFORE UPDATE` | Rechaza si cambia cualquiera de `contenido`, `sha256`, `nombre_original`, `content_type`, `extension`, `size_bytes`, `num_paginas`, `journal_entry_id`, `empresa_id`, `tipo_documento`, `descripcion`, `importe_informativo`, `created_by` o `created_at`. Solo se admite el cambio de `estado`, `baja_motivo`, `baja_usuario` y `baja_at` (research.md D3) |
| `trg_documento_asiento_inmutable_delete` | `BEFORE DELETE` | Rechaza siempre: la baja es logica y el contenido se conserva durante el plazo legal (FR-012) |

Implementacion: funcion `f_documento_asiento_inmutable_update()` que compara `OLD` y `NEW` con
`IS DISTINCT FROM` y lanza `RAISE EXCEPTION` con el mensaje `documento_asiento inmutable`. El
espejo para SQLite vive en `backend/src/db/triggers.py` y se instala en los tests tras
`create_all`.

## 4. Entidades existentes implicadas (sin cambios)

| Entidad | Fichero | Que aporta | Cambios |
|---|---|---|---|
| `JournalEntry` | `models/acct/journal.py` | Asiento ancla y su estado `DRAFT`/`POSTED`/`CANCELLED` | Ninguno |
| `JournalEntryLine` | `models/acct/journal.py` | Apuntes y cuadre | Ninguno |
| `AuditLog` | `models/audit/audit_log.py` | Traza WORM de altas y bajas | Ninguno |
| `PermisoOperacion`, `Rol`, `MatrizPermiso` | `models/rbac/` | Permisos `acct:ver`, `acct:crear`, `acct:baja` | Ninguno |

`journal_entry` **no** recibe columna de recuento ni `NOT NULL`: la adjuncion es opcional
(FR-020, research.md D11).

## 5. Reglas de validacion

Se aplican en `services/documentos/validacion.py`, antes de insertar. Cada fallo produce un
`DocumentoError` con su `code`, que la API mapea a 404, 409 o 422.

| `code` | HTTP | Condicion |
|---|---|---|
| `formato_no_admitido` | 422 | La extension no es `pdf`, `jpg`, `jpeg`, `png` ni `tif`/`tiff` (FR-002) |
| `documento_ilegible` | 422 | El contenido no corresponde a la firma declarada, o el PDF esta corrupto, o la imagen no supera `verify()` (FR-014) |
| `documento_protegido` | 422 | El PDF esta cifrado con contrasena (D16) |
| `documento_paginas_excedidas` | 422 | El PDF supera `documento_max_paginas` (D16) |
| `documento_demasiado_grande` | 422 | Supera `documento_max_bytes` (FR-003) |
| `documento_vacio` | 422 | `size_bytes == 0` |
| `documento_nombre_largo` | 422 | `nombre_original` supera 255 caracteres o su tamano en bytes excede el limite de la columna (D18) |
| `descripcion_larga` | 422 | `descripcion` supera 500 caracteres |
| `motivo_largo` | 422 | `baja_motivo` supera 500 caracteres |
| `importe_informativo_invalido` | 422 | No es un decimal valido o es negativo (D19) |
| `tipo_documento_invalido` | 422 | Valor fuera del enum (D17) |
| `asiento_no_encontrado` | 404 | El asiento no existe **o** no pertenece a la empresa activa (D14) |
| `documento_no_encontrado` | 404 | El documento no existe, no pertenece a la empresa activa, o esta dado de baja y se pidio por una via que excluye las bajas (D14) |
| `documento_duplicado` | 409 | Ya existe un documento con la misma `sha256` en ese asiento (FR-006) |
| `limite_documentos_alcanzado` | 409 | El asiento ya tiene `documento_max_por_asiento` documentos activos |
| `baja_no_permitida` | 409 | El asiento no esta en `DRAFT`; el soporte de un asiento asentado no se retira (FR-010) |
| `baja_motivo_obligatorio` | 422 | `baja_motivo` vacio en una solicitud de baja (FR-012) |

## 6. Estados y transiciones

```text
                 adjuntar (permiso acct:crear)
   [no existe] ------------------------------> activo
                                                |
                                                | dar de baja (permiso acct:baja)
                                                | solo si asiento en DRAFT
                                                | con motivo obligatorio
                                                v
                                          dado_de_baja
                                          (contenido y sha256 conservados)
```

- El asiento destino puede estar en `DRAFT`, `POSTED` o `CANCELLED` al **adjuntar**
  (FR-010). Un asiento `CANCELLED` conserva sus documentos como evidencia historica.
- El contenido nunca pasa de `activo` a `dado_de_baja` por otra via: no hay endpoint de
  borrado fisico.
- La unicidad `uq_documento_asiento_huella` sigue aplicandose en `dado_de_baja`, por lo que el
  mismo fichero no puede volver a adjuntarse al mismo asiento (research.md D6).

## 7. Reglas de aislamiento multi-empresa

Se aplican en **todas** las consultas, sin excepcion:

1. `empresa_id` se obtiene de `Depends(get_empresa_id)`, que lo lee de la cabecera
   `X-Empresa-Activa` y valida la relacion `UserCompany` activa. Nunca se acepta del cuerpo ni
   de la ruta.
2. Toda lectura de `documento_asiento` incluye `DocumentoAsiento.empresa_id == empresa_id`.
3. La escritura de `journal_entry` para comprobar el estado del asiento incluye tambien
   `JournalEntry.empresa_id == empresa_id`.
4. Un identificador de documento o de asiento de otra empresa produce 404 con el mismo mensaje
   que un recurso inexistente, para no permitir enumeracion (research.md D14).
5. La FK compuesta `(empresa_id, journal_entry_id)` impide en la base de datos que un documento
   de una empresa se ancle a un asiento de otra, aunque la aplicacion fallara.
