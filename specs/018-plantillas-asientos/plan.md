# Implementation Plan: Plantillas de Asientos

**Branch**: `018-plantillas-asientos` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/018-plantillas-asientos/spec.md`

## Summary

Módulo de **plantillas de asientos reutilizables** por empresa: el contador define un conjunto de apuntes predefinidos (cuenta, posición Debe/Haber) donde algunos importes son **fijos** y otros **variables** que se solicitan en la generación. El sistema **genera un asiento** de la empresa activa a partir de la plantilla, resolviendo las variables y **validando contra el motor de asientos** (SPEC-002): balance estricto Debe==Haber, ejercicio abierto, cuentas existentes en el plan (SPEC-001) y multiplicidad de líneas (SPEC-006). Los asientos generados son **inmutables** e independientes de ediciones posteriores de la plantilla (versiones/activación): la plantilla puede editarse, desactivarse o versionarse sin alterar los asientos ya generados. Se respeta la matriz de permisos (SPEC-015).

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Reutiliza el motor de asientos multilínea de SPEC-002/006 (models/services de `acct/`) y el plan de cuentas de SPEC-001.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integración); generación de asientos y verificación de balance/ejercicio/cuentas.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: generación de un asiento desde plantilla en <300 ms p95; listado de plantillas de una empresa <200 ms p95 bajo 100 usuarios concurrentes.

**Constraints**: importes siempre `Decimal`; sin fórmulas (solo fijos/variables numéricas); la plantilla sin balance con las variables no puede generar; cuentas validadas contra el plan antes de generar; ejercicio cerrado bloquea la generación.

**Scale/Scope**: 1.000+ empresas multi-tenant; hasta ~1.000 plantillas activas por empresa y cientos de generaciones/día.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: la generación resuelve las variables y delega la validación Debe==Haber al motor en el punto de persistencia; una plantilla que no cuadra no genera. → Cumple.
- **II. Inmutabilidad del diario**: el asiento generado es `POSTED` inmutable; editar/desactivar la plantilla no lo altera; las correcciones usan `REVERSAL`/`ADJUSTMENT`. → Cumple.
- **III. Multi-tenancy estricto**: plantillas y asientos generados llevan `empresa_id` en PK/índices, derivado de sesión; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: el asiento generado toma su número correlativo del motor (por empresa+ejercicio, secuencia bloqueada en la misma transacción). → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto de la generación y aislamiento multi-tenant de plantillas/asientos). → Cumple.
- **Decimal/no float**: fijos/variables y asiento generado en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): creación/edición/activación de plantilla y cada generación de asiento se auditan. → Cumple.

Sin violaciones. La decisión de **resolución de variables en el servicio (no en el motor)** y de **versionado ligero (snapshot de plantilla + activación)** está justificada en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/018-plantillas-asientos/
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
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002)
    │   └── templates/       # plantilla.py, linea_plantilla.py, variable.py,
    │                        # asiento_generado.py
    ├── services/
    │   └── templates/       # crud_plantillas.py, generacion.py
    ├── api/
    │   └── templates/       # routers (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # resolución de variables, balance, versiones
    ├── integration/         # generación de asiento completa + multi-tenant
    └── contract/            # firma de contratos de API + aislamiento

frontend/
└── src/
    ├── app/
    │   └── plantillas/      # listado, creación/edición, activación, generación
    ├── components/templates/
    └── services/            # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web del `plan.md` raíz. La feature 018 aporta models/services/api `templates/` y llama al servicio de creación de asientos del motor (`journal_engine`, SPEC-002/006) para la generación, de modo que numeración, balance, ejercicio y auditoría sigan gobernados por el motor.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de variables, resolución/validación en el servicio, versionado, inmutabilidad del generado y activación.
- **data-model.md** (Phase 1): entidades `PlantillaAsiento`, `LineaPlantilla`, `VariablePlantilla`, `AsientoGenerado`.
- **contracts/** (Phase 1): contrato de API REST de plantillas y generación.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.