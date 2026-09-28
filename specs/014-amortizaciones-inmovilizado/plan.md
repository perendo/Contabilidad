# Implementation Plan: Amortizaciones del Inmovilizado

**Branch**: `014-amortizaciones-inmovilizado` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/014-amortizaciones-inmovilizado/spec.md`

## Summary

Módulo del inmovilizado que permite **dar de alta activos fijos** (cuentas 21x) con su coste amortizable, vida útil, método de amortización (**lineal** o **regresivo/degresivo**) y fechas, y calcula y valida el **plan de amortización** (nunca permite que lo amortizado acumulado supere el coste amortizable). El usuario o el proceso **genera los asientos periódicos de amortización** (cuota a **681** contra amortización acumulada **281** de la cuenta del activo) como asientos balanceados en el ejercicio abierto, **sin duplicados por activo y período** (un período ya amortizado se bloquea o se reabre con trazabilidad). El contador registra la **baja o venta** de un activo: el sistema calcula la amortización hasta la fecha de baja, el **valor neto contable** y genera el asiento de baja balanceado (bancos/caja, amortización acumulada 281 y pérdidas/ganancias 671/771).

Se construye sobre el motor de asientos de SPEC-002 (partida doble estricta, inmutabilidad con `REVERSAL`/`ADJUSTMENT`, numeración correlativa por empresa+ejercicio), el plan de cuentas de SPEC-001 (21x/281/681) y las reglas de cierre de SPEC-004 (generación restringida al ejercicio abierto). Correcciones de activos ya amortizados **recalculan el plan futuro sin reabrir asientos posteados** (constitución II).

**Stack**: FastAPI (async) + PostgreSQL 16+ + Next.js, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Aritmética de cuotas en `Decimal` (contexto de alta precisión ROUND_HALF_EVEN); sin librerías externas de amortización.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)` para importes y `NUMERIC(5,2)` para porcentajes).

**Testing**: pytest (unit + integración); fixtures de activos con planes esperados calculados a mano (tabla de prueba).

**Target Platform**: Linux server (backend API + worker para generación periódica), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: cálculo del plan de hasta 1.000 activos <2 s; generación de asientos del período para 1.000 activos <10 s (una transacción ACID); consulta de plan <200 ms p95.

**Constraints**: <200 ms p95 en listados; cuota acumulada <= coste amortizable en todo momento (FR-006); asientos siempre balanceados y sin duplicados por (activo, período) (FR-003); generación restringida al ejercicio abierto (SPEC-004); importes `Decimal` exactos (FR-007).

**Scale/Scope**: 1.000+ empresas multi-tenant; de decenas a miles de activos por empresa; planes mensuales o por días (prorrateo). Configuración de prorrateo (mensual/días) y política de cierres exactos: NEEDS CLARIFICATION — resuelto en `research.md` (D5).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: los asientos de amortización (681/281) y de baja (281 vs bancos/caja y 671/771) se crean con Debe==Haber validado en backend (motor SPEC-002). → Cumple.
- **II. Inmutabilidad del diario**: los asientos de amortización se generan como `POSTED` inmutables; la corrección de un activo recalculca el plan futuro sin reabrir asientos posteados; baja y revalorización usan asientos nuevos enlazados. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (activos, planes, generaciones, bajas) incluyen `empresa_id` en PK/índices/filtros derivado de sesión; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: la numeración de asientos la garantiza SPEC-002 (secuencia bloqueada por empresa+ejercicio); el activo no exige numeración propia. → Cumple (delegado al motor de asientos).
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto 681/281, no duplicados por período, cuota ≤ coste, aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: costes, cuotas, acumulados y valores netos en `Decimal`/`NUMERIC(18,4)`; porcentajes en `NUMERIC(5,2)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): alta, edición, generación, reapertura y baja de activos se auditan. → Cumple.

Sin violaciones. La elección de métodos (lineal/regresivo), el prorrateo y la reapertura de períodos están justificadas en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/014-amortizaciones-inmovilizado/
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
└── src/
    ├── models/
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002)
    │   └── inmovilizado/    # activo.py, plan_amortizacion.py,
    │                        # amortizacion_generada.py, baja_activo.py
    ├── services/
    │   └── inmovilizado/    # activo.py (alta/edición), plan.py (cálculo),
    │                        # generacion.py (asientos 681/281),
    │                        # baja.py (baja/venta)
    ├── api/                 # inmovilizado.py (endpoints, ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # cálculo de planes, cuota acumulada, balance, baja
    ├── integration/         # alta + plan, generación 681/281, baja, aislamiento
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   └── inmovilizado/    # alta activo, plan, generación del período, baja
    ├── components/inmovilizado/
    └── services/            # cliente HTTP con cabecera de empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raíz: `backend/` con separación models/services/api y dominio `inmovilizado/`; el motor de asientos (SPEC-002) se reutiliza como servicio base (`services/acct/`), nunca se duplica. `frontend/` con las páginas del inmovilizado.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de métodos de amortización, cálculo de cuotas, prorrateo, generación y reapertura de asientos, baja/venta y aislamiento.
- **data-model.md** (Phase 1): entidades `ActivoInmovilizado`, `PlanAmortizacion`, `AmortizacionGenerada`, `BajaActivo`.
- **contracts/** (Phase 1): contrato de API REST (sin formatos externos; no aplica ficheros).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.