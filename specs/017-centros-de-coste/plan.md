# Implementation Plan: Centros de Coste

**Branch**: `017-centros-de-coste` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/017-centros-de-coste/spec.md`

## Summary

Módulo de control de gestión que permite al contador definir **centros de coste** (departamentos, proyectos, subvenciones, delegaciones) organizados en **jerarquía** y exclusivos de la empresa activa, **imputar apuntes** (líneas de asiento) a un centro, y generar **informes de costes** por centro y período con subtotales por jerarquía y precisión decimal exacta. La imputación se integra en el motor de asientos multilínea (SPEC-002/006) como dimensión opcional de línea, sin romper el balance Debe==Haber, y respeta la inmutabilidad del diario: la reasignación sobre asientos posteados solo es posible vía asiento de rectificación.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Reutiliza el motor de asientos multilínea de SPEC-002/006 (modelos de `acct/`) para la dimensión de centro en las líneas.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)` para importes de informes).

**Testing**: pytest (unit + integración); agregaciones de informes con precision decimal exacta contra fixtures.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: informe de costes de un ejercicio con subtotales por jerarquía en <1 s para hasta 50.000 líneas imputadas; listado de centros <200 ms p95 bajo 100 usuarios concurrentes.

**Constraints**: importes siempre `Decimal`; la imputación nunca altera Debe/Haber de la línea; deletes físicos prohibidos sobre centros con imputaciones; `empresa_id` siempre del contexto de sesión, nunca del cliente.

**Scale/Scope**: 1.000+ empresas multi-tenant; hasta ~10.000 centros y ~100.000 imputaciones por empresa y ejercicio.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: la imputación es una dimensión de metadatos de la línea; el balance del asiento se valida en backend (SPEC-002) y la imputación no modifica Debe/Haber. → Cumple.
- **II. Inmutabilidad del diario**: no hay edición de líneas posteadas; reasignar un centro exige asiento de rectificación enlazado. → Cumple.
- **III. Multi-tenancy estricto**: centros e imputaciones llevan `empresa_id` en PK/índices, derivado de sesión; la imputación validada contra la empresa activa; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: no aplica nuevos documentos numerados; los asientos rectificativos usan la numeración del motor (SPEC-002). → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto tras imputar y aislamiento multi-tenant de centros e informes). → Cumple.
- **Decimal/no float**: importes de informe con `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): alta/inactivación de centros, reasignación vía rectificación e informes se auditan. → Cumple.

Sin violaciones. La decisión de usar **tabla de cierre (closure table)** para la jerarquía y de impedir el borrado físico (inactivación) está justificada en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/017-centros-de-coste/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002); líneas asentadas
    │   └── costcenters/     # centro_coste.py, imputacion.py, jerarquia.py (closure)
    ├── services/
    │   └── costcenters/     # crud_centros.py, imputacion.py, informes.py
    ├── api/
    │   └── costcenters/     # routers (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # jerarquía, imputación, agregación de informes
    ├── integration/         # imputación con balance, informes cross-jerarquía
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   ├── centros/         # árbol de centros, alta/edición, inactivación
    │   └── informes/costes/ # informe por centro y período
    ├── components/costcenters/
    └── services/            # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web del `plan.md` raíz. La feature 017 aporta models/services/api `costcenters/` y añade el campo de dimensión de centro a las líneas del motor multilínea (SPEC-006) mediante una columna opcional en el modelo `JournalEntryLine` de `acct/`, preservando que el motor de asientos siga siendo el único responsable de crear líneas.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de jerarquía (closure table), dimensión de línea, vínculo con subvenciones (SPEC-019), ciclo de vida e informes.
- **data-model.md** (Phase 1): entidades `CentroCoste`, `JerarquiaCentro` (closure) e `ImputacionCentro` (extensión de línea).
- **contracts/** (Phase 1): contrato de API REST de centros, imputaciones e informes.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.