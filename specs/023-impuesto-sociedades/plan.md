# Implementation Plan: Impuesto sobre Sociedades (Modelo 200)

**Branch**: `023-impuesto-sociedades` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/023-impuesto-sociedades/spec.md`

## Summary

Módulo fiscal que calcula el **Impuesto sobre Sociedades** (IS) del ejercicio: toma el resultado contable del cierre (SPEC-004), permite aplicar **ajustes extracontables** (positivos/negativos) y **deducciones/bonificaciones**, calcula la **base imponible** y la **cuota íntegra** con el tipo impositivo configurado por empresa, descuenta los **pagos a cuenta** (cuenta 473) y determina la **cuota diferencial** (a pagar o adevolver). Genera el **asiento del impuesto** (630 contra 473/4752/4757) de forma balanceada y atómica, y exporta el **modelo 200** como soporte descargable para presentación ante la AEAT.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

Dependencias directas: **SPEC-002/004** (motor de asientos, cierre), **SPEC-010** (cuentas anuales), **SPEC-024** (retenciones del periodo para saldos a favor).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router); generación de modelo 200 como informe/descargable (sin integración AEAT telemática).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integración); fixtures con `Decimal` para importes y porcentajes.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: cálculo del IS para un ejercicio completo <5 s; generación del modelo 200 <2 s.

**Constraints**: tipo impositivo configurable por empresa (default 25%); ajustes extracontables manuales; cálculo provisional permitido en cierres intermedios; importes siempre con `Decimal`; presentación telemática fuera de alcance.

**Scale/Scope**: 1.000+ empresas multi-tenant; 1 cálculo por ejercicio por empresa (con posibilidad de recálculo provisional).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: el asiento del IS (630 contra 473/4752/4757) debe cuadrar Debe==Haber en backend. → Cumple; se valida en servicio.
- **II. Inmutabilidad del diario**: el asiento del IS se crea como POSTED; no se modifica. Si hay corrección, se crea REVERSAL/ADJUSTMENT. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (cálculo IS, ajustes, modelo 200) incluyen `empresa_id` en PK/índices/filtros derivado de sesión. → Cumple.
- **IV. Numeración correlativa**: si aplica número de modelo, se asigna por empresa+ejercicio de forma atómica. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: importes en `Decimal`/`NUMERIC(18,4)` y tipos impositivos en `NUMERIC(5,2)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): cálculo, asiento y modelo 200 se auditan. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/023-impuesto-sociedades/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── api-contracts.md
│   └── modelo-200.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002)
    │   └── fiscal/          # calculo_is.py, ajuste_extracontable.py, modelo_200.py
    ├── services/
    │   └── fiscal/          # impuesto_sociedades.py, modelo_200.py
    ├── api/                 # endpoints (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # cálculo IS, ajustes, modelo 200
    ├── integration/         # flujo completo IS con cierre
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   └── fiscal/
    │       ├── impuesto-sociedades/  # cálculo, ajustes, asiento
    │       └── modelo-200/           # exportación modelo 200
    └── services/            # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de cálculo IS, cuentas 630/473/4752, modelo 200, cierres intermedios.
- **data-model.md** (Phase 1): entidades `CalculoIS`, `AjusteExtracontable`, `PagoCuenta`, `Modelo200`.
- **contracts/** (Phase 1): contrato de API REST + layout del modelo 200.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.
