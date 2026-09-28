# Implementation Plan: Cuentas Anuales (Balance de Situación y Pérdidas y Ganancias)

**Branch**: `010-cuentas-anuales` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-cuentas-anuales/spec.md`

## Summary

Módulo de informes que formula las cuentas anuales de cada ejercicio: **Balance de Situación** (activo, pasivo, patrimonio neto con cuadre Activo == Pasivo + Patrimonio), **Cuenta de Pérdidas y Ganancias** (ingresos, gastos y resultado exacto que coincide con la regularización del cierre) y **Estado de Flujos de Efectivo (EFE)** por actividades (operativa, inversión, financiación) con cuadre de saldo inicial + movimientos = saldo final. Los informes se derivan de los saldos del plan de cuentas (SPEC-001) y de los asientos (SPEC-002). La **formulación oficial** está restringida a ejercicios cerrados y produce un documento inmutable y trazable.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integración); verificación de cuadres y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: generación de balance/PyG de un ejercicio con miles de asientos en <10 s (consultas agregadas); formulación oficial <1 s; consultas de estados <200 ms p95.

**Constraints**: cuadre estricto Activo == Pasivo + Patrimonio; resultado PyG idéntico al cierre (SPEC-004); EFE cuadra con variación de tesorería (grupo 5); formulación solo en ejercicios cerrados; importes siempre `Decimal`.

**Scale/Scope**: 1.000+ empresas multi-tenant; balance/PyG con decenas de masas patrimoniales por agrupación del plan.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: los informes se agregan desde asientos que ya cumplen Debe==Haber; el cuadre de balance es una verificación adicional en backend. → Cumple.
- **II. Inmutabilidad del diario**: la formulación oficial genera un documento inmutable; reformulaciones se registran con trazabilidad, nunca se muta lo formulado ni los asientos origen. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas y agregaciones incluyen `empresa_id` derivado de sesión. → Cumple.
- **IV. Numeración correlativa**: aplica al asignar número secuencial de formulación por (empresa, ejercicio); asignado atómicamente. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (cuadres y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: todos los saldos y agregaciones en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): formulaciones y reformulaciones se auditan. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/010-cuentas-anuales/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── api-contracts.md
│   └── informes-cuentas-anuales.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002)
    │   └── reporting/       # cuentas_anuales.py, balance.py, pyg.py, efe.py
    ├── services/
    │   ├── reporting/        # formulacion.py, agrupacion.py, efe.py
    │   └── journal/          # Servicio de asientos (SPEC-002)
    ├── api/
    │   └── cuentas_anuales.py # Endpoints de informes y formulación
    └── config.py

backend/
└── tests/
    ├── unit/                # cuadres, agrupación PGC, EFE
    ├── integration/         # formulación completa, reformulación, multi-tenant
    └── contract/            # firma de contratos de API

frontend/
└── src/
    ├── app/
    │   ├── cuentas-anuales/  # página principal de informes
    │   ├── balance/          # Balance de Situación
    │   ├── pyg/              # Pérdidas y Ganancias
    │   └── efe/              # Estado de Flujos de Efectivo
    └── components/
        └── reporting/        # componentes de informes
```

**Structure Decision**: Se crea el módulo `reporting/` para informes. La agrupación se deriva de la estructura del plan de cuentas (SPEC-001) con configuración por empresa. La formulación oficial se apoya en la inmutabilidad del ejercicio cerrado.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de agrupación PGC, cuadres, EFE, formulación/inmutabilidad.
- **data-model.md** (Phase 1): entidades `Balance`, `PyG`, `EFE`, `FormulacionCuentasAnuales`.
- **contracts/** (Phase 1): contrato de API REST y esquema de los informes (fichas de cuentas anuales).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.