# Implementation Plan: Cierre Intermedio y Reapertura Controlada

**Branch**: `028-cierre-intermedio` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/028-cierre-intermedio/spec.md`

## Summary

Módulo de cierres que añade al cierre anual de SPEC-004 los **cierres intermedios** (mensuales/trimestrales) y la **reapertura controlada** de periodos cerrados sin romper la inmutabilidad del diario (constitución II). Los cierres intermedios son de control: calculan el **balance de comprobación del periodo** y el **resultado provisional** (PyG +, si procede, IS provisional de SPEC-023) en memoria, sin asentar en el diario ni mutar asientos publicados; el periodo queda bloqueado para nuevas contabilizaciones. El cierre anual completo (integrando SPEC-004/SPEC-009) genera los asientos de regularización y cierre (asentados e inmutables) y la apertura. La reapertura controlada exige justificación, permiso, un solo periodo a la vez y la publicación de un asiento de rectificación `REVERSAL`/`ADJUSTMENT` enlazado que preserva el original; el periodo se re-cierra tras el ajuste.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; Next.js (App Router). Dependencias directas de SPEC-002 (motor de asientos), SPEC-004 (informes y cierre), SPEC-009 (apertura), SPEC-010 (cuentas anuales), SPEC-023 (IS).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`). Snapshot de balanza en tabla inmutable; trigger DB que prohíbe UPDATE/DELETE sobre JournalEntry POSTED.

**Testing**: pytest (unit + integración + contract); tests de cuadre estricto (Sum Debe == Sum Haber), aislamiento multi-tenant, trigger inmutabilidad.

**Target Platform**: Linux server (backend API + worker), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: cierre intermedio de un mes (< 2 s); cierre anual completo (< 10 s para 50 k asientos); generación de balanza por periodo (< 200 ms p95 en listados).

**Constraints**: bloqueo atómico de periodo (ejercicio definido, asientos del periodo con fecha dentro de rango); trigger DB que impide INSERT de JournalEntry/Línea cuya fecha caiga en periodo cerrado; reglas de reapertura obligatorias; importes siempre con `Decimal`; snapshot inmutable.

**Scale/Scope**: 1.000+ empresas multi-tenant, ejercicios de decenas a cientos de miles de asientos, periodos mensuales y trimestrales.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: todo asiento generado (regularización, cierre, apertura, rectificación de reapertura) debe cuadrar Debe==Haber en backend, validado antes de persistir en la transacción atómica. → Cumple; el cierre intermedio NO crea asientos, solo calcula balanza; los asientos de cierre anual y de reapertura validan balance estricto.
- **II. Inmutabilidad del diario**: asientos POSTED (POSTED, REGULARIZACION, CIERRE, APERTURA, ADJUSTMENT, REVERSAL) son inmutables: UPDATE/DELETE prohibido vía trigger DB; la corrección solo se hace con un asiento nuevo. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (`PeriodoCerrado`, `BalanzaPeriodo`, `CierreEjercicio`, `SolicitudReapertura`) llevan `empresa_id` en PK/índices/filtros; empresa siempre derivada de la sesión autenticada; nunca del request body. → Cumple.
- **IV. Numeración correlativa**: `numero_solicitud` de reapertura correlativo por `(empresa_id, ejercicio)` asignado atómicamente en la misma transacción; cierre anual usa numeración de asientos de SPEC-002. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto + aislamiento multi-tenant) en cada user story. → Cumple.
- **Decimal/no float**: todos los importes de balanza, resultado provisional e asientos en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): cada cierre, reapertura y generación de asiento se audita con actor, timestamp UTC, IP, acción y payload. → Cumple.

Sin violaciones. El diseño resuelve la tensión cierre intermedio vs. mutación del diario mediante snapshot de balanza sin asientos y restrictión de asientos de cierre al flujo anual.

## Project Structure

### Documentation (this feature)

```text
specs/028-cierre-intermedio/
├── plan.md                 # Este fichero
├── research.md             # Decisiones de diseño (Phase 0)
├── data-model.md           # Modelo de entidades (Phase 1)
├── quickstart.md           # Escenarios de validación (Phase 1)
├── contracts/              # Contratos de API y reglas de negocio (Phase 1)
│   └── api-contracts.md
└── tasks.md                # Checklist de implementación (Phase 2)
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── closing/            # Esta feature
    │   │   ├── __init__.py
    │   │   ├── periodo_cerrado.py
    │   │   ├── balanza_periodo.py
    │   │   ├── cierre_ejercicio.py
    │   │   └── solicitud_reapertura.py
    │   └── acct/               # Ampliación: tipo en JournalEntry + reverses_id
    │       └── asiento.py
    ├── services/
    │   └── closing/
    │       ├── __init__.py
    │       ├── periodo.py          # cerrar/validar/bloquear periodo
    │       ├── balanza.py          # calcular balanza de comprobación
    │       ├── reglas_cierre.py    # reglas: cierre anual, ejercicios, IS
    │       ├── cierre_anual.py     # regularización + cierre + bloqueo
    │       └── reapertura.py       # solicitud, aprobación, ejecución, re-cierre
    ├── api/
    │   ├── closing.py             # router endpoints cierres
    │   └── deps.py                # get_empresa_id() de sesión (ya existente)
    └── config.py

backend/
└── tests/
    ├── unit/
    │   ├── test_periodo_cerrado.py
    │   ├── test_balanza_cuadre.py
    │   ├── test_cierre_anual_balance.py
    │   ├── test_reapertura_reversal_balance.py
    │   └── test_reglas_reapertura.py
    ├── integration/
    │   ├── test_cierre_intermedio_flujo.py
    │   ├── test_cierre_anual_flujo.py
    │   ├── test_reapertura_flujo.py
    │   └── test_closing_tenant_isolation.py
    └── contract/
        └── test_closing_api_contracts.py

frontend/
└── src/
    ├── app/
    │   ├── cierres/
    │   │   ├── page.tsx                # listado de periodos y cierres
    │   │   ├── intermedio/
    │   │   │   └── page.tsx            # cerrar mes/trimestre
    │   │   ├── anual/
    │   │   │   └── page.tsx            # cierre anual
    │   │   ├── reaperturas/
    │   │   │   └── page.tsx            # solicitudes de reapertura
    │   │   └── [id]/
    │   │       └── page.tsx            # detalle de periodo/cierre
    │   └── components/
    │       └── closing/
    │           └── BalanzaTabla.tsx     # tabla de balanza de comprobación
    └── services/
        └── client.ts                   # ampliar métodos de cierre
```

**Structure Decision**: Módulo `closing/` dedicado bajo `models/` y `services/`; el router `api/closing.py` centraliza endpoints; la ampliación del modelo `JournalEntry` se hace en `models/acct/asiento.py` añadiendo tipos `REGULARIZACION`, `CIERRE`, `APERTURA`, `ADJUSTMENT`, `REVERSAL` y el campo `reverses_id`. Los servicios usan `async with async_session.begin()` y heredan la infraestructura de `deps.py` para `get_empresa_id()`.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): naturaleza del cierre intermedio vs. anual, representación de periodos, balance de comprobación como snapshot, reglas de reapertura, integración con SPEC-004/009/010/023.
- **data-model.md** (Phase 1): entidades `PeriodoCerrado`, `BalanzaPeriodo` + `BalanzaPeriodoLinea`, `CierreEjercicio`, `SolicitudReapertura` y ampliación de `JournalEntry`.
- **contracts/** (Phase 1): contrato API REST de cierres intermedios, anuales y reaperturas.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.
