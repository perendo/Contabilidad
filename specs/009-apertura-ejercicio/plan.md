# Implementation Plan: Apertura del Ejercicio

**Branch**: `009-apertura-ejercicio` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-apertura-ejercicio/spec.md`

## Summary

Módulo de ciclo contable que genera el asiento de apertura del ejercicio siguiente al cierre (SPEC-004). El sistema toma los saldos de las cuentas patrimoniales del cierre anterior, genera un asiento de apertura balanceado en el nuevo ejercicio y reinicia la numeración desde 1. Soporta anulación y regeneración de la apertura mediante asiento rectificativo, sin alterar el ejercicio cerrado anterior.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integración); verificación de balance y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: generación del asiento de apertura con cientos de cuentas patrimoniales en <5 s; respuesta de consulta de estado de apertura <200 ms p95.

**Constraints**: transacción ACID atómica (asiento + líneas); numeración correlativa por (empresa, ejercicio) sin saltos; ejercicio anterior debe estar cerrado; imports siempre `Decimal`.

**Scale/Scope**: 1.000+ empresas multi-tenant; un asiento de apertura por ejercicio y empresa con decenas a cientos de líneas.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: el asiento de apertura se genera con Debe==Haber verificado en backend antes de persistir. → Cumple; se valida en servicio.
- **II. Inmutabilidad del diario**: la anulación de una apertura genera un asiento `REVERSAL`/`ADJUSTMENT` nuevo enlazado; el asiento original de apertura no se modifica ni borra. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (ejercicios, asientos, líneas) incluyen `empresa_id` en PK/índices/filtros derivado de sesión. → Cumple.
- **IV. Numeración correlativa**: número de asiento asignado atómicamente por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE`. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: importes en `Decimal`/`NUMERIC(18,4)` en el asiento y líneas de apertura. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): la apertura y su posible anulación se auditan. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/009-apertura-ejercicio/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api-contracts.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002)
    │   └── fiscal/          # Ejercicio contable (ejercicio.py)
    ├── services/
    │   ├── cycle/            # apertura.py, validacion_previa.py
    │   └── journal/          # Servicio de asientos (SPEC-002)
    ├── api/
    │   └── apertura.py       # Endpoints de apertura
    └── config.py

backend/
└── tests/
    ├── unit/                # generación de apertura, validaciones
    ├── integration/         # apertura completa, anulación, multi-tenant
    └── contract/            # firma de contratos de API

frontend/
└── src/
    ├── app/
    │   └── apertura/        # página de apertura del ejercicio
    └── components/
        └── cycle/           # componentes de ciclo contable
```

**Structure Decision**: Se reutiliza la estructura de modelos de `acct/` y `fiscal/` existente. El servicio de apertura se ubica en `services/cycle/` como parte del ciclo contable. El endpoint se registra bajo el prefijo `/api/v1/...` con dependencia de sesión.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones sobre mecánica de apertura, cálculo de saldos patrimoniales, generación de asiento, regeneración, correlatividad.
- **data-model.md** (Phase 1): entidades `EjercicioContable`, `JournalEntry` (extensión del dominio de apertura), relación con saldos del cierre.
- **contracts/** (Phase 1): contrato de API REST para apertura/regeneración.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.
