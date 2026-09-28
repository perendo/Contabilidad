# Data Model: Asientos Contables Multilínea (SPEC-006)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)` / `Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## Entidades ampliadas (no crea tablas nuevas)

Esta feature amplía las entidades existentes de SPEC-002. Las siguientes tablas ya existen y se describen aquí con las reglas multilínea.

## JournalEntry (Cabecera de asiento — ampliación SPEC-002)

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id); FK a empresa |
| numero_asiento | BIGINT | correlativo por (empresa_id, ejercicio); asignado atómicamente |
| ejercicio | INT | año fiscal |
| fecha | DATE | debe pertenecer a un ejercicio abierto de la empresa |
| concepto | VARCHAR(255) | concepto del asiento |
| estado | ENUM | `DRAFT`, `POSTED`, `REVERSAL` |
| asiento_original_id | UUID FK NULL → JournalEntry | si es REVERSAL/rectificativo, enlace al original |
| tipo | ENUM | `NORMAL`, `REVERSAL`, `ADJUSTMENT` | 
| creado_por / created_at | | auditoría |

**Validaciones**: número correlativo único por (empresa_id, ejercicio); si `asiento_original_id` no es nulo, el original debe estar `POSTED`.

**Transiciones**: `DRAFT → POSTED` (confirmación, irreversible) | `POSTED → [rectificativo nuevo]` (anulación, genera nuevo JournalEntry).

## JournalEntryLine (Línea de asiento — ampliación SPEC-002)

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| journal_entry_id | UUID FK → JournalEntry | |
| cuenta | VARCHAR(20) FK → CuentaContable | debe existir, ser apuntable y pertenecer a la empresa activa |
| debe | NUMERIC(18,4) | >= 0; si es > 0, `haber` debe ser 0 |
| haber | NUMERIC(18,4) | >= 0; si es > 0, `debe` debe ser 0 |
| detalle | VARCHAR(255) | descripción del apunte (opcional) |

**Validaciones multilínea** (T-02, T-03):
- Todo asiento tiene **al menos una línea con `debe > 0`** y **al menos una línea con `haber > 0`** (regla de los dos lados).
- No se permite una línea con `debe = 0` y `haber = 0`.
- No se permite una línea con `debe > 0` Y `haber > 0` simultáneamente.
- `sum(line.debe for line in lines) == sum(line.haber for line in lines)` en precisión decimal exacta (partida doble).
- Líneas de la misma cuenta en un mismo asiento son admitidas (FR-007).
- Límite configurable de dominio: máx 100 líneas por asiento (default).

**Transiciones de JournalEntryLine**: las líneas se crean junto con la cabecera en la misma transacción; una vez `POSTED`, las líneas son inmutables.

## Asiento rectificativo (generado por anulación)

Al anular un asiento multilínea (N débitos, M créditos):
- Se crea un nuevo `JournalEntry` con `tipo = REVERSAL` y `asiento_original_id` apuntando al original.
- Se crean M líneas al Debe (invertidas de las N originales al Haber) y N líneas al Haber (invertidas de las N originales al Debe).
- Cada línea invertida: si la original tenía `debe = X, haber = 0`, la nueva tiene `debe = 0, haber = X`; si la original tenía `debe = 0, haber = Y`, la nueva tiene `debe = Y, haber = 0`.
- El balance del rectificativo es `sum(debe) == sum(haber)` (ya que es la inversión exacta del original).
- El asiento original **no se modifica** (inmutabilidad II).

## Resumen de relaciones

```
JournalEntry (SPEC-002) 1 ── n JournalEntryLine
JournalEntry (rectificativo) FK ── JournalEntry (original)
CuentaContable (SPEC-001) 1 ── n JournalEntryLine.cuenta
EjercicioContable (SPEC-004) n ── 1 JournalEntry.ejercicio

Un asiento multilínea: 1 cabecera + N líneas Debe + M líneas Haber
Rectificativo: 1 cabecera (REVERSAL) + M líneas Debe + N líneas Haber (invertidas)
```
