# Implementation Plan: Multi-Divisa

**Branch**: `016-multi-divisa` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/016-multi-divisa/spec.md`

## Summary

Módulo de monedas que fija la **moneda funcional por empresa**, admite operaciones en **divisas de trabajo** y gestiona **tipos de cambio por divisa y fecha con histórico inmutable** (una vez usados en asientos posteados no pueden modificarse). El motor de asientos (SPEC-002) se amplía para **registrar asientos en divisa**: cada línea conserva el importe en divisa y el equivalente en moneda funcional con el tipo de cambio de la fecha, manteniendo la **partida doble balanceada en ambas columnas** (Debe==Haber en divisa y en funcional). La conversión aplica una **regla de redondeo acordada a nivel de empresa** (half-even por defecto) que jamás desequilibra el asiento (el redondeo residual se imputa a una línea de redondeo). Al **cierre de un ejercicio/período**, el contador **valora los saldos en divisa pendientes** con el tipo de cierre y el sistema calcula y genera el **asiento de diferencias de cambio** (pérdidas o ganancias) balanceado y vinculado al cierre. La **consulta histórica** del tipo de cambio por fecha y divisa permite reproducir cualquier asiento, y el sistema **bloquea la modificación del tipo usado en asientos posteados** (inmutabilidad).

Se construye sobre el plan de cuentas de SPEC-001 (cuentas en divisa), el motor de asientos de SPEC-002, el cierre de SPEC-004 y las multilíneas de SPEC-006. La conciliación bancaria (SPEC-013) y los arqueos (SPEC-019) consumirán esta feature para cuentas en divisa.

**Stack**: FastAPI (async) + PostgreSQL 16+ + Next.js, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, inmutabilidad e pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Conversión monetaria propia con contexto `Decimal` (`ROUND_HALF_EVEN` por defecto, configurable por empresa).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)` para importes, `NUMERIC(18,8)` para tipos de cambio que se resuelven a 4 decimales en el equivalente); jornada y fechas como `DATE` (UTC para auditoría).

**Testing**: pytest (unit + integración); fixtures de tipos de cambio y asientos en divisa con cuadres esperados en ambas monedas.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: registro de asiento en divisa <200 ms p95 (una transacción); conversión de hasta 1.000 líneas <500 ms; valoración a cierre de saldos de divisa <2 s; consultas de histórico <200 ms p95.

**Constraints**: <200 ms p95 en listados; todo asiento en divisa cuadra en divisa y funcional (SC-001); tipos usados en posteados inmutables (SC-002); conversión según regla de redondeo acordada (SC-003); diferencias de cambio balanceadas (SC-004); aislamiento por empresa (SC-005).

**Scale/Scope**: 1.000+ empresas multi-tenant; 3-10 divisas de trabajo por empresa; tipos diarios; ejercicio de cierre con decenas a miles de saldos en divisa. Política de varias monedas funcionales por grupo y volumen de tipos por día: NEEDS CLARIFICATION — resuelto en `research.md` (D1/D3).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: los asientos en divisa se validan con Debe==Haber en **ambas** columnas (divisa y funcional), en backend junto a la persistencia (motor SPEC-002 ampliado); el redondeo nunca rompe el balance (línea de redondeo). → Cumple.
- **II. Inmutabilidad del diario**: los asientos posteados en divisa son inmutables; el tipo de cambio usado queda sellado (no se puede modificar al afectar a un posteado); correcciones vía asientos nuevos. → Cumple.
- **III. Multi-tenancy estricto**: monedas funcionales, divisas de trabajo, tipos de cambio y saldos en divisa se aíslan por `empresa_id` derivado de sesión; tipos y asientos de otra empresa → 404; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: la numeración de asientos la delega en SPEC-002 (secuencia bloqueada por empresa+ejercicio); la valoración a cierre no reabre el ejercicio. → Cumple (delegado).
- **V. Pruebas obligatorias**: pytest unit + integración (cuadre en doble moneda, redondeo, inmutabilidad del tipo, aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: importes en divisa y funcional en `NUMERIC(18,4)`; tipos de cambio en `NUMERIC(18,8)` usados en aritmética `Decimal`; prohibido `float`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): registro en divisa, sellado de tipos y valoraciones se auditan. → Cumple.

Sin violaciones. La regla de redondeo half-even, la línea de ajuste de redondeo y el sellado de tipos se justifican en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/016-multi-divisa/
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
    │   └── monedas/         # moneda.py, tipo_cambio.py, asiento_divisa.py,
    │                        # diferencia_cambio.py
    ├── services/
    │   └── forex/           # conversion.py (redondeo), tipos.py (histórico+sellado),
    │                        # asiento_divisa.py (registro doble moneda),
    │                        # valoracion.py (diferencias a cierre)
    ├── api/                 # forex.py (endpoints, ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # conversión, redondeo, cuadre doble moneda, valoración
    ├── integration/         # asiento divisa, sellado, valoración a cierre, aislamiento
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   └── divisas/         # tipos de cambio, asiento en divisa, valoración a cierre
    ├── components/forex/
    └── services/            # cliente HTTP con cabecera de empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raíz: `backend/` con modelos en `models/monedas/` y procesos en `services/forex/`; el registro del asiento en divisa **amplía el motor de SPEC-002** (tabla adjunta `AsientoDivisa` y líneas en divisa) sin alterar los asientos en moneda funcional existentes. `frontend/` con las páginas de divisas.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de moneda funcional/divisas de trabajo, tipos de cambio e histórico, conversión y redondeo, límites al balance en doble moneda, sellado de tipos, valoración a cierre y aislamiento.
- **data-model.md** (Phase 1): entidades `Moneda`, `TipoCambio`, `AsientoDivisa` (ampliación SPEC-002), `DiferenciaCambio`.
- **contracts/** (Phase 1): contrato de API REST (sin formatos externos; no aplica ficheros).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.