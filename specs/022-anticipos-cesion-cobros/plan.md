# Implementation Plan: Anticipos, Fondos a Cuenta y Cesión de Cobros

**Branch**: `022-anticipos-cesion-cobros` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/022-anticipos-cesion-cobros/spec.md`

## Summary

Módulo de **B2B y financiación** que gestiona: (1) **anticipos de clientes** (cuenta 438) y **anticipos a proveedores** (cuenta 407/408) con su liquidación posterior contra facturas (trazabilidad de aplicación), y (2) **cesión de cobros** (factoring/confirming) con registro de la cesión, comisión financiera y notificación al cliente, evitando el doble cobro de vencimientos cedidos.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

Dependencias directas: **SPEC-007** (facturación), **SPEC-011** (vencimientos), **SPEC-008** (terceros), **SPEC-021** (medios de pago para el desembolso inicial de anticipos).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). No dependencias externas adicionales.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integración); fixtures con `Decimal` para importes.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: liquidación de anticipo <500 ms; consulta de cesiones <200 ms p95.

**Constraints**: importes siempre con `Decimal`; asientos balanceados validados en backend; ejercicios cerrados rechazan operaciones; solo vencimientos pendientes pueden cederse.

**Scale/Scope**: 1.000+ empresas multi-tenant; cientos de anticipos y cesiones por empresa y ejercicio.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: todo asiento (anticipo, liquidación, cesión, comisión) debe cuadrar Debe==Haber en backend. → Cumple; se valida en servicio, no en UI.
- **II. Inmutabilidad del diario**: los asientos de anticipo y cesión se crean como POSTED; no se modifican. Las correcciones usan REVERSAL/ADJUSTMENT. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (anticipos, liquidaciones, cesiones) incluyen `empresa_id` en PK/índices/filtros derivado de sesión. → Cumple.
- **IV. Numeración correlativa**: si aplica numeración de cesión, se asigna por empresa+ejercicio de forma atómica. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: importes en `Decimal`/`NUMERIC(18,4)` en todo el flujo. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): anticipos, liquidaciones y cesiones se auditan. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/022-anticipos-cesion-cobros/
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
    │   ├── ar/              # Terceros, vencimientos (SPEC-008/011)
    │   └── treasury/        # anticipo.py, liquidacion_anticipo.py, cesion.py, notificacion_cesion.py
    ├── services/
    │   └── treasury/        # anticipo.py, liquidacion.py, cesion.py
    ├── api/                 # endpoints (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # anticipos, liquidaciones, cesiones
    ├── integration/         # flujos completos B2B
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   ├── anticipos/       # registro, liquidación, listado
    │   └── cesiones/        # factoring/confirming, notificaciones
    └── services/            # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de cuentas 438/407/408, liquidación de anticipos, cesión factoring, comisión y notificación.
- **data-model.md** (Phase 1): entidades `Anticipo`, `LiquidacionAnticipo`, `CesionCobro`, `NotificacionCesion`.
- **contracts/** (Phase 1): contrato de API REST.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.
