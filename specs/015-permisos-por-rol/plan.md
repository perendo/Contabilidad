# Implementation Plan: Matriz de Permisos por Rol

**Branch**: `015-permisos-por-rol` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/015-permisos-por-rol/spec.md`

## Summary

Módulo de seguridad que implementa la **matriz de permisos por rol y módulo/operación** sobre la capa de identidad de **SPEC-003 (RBAC/determinación de empresa activa)**. El administrador define, por **módulo × operación × rol × empresa**, qué operaciones (ver, crear, editar, aprobar, importar/exportar, configurar) puede ejecutar cada rol. La autorización es **denegación por defecto**: toda operación no concedida explícitamente queda denegada, y la decisión se aplica como el **mínimo entre la empresa activa, el rol del usuario y el permiso de la operación** — sin bypass posible (un usuario con rol global no accede a datos de una empresa donde la matriz no le concede el permiso). La autorización se **verifica en cada operación** del sistema mediante una dependency central de FastAPI y se re-evalúa en cada petición (sin cacheo excesivo). Cada **intento denegado y cada permiso concedido** sobre datos contables se registran en el log de auditoría inmutable (actor, empresa, operación) en la misma transacción ACID.

Se apoya en los roles base sembrados por SPEC-003/creación de empresa (`ADMIN`, `ACCOUNTANT`, `READ_ONLY`), siembra la matriz inicial y restringe las operaciones de configuración de la matriz a la matriz de configuración de la empresa. No existe "superusuario" global por defecto fuera de la matriz.

**Stack**: FastAPI (async) + PostgreSQL 16+ + Next.js, multi-tenancy estricto por `empresa_id`, auditoría inmutable y pruebas pytest obligatorias (constitución III y V).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Sin librerías de autorización externas: implementación propia (lista cerrada módulo×operación, evaluación por empresa).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; sin importes monetarios — `NUMERIC` no aplica fuera del dominio contable).

**Testing**: pytest (unit + integración); fixtures de usuarios/roles por empresa; pruebas de denegación por defecto y aislamiento empresa×rol.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: evaluación de autorización <10 ms por petición (consulta indexada por empresa+rol+operación); sin cacheo que perviva a una revocación (matriz evaluada por petición, FR/A. de la spec); latencia de endpoints <200 ms p95.

**Constraints**: latencia de autorización <10 ms p95; toda operación pasa por la dependency central (SC-004 sin bypass); denegación por defecto (SC-001); evaluación por petición (Assumptions de la spec); eventos de acceso auditados (SC-003).

**Scale/Scope**: 1.000+ empresas multi-tenant; roles base (3) + roles personalizados por empresa; decenas de operaciones por módulo. Nº máximo de operaciones por módulo y política de roles personalizados: NEEDS CLARIFICATION — resuelto en `research.md` (D1/D2).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: no aplica — esta feature no crea ni muta asientos contables; la validación de balance de SPEC-002 queda intacta. → No aplica (sin violación).
- **II. Inmutabilidad del diario**: no toca el diario; los eventos de auditoría de acceso se persisten como registro inmutable (sin UPDATE/DELETE) en la misma transacción ACID. → Cumple (auditoría inmutable).
- **III. Multi-tenancy estricto**: la matriz se evalúa por `empresa_id` derivado de sesión (SPEC-003); un rol global no excede la matriz de la empresa; pruebas que demuestran que un usuario con rol en A no accede a B. → Cumple.
- **IV. Numeración correlativa**: no aplica — no existe numeración legal en este módulo (los asientos la gestionan en SPEC-002). → No aplica (sin violación).
- **V. Pruebas obligatorias**: pytest unit + integración (denegación por defecto y aislamiento empresa×rol, constitución V). → Cumple.
- **Decimal/no float**: no aplica — módulo sin importes monetarios; las operaciones con datos contables conservan `Decimal` los valores del dominio. → No aplica (sin violación).
- **Auditoría inmutable** (misma transacción ACID): intentos denegados y permisos concedidos se persisten con actor, empresa y operación. → Cumple.

Sin violaciones. Las decisiones de denegación por defecto, evaluación por petición y ausencia de superusuario global se justifican en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/015-permisos-por-rol/
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
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002)
    │   └── rbac/            # permiso_operacion.py (catálogo), rol.py,
    │                        # matriz_permiso.py, evento_auditoria_acceso.py
    ├── services/
    │   └── security/        # catalogo.py, matriz.py, authorize.py,
    │                        # auditoria_acceso.py
    ├── api/                 # rbac.py (endpoints, ver contracts/)
    │   └── deps.py          # require_permission(modulo, operacion) central
    └── config.py

backend/
└── tests/
    ├── unit/                # evaluación denegación por defecto, mín. empresa×rol×permiso
    ├── integration/         # matriz por empresa, auditoría, aislamiento
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   └── permisos/        # matriz de permisos por rol/empresa, log de accesos
    ├── components/rbac/
    └── services/            # cliente HTTP con cabecera de empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raíz: `backend/` con modelos en `models/rbac/` y procesos en `services/security/`; la dependency `require_permission` vive en `backend/src/api/deps.py` para ser aplicada por cualquier router (SPEC-001/002/011/013/014/016/020). La identidad/sesión y la determinación de la empresa activa se consumen de SPEC-003, nunca se duplican.

## Complexity Tracking

No aplica (sin violaciones de constitución; la inmutabilidad del diario no se ve afectada porque este módulo no escribe asientos).

## Design Artifacts

- **research.md** (Phase 0): decisiones de diseño del catálogo módulo×operación, evaluación por petición, denegación por defecto, mínimo empresa×rol×permiso, auditoría de accesos y no bypass.
- **data-model.md** (Phase 1): entidades `PermisoOperacion`, `Rol`, `MatrizPermiso`, `EventoAuditoriaAcceso`.
- **contracts/** (Phase 1): contrato de API REST (sin formatos externos; no aplica ficheros).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.