# Implementation Plan: Vencimientos, Cobros y Pagos

**Branch**: `011-cobros-y-pagos` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-cobros-y-pagos/spec.md`

## Summary

Modulo de tesoreria que gestiona los **vencimientos** (fechas/importes de cobro y pago de facturas de SPEC-007) y las operaciones de **cobro/pago** (totales y parciales) de cada empresa. Cada cobro/pago genera su asiento contable vinculado (banco/caja contra deuda del tercero, SPEC-002) de forma balanceada y atomica, actualiza el saldo pendiente y cierra el vencimiento cuando el acumulado lo iguala. Incluye la **agrupacion de vencimientos en remesas de cobro/pago** con estado y trazabilidad (la generacion de ficheros SEPA/CSB 19.19 se cubre en SPEC-020) y el **informe de antiguedad de saldos** por tercero (rangos 30/60/90+ dias). Toda la gestion se bloquea en ejercicios cerrados.

Se construye sobre el stack fijado por la constitucion y el `plan.md` raiz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precision `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/indices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integracion); verificacion de balances de asientos de cobro/pago y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raiz PGC de ContabilidadV1.

**Performance Goals**: registro de cobro/pago <300 ms p95; informe de antiguedad para 10.000 vencimientos en <5 s; listados paginados <200 ms p95.

**Constraints**: parciales nunca superan el importe del vencimiento; asientos de cobro/pago balanceados (Debe==Haber); gestion rechazada en ejercicios cerrados (409); importes siempre `Decimal`.

**Scale/Scope**: 1.000+ empresas multi-tenant; decenas de miles de vencimientos activos por empresa.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: todo asiento de cobro/pago debe cuadrar Debe==Haber; se valida en servicio, nunca en UI. → Cumple.
- **II. Inmutabilidad del diario**: un cobro/pago asentado se corrige con REVERSAL/ADJUSTMENT enlazado; nunca UPDATE/DELETE sobre el asiento POSTED. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (vencimientos, cobros/pagos, remesas, antiguedad) incluyen `empresa_id` en PK/indices/filtros derivado de sesion. → Cumple.
- **IV. Numeracion correlativa**: numero de vencimiento/operacion por (empresa, ejercicio) asignado atomicamente en la misma transaccion. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integracion (balance estricto y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: todos los importes en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoria inmutable** (misma transaccion ACID): cobros, parciales, remesas y cambios de estado se auditan. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/011-cobros-y-pagos/
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
    │   ├── ar/             # Terceros, facturacion (SPEC-008/007)
    │   └── treasury/       # vencimiento.py, cobro_pago.py, remesa.py
    ├── services/
    │   ├── treasury/       # vencimientos.py, cobros_pagos.py,
    │   │                   # remesas.py, antiguedad.py
    │   └── journal/        # Servicio de asientos (SPEC-002)
    ├── api/
    │   ├── vencimientos.py # Endpoints de vencimientos
    │   ├── cobros.py       # Endpoints de cobros/pagos
    │   ├── remesas.py      # Endpoints de remesas (agrupacion/estado)
    │   └── antiguedad.py   # Informe de antiguedad
    └── config.py

backend/
└── tests/
    ├── unit/                # parciales, balances, antiguedad
    ├── integration/         # cobros completos, remesas, multi-tenant
    └── contract/            # firma de contratos de API

frontend/
└── src/
    ├── app/
    │   ├── vencimientos/    # listado y detalle de vencimientos
    │   ├── cobros/          # registro de cobros/pagos
    │   ├── remesas/         # agrupacion y estado de remesas
    │   └── antiguedad/      # informe de antiguedad de saldos
    └── components/
        └── treasury/        # componentes de tesoreria
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raiz. Los models de vencimientos/recebros se ubican en `ar/` heredando facturacion (SPEC-007); las remesas y antiguedad se apoyan en `treasury/`. La feature 011 aporta `services/treasury` (vencimientos, cobros/pagos, remesas de agrupacion, antiguedad) reutilizando el motor de asientos de `journal/` (SPEC-002). La generacion de ficheros SEPA/CSB queda fuera del alcance (SPEC-020).

## Complexity Tracking

No aplica (sin violaciones de constitucion).

## Design Artifacts

- **research.md** (Phase 0): decisiones de estados de vencimiento, asientos de cobro/pago, parciales, remesas y antiguedad.
- **data-model.md** (Phase 1): entidades `Vencimiento`, `CobroPago`, `RemesaCobro` (agrupacion), informe de antiguedad.
- **contracts/** (Phase 1): contrato de API REST de vencimientos, cobros/pagos, remesas y antiguedad.
- **quickstart.md** (Phase 1): escenarios de validacion ejecutables.