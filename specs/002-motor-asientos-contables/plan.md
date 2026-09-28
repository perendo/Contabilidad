# Implementation Plan: Motor de Asientos Contables

**Branch**: `002-motor-asientos-contables` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-motor-asientos-contables/spec.md`

## Summary

Motor de asientos contables conforme a la constitución: cabecera (`JournalEntry`) + línea (`JournalEntryLine`) con **partida doble estricta** (Debe == Haber en precisión decimal), persistidas de forma **indivisible** (`async with async_session.begin()`); **numeración correlativa sin saltos por (empresa, ejercicio)** asignada atómicamente sobre secuencia bloqueada (`SELECT ... FOR UPDATE`); **inmutabilidad de asientos `POSTED`** a nivel DB (triggers) y corrección exclusiva mediante asiento **`REVERSAL`**/rectificativo enlazado al original; libro diario paginado por fechas; auditoría automática en la misma transacción ACID.

Cada asiento referencia exclusivamente cuentas **apuntables y activas de la misma empresa** (integración con el plan de cuentas de SPEC-001: FK compuesta de empresa + trigger `chk_journal_line_account_selectable` del plan raíz §5.d). El ejercicio fiscal se deriva de la fecha del asiento; los ejercicios cerrados (SPEC-004) rechazan escrituras con HTTP 400.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias (balance estricto + aislamiento multi-tenant).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Aritmética decimal con `Decimal` (contexto de alta precisión); sin `float`.

**Storage**: PostgreSQL 16+ (tablas `journal_entry`, `journal_entry_line` multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)` para importes; secuencia de numeración por (empresa, ejercicio)).

**Testing**: pytest (unit + integración); balance estricto, atomicidad, inmutabilidad, correlatividad bajo concurrencia y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: libro diario paginado < 200 ms p95 bajo 100 usuarios concurrentes; registro + asentado de asiento < 500 ms p95; asignación atómica de número sin bloqueos de secuencia en bóveda.

**Constraints**: < 200 ms p95 en listados; importes siempre `NUMERIC(18,4)`/`Decimal`; profundidad de precisión canónica a 4 decimales (redondeo decimal, nunca flotante); `POSTED` inmutables (API y DB); un asiento desbalanceado NUNCA persiste.

**Scale/Scope**: 1.000+ empresas multi-tenant; miles de asientos por empresa y ejercicio; paginación con offsets estándar; libro diario con filtro obligatorio de rango de fechas.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: validación en el servicio en el punto de persistencia (`async with async_session.begin()`) y refuerzo con trigger DB: todo asiento solo se acepta si `sum(Debe) == sum(Haber)` exacto (4 decimales); se exige al menos un apunte al Debe y uno al Haber; nunca validar solo en UI. → Cumple.
- **II. Inmutabilidad del diario**: asientos `POSTED`/`CANCELLED` PROHIBIDOS de `UPDATE`/`DELETE` a nivel de API y de base de datos (triggers); corrección solo vía `REVERSAL`/rectificativo enlazado (`reversal_of_id`) que deja el original `CANCELLED`; el original nunca se modifica. → Cumple.
- **III. Multi-tenancy estricto**: `empresa_id` en PK/índices/filtros/triggers de cabeceras, líneas y secuencia; FK compuestas `(empresa_id, account_id)` → `account_plan(tenant_id, id)`; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: `numero` correlativo por (empresa, ejercicio), asignado **en la misma transacción** que se asienta el asiento mediante secuencia bloqueada (`SELECT ... FOR UPDATE`); los números no emitidos (rollback) no se reutilizan; duplicados imposibles por `UNIQUE (empresa_id, ejercicio, numero)`. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto, inmutabilidad y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: todos los importes en `Decimal`/`NUMERIC(18,4)`; la validación de balance opera sobre la precisión canónica de 4 decimales; payload de auditoría con importes como cadenas Decimal. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): cada creación, asentado y anulación registra `audit_log` (actor, timestamp UTC, IP, action, payload) en la misma transacción que la operación; no puede omitirse. → Cumple.

Sin violaciones. La decisión de ciclo `borrador → asentado` con número solo al asentarse y el refuerzo del balance con trigger DB están justificados en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/002-motor-asientos-contables/
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
│   └── 003_journal.sql  # DDL journal_entry/journal_entry_line + triggers balance/inmutabilidad/FK selectable + índice secuencia
└── src/
    ├── models/
    │   └── acct/        # journal_entry.py, journal_entry_line.py
    ├── services/
    │   ├── journal/     # entry_service.py, journal_query.py, reversal.py, sequence.py
    │   └── audit/       # writer.py (payload Decimal strings, misma transacción)
    ├── api/
    │   ├── journal/journal.py   # endpoints /api/v1/journal/entries
    │   └── deps.py              # get_empresa_id() compartido (SPEC-001)
    └── config.py

backend/
└── tests/
    ├── unit/            # balance, inmutabilidad, correlatividad, reversal
    ├── integration/     # atomicidad, concurrencia, aislamiento multi-tenant
    └── contract/        # firma de contratos de API

frontend/
├── src/
│   ├── app/
│   │   ├── asientos/            # page.tsx (listado/diario), nuevo/page.tsx, [id]/page.tsx
│   │   └── cuentas/             # usa AccountAutocomplete (SPEC-001)
│   ├── components/
│   │   └── journal/             # JournalEntryForm.tsx (teclado), EntryLineTable.tsx
│   └── services/client.ts       # cliente HTTP con cabecera de empresa activa
└── tests/
```

**Structure Decision**: se adopta la estructura web del `plan.md` raíz; la feature 002 aporta el módulo `journal` (models/services/api) construido sobre los modelos y triggers de `acct` (SPEC-001) — el trigger `chk_journal_line_account_selectable` del plan raíz §5.d queda dentro del alcance de esta feature.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de modelado cabecera/líneas, patrón de numeración atómica, refuerzo DB del balance, estados/transiciones, REVERSAL, ejercicio cerrado, precisión decimal, libro diario paginado y auditoría.
- **data-model.md** (Phase 1): entidades `JournalEntry`, `JournalEntryLine` (+ referencia `fiscal_year`) con reglas y transiciones de estado.
- **contracts/** (Phase 1): contrato REST de asientos (crear/borrador, asentar, libro diario, detalle, anulación) con errores 401/403/404/409/422.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.