# Implementation Plan: Medios de Pago y Efectos

**Branch**: `021-medios-pago-efectos` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/021-medios-pago-efectos/spec.md`

## Summary

Módulo de tesorería que gestiona **medios de pago y cobro** (cheques, pagarés, letras, TPV/tarjeta, transferencia) con su ciclo de vida completo: emisión/registro → vencimiento → cobro o impago. Cada operación genera un **asiento contable balanceado** (partida doble) según las cuentas del PGC: 431/401 para efectos, 572/570 para banco/caja, 626 para comisiones bancarias. El **impago** de efectos reabre el vencimiento del tercero (SPEC-011) con un asiento `REVERSAL` (inmutabilidad). Incluye la **cartera de efectos** como vista consolidada por medio, estado y vencimiento, y el **registro de comisiones** por cobro con TPV/transferencia.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

Dependencias directas: **SPEC-011** (vencimientos de clientes/proveedores), **SPEC-010** (cuentas anuales EFE), **SPEC-020** (domiciliaciones para verificar saldos de remesas), **SPEC-001/002** (plan de cuentas y motor de asientos).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). No dependencias externas adicionales.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integración); fixtures con `Decimal` para importes.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: consulta de cartera de efectos <200 ms p95 bajo 100 usuarios concurrentes; liquidación de efecto con asiento <500 ms.

**Constraints**: importes siempre con `Decimal`; asientos balanceados validados en backend; ejercicios cerrados rechazan operaciones (SPEC-002/004); comisiones editables solo antes de contabilizar.

**Scale/Scope**: 1.000+ empresas multi-tenant; miles de efectos por empresa y ejercicio.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: todo asiento (cobro, impago, comisión) debe cuadrar Debe==Haber en backend. → Cumple; se valida en servicio, no en UI.
- **II. Inmutabilidad del diario**: el impago genera un asiento `REVERSAL` nuevo enlazado; el asiento original del cobro no se toca. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (efectos, cobros, comisiones) incluyen `empresa_id` en PK/índices/filtros derivado de sesión; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: número correlativo por `empresa_id` + ejercicio para la secuencia de efectos si aplica; validación de unicidad. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: importes en `Decimal`/`NUMERIC(18,4)` en todo el flujo. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): efectos, cobros, impagos y comisiones se auditan. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/021-medios-pago-efectos/
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
    │   ├── ar/              # Terceros, vencimientos, cobros (SPEC-008/011)
    │   └── treasury/        # efecto.py, cobro_medio.py, comision.py
    ├── services/
    │   └── treasury/        # efecto.py, cobro_medio.py, cartera.py
    ├── api/                 # endpoints (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # efectos, comisiones, impagos
    ├── integration/         # liquidación de efectos, cobro TPV
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   ├── efectos/         # cartera, detalle, registro
    │   └── tesoreria/       # cobros por medio
    └── services/            # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raíz: `backend/` con separación models/services/api y módulo `treasury/` para efectos y cobros; `frontend/` con las páginas de cartera y tesorería. La feature 021 aporta modelos de efectos y comisiones reutilizando models de `ar/` y `acct/`.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de ciclo de vida de efectos, cuentas PGC, comisiones, impagos y cartera.
- **data-model.md** (Phase 1): entidades `Efecto`, `CobroMedio`, `ComisionBancaria`.
- **contracts/** (Phase 1): contrato de API REST.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.
