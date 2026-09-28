# Implementation Plan: Asientos Contables Multilínea

**Branch**: `006-asientos-multilinea` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-asientos-multilinea/spec.md`

## Summary

Ampliación del motor de asientos (SPEC-002) para soportar asientos con N partidas al Debe y M partidas al Haber sin límite fijo por lado. Incluye: validación estricta de balance multilínea con `Decimal`, regla de los dos lados (al menos una partida por lado), anulación/rectificativo con todas las líneas invertidas, integración con importación/exportación masiva (SPEC-005) para que los archivos conserven todas las líneas, y entrada contable por teclado con filas dinámicas en el frontend.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). No se añaden dependencias nuevas; se amplía el motor de asientos existente.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`). No crea tablas nuevas; amplía las validaciones sobre `JournalEntry` y `JournalEntryLine` existentes.

**Testing**: pytest (unit + integración); validación de balance multilínea, rechazo de lado vacío, anulación invertida.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: validación de balance de hasta 50 líneas en <100 ms; persistencia de asiento multilínea en <200 ms; respuesta de listado <200 ms p95.

**Constraints**: precisión decimal estricta en todas las sumas de múltiples líneas; sin límite fijo de dominio por lado (límite práctico configurable, default 100 líneas); la suma se calcula en precisión decimal canónica.

**Scale/Scope**: 1.000+ empresas multi-tenant; asientos de hasta 50-100 líneas en uso normal; operación puntual.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: la validación de balance multilínea calcula `sum(Decimal(debe)) == sum(Decimal(haber))` sobre N+M líneas en precisión decimal canónica; rechazo sin persistir si no cuadra. → Cumple; se valida en backend.
- **II. Inmutabilidad del diario**: la anulación de un asiento multilínea genera un asiento rectificativo nuevo con todas las líneas invertidas, enlazado al original; el original no se modifica ni elimina. → Cumple.
- **III. Multi-tenancy estricto**: todas las operaciones (creación, consulta, anulación) se filtran por `empresa_id` derivado de sesión. → Cumple.
- **IV. Numeración correlativa**: los asientos multilínea usan la misma secuencia correlativa por (empresa_id, ejercicio) que los asientos normales. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración verificando balance multilínea y aislamiento multi-tenant. → Cumple.
- **Decimal/no float**: sumas de líneas en `Decimal`; prohíbido usar `float` para acumular importes. → Cumple.
- **Auditoría inmutable**: creación y anulación de asientos multilínea se auditan en la misma transacción ACID. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/006-asientos-multilinea/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api-contracts.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   └── acct/            # Entidades existentes de SPEC-002 (JournalEntry, JournalEntryLine)
    ├── services/
    │   └── journal/         # motor.py (ampliado), validador_multilinea.py, anulador.py
    ├── api/
    │   └── journal.py       # endpoints ampliados de SPEC-002
    └── config.py

backend/
└── tests/
    ├── unit/                # balance multilínea, rechazo lado vacío, anulación invertida
    ├── integration/         # flujo completo multilinea, aislamiento
    └── contract/            # firma de contratos de API

frontend/
└── src/
    ├── app/
    │   └── contabilidad/
    │       └── asientos/
    │           └── nuevo/   # entrada contable multilínea optimizada por teclado
    └── components/
        │   └── journal/     # line-editor, dynamic-rows, keyboard-shortcuts
    └── services/
        └── client.ts

frontend/
└── tests/
```

**Structure Decision**: Se amplía el módulo `journal/` del motor de asientos (SPEC-002): `validador_multilinea.py` para las validaciones específicas N:M y `anulador.py` para la generación de rectificativos. El frontend añade un componente de entrada dinámica con filas ilimitadas.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de modelo multilínea, estrategia de validación de balance, manejo de anulación invertida, integración con importación/exportación.
- **data-model.md** (Phase 1): entidades ampliadas (JournalEntry, JournalEntryLine) y reglas de validación multilínea.
- **contracts/** (Phase 1): contrato de API REST ampliado.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.
