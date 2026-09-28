# Implementation Plan: Catálogo Versionado del Plan de Cuentas (Vigencias Normativas)

**Branch**: `025-catalogo-versionado` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/025-catalogo-versionado/spec.md`

## Summary

Módulo que introduce **versionado normativo del plan de cuentas** (SPEC-001): cada empresa mantiene versiones del catálogo con vigencia por ejercicio (fecha inicio/fin) **sin solapes**, conservando las versiones anteriores intactas. Permite importar actualizaciones normativas (CSV/JSON) con altas, bajas y renombrados definiendo un **mapeo de cuentas entre versiones** (T-03), resolver cada asiento con la versión vigente en su fecha (**consulta histórica**, T-04/FR-003) y **reclasificar saldos** para la apertura del nuevo ejercicio (SPEC-009) cuadrando el balance (T-05/FR-005). La activación de una versión exige mapeos completos y vigencias sin solape (T-06/FR-004 y FR-006).

Los asientos ya contabilizados no se reescriben (constitución II): solo los saldos de apertura se reclasifican explícitamente mediante asientos nuevos balanceados. Se apoya en el `plan.md` raíz (PGC): la tabla `account_plan` con `tenant_id`/`empresa_id` en PK/índices y triggers de estructura, apuntabilidad y protección; aquí se añade la capa de versiones sin mutar la identidad histórica de las cuentas.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Importación normativa: parser CSV/JSON propio (biblioteca estándar `csv` / `json`) con esquema Pydantic v2 de validación.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`; triggers de vigencia sin solape y mapeos completos).

**Testing**: pytest (unit + integración); verificación de vigencias, resolución histórica, reclasificación de saldos (balance estricto) y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: resolución de la versión vigente de un asiento en <50 ms p95; importación de un catálogo normativo de hasta 5.000 cuentas en <10 s; reclasificación de apertura con cientos de cuentas en <5 s.

**Constraints**: vigencia SIN solapes por empresa (rechazo 409/422); toda cuenta suprimida con saldo ≠ 0 requiere mapeo explícito antes de activar; la activación bloquea mapeos incompletos; los asientos históricos se resuelven siempre con la versión vigente en su fecha; importes en `Decimal`/`NUMERIC(18,4)`.

**Scale/Scope**: 1.000+ empresas multi-tenant; decenas de versiones de catálogo por ejercicio; catálogos de miles de cuentas; importaciones normativas periódicas (cambios de PGC).

**Unknowns / NEEDS CLARIFICATION** (resueltas en research.md): estrategia de versionado (snapshot vs delta), algoritmo de resolución histórica, formato y semántica del fichero de importación, mecánica de reclasificación de saldos y cruce con SPEC-009, y asignación de número de versión.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: toda reclasificación de saldos genera asientos balanceados (Debe==Haber) verificados en backend al persistir. → Cumple; se valida en servicio, nunca solo en UI.
- **II. Inmutabilidad del diario**: ninguna operación reescribe asientos históricos; la activación de una versión y la reclasificación generan asientos nuevos (REVERSAL/ADJUSTMENT para correcciones); la cuenta histórica permanece visible en su contexto. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (versiones, catálogos, mapeos, reclasificaciones) incluyen `empresa_id` en PK/índices/filtros derivado de sesión; FK compuestas (empresa_id, parent) y pruebas de aislamiento. → Cumple.
- **IV. Numeración correlativa**: `numero_version` correlativo por empresa, asignado atómicamente en la misma transacción (secuencia bloqueada), sin saltos. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto y aislamiento multi-tenant) en cada user story. → Cumple.
- **Decimal/no float**: importes de saldos y reclasificaciones en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): alta de versiones, importaciones, activaciones y reclasificaciones se auditan con actor, UTC, IP y payload. → Cumple.

Sin violaciones. La estrategia de versionado (mixto base + deltas con estado), la resolución histórica y el formato de importación se justifican en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/025-catalogo-versionado/
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
    │   ├── acct/            # account_plan, asientos (SPEC-001/002) — NO se modifica
    │   └── catalog/         # catalogo_version.py, catalogo_cuenta.py,
    │                        # mapeo_cuenta.py, reclasificacion_saldo.py
    ├── services/
    │   └── catalog/         # registro_version.py, importacion_catalogo.py,
    │                        # resolucion_historica.py, reclasificacion_saldos.py
    ├── api/
    │   └── catalogo.py      # endpoints (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # modelos, vigencias, mapeos, resolucion, reclasificacion
    ├── integration/         # importacion, activacion, apertura reclasificada, multi-tenant
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   ├── catalogo/        # listado de versiones, detalle
    │   ├── catalogo/[id]/   # detalle de versión, cuenta vigente en fecha
    │   ├── catalogo/importar/  # importación de normativa con mapeo
    │   └── catalogo/reclasificar/ # revisión y confirmación de reclasificación
    ├── components/
    │   └── catalog/         # widgets de versión y mapeo
    └── services/            # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

**Structure Decision**: se adopta la estructura web del `plan.md` raíz. La capa de versiones (`catalog/`) es aditiva sobre `acct/account_plan`; no se altera la tabla canónica de cuentas ni sus triggers. La feature aporta `services/catalog` (registro, importación, resolución y reclasificación) reutilizando el motor de asientos de SPEC-002 para la reclasificación.

## Complexity Tracking

No aplica (sin violaciones de constitución). La complejidad funcional (delta de versionado histórico frente a modelo de mirrors) se documenta en `research.md` D1/D2.

## Design Artifacts

- **research.md** (Phase 0): decisiones de estrategia de versionado, resolución histórica, formato de importación, validación de mapeos/vigencias, reclasificación con SPEC-009 y numeración de versión.
- **data-model.md** (Phase 1): entidades `CatalogoVersion`, `CatalogoCuenta`, `MapeoCuenta`, `ReclasificacionSaldo` y su relación con `account_plan` y asientos.
- **contracts/** (Phase 1): contrato de API REST (versiones, importación, resolución y reclasificación).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.