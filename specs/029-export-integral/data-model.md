# Data Model: Export Integral del Tenant (Backup y Portabilidad) (SPEC-029)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión, nunca del request.
- Importes en `NUMERIC(18,4)`/`Decimal`; serializados como strings `"123.4500"` en JSON; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.
- `Exportacion`, `ManifiestoExportacion`, `ManifiestoBloque` y `BlobExportacion` son inmutables tras persistirse (INSERT único, sin UPDATE/DELETE).

## Exportacion

Registro de una operación de exportación integral de un tenant.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de la clave única (empresa_id, anio_creacion, numero_exportacion) |
| anio_creacion | INT | año en que se ejecuta la exportación (para correlatividad) |
| numero_exportacion | BIGINT | correlativo por (empresa_id, anio_creacion), asignado atómicamente |
| tipo | ENUM | `INTEGRAL` / `SII` |
| ejercicio_desde | INT NULL | si NULL, exporta todo el tenant sin filtro |
| ejercicio_hasta | INT NULL | si NULL, exporta todo el tenant sin filtro |
| estado | ENUM | `en_proceso`, `lista`, `fallida` |
| creado_por | UUID | usuario que ejecuta la exportación |
| created_at | TIMESTAMPTZ | (UTC) |
| completado_at | TIMESTAMPTZ NULL | |
| blob_id | UUID NULL | FK → BlobExportacion.id |
| sha256 | CHAR(64) NULL | huella del ZIP generado |
| tamano_bytes | BIGINT | tamaño del ZIP |
| n_bloques | INT | número de bloques exportados |
| mensaje_error | TEXT NULL | si `estado=fallida`, descripción del error |

**Validaciones**:
- Unicidad de `numero_exportacion` por `(empresa_id, anio_creacion)`.
- `ejercicio_desde <= ejercicio_hasta` si ambos no son NULL.
- La exportación es inmutable: tras `estado=lista`, no admite UPDATE/DELETE.
- La descarga solo se permite a la empresa activa del usuario autenticado.

**Transiciones de estado**: `en_proceso → lista` (éxito, blob+manifiesto+sha256 registrados) | `en_proceso → fallida` (error durante la generación; `mensaje_error` explica).

## ManifiestoExportacion

Inventario de bloques incluidos en la exportación, almacenado como registros vinculados.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| exportacion_id | UUID FK → Exportacion | UNIQUE (un manifiesto por exportación) |
| formato_version | VARCHAR(20) | versión del formato del manifiesto (p. ej. `"1.0.0"`) |
| fecha_generacion | TIMESTAMPTZ | (UTC) |
| empresa_id | BIGINT | redundante con empresa_id para verificación en el JSON interior |
| n_bloques | INT | total de bloques listados |
| sha256_fichero | CHAR(64) | huella SHA-256 del ZIP completo |

## ManifiestoBloque

Línea de manifiesto: inventario de un bloque de datos incluido.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| manifiesto_id | UUID FK → ManifiestoExportacion | |
| bloque | VARCHAR(64) | nombre del bloque (p. ej. `asientos`, `cuentas`, `terceros`) |
| entidades_exportadas | VARCHAR(100) | lista de entidades incluidas (snapshot) |
| conteo_registros | BIGINT | número de registros del bloque |
| sha256 | CHAR(64) NULL | hash del contenido del bloque (opcional a nivel DB; calculado en ZIP) |
| fecha_min | DATE NULL | fecha del registro más antiguo del bloque (si aplica) |
| fecha_max | DATE NULL | fecha del registro más reciente |
| ejercicio_min | INT NULL | ejercicio mínimo de los datos exportados |
| ejercicio_max | INT NULL | ejercicio máximo |

**Validaciones**: el conteo de registros en DB debe coincidir con los registros serializados en el ZIP; si no, la verificación de integridad falla.

## BlobExportacion

Contenido binario del ZIP generado, almacenado en la misma transacción.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| exportacion_id | UUID FK → Exportacion | UNIQUE (un blob por exportación) |
| contenido | BYTEA | el ZIP comprimido |
| sha256 | CHAR(64) | huella del contenido (redundante con Exportacion.sha256) |
| tamano_bytes | BIGINT | |
| created_at | TIMESTAMPTZ | |

**Validación**: la huella se calcula sobre el contenido del ZIP; la re-descarga entrega el mismo binario (inmutabilidad del blob).

## ConfigSii

Configuración de la empresa para el SII de la AEAT (opcional, habilitable por empresa).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | UNIQUE por empresa |
| obligado_sii | BOOLEAN | default `false` |
| sin_anexo | BOOLEAN | default `false` (exento de anexos) |
| clave_regimen | VARCHAR(10) | código de régimen (01–17, según modelo 303) |
| entidad_representante_id | UUID NULL | FK → tercero representante (SPEC-008) |
| fecha_alta | DATE | fecha de alta en el SII |
| created_at | TIMESTAMPTZ | |

**Validación**: `ConfigSii` solo se inserta si `obligado_sii=true`; los datos del SII se exportan solo cuando `tipo=INTEGRAL` o `tipo=SII` y `obligado_sii=true`.

## Resumen de relaciones

```
Exportacion 1 ── 1 BlobExportacion
Exportacion 1 ── 1 ManifiestoExportacion
ManifiestoExportacion 1 ── n ManifiestoBloque
Exportacion 1 ── 0..1 ConfigSii (empresa, si obligada)
Empresa (SPEC-003) 1 ── n Exportacion
Empresa (SPEC-003) 1 ── 0..1 ConfigSii
```

## Contenido serializado en el ZIP (manifest.json)

```json
{
  "formato_version": "1.0.0",
  "fecha_generacion": "2026-09-16T12:00:00Z",
  "empresa_id": 42,
  "ejercicio_desde": 2024,
  "ejercicio_hasta": 2026,
  "bloques": [
    { "bloque": "plan_cuentas", "conteo_registros": 150, "ejercicio_min": null, "ejercicio_max": null },
    { "bloque": "asientos", "conteo_registros": 12500, "ejercicio_min": 2024, "ejercicio_max": 2026 }
  ],
  "sha256_fichero": "abc123..."
}
```