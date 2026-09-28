# Implementation Plan: Retenciones IRPF y Modelos 111/115/190

**Branch**: `024-retenciones-irpf` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/024-retenciones-irpf/spec.md`

## Summary

Módulo fiscal que gestiona la **acumulación, liquidación y declaración de retenciones IRPF**: acumula las retenciones generadas en facturación (SPEC-007) y alquileres por trimestre, genera el **modelo 111** (trimestral) y **modelo 115** (arrendamientos), contabiliza la **liquidación trimestral** (asiento 4751 contra 572), y genera el **modelo 190** anual por perceptor con NIF obligatorio. La liquidación deja el periodo liquidado y el saldo de la cuenta 4751 a cero.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

Dependencias directas: **SPEC-007** (facturación y retenciones), **SPEC-008** (terceros/NIF), **SPEC-023** (IS para cruce de saldos con Hacienda).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router); generación de modelos 111/115/190 como informes/descargables (sin integración AEAT telemática).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integración); fixtures con `Decimal` para importes y tipos de retención.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: acumulación de retenciones trimestrales <2 s; generación del modelo 190 <3 s.

**Constraints**: tipos de retención configurables por empresa y régimen; rectificativas recalculan retención del periodo; NIF obligatorio para perceptores del 190; importes siempre con `Decimal`; presentación telemática fuera de alcance.

**Scale/Scope**: 1.000+ empresas multi-tenant; miles de retenciones por empresa y ejercicio.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: el asiento de liquidación (4751 contra 572) debe cuadrar Debe==Haber en backend. → Cumple; se valida en servicio.
- **II. Inmutabilidad del diario**: el asiento de liquidación se crea como POSTED; no se modifica. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (retenciones, liquidaciones, modelos) incluyen `empresa_id` en PK/índices/filtros derivado de sesión. → Cumple.
- **IV. Numeración correlativa**: si aplica número de liquidación, se asigna por empresa+ejercicio+trimestre de forma atómica. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: importes en `Decimal`/`NUMERIC(18,4)` y tipos de retención en `NUMERIC(5,2)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): acumulación, liquidación y modelos se auditan. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/024-retenciones-irpf/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── api-contracts.md
│   ├── modelo-111.md
│   ├── modelo-115.md
│   └── modelo-190.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002)
    │   ├── ar/              # Terceros, facturas (SPEC-008/007)
    │   └── fiscal/          # retencion.py, liquidacion_retenciones.py, modelo_111.py, modelo_115.py, modelo_190.py
    ├── services/
    │   └── fiscal/          # retenciones.py, liquidacion.py, modelo_111.py, modelo_115.py, modelo_190.py
    ├── api/                 # endpoints (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # acumulación, liquidación, modelos
    ├── integration/         # flujos completos trimestrales y anuales
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   └── fiscal/
    │       ├── retenciones/       # acumulación, consulta
    │       ├── liquidacion/       # liquidación trimestral
    │       └── modelos/           # 111, 115, 190
    └── services/            # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de acumulación, liquidación 4751, modelos 111/115/190, rectificativas, NIF.
- **data-model.md** (Phase 1): entidades `RetencionPeriodo`, `LiquidacionRetenciones`, `Modelo111`, `Modelo115`, `Modelo190`.
- **contracts/** (Phase 1): contrato de API REST + layout de modelos 111, 115 y 190.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.
