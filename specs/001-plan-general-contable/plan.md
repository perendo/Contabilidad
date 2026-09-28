# Implementation Plan: Plan General Contable (PGC)

**Branch**: `001-plan-general-contable` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-plan-general-contable/spec.md`

## Summary

Módulo del Plan General Contable español: modelo de cuentas multi-tenant (`account_plan`), árbol jerárquico de hasta 5 niveles, búsqueda por autocompletar de cuentas apuntables, alta de subcuentas, edición de nombre/estado y protección de cuentas con asientos asociados. Toda consulta, búsqueda, alta y edición opera exclusivamente sobre la empresa activa de la sesión (constitución III).

El **plan.md raíz del repositorio** (`H:\ContabilidadV1\plan.md`) es el **plan técnico autoritativo** de SPEC-001: define la tabla `account_plan` (columna `tenant_id`, PK `(tenant_id, id)`, `UNIQUE (tenant_id, code)`, `UNIQUE (tenant_id, name)`), la jerarquía por longitud de código (nivel 1-4 = longitud; nivel 5 = 5 a 8 dígitos), los triggers de validación estructural, el mantenimiento automático de `is_selectable`, la protección de cuentas con imputaciones, el seeding `seed_default_pgc` automático por tenant y el `audit_log` inmutable (WORM). **Este plan.md no reescribe ese plan**: lo referencia como fuente de verdad y este artefacto (junto con `data-model.md`, `contracts/` y `tasks.md`) se alinea 1:1 con él (naming `tenant_id`, tabla `account_plan`, triggers).

Se construye sobre el stack fijado por la constitución y el plan raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto, asientos inmutables (protección de cuentas) y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Búsqueda por autocompletar: extensión `pg_trgm` de PostgreSQL (índice GIN sobre `name`) + `ILIKE` por prefijo de código.

**Storage**: PostgreSQL 16+ (tabla `account_plan` multi-tenant con `tenant_id` en PK/índices; `TIMESTAMPTZ` UTC; sin importes — el plan de cuentas no lleva importes).

**Testing**: pytest (unit + integración); aislamiento multi-tenant, jerarquía/apuntabilidad, triggers DB y seeding.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: autocompletar de sugerencias en **< 1 s** en condiciones normales de red (SC-002); árbol de cuentas completo devuelto en una sola consulta con N+1 nulo.

**Constraints**: < 1 s p95 en suggest; toda consulta filtra por `tenant_id` de sesión; sin `DELETE` físico en la API del plan; triggers DB para estructura/apuntabilidad/protección; `is_selectable = true` solo en hojas de nivel ≥ 4 (criterio del plan raíz §1.3 que concreta FR-005).

**Scale/Scope**: 1.000+ empresas multi-tenant; catálogo seed de 7 grupos + subcuentas de nivel 4; alta de auxiliares de 5-8 dígitos por empresa; profundidad máxima 5.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: esta feature no genera asientos, pero garantiza en el punto de persistencia (triggers del plan raíz §5.d y §5.a) que **solo cuentas `is_selectable = true` e `is_active = true` de la misma empresa pueden recibir apuntes**, pre-requisito del invariante de balance. → Cumple (habilitador).
- **II. Inmutabilidad del diario**: sin `DELETE` físico en la API del plan; trigger `chk_account_plan_protected` impide a nivel DB borrar o desactivar cuentas con imputaciones o con hijas. → Cumple.
- **III. Multi-tenancy estricto**: `tenant_id` en PK/índices/filtros/triggers de `account_plan` (FK compuesta a padre `(tenant_id, parent_id)`, FK a `companies(company_id)`); toda operación filtra por la empresa activa de sesión. Pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: no aplica secuencia numérica en esta feature (las cuentas usan **código único por empresa**, no número de asiento/factura); la correlatividad de asientos se cubre en SPEC-002. → No aplica (justificado).
- **V. Pruebas obligatorias**: pytest unit + integración (aislamiento multi-tenant y jerarquía/apuntabilidad). → Cumple.
- **Decimal/no float**: la tabla de cuentas no contiene importes; el `payload` JSONB de auditoría serializa cualquier importe como **cadena Decimal** (patrón heredado a SPEC-002). → Cumple.
- **Auditoría inmutable** (misma transacción ACID): `audit_log` WORM (root plan §5.e) registra seed (`SEED_PGC`), altas, ediciones y desactivaciones con actor, UTC, IP y payload en la misma transacción que la operación. → Cumple.

Sin violaciones, por tanto no procede Complexity Tracking. Decisiones de diseño justificadas en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/001-plan-general-contable/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   └── api-contracts.md
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

**Fuente técnica autoritativa**: [H:\ContabilidadV1\plan.md](../../plan.md) — DDL `account_plan`, triggers y seed. Se referencia desde data-model.md/contracts/tasks.

### Source Code (repository root)

```text
backend/
├── migrations/
│   ├── 000_audit_log.sql       # audit_log WORM (root plan §5.e)
│   ├── 001_account_plan.sql    # DDL + triggers estructura/apuntabilidad/protección + pg_trgm
│   └── 002_seed_pgc.sql        # seed_default_pgc + trigger trg_companies_seed
└── src/
    ├── models/
    │   └── acct/               # account_plan.py (modelo SQLAlchemy)
    ├── services/
    │   └── acct/               # plan_tree.py, suggest.py, account_service.py
    ├── api/
    │   ├── acct/accounts.py    # router GET tree / GET suggest / POST / PATCH
    │   └── deps.py             # get_empresa_id() contexto de sesión
    └── config.py

backend/
└── tests/
    ├── unit/                   # jerarquía, apuntabilidad, alta/edición, suggest
    ├── integration/            # aislamiento multi-tenant, triggers DB, seeding
    └── contract/               # firma de contratos de API

frontend/
├── src/
│   ├── app/
│   │   ├── cuentas/            # page.tsx (árbol), nueva/page.tsx (alta)
│   │   └── asientos/           # consume AccountAutocomplete (SPEC-002)
│   ├── components/
│   │   └── acct/               # PlanTree.tsx, AccountAutocomplete.tsx, AccountEdit.tsx
│   └── services/client.ts      # cliente HTTP con cabecera de empresa activa
└── tests/
```

**Structure Decision**: se adopta la estructura web del `plan.md` raíz (`backend/` con models/services/api, `frontend/` con páginas); la feature 001 aporta el módulo `acct` (models/services/api) que será consumido por el motor de asientos (SPEC-002).

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de jerarquía por longitud de código, regla de apuntabilidad, seeding por trigger, triggers DB, búsqueda pg_trgm y recuperación del árbol.
- **data-model.md** (Phase 1): entidad `account_plan` (alineada con el plan raíz) + dependencias (`companies`, `journal_entry_line`, `audit_log`).
- **contracts/** (Phase 1): contrato REST de cuentas (árbol, suggest, alta, edición) con errores 401/403/404/409/422.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables (seeding, árbol, suggest, alta, edición, protección, aislamiento).