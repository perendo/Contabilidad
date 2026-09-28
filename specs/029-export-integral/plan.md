# Implementation Plan: Export Integral del Tenant (Backup y Portabilidad)

**Branch**: `029-export-integral` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/029-export-integral/spec.md`

## Summary

Módulo de exportación integral que genera un archivo **ZIP descargable** con todos los datos de contabilidad de la empresa activa (plan de cuentas y versiones, asientos, terceros, facturas, vencimientos, cobros/pagos, remesas, cierres, amortizaciones, presupuestos, previsiones, libros fiscales/SII) con un **manifiesto de integridad** y **huella SHA-256** verificable. La exportación es de lectura y descarga exclusivamente (la importación/restore no está en alcance de esta versión). Incluye un bloque opcional de datos preparados para el **SII de la AEAT** (FR-006). Multi-tenancy estricto: solo se exporta la empresa activa; los datos de otros tenants están excluidos. Los importes se serializan como `Decimal` strings (4 decimales) y el proceso genera auditoría inmutable en la misma transacción ACID.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, auditoría inmutable ACID y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; Next.js (App Router). Generación ZIP: `zipfile` de la stdlib Python (suficiente para streaming dentro de Python). Formatos SII: plantilla de exportación compatible con AEAT (JSON normalizado + campos por registro). Dependencias de datos: SPEC-001/025 (plan de cuentas/versiones), SPEC-002 (asientos), SPEC-003 (multiempresa), SPEC-007 (facturas), SPEC-008 (terceros), SPEC-011 (vencimientos/cobros/pagos), SPEC-020 (remesas), SPEC-028 (cierres), SPEC-014 (amortizaciones), SPEC-026 (presupuestos), SPEC-027 (previsiones), SPEC-012 (libros/SII).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices). El ZIP se almacena como `BYTEA` en `BlobExportacion` con `sha256` verificable; alternativamente, para ficheros > 10 MB, se considera almacenamiento externo (S3 compatible) vía configuración; MVP usa BYTEA.

**Testing**: pytest (unit + integración + contract); tests de integridad de huella, aislamiento multi-tenant y precisión decimal; validación del manifiesto y de contenido por bloque.

**Target Platform**: Linux server (backend API + worker), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: exportación de 10.000 asientos + plan completo + terceros (< 30 s); descarga de ZIP grande (< 500 ms); generación de huella SHA-256 (< 1 s por MB).

**Constraints**: todos los importes serializados como `Decimal` strings (nunca JSON float); ZIP determinista (orden de archivos estable); manifiesto interior `manifest.json` con inventario de bloques; exportación asíncrona o síncrona con streaming para volúmenes grandes; las consultas de datos son read-only.

**Scale/Scope**: 1.000+ empresas multi-tenant; exportaciones de hasta ~50 MB de datos (ZIP) para tenants grandes; varios ejercicios simultáneos; LÍMITE: MVP usa BYTEA (en RAM, en trás de request); tenant muy grande → streaming + paginate lotes de 10 k registros por bloque.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: la exportación no crea ni modifica asientos; verifica que los importes serializados en cada bloque conservan `Decimal`/`NUMERIC(18,4)`; no requiere validar balance (ese trabajo es de SPEC-002 al crear). → Cumple.
- **II. Inmutabilidad del diario**: la exportación es de solo lectura; los datos exportados son inmutables al momento de la consulta; la exportación persistida es inmutable (sin UPDATE/DELETE de `Exportacion`). → Cumple.
- **III. Multi-tenancy estricto**: todas las consultas de cada bloque se ejecutan con `empresa_id` de la sesión autenticada; la exportación registrada lleva `empresa_id` y la descarga está sujeta a permiso; los datos de otros tenants nunca entran en el ZIP. → Cumple.
- **IV. Numeración correlativa**: `numero_exportacion` correlativo por `(empresa_id, anio_creacion)`, asignado atómicamente en la misma transacción. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (hash verificable, aislamiento multi-tenant, precisión decimal). → Cumple.
- **Decimal/no float**: todos los importes de exportación serializados como strings `"1234.5678"` con precisión 4 decimales; prohibido JSON float. → Cumple.
- **Auditoría inmutable**: cada generación de exportación y verificación se registra en audit log en la misma transacción ACID (empresa, usuario, acción, exportacion_id, timestamp, IP). → Cumple.

Sin violaciones. La decisión de formato ZIP con JSON por bloque y manifest.json se justifica en research.md.

## Project Structure

### Documentation (this feature)

```text
specs/029-export-integral/
├── plan.md                 # Este fichero
├── research.md             # Decisiones de diseño (Phase 0)
├── data-model.md           # Modelo de entidades (Phase 1)
├── quickstart.md           # Escenarios de validación (Phase 1)
├── contracts/              # Contratos de API y formato de fichero (Phase 1)
│   ├── api-contracts.md
│   └── export-layout.md    # Especificación del ZIP y manifest.json
└── tasks.md                # Checklist de implementación (Phase 2)
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   └── export/             # Esta feature
    │       ├── __init__.py
    │       ├── config_sii.py
    │       ├── exportacion.py
    │       ├── manifiesto.py
    │       └── blob_exportacion.py
    ├── services/
    │   └── export/
    │       ├── __init__.py
    │       ├── bloques.py      # inventario de fuentes de datos por bloque
    │       ├── recopilar.py    # consultas paginadas por bloque (empresa_id)
    │       ├── manifiesto.py   # generación de manifest.json
    │       ├── zip_generator.py # streaming del ZIP + sha256
    │       ├── persistir.py    # ACID: Exportacion + Manifiesto + Blob + audit
    │       ├── verificar.py    # verificación de integridad
    │       └── sii.py          # generación bloque SII (AEAT)
    ├── api/
    │   ├── export.py           # router endpoints exportaciones
    │   └── deps.py             # get_empresa_id() (ya existente)
    └── config.py

backend/
└── tests/
    ├── unit/
    │   ├── test_manifiesto.py
    │   ├── test_zip_layout.py
    │   ├── test_hash_integridad.py
    │   ├── test_precision_decimal_export.py
    │   └── test_config_sii.py
    ├── integration/
    │   ├── test_export_completo.py
    │   ├── test_export_rango_ejercicio.py
    │   ├── test_export_tenant_isolation.py
    │   ├── test_verificar_integridad.py
    │   └── test_bloque_sii.py
    └── contract/
        └── test_export_api_contracts.py

frontend/
└── src/
    ├── app/
    │   ├── exportaciones/
    │   │   ├── page.tsx              # listado de exportaciones
    │   │   ├── nueva/
    │   │   │   └── page.tsx          # crear nueva exportación
    │   │   └── [id]/
    │   │       └── page.tsx          # detalle + descarga + verificar
    │   └── components/
    │       └── export/
    │           ├── ManifiestoEstado.tsx  # estado de bloques + manifiesto
    │           └── DescargaExport.tsx    # botón descarga + hash verificado
    └── services/
        └── client.ts             # ampliar métodos de exportación
```

**Structure Decision**: Módulo `export/` dedicado bajo `models/` y `services/`; el router `api/export.py` centraliza endpoints; el servicio `bloques.py` mantiene un catálogo extensible de bloques de datos (cada bloque define su función query, su nombre de fichero y el conteo); `zip_generator.py` gestiona la escritura determinista del ZIP y el cálculo de SHA-256 en streaming; `persistir.py` atomiza la escritura de `Exportacion` + `ManifiestoExportacion` + `BlobExportacion` + audit log en una sola transacción.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): formato ZIP, bloques de datos, filtro por ejercicio, multi-tenancy en export, streaming, huella y manifiesto, precisión decimal, enlace SII.
- **data-model.md** (Phase 1): entidades `Exportacion`, `ManifiestoExportacion`, `ManifiestoBloque`, `BlobExportacion`, `ConfigSii`.
- **contracts/** (Phase 1): contrato API REST de exportaciones, verificación y SII + especificación del formato ZIP (`export-layout.md`).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.
