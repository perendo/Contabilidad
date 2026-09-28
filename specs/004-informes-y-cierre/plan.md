# Implementation Plan: Contabilidad Habitual, Informes y Cierre de Ejercicio

**Branch**: `004-informes-y-cierre` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-informes-y-cierre/spec.md`

## Summary

Contabilidad habitual y motor de informes: **Balance de Sumas y Saldos** (agregación por cuenta en el rango y nivel solicitados, Debe/Haber/saldo, siempre cuadra), **Libro Mayor** por subcuenta (movimientos cronológicos con saldo acumulado exacto), **ejercicios contables** (`fiscal_year`) con bloqueo `is_closed` que rechaza escrituras de asientos, **cierre de ejercicio atómico** (regularización de los grupos 6 y 7 + asiento de cierre + `is_closed = True`, todo en una transacción o nada) y **facturas emitidas/recibidas** con precisión monetaria exacta (base, IVA, total) y numeración correlativa por empresa.

Los informes se derivan de los asientos del motor SPEC-002 (solo `POSTED`/`CANCELLED` rectificados): el cuadre del Balance es consecuencia directa de la partida doble estricta. El cierre respeta la inmutabilidad (los asientos de regularización/cierre quedan asentados e inmunutables), la correlatividad (numeración por la secuencia de SPEC-002) y el multi-tenancy estricto.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id` y pruebas pytest obligatorias (cuadre, bloqueo de periodos y aislamiento).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Agregaciones SQL sobre `journal_entry_line` + `account_plan`; aritmética de saldos con `Decimal`.

**Storage**: PostgreSQL 16+ (tablas `fiscal_year`, `invoice` multi-tenant; informes **derivados sin tabla**; `NUMERIC(18,4)` para importes).

**Testing**: pytest (unit + integración); cuadre del Balance (Sum Debe == Sum Haber), bloqueo de ejercicios cerrados (HTTP 400), atomicidad del cierre, precisión decimal de facturas y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: Balance de Sumas y Saldos y Libro Mayor < 500 ms p95 para hasta 10.000 líneas por empresa y ejercicio; cierre de ejercicio < 2 s p95; validación de ejercicio cerrado < 50 ms por creación de asiento.

**Constraints**: < 500 ms p95 en informes; importes siempre `Decimal`/`NUMERIC(18,4)`; `is_closed` bloquea cualquier escritura en el rango (400); cierre atómico (regularización + cierre + bloqueo en una transacción); facturas sin `float`; niveles de agregación hasta el nivel del plan (si se pide más, se agrega al mayor disponible).

**Scale/Scope**: 1.000+ empresas multi-tenant; ejercicios por empresa; miles de facturas y asientos; informes por rango y nivel de plan.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: el Balance de Sumas y Saldos **debe cuadrar siempre** (Sum Debe == Sum Haber) porque se alimenta de asientos ya balanceados; los asientos generados por el cierre (regularización, cierre) se crean balanceados en la misma transacción; validado en backend cerca de la persistencia. → Cumple.
- **II. Inmutabilidad del diario**: los asientos de regularización y cierre se registran `POSTED` e inmunutables; ninguna escritura entra en ejercicios cerrados; el bloqueo `is_closed` se aplica en la misma transacción que los asientos de cierre (o ninguno). → Cumple.
- **III. Multi-tenancy estricto**: `empresa_id` en PK/índices/filtros de `fiscal_year` e `invoice` y en todas las agregaciones de informes; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: facturas con número correlativo por (empresa, ejercicio) asignado atómicamente (secuencia bloqueada, patrón SPEC-002); los asientos de cierre consumen la secuencia del diario. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (cuadre, bloqueo de periodos y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: `NUMERIC(18,4)`/`Decimal` en facturas (base/IVA/total), consolidaciones y saldos acumulados; payload de auditoría con importes como cadenas Decimal. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): creación de facturas, cierre de ejercicio y generación de asientos de cierre se auditan en la misma transacción; sin reapertura de ejercicios. → Cumple.

Sin violaciones. La convención de agregación por nivel de plan, el rechazo de fechas sin ejercicio y el alcance de la API de facturas (entidad + servicio, sin endpoints de gestión en esta feature) se justifican en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/004-informes-y-cierre/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   └── api-contracts.md
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├── migrations/
│   └── 005_fiscal_invoice.sql  # DDL fiscal_year + invoice + constraints (UNIQUE por empresa/ejercicio/numero, CHECK total=base+iva)
└── src/
    ├── models/
    │   ├── acct/        # fiscal_year.py
    │   └── ar/          # invoice.py
    ├── services/
    │   ├── reports/     # trial_balance.py, ledger.py, common.py (agregación por nivel de plan)
    │   ├── closing/     # close_year.py (regularización + cierre + bloqueo atómico)
    │   └── invoicing/   # invoice_service.py (precisión + numeración correlativa)
    ├── api/
    │   ├── reports/informes.py   # GET trial-balance, GET ledger
    │   ├── fiscal.py             # GET fiscal-years, POST fiscal-years/{year}/close
    │   └── deps.py               # get_empresa_id() compartido
    └── config.py

backend/
└── tests/
    ├── unit/            # agregación, saldo acumulado, precisión, numeración factura
    ├── integration/     # cuadre, cierre atómico, bloqueo de periodos, aislamiento
    └── contract/        # firma de contratos de API

frontend/
├── src/
│   ├── app/
│   │   ├── informes/
│   │   │   ├── sumas-saldos/    # page.tsx
│   │   │   └── mayor/           # page.tsx (por subcuenta)
│   │   └── cierre/              # page.tsx (cierre de ejercicio)
│   └── components/
│       └── reports/             # TrialBalanceTable.tsx, LedgerTable.tsx
└── tests/
```

**Structure Decision**: se adopta la estructura web del `plan.md` raíz; la feature 004 aporta los servicios de `reports/`, `closing/` e `invoicing/` sobre los modelos de `acct`/`ar`; los informes son servicios de lectura puros sobre el diario (SPEC-002).

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de agregación del Balance por nivel de plan, saldo acumulado del Mayor, ejercicios `is_closed`, atomicidad del cierre, asientos de regularización/cierre, precisión decimal, facturas con numeración correlativa y alcance de su API.
- **data-model.md** (Phase 1): entidades `fiscal_year` e `invoice` (informes derivados, sin tabla).
- **contracts/** (Phase 1): contrato REST de informes, ejercicios y cierre con errores 401/403/404/409/422.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.