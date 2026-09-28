# Implementation Plan: Previsión y Flujo de Caja

**Branch**: `027-prevision-tesoreria` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/027-prevision-tesoreria/spec.md`

## Summary

Módulo de **previsión de tesorería** que genera proyecciones de saldo y movimientos futuros a partir de vencimientos pendientes (SPEC-011), remesas cobradas (SPEC-020) y pagos recurrentes o cobros estimados insertados manualmente (T-01/FR-001). Proyecta el saldo acumulado y los movimientos por **día, semana o mes** (T-02/FR-002), genera **alertas de liquidez** cuando el saldo proyectado es negativo (T-03/FR-003) y produce un **informe EFE (Estado de Flujos de Efectivo)** consolidado por tipo de actividad (operativa, inversión, financiación) con cuadre `saldo_inicial + movimientos = saldo_final` (T-04/FR-004/FR-005). Vencimientos vencidos y cobrados/pagados se excluyen de la proyección futura (FR-006).

No hay integración bancaria externa; la fuente del saldo de tesorería proviene de la conciliación bancaria (SPEC-013) o del balance de cuentas 570/572 del motor (SPEC-002). No genera asientos nuevos. Se apoya en los movimientos proyectados con fechas estimadas, clasificados por tipo de actividad (operativa: grupos 6/7/tesorería; inversión: grupo 2; financiación: grupo 1/9).

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id` y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Consultas SQL con `SUM` en `NUMERIC` contra `Vencimiento` (SPEC-011), `ReciboRemesa` (SPEC-020) y `journal_entry_line` (SPEC-002) para clasificación del EFE.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integración); verificación de proyección, cuadre EFE, alertas de liquidez y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: proyección de 1.000 vencimientos pendientes en <3 s; generación EFE del ejercicio completo en <5 s; alertas de liquidez en tiempo real al consultar la previsión.

**Constraints**: importes en `Decimal`/`NUMERIC(18,4)`; vencimientos sin fecha de cobro/pago real se excluyen salvo que el usuario indique fecha estimada (US1); saldo exactamente cero se muestra como límite de solvencia sin alerta; EFE debe cuadrar (apertura + movimientos = cierre); datos sensibles sin exposición cruzada.

**Scale/Scope**: 1.000+ empresas multi-tenant; previsión de hasta miles de movimientos por empresa; EFE mensual o anual; alertas en tiempo real.

**Unknowns / NEEDS CLARIFICATION** (resueltas en research.md): algoritmo de proyección (día/semana/mes), clasificación de las cuentas por tipo de actividad, obtención del saldo inicial, tratamiento de pagos recurrentes y cobros estimados, mecanismo de alerta y cuadre del EFE con la conciliación bancaria.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: la feature no genera asientos; el EFE se construye a partir de movimientos ya balanceados del diario (SPEC-002). El cuadre del EFE (`inicial + movimientos = final`) es aritmético (Decimal) y se verifica en el backend. La prueba de consistencia verifica que los totales de movimientos del EFE respetan el balance subyacente del diario. → Cumple.
- **II. Inmutabilidad del diario**: no se modifican asientos; los movimientos proyectados son lecturas de vencimientos y pagos recurrentes, sin persistencia como asientos (constitución II). → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (previsiones, movimientos, alertas, EFE) incluyen `empresa_id` en PK/índices/filtros derivado de sesión; `empresa_id` nunca del body/path. → Cumple.
- **IV. Numeración correlativa**: `numero_prevision` correlativo por empresa, asignado atómicamente en la misma transacción (secuencia bloqueada), sin saltos. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (consistencia de EFE y aislamiento multi-tenant) en cada user story. → Cumple.
- **Decimal/no float**: importes proyectados, totales EFE y alertas en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): generación de previsiones, alertas y cierres EFE se auditan. → Cumple.

Sin violaciones. El algoritmo de proyección, la clasificación EFE y el cuadre se justifican en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/027-prevision-tesoreria/
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
    │   ├── acct/            # journal_entry_line (SPEC-002) — solo lectura
    │   ├── ar/              # vencimiento, recibo_remesa (SPEC-011/020) — fuente de movimientos
    │   └── treasury/        # prevision.py, movimiento_prevision.py, alerta_liquidez.py,
    │                        # efe.py (InformeEFE + LineaEFE)
    ├── services/
    │   └── cashflow/        # proyeccion.py, efe.py, alertas.py, clasificacion_actividad.py
    ├── api/
    │   └── tesoreria.py     # endpoints (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # proyección, clasificación, cuadre EFE, alertas
    ├── integration/         # escenarios completos con vencimientos, EFE, multi-tenant
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   ├── tesoreria/           # previsión: listado y detalle
    │   ├── tesoreria/efe/       # informe EFE del ejercicio
    │   └── tesoreria/alertas/   # alertas de liquidez
    ├── components/
    │   └── cashflow/            # widgets de proyección y EFE
    └── services/                # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

**Structure Decision**: se adopta la estructura web del `plan.md` raíz. La feature aporta el módulo `treasury/` (models) y `cashflow/` (services) reutilizando las entidades de `ar/` (vencimientos, remesas) y `acct/` (diario) en modo lectura. El EFE se construye como vista materializable en la tabla `InformeEFE`+`LineaEFE` (snapshot histórico).

## Complexity Tracking

No aplica (sin violaciones de constitución). El algoritmo de proyección, la clasificación de actividades y el cuadre EFE se documentan en `research.md` D1-D6.

## Design Artifacts

- **research.md** (Phase 0): decisiones sobre algoritmo de proyección, saldo inicial, pagos recurrentes/cobros estimados, clasificación EFE por tipo de actividad, cuadre con conciliación y mecanismo de alerta.
- **data-model.md** (Phase 1): entidades `PrevisionTesoreria`, `MovimientoPrevision`, `AlertaLiquidez`, `InformeEFE`, `LineaEFE` y su relación con vencimientos y diario.
- **contracts/** (Phase 1): contrato de API REST (previsión, EFE, alertas).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.