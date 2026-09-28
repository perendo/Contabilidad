# Data Model: Apertura del Ejercicio (SPEC-009)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## EjercicioContable (extensión del dominio existente)

Gestiona el estado del ciclo contable para cada ejercicio de cada empresa.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta |
| ejercicio | INT | año fiscal (ej. 2026) |
| fecha_inicio | DATE | primer día del ejercicio |
| fecha_fin | DATE | último día del ejercicio |
| estado | ENUM | `abierto`, `cerrado`, `con_apertura` |
| creado_por / created_at | | auditoría |

**Validaciones**: unicidad de (empresa_id, ejercicio); `fecha_inicio < fecha_fin`; no se permite solapamiento de rangos en la misma empresa.

**Transiciones de estado**: `abierto → cerrado` (cierre SPEC-004) | `cerrado → con_apertura` (generación de apertura) | `con_apertura → abierto` (el nuevo ejercicio queda listo para asentar).

## JournalEntry — Tipo OPENING (extensión del dominio de asientos)

El asiento de apertura es un `JournalEntry` existente con tipo específico y metadatos adicionales.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio_id | UUID FK → EjercicioContable | ejercicio **destino** (el que se abre) |
| numero_asiento | BIGINT | correlativo por (empresa_id, ejercicio_id), asignado atómicamente |
| tipo | ENUM | `OPENING` (apertura), `OPENING_REVERSAL` (anulación de apertura) |
| fecha | DATE | fecha del primer día del ejercicio destino |
| descripcion | VARCHAR(255) | e.g. "Asiento de apertura ejercicio 2026" |
| referencia_cierre_id | UUID FK NULL → JournalEntry | asiento de cierre del ejercicio origen (trazabilidad) |
| estado | ENUM | `POSTED` (inmediato, sin borrador) |
| created_at / created_by / ip | | auditoría inmutable |

**Validaciones**: un solo `OPENING` activo por (empresa_id, ejercicio_id); el `referencia_cierre_id` apunta al asiento de cierre del ejercicio anterior; si se anula, se crea un `OPENING_REVERSAL` nuevo sin tocar el original.

## JournalEntryLine — Líneas del asiento de apertura

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| journal_entry_id | UUID FK → JournalEntry | |
| account_id | UUID FK → SPEC-001 Account | cuenta patrimonial (grupo 1-3) |
| descripcion | VARCHAR(255) | |
| debit | NUMERIC(18,4) | >= 0; uno de los dos debe ser 0 |
| credit | NUMERIC(18,4) | >= 0; uno de los dos debe ser 0 |
| orden | INT | orden de línea |

**Validaciones**: `suma(debit) == suma(credit)` en la transacción; cada línea tiene `debit > 0` XOR `credit > 0`; solo cuentas de grupo 1-3 (patrimoniales).

## Resumen de relaciones

```
EjercicioContable (empresa_id, ejercicio) 1 ── 1 JournalEntry (OPENING)
JournalEntry (OPENING) 1 ── n JournalEntryLine
JournalEntry (OPENING) 0..1 ── 1 JournalEntry (OPENING_REVERSAL) enlazado
JournalEntry (OPENING) 0..1 ── 1 JournalEntry (cierre, referencia_cierre_id)
Account (SPEC-001) 1 ── n JournalEntryLine
EjercicioContable 1 ── n JournalEntry (todos los tipos)
```
