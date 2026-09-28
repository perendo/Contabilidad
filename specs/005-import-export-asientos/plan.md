# Implementation Plan: Importación y Exportación Masiva de Asientos Contables

**Branch**: `005-import-export-asientos` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-import-export-asientos/spec.md`

## Summary

Módulo de importación masiva (CSV/Excel) de asientos contables con previsualización dry-run, validación de cuentas apuntables, partida doble estricta con `Decimal` y ejercicios abiertos; importación definitiva con transacción atómica por asiento, numeración secuencial correlativa y auditoría inmutable; exportación del libro diario a CSV/XLSX con precisión de 4 decimales; interfaz drag-and-drop con vista previa de errores.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router); para importación CSV se usa `csv` estándar de Python, para XLSX se usa `openpyxl`; para exportación CSV/XLSX se generan ambos formatos.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`). No crea tablas propias; consume las tablas de asientos (SPEC-002), cuentas (SPEC-001) y ejercicios (SPEC-004).

**Testing**: pytest (unit + integración); validación de parseo CSV/XLSX, validación de balance y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: previsualización de archivo con hasta 5.000 asientos en <5 s; importación definitiva secuencial por asiento <2 s por asiento; exportación de 10.000 asientos en <10 s; respuesta de listado <200 ms p95 bajo 100 usuarios concurrentes.

**Constraints**: precisión decimal estricta en todas las sumas y conversiones; sin uso de `float`; re-validación antes de la importación definitiva; tamaño máximo de archivo configurable (default 10 MB); procesamiento secuencial por asiento para garantizar atomicidad.

**Scale/Scope**: 1.000+ empresas multi-tenant; archivos de hasta miles de asientos; operación puntual no concurrente (un usuario importa/exporta a la vez).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: la prevalidación y la re-validación antes de importar verifican `Sum(Debe) == Sum(Haber)` en `Decimal`; rechazo de asientos desbalanceados. → Cumple; se valida en backend, no en UI.
- **II. Inmutabilidad del diario**: la importación crea asientos nuevos; nunca modifica/borra asientos existentes. → Cumple.
- **III. Multi-tenancy estricto**: todas las operaciones (previsualización, importación, exportación) se filtran por `empresa_id` derivado de sesión; cuentas de otra empresa se reportan como no encontradas sin revelar su existencia. → Cumple.
- **IV. Numeración correlativa**: la importación definitiva asigna `numero_asiento` correlativo por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE` en secuencia bloqueada dentro de la misma transacción. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración verificando balance estricto y aislamiento multi-tenant. → Cumple.
- **Decimal/no float**: importes en `Decimal`/`NUMERIC(18,4)` en todo el flujo de importación y exportación; parseo de valores del archivo con `Decimal(str)`. → Cumple.
- **Auditoría inmutable**: la importación definitiva se registra en auditoría en la misma transacción ACID. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/005-import-export-asientos/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── api-contracts.md
│   └── file-layouts.md  # Plantillas CSV/XLSX de importación y exportación
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   └── acct/            # Entidades existentes de SPEC-002 (JournalEntry, JournalEntryLine)
    │   └── importexport/    # ResultadoImportacion, ErrorImportacion (si necesario)
    ├── services/
    │   └── importexport/    # parseador.py, validador.py, importador.py, exportador.py
    ├── api/
    │   └── importexport.py  # endpoints de importación/exportación
    └── config.py

backend/
└── tests/
    ├── unit/                # parseo CSV/XLSX, validación, Decimal
    ├── integration/         # flujo completo importación/exportación, aislamiento
    └── contract/            # firma de contratos de API

frontend/
└── src/
    ├── app/
    │   └── contabilidad/
    │       └── import-export/  # página de drag-and-drop + vista previa + confirmación
    └── components/
        │   └── importexport/   # uploader, preview-table, error-list
    └── services/
        └── client.ts          # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raíz: `backend/src/services/importexport/` con servicios puros de parseo, validación, importación y exportación; `frontend/src/app/contabilidad/import-export/` para la página de drag-and-drop y vista previa. No crea tablas nuevas; consume las entidades de SPEC-002 y SPEC-001.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de formato CSV/XLSX, estrategia de validación, manejo de Decimal en parseo, tamaño máximo de archivo, correlatividad bajo concurrencia.
- **data-model.md** (Phase 1): entidades resultantes (ResultadoImportacion, ErrorImportacion) y sus relaciones con entidades existentes.
- **contracts/** (Phase 1): contrato de API REST y plantillas de ficheros (CSV/XLSX importación y exportación).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.
