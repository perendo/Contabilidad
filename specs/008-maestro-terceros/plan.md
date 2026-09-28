# Implementation Plan: Maestro de Terceros (Clientes y Proveedores)

**Branch**: `008-maestro-terceros` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-maestro-terceros/spec.md` (ampliada con IBAN/datos bancarios y condiciones de pronto pago T-08/FR-009, consumidas por SPEC-020)

## Summary

Maestro de terceros (clientes/proveedores) que da de alta, consulta y retira fichas de terceros con identificación fiscal, razón social, direcciones, contactos y **datos bancarios (IBAN/banco)**; valida NIF/CIF y unicidad por empresa; asigna automáticamente las subcuentas contables 430/410 dentro del plan de la empresa (SPEC-001); expone la ficha con histórico de movimientos (facturas SPEC-007, asientos SPEC-002, vencimientos SPEC-011) y saldo pendiente; protege la baja de terceros con movimientos (solo inactivación); registra auditoría de cambios y **condiciones de pronto pago (plazo y %) por tercero** para la liquidación de SPEC-020.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). No dependencias nuevas; se consume el plan de cuentas (SPEC-001) y se integra con facturación (SPEC-007) y remesas (SPEC-020).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`). Tablas nuevas: `Tercero`, `TerceroSubcuenta`, `CondicionProntoPago`, `TerceroMovimientoHistorico` (si se necesita agregado), o consultas derivadas de SPEC-007/011.

**Testing**: pytest (unit + integración); unicidad de NIF, protección de baja, aislamiento multi-tenant, validación IBAN.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: alta de tercero con subcuentas en <300 ms; consulta de ficha con saldo en <500 ms; listado paginado de terceros <200 ms p95.

**Constraints**: NIF/CIF válido por empresa; IBAN validado (MÓDULO 97); subcuentas dentro del plan de la empresa activa; baja definitiva bloqueada si hay movimientos; cambio de NIF con movimientos exige permiso de administrador y queda auditado.

**Scale/Scope**: 1.000+ empresas multi-tenant; maestro de hasta decenas de miles de terceros por empresa; operación puntual.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: no genera asientos directamente, pero alimenta subcuentas de asientos existentes (430/410). No arriesga el balance; las subcuentas se validan en el plan (SPEC-001). → Cumple.
- **II. Inmutabilidad del diario**: la baja/inactivación de terceros nunca toca asientos existentes; el histórico queda intacto. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas del maestro incluyen `empresa_id` en PK/índices/filtros derivado de sesión; cada empresa tiene su propio maestro (edge case "dos empresas comparten tercero → fichas separadas"). → Cumple.
- **IV. Numeración correlativa**: no aplica directamente (el maestro no lleva numeración documental). Las subcuentas se numeran según convección configurable del plan. → No aplica / sin violación.
- **V. Pruebas obligatorias**: pytest unit + integración verificando unicidad, protección de baja y aislamiento multi-tenant. → Cumple.
- **Decimal/no float**: importes de saldo pendiente en `Decimal`/`NUMERIC(18,4)`; condiciones de pronto pago en `NUMERIC(5,2)`. → Cumple.
- **Auditoría inmutable**: cada cambio del maestro (alta, modificación, NIF, inactivación, condiciones, IBAN) se registra en auditoría en la misma transacción ACID. → Cumple.

Sin violaciones. La ampliación T-08/FR-009 (IBAN/banco y condiciones de pronto pago) está justificada en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/008-maestro-terceros/
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
    │   ├── ar/             # tercero.py, tercero_subcuenta.py, condicion_pronto_pago.py
    │   └── acct/           # plan de cuentas (SPEC-001) consumido
    ├── services/
    │   └── thirdparty/     # validacion_nif.py, alta.py, saldo.py, retirada.py, bancos.py
    │       ├── condiciones_pronto_pago.py  # condiciones por tercero (SPEC-020)
    │       └── subcuentas.py               # asignación automática 430/410
    ├── api/
    │   └── thirdparty.py   # endpoints de terceros
    └── config.py

backend/
└── tests/
    ├── unit/                # validación NIF/IBAN, unicidad, cálculo saldo
    ├── integration/         # alta/consulta/retirada, aislamiento multi-tenant
    └── contract/            # firma de contratos de API

frontend/
└── src/
    ├── app/
    │   └── terceros/        # listado, ficha, alta, retirada, condiciones
    └── components/
        │   └── thirdparty/  # fichero de tercero, editor de condiciones
    └── services/
        └── client.ts

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raíz: `backend/src/models/ar/` (domain de cuentas a cobrar/pagar) y `backend/src/services/thirdparty/`; `frontend/src/app/terceros/` para las páginas. El servicio de saldo consulta los movimientos derivados de SPEC-007/002/011 agrupándolos por tercero.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de modelo de tercero, validación NIF/CIF, asignación de subcuentas, saldo/histórico, retirada, IBAN y condiciones de pronto pago.
- **data-model.md** (Phase 1): entidades `Tercero`, `TerceroSubcuenta`, `CondicionProntoPago`, + agregado de saldo.
- **contracts/** (Phase 1): contrato de API REST del maestro.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.