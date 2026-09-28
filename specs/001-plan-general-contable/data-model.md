# Data Model: Plan General Contable (SPEC-001)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md) | **Fuente autoritativa**: plan.md raíz (`plan.md` del repositorio raíz)

Reglas transversales (constitución + plan raíz):
- La tabla hereda el naming del plan raíz: columna **`tenant_id`** (équivale a `empresa_id` de otras features; constitución III) en PK/índices/filtros de todas las operaciones; se deriva de sesión.
- Toda escritura se persiste con su registro de auditoría en la misma transacción ACID.
- Importes: el plan no lleva importes; el `payload` de auditoría serializa importes como cadenas Decimal (prohibido `float`).

## Cuenta contable (`account_plan`)

Nodo del plan de cuentas de la empresa activa; árbol jerárquico con hasta 5 niveles.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| tenant_id | BIGINT NOT NULL | empresa activa (aislamiento). FK → `companies(company_id)` ON DELETE CASCADE (SPEC-003) |
| code | VARCHAR(8) NOT NULL | solo dígitos; `UNIQUE (tenant_id, code)`. Nivel 1-4: `length(code) == level`; nivel 5: 5 a 8 dígitos |
| name | VARCHAR(200) NOT NULL | `UNIQUE (tenant_id, name)` |
| parent_id | BIGINT NULL | FK compuesta `(tenant_id, parent_id)` → `account_plan (tenant_id, id)`; NULL solo nivel 1; debe cumplir prefijo del código padre |
| level | SMALLINT NOT NULL | `CHECK (level BETWEEN 1 AND 5)` |
| is_selectable | BOOLEAN NOT NULL DEFAULT FALSE | apuntable: solo hojas (sin hijas) y nivel ≥ 4 — mantenido por trigger |
| is_active | BOOLEAN NOT NULL DEFAULT TRUE | activa/inactiva; no desactivable si tiene imputaciones |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | UTC (constitución) |
| updated_at | TIMESTAMPTZ NOT NULL DEFAULT now() | UTC (constitución) |

**Claves e índices (multi-tenant estrictos, tenant en cabeza)**: `UNIQUE (tenant_id, id)`, `UNIQUE (tenant_id, code)`, `UNIQUE (tenant_id, name)`, `ix_account_plan_tenant`, `ix_account_plan_tenant_parent (tenant_id, parent_id)`, `ix_account_plan_tenant_level (tenant_id, level, is_selectable)`, `ix_account_plan_tenant_code (tenant_id, code)`, `ix_account_plan_name_trgm GIN (name gin_trgm_ops)` (pg_trgm).

**Validaciones estructurales (trigger `chk_account_plan_structure`, BEFORE INSERT/UPDATE)**:
1. `code` solo dígitos (`~ '^[0-9]+$'`).
2. `level == length(code)` para niveles 1-4; nivel 5 solo longitudes 5-8.
3. Si `parent_id` no es NULL: el padre existe, es **de la misma empresa**, `is_active = true`, `level = nivel hijo - 1` y el código hijo hereda el prefijo del padre (`code LIKE parent.code || '%'`).
4. Si `parent_id` es NULL → solo nivel 1.

**Mantenimiento automático de `is_selectable` (trigger `sync_account_plan_selectable`, AFTER INSERT/UPDATE OF parent_id)**:
- Al insertar una hija, la madre pasa a `is_selectable = false` (deja de ser hoja).
- La cuenta recién insertada es apuntable si `is_selectable = (level >= 4)`.

**Protección (trigger `chk_account_plan_protected`, BEFORE UPDATE/DELETE)**:
- `DELETE` → rechazado si la cuenta tiene imputaciones en `journal_entry_line` o tiene hijas (además, la API no expone DELETE).
- `UPDATE` de `is_active true → false` → rechazado si la cuenta tiene asientos asociados.

**Transiciones de estado**:

```
is_active :  true ⇄ false  (activar libre; desactivar solo sin imputaciones ni hijas)
is_selectable: derivado por trigger — siempre false si tiene hijas;
                true (nivel ≥ 4) solo si es hoja
level/nivel padre: fijado en el alta; inmutable en la práctica (el cambio de padre
                no se expone en esta feature)
```

## Empresa / Tenant (`companies`)

Entidad de plataforma (SPEC-003) que agrupa y aísla los datos; el plan la referencia por FK.

| Campo | Tipo | Reglas |
|-------|------|--------|
| company_id | BIGINT IDENTITY PK | objetivo de la FK `account_plan.tenant_id` y del trigger de seeding |
| nif | VARCHAR | identificación fiscal (unicidad diferida a SPEC-003) |
| razon_social | VARCHAR(200) | |
| is_active | BOOLEAN | |
| created_at | TIMESTAMPTZ | UTC |

**Trigger de plataforma**: `trg_companies_seed` (AFTER INSERT ON companies) invoca `seed_default_pgc(NEW.company_id)` en la misma transacción.

## Asiento contable / Apunte (`journal_entry_line`)

Entidad del dominio contable definida en SPEC-002; su existencia protege las cuentas del plan.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| tenant_id | BIGINT NOT NULL | (naming del plan raíz; FK compuesta con `account_id`) |
| entry_id / account_id | FK | referencia `account_plan(tenant_id, id)`; trigger `chk_journal_line_account_selectable` (SPEC-001 §5.d / SPEC-002) exige `is_selectable = true` e `is_active = true` de la misma empresa |

**Efecto sobre el plan**: el trigger `chk_account_plan_protected` consulta esta tabla para bloquear borrado/desactivación de cuentas con movimientos (constitución II).

## Registro de auditoría (`audit_log`)

Log inmutable (WORM) definido en el plan raíz §5.e; cada escritura del plan lo rellena en la misma transacción ACID.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| tenant_id | BIGINT NOT NULL | empresa afectada (aislamiento) |
| actor | VARCHAR(200) | usuario; `system`/`data_seed` en el seed |
| action | VARCHAR(100) | `SEED_PGC`, `CREATE`, `POST`, `UPDATE`, … |
| entity | VARCHAR(100) | `account_plan`, `company`, … |
| entity_id | BIGINT NULL | opcional |
| ip | INET | NULL en batch/seed |
| payload | JSONB | delta de la entidad; importes como cadenas Decimal |
| created_at | TIMESTAMPTZ | UTC |

**Inmutabilidad**: trigger que deniega `UPDATE`/`DELETE` (WORM). Índices multi-tenant `(tenant_id)`, `(tenant_id, action, created_at)`.

## Resumen de relaciones

```
companies (SPEC-003) 1 ── n account_plan (tenant_id → company_id; seed por trigger)
account_plan 1 ── n account_plan (parent_id compuesto (tenant_id, parent_id), misma empresa)
account_plan 1 ── n journal_entry_line (SPEC-002; protege la cuenta vs borrado/desactivación)
companies 1 ── n audit_log (tenant_id)
account_plan / companies 1 ── n audit_log (cada escritura audita en la misma transacción)
```

No hay entidades con importes en esta feature (el plan de cuentas no lleva saldos); los importes llegan con el motor de asientos (SPEC-002).