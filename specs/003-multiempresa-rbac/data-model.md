# Data Model: Multiempresa y Control de Acceso por Roles (SPEC-003)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- La empresa activa se deriva de la sesión autenticada (cabecera `X-Empresa-Activa`); nunca de datos del cliente.
- Importes: esta feature no maneja importes; el `payload` de auditoría serializa cualquier valor sensible como cadena string (prohibido `float`).
- Toda escritura se audita en la misma transacción ACID.

## Empresa / Tenant (`companies`)

Entidad que representa una razón social independiente del sistema.

| Campo | Tipo | Reglas |
|-------|------|--------|
| company_id | BIGINT IDENTITY PK | nombre alineado con FK del `account_plan.tenant_id` de SPEC-001 |
| nif | VARCHAR(20) | identificación fiscal (unicidad diferida; no se fuerza en esta feature) |
| razon_social | VARCHAR(200) | NOT NULL |
| is_active | BOOLEAN | default TRUE; empresa inactiva → deniega acceso (FR-008) |
| created_at | TIMESTAMPTZ | UTC |

**Trigger**: `trg_companies_seed` (AFTER INSERT, plan raíz) invoca `seed_default_pgc(NEW.company_id)` en la misma transacción. Si el seed falla, el INSERT revierte (atomicidad).

## Usuario (`users`)

Entidad global de la plataforma; un usuario puede pertenecer a varias empresas.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| email | VARCHAR(255) NOT NULL | `UNIQUE`; normalizado (lowercase) |
| password_hash | VARCHAR(255) NOT NULL | bcrypt/argon2; salt automático |
| full_name | VARCHAR(200) | |
| is_active | BOOLEAN | default TRUE; usuario inactivo → deniega todas las sesiones (FR-008) |
| created_at | TIMESTAMPTZ | UTC |

## Relación Usuario-Empresa-Rol (`user_companies`)

Determina las empresas a las que accede el usuario y el rol en cada una.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| user_id | BIGINT NOT NULL | FK → `users(id)` ON DELETE CASCADE |
| company_id | BIGINT NOT NULL | FK → `companies(company_id)` ON DELETE CASCADE |
| role | ENUM NOT NULL | `ADMIN`, `ACCOUNTANT`, `READ_ONLY` |
| is_default | BOOLEAN | TRUE si es la empresa por defecto del usuario |
| is_active | BOOLEAN | default TRUE; relación inactiva → deniega acceso |
| created_at | TIMESTAMPTZ | UTC |

**Constraints**:
- `UNIQUE (user_id, company_id)` (un solo registro de relación por par).
- **Índice único parcial**: `CREATE UNIQUE INDEX uq_default_company ON user_companies (user_id) WHERE is_default = TRUE;` (una sola empresa por defecto por usuario, FR-002/FR-005).
- FKs compuestas multi-tenant: `(user_id, company_id)` forma la clave de acceso; la consulta de la empresa activa filtra `user_id + company_id` y `is_active = TRUE` de ambas tablas.

**Reglas de visibilidad** (FR-008/FR-005):
- Una relación se considera **activa** solo si el usuario (`is_active=TRUE`) y la empresa (`is_active=TRUE`) lo están.
- Toda consulta de "mis empresas" filtra por `is_active=TRUE` de las tres tablas.
- El rol define capacidades: `READ_ONLY` no puede ejecutar endpoints de escritura (mínimo de esta feature); `ACCOUNTANT` y `ADMIN` sí.

**Transiciones de estado**:
- `is_default`: puede actualizarse libremente (la nueva empresa por defecto reemplaza la anterior en el índice parcial).
- `role`: puede actualizarse (solo por `ADMIN` de la empresa).

## Registro de auditoría (`audit_log`)

Ver modelo de SPEC-001/plan raíz §5.e. Acciones de esta feature: `LOGIN`, `LOGIN_FAILED`, `SWITCH_COMPANY`, `CREATE_COMPANY`, `CREATE_RELATION`, `UPDATE_DEFAULT_COMPANY`. Escritura en la misma transacción que la operación.

## Resumen de relaciones

```
companies (PK company_id) 1 ── n user_companies (FK company_id)
users (PK id) 1 ── n user_companies (FK user_id)
companies 1 ── n account_plan (FK tenant_id → company_id; seed por trigger)
companies 1 ── n audit_log (empresa afectada)
users 1 ── n audit_log (actor)
user_companies 1 ── 0..1 user_companies (is_default: empresa por defecto del usuario)
```

La relación `companies.company_id` es la misma columna referenciada como `tenant_id` en `account_plan` (SPEC-001) y `empresa_id` en los asientos (SPEC-002), formando el aislamiento multi-tenant de la plataforma.