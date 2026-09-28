# Data Model: Motor de Asientos Contables (SPEC-002)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` en PK/índices/filtros (equivalente a `tenant_id` del plan de cuentas de SPEC-001); se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cabecera y líneas se persisten indivisibles en `async with async_session.begin()`; cada escritura se audita en la misma transacción ACID.

## Asiento contable — Cabecera (`journal_entry`)

Agrupa los apuntes de una operación contable.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| empresa_id | BIGINT NOT NULL | empresa activa (aislamiento); `UNIQUE (empresa_id, id)` |
| numero | BIGINT NULL | correlativo por (empresa, ejercicio); **NULL en borrador**, asignado atómicamente al asentar. `UNIQUE (empresa_id, ejercicio, numero)` |
| ejercicio | INT NOT NULL | derivado de `fecha` (nunca manual); debe existir en `fiscal_year` de la empresa y no estar cerrado |
| fecha | DATE NOT NULL | fecha del asiento |
| concepto | VARCHAR(255) NOT NULL | |
| estado | ENUM | `DRAFT`, `POSTED`, `CANCELLED` |
| tipo | ENUM | `GENERAL`, `REVERSAL` |
| reversal_of_id | BIGINT NULL | FK `(empresa_id, reversal_of_id)` → `journal_entry(empresa_id, id)`; no nulo si `tipo=REVERSAL`; el original queda `CANCELLED` |
| created_by / created_at / updated_at | | auditoría; `created_at`/`updated_at` TIMESTAMPTZ UTC |

**Validaciones**: mínimo un apunte al Debe y uno al Haber; `sum(Debe) == sum(Haber)` exacto (trigger sobre sumas de líneas); el `numero` no se asigna en `DRAFT`; un número ya emitido no se reutiliza.

**Transiciones de estado**:

```
DRAFT → POSTED   (asentar: valida balance/cuentas/ejercicio, asigna numero atómico)
POSTED → CANCELLED (única vía: nuevo asiento REVERSAL enlazado por reversal_of_id)
DRAFT → CANCELLED (descartar borrador sin número — opcional de plataforma)
```

**Triggers**: `chk_journal_entry_balance` (suma líneas == en cualquier mutación), `trg_journal_immutable` (prohíbe UPDATE/DELETE de filas `POSTED`/`CANCELLED`), guarda de `numero` (solo al pasar a `POSTED`).

## Apunte contable — Línea (`journal_entry_line`)

Detalle del asiento; importes de Debe/Haber con precisión exacta.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| empresa_id | BIGINT NOT NULL | |
| entry_id | BIGINT NOT NULL | FK compuesta `(empresa_id, entry_id)` → `journal_entry(empresa_id, id)` |
| line_no | SMALLINT NOT NULL | orden dentro del asiento; `UNIQUE (empresa_id, entry_id, line_no)` |
| account_id | BIGINT NOT NULL | FK compuesta `(empresa_id, account_id)` → `account_plan(tenant_id, id)` |
| debit | NUMERIC(18,4) NOT NULL DEFAULT 0 | `>= 0` |
| credit | NUMERIC(18,4) NOT NULL DEFAULT 0 | `>= 0` |
| detail | VARCHAR(255) NULL | detalle del apunte |

**Validaciones (CHECK)**:
- Una línea es **Debe o Haber**, nunca ambos: `CHECK (debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)`, y `CHECK (debit > 0 OR credit > 0)` (no se aceptan líneas nulas).
- Importes siempre 4 decimales canónicos (normalización previa en el servicio).

**Triggers**: `chk_journal_line_account_selectable` (SPEC-001 plan raíz §5.d): la cuenta debe ser de la **misma empresa**, `is_selectable = true` e `is_active = true`; `trg_journal_line_immutable` (prohíbe UPDATE/DELETE de líneas cuyo asiento esté `POSTED`/`CANCELLED`).

## Ejercicio contable (`fiscal_year`)

Período derivado de la fecha; gestión y bloqueo explicados en SPEC-004 (aquí solo se referencia).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| empresa_id | BIGINT NOT NULL | |
| year | INT NOT NULL | `UNIQUE (empresa_id, year)` |
| date_start / date_end | DATE | rango del ejercicio |
| is_closed | BOOLEAN | bloquea escrituras de asientos con fecha dentro del rango |

**Guarda del motor**: al crear/asentar un asiento, si no existe `fiscal_year` para la fecha o está `is_closed` → HTTP 400 sin persistir nada.

## Registro de auditoría (`audit_log`)

Ver modelo de SPEC-001 (plan raíz §5.e). Acciones de esta feature: `CREATE` (borrador), `POSTED`, `REVERSAL`, `CANCELLED`; payload con los importes del asiento como cadenas Decimal, actor y IP de la petición, `created_at` UTC, en la misma transacción.

## Resumen de relaciones

```
account_plan (SPEC-001) 1 ── n journal_entry_line (FK compuesta (empresa_id, account_id))
journal_entry 1 ── n journal_entry_line (FK compuesta (empresa_id, entry_id))
journal_entry 1 ── 0..1 journal_entry (reversal_of_id: original ⇠ rectificativo)
fiscal_year (SPEC-004) 1 ── n journal_entry (por el ejercicio derivado de la fecha)
empresa/tenant 1 ── n journal_entry / journal_entry_line (aislamiento)
journal_entry/journal_entry_line 1 ── n audit_log (misma transacción)
```

La relación `account_plan` ↔ `journal_entry_line` es la base de la protección de cuentas del SPEC-001 (desactivación/borrado bloqueados si hay imputaciones).