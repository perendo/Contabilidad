# Implementation Plan: Multiempresa y Control de Acceso por Roles (RBAC)

**Branch**: `003-multiempresa-rbac` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-multiempresa-rbac/spec.md`

## Summary

Arquitectura multiempresa y RBAC: entidades `Empresa` (companies), `Usuario` y relación `UsuarioEmpresa` (usuario-empresa-rol, con empresa por defecto); sesión (`JWT`) que transporta la **empresa activa**; **login** devolviendo la lista de empresas accesibles y su empresa por defecto; **conmutación de empresa activa sin re-login** con revalidación de acceso (403 si no hay relación activa); **bloqueo de cualquier operación fuera de las empresas autorizadas** (contexto de empresa derivado exclusivamente de la sesión, nunca de datos del cliente); **creación de empresa** con rol `ADMIN` automático e inicialización de la plantilla base del PGC (seed `seed_default_pgc` de SPEC-001 en la misma transacción ACID).

Es la feature fundacional del **multi-tenancy estricto** (constitución III): todas las features de datos (SPEC-001/002/004) consumen el contexto de empresa y los guards de esta feature para garantizar el aislamiento y responder `HTTP 403` sin filtrar información.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)` (sin importes en esta feature), multi-tenancy estricto por relación activa y pruebas pytest obligatorias (403 + aislamiento).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Hashing de contraseñas (bcrypt/argon2) y emisión/validación de tokens JWT (`python-jose` o alternativa fijada en research).

**Storage**: PostgreSQL 16+ (tablas `companies`, `users`, `user_companies` multi-tenant; sin importes monetarios — RBAC no lleva importes).

**Testing**: pytest (unit + integración); 403 sin acceso, aislamiento multi-tenant, conmutación de empresa sin fuga de datos, seed del PGC al crear empresa.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: login y conmutación de empresa < 300 ms p95; validación de contexto de empresa < 20 ms por petición (guard por dependency reutilizada).

**Constraints**: < 20 ms p95 por guard de contexto; contexto de empresa **siempre** derivado de la sesión autenticada; una relación (usuario, empresa) activa exige usuario y empresa activos; `READ_ONLY` bloqueado en escrituras (mínimo FR-006); ninguna operación "sin empresa".

**Scale/Scope**: 1.000+ empresas y 10.000+ usuarios; un usuario en varias empresas; un único rol por par (usuario, empresa) entre `ADMIN`, `ACCOUNTANT`, `READ_ONLY`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: no aplica a esta feature (no gestiona asientos ni importes); sí exige que el circuito de creación de empresa invoque el seed PGC base sin romper invariantes. → No aplica (justificado).
- **II. Inmutabilidad del diario**: no aplica directamente; la auditoría (log WORM de la plataforma) registra login, conmutaciones y creación de empresa. → No aplica (justificado) / Cumple vía auditoría.
- **III. Multi-tenancy estricto**: núcleo de esta feature — `empresa_id` (relación activa) en toda operación de datos; contexto derivado solo de sesión; 403 sin exponer información; pruebas de aislamiento obligatorias; seed del PGC aislado por tenant en el alta. → Cumple.
- **IV. Numeración correlativa**: no aplica (no hay asientos/facturas en esta feature; los números se gestionan en SPEC-002/004). → No aplica (justificado).
- **V. Pruebas obligatorias**: pytest unit + integración (acceso no autorizado → 403 y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: la feature no maneja importes; se conserva el patrón (payload de auditoría como cadenas Decimal si procediera). → N/A/Cumple.
- **Auditoría inmutable** (misma transacción ACID): login, conmutación de empresa y creación de empresa se auditan en la misma transacción que la operación. → Cumple.

Sin violaciones. La decisión de sesión JWT con `empresa_activa` y el lifecycle del contexto se justifican en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/003-multiempresa-rbac/
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
│   └── 004_iam.sql      # DDL companies/users/user_companies + índices + default único
└── src/
    ├── models/
    │   └── iam/         # company.py, user.py, user_company.py
    ├── services/
    │   ├── auth/        # security.py (hash/token), session.py, rbac.py, company_service.py
    │   └── pgc_seed/    # wrapper del seed de SPEC-001: seed_default_pgc(empresa_id)
    ├── api/
    │   ├── auth/auth.py       # /api/v1/auth/* (login, me, switch-company)
    │   ├── companies.py       # /api/v1/companies (crear empresa)
    │   └── deps.py            # get_empresa_id(), get_current_user(), require_role()
    └── config.py

backend/
└── tests/
    ├── unit/            # RBAC, tokens, default único, roles
    ├── integration/     # 403, aislamiento, conmutación sin fuga, seed en alta
    └── contract/        # firma de contratos de API

frontend/
├── src/
│   ├── app/
│   │   ├── login/       # page.tsx
│   │   ├── empresas/
│   │   │   └── nueva/   # page.tsx (crear empresa)
│   │   └── (empresa)…   # todas las páginas consumen el contexto de empresa activa
│   ├── components/
│   │   └── rbac/        # CompanySwitch.tsx (selector de empresa del navbar)
│   └── services/client.ts  # cliente HTTP: JWT + cabecera de empresa activa en cada petición
└── tests/
```

**Structure Decision**: se adopta la estructura web del `plan.md` raíz; la feature 003 aporta el módulo `iam` (models/services/api) y los *deps* compartidos (`backend/src/api/deps.py`) que consumen SPEC-001/002/004.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de modelo usuario-empresa-rol, sesión JWT y empresa activa, cabecera de empresa, guards 403, creación de empresa con seed y ciclo de conmutación.
- **data-model.md** (Phase 1): entidades `companies`, `users`, `user_companies` con reglas de rol/actividad/por defecto.
- **contracts/** (Phase 1): contrato REST de autenticación, conmutación y creación de empresa con errores 401/403/404/409/422.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.