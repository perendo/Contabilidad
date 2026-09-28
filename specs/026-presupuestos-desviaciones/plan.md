# Implementation Plan: Presupuestos y Desviaciones

**Branch**: `026-presupuestos-desviaciones` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/026-presupuestos-desviaciones/spec.md`

## Summary

Módulo de **control presupuestario**: el usuario define el presupuesto anual desglosado por **cuenta y centro de coste** (SPEC-017 opcional) y ejercicio (T-01/FR-001), el sistema calcula la **desviación** (absoluta y relativa) entre lo presupuestado y el gasto/ingreso real del motor de asientos (SPEC-002/007) (T-02/FR-002), genera **informes de desviación** por centro/cuenta con acumulación del periodo (T-03/FR-003) y **cierra el seguimiento** de un periodo dejando la desviación final registrada como trazable (T-04) y bloqueando la modificación de presupuestos cerrados (T-05/FR-004). Se rechazan duplicidades en la combinación cuenta-centro-ejercicio (FR-005) y las cuentas sin centro se siguen solo por cuenta (FR-006).

No genera asientos nuevos; consume los saldos del motor (SPEC-002) como informativo. Se apoya en `PeriodoSeguimiento` con numeración correlativa por (empresa, ejercicio) asignada atómicamente (constitución IV).

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id` y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Agregación de reales: consultas SQL con `SUM` en `NUMERIC` contra `journal_entry_line` (SPEC-002/007).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`; constraints de unicidad y cierre).

**Testing**: pytest (unit + integración); verificación del cálculo de desviaciones, bloqueo de presupuestos cerrados, duplicidades y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: guardado masivo de presupuestos (10.000 combinaciones) en <10 s; consulta de desviación por cuenta/centro <300 ms p95 con Deco meses; generación de informe de desviación <2 s por ejercicio.

**Constraints**: importes en `Decimal`/`NUMERIC(18,4)`; `real` se calcula con precisión decimal exacta contra el diario (nunca `float`); presupuesto modificable solo mientras el periodo de seguimiento esté abierto; rechazo de duplicidades en la combinación; cierre del periodo con snapshot trazable.

**Scale/Scope**: 1.000+ empresas multi-tenant; presupuestos de miles de combinaciones cuenta-centro por ejercicio; consultas mensuales/acumuladas sobre diarios de decenas de miles de apuntes.

**Unknowns / NEEDS CLARIFICATION** (resueltas en research.md): codificación del presupuesto (importe anual vs períodos), signo/naturaleza de la desviación (gastos/ingresos), granularidad del real (anual/acumulado parcial), manejo de cuentas sin presupuesto, y mecánica de cierre del periodo.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: la feature no genera asientos; el real se agrega del diario (SPEC-002) que ya valida Debe==Haber. La prueba de consistencia verifica que el real calculado por cuenta respeta el balance del diario de origen. → Cumple.
- **II. Inmutabilidad del diario**: no se modifica ningún asiento; los presupuestos cerrados son inmutables (rechazo de modificación post-cierre, FR-004). → Cumple; el cierre convierte el presupuesto y la desviación final en datos inmutables.
- **III. Multi-tenancy estricto**: todas las tablas (presupuesto, periodo, desviación snapshot) incluyen `empresa_id` en PK/índices/filtros derivado de sesión; pruebas de integración demuestran la imposibilidad de acceso cross-tenant. → Cumple.
- **IV. Numeración correlativa**: `numero_periodo` correlativo por (empresa_id, ejercicio), asignado atómicamente en la misma transacción (secuencia bloqueada). → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (consistencia de partida doble y aislamiento multi-tenant) en cada user story. → Cumple.
- **Decimal/no float**: presupuestos, reales y desviaciones en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): altas/modificaciones de presupuesto, cierres de periodo y consolidaciones se auditan. → Cumple.

Sin violaciones. La convención de signos de la desviación (gastos vs ingresos), el tratamiento de "sin presupuesto" y la mecánica de cierre se justifican en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/026-presupuestos-desviaciones/
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
    │   ├── acct/            # journal_entry_line, asientos (SPEC-002) — solo lectura
    │   └── budget/          # presupuesto.py, periodo_seguimiento.py, desviacion.py
    ├── services/
    │   └── budget/          # presupuesto_service.py, desviaciones.py,
    │                        # informe_desviacion.py, cierre_periodo.py
    ├── api/
    │   └── presupuestos.py  # endpoints (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # modelos, cálculo de desviaciones, cierre
    ├── integration/         # seguimiento completo, consolidación, multi-tenant
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   ├── presupuestos/        # definición y listado por ejercicio
    │   ├── presupuestos/seguimiento/  # comparación presupuesto vs real
    │   └── presupuestos/informes/     # informes de desviación acumulada
    ├── components/
    │   └── budget/             # widgets de presupuesto y desviación
    └── services/               # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

**Structure Decision**: se adopta la estructura web del `plan.md` raíz. La feature aporta el módulo `budget/` (models + services) y un router `presupuestos.py`; consume el diario de SPEC-002 en modo lectura con agregación `SUM` en `NUMERIC`. `CentroCoste` (SPEC-017) se referencia opcionalmente por FK compuesta multi-tenant.

## Complexity Tracking

No aplica (sin violaciones de constitución). La convención de signos de desviación y el tratamiento de cuentas sin presupuesto se documentan en `research.md` D2/D4.

## Design Artifacts

- **research.md** (Phase 0): decisiones de codificación del presupuesto, convención de signos de la desviación, granularidad del real, cuentas sin presupuesto y cierre de seguimiento.
- **data-model.md** (Phase 1): entidades `Presupuesto`, `PeriodoSeguimiento`, `Desviacion` (snapshot) y su relación con `journey_entry_line` y `CentroCoste`.
- **contracts/** (Phase 1): contrato de API REST (presupuesto, seguimiento, informes, cierre).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.