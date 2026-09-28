# Data Model: Presupuestos y Desviaciones (SPEC-026)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003; alias `tenant_id` del `plan.md` raíz) en PK/índices/filtros; se deriva de la sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría (`audit_log`, WORM) en la misma transacción ACID.
- `journal_entry_line` (SPEC-002) es la fuente del real; esta feature lo consulta en modo lectura.

## Presupuesto

Importe anual previsto para una combinación cuenta-centro-ejercicio, único por empresa.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id) |
| ejercicio | INT | año fiscal; forma unicidad con la combinación |
| cuenta_id | UUID FK → account_plan (SPEC-001) | FK compuesta (empresa_id, cuenta_id); cuenta apuntable |
| centro_coste_id | UUID NULL FK → CentroCoste (SPEC-017) | FK compuesta (empresa_id, centro_coste_id); nulo si no se usan centros (FR-006) |
| importe | NUMERIC(18,4) | importe anual previsto; puede ser negativo para ingresos |
| tipo | ENUM | `gasto` (grupo 6) / `ingreso` (grupo 7) |
| periodo_id | UUID FK NULL → PeriodoSeguimiento | periodo al que pertenece; NULL si es base anual |

**Validaciones**: único `(empresa_id, ejercicio, cuenta_id, centro_coste_id)` (FR-005); la cuenta debe ser `is_selectable = true` de la misma empresa; si `centro_coste_id` no es nulo, pertenece a la misma empresa.

**Transiciones de estado**: el presupuesto es modificable solo si el periodo de seguimiento está en `abierto`. Tras el cierre, las líneas del periodo quedan inmutables (constitución II; cierre genera snapshot `Desviacion`).

## PeriodoSeguimiento

Rango de fechas para el cotejo y cierre del seguimiento presupuestario, con numeración correlativa por empresa y ejercicio.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta |
| ejercicio | INT | año fiscal |
| numero_periodo | BIGINT | correlativo por (empresa_id, ejercicio), asignado atómicamente (constitución IV) |
| fecha_inicio | DATE | inicio del periodo |
| fecha_fin | DATE | fin del periodo |
| estado | ENUM | `abierto`, `cerrado` |
| fecha_cierre | TIMESTAMPTZ NULL | momento del cierre |
| cerrado_por | VARCHAR(200) NULL | actor del cierre |

**Validaciones**: único `(empresa_id, ejercicio, numero_periodo)`; solo un periodo `abierto` por `(empresa_id, ejercicio)` (constraint); `fecha_fin > fecha_inicio`. Tras cierre: `estado = cerrado`, `fecha_cierre` y `cerrado_por` persistidos, y las líneas de presupuesto del periodo quedan inmutables (rechazo de modificaciones).

**Transiciones**: `abierto → cerrado` (irreversible; genera snapshot `Desviacion`).

## Desviacion (snapshot al cierre)

Registro trazable de la desviación final por combinación cuenta-centro-ejercicio al cierre de un periodo de seguimiento (US3 scenario 2: "la desviación final queda registrada como trazable").

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| periodo_id | UUID FK → PeriodoSeguimiento | periodo cerrado |
| cuenta_id | UUID FK → account_plan (SPEC-001) | |
| centro_coste_id | UUID NULL FK → CentroCoste (SPEC-017) | nulo si el presupuesto no tiene centro |
| importe_presupuestado | NUMERIC(18,4) | valor original del presupuesto |
| importe_real | NUMERIC(18,4) | valor calculado del diario |
| desviacion_absoluta | NUMERIC(18,4) | real − presupuesto |
| desviacion_relativa | NUMERIC(7,4) NULL | `(real − presupuesto) / |presupuesto|` en ratio decimal; null si presupuesto = 0 |
| sin_presupuesto | BOOLEAN | true si la línea no tenía presupuesto asociado |

**Validaciones**: única `(empresa_id, periodo_id, cuenta_id, centro_coste_id)`; `estado` cerrado = inmutable (no UPDATE/DELETE, trigger WORM parcial del `audit_log`); reflejo exacto de `Presupuesto + SUM(journal_entry_line)` al momento del cierre.

**Estado**: la tabla solo crece al cerrar periodos; las filas no se actualizan ni borran (inmutabilidad de snapshot).

## Referencias externas (solo lectura)

- `account_plan` (SPEC-001): cuenta apuntable de la empresa; origen del código y naturaleza (gasto/ingreso por grupo).
- `journal_entry_line` (SPEC-002): apuntes del diario; `SUM(Debe)` o `SUM(Haber)` según naturaleza, filtrado por `(empresa_id, fecha_asiento, cuenta_id)`.
- `CentroCoste` (SPEC-017): centro de coste opcional, FK compuesta `(empresa_id, id)`.

## Resumen de relaciones

```
account_plan (SPEC-001) 1 ── n Presupuesto (cuenta_id)
CentroCoste (SPEC-017) 1 ── 0..n Presupuesto (centro_coste_id, FK compuesta empresa)
PeriodoSeguimiento 1 ── n Presupuesto (periodo_id)
PeriodoSeguimiento 1 ── n Desviacion (snapshot al cierre)
journal_entry_line (SPEC-002) — lectura por (empresa_id, cuenta_id, fecha) → importe_real de Desviacion
```

**Nota de convención**: `empresa_id` == `tenant_id` del `plan.md` raíz; alias documentado en `research.md` D9.