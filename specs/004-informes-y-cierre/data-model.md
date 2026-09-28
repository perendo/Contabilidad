# Data Model: Contabilidad Habitual, Informes y Cierre de Ejercicio (SPEC-004)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` en PK/índices/filtros (equivale a `tenant_id` del plan de cuentas); se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Toda escritura se persiste con su registro de auditoría en la misma transacción ACID.

## Ejercicio contable (`fiscal_year`)

Período por empresa; su estado cerrado/abierto determina si se admiten escrituras en el rango.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| empresa_id | BIGINT NOT NULL | `UNIQUE (empresa_id, year)` |
| year | INT NOT NULL | año del ejercicio |
| date_start / date_end | DATE NOT NULL | rango; los asientos derivan su `ejercicio` de estos límites |
| is_closed | BOOLEAN NOT NULL DEFAULT FALSE | bloquea escrituras de asientos en el rango |
| closed_at | TIMESTAMPTZ NULL | momento del cierre (UTC) |
| regularizacion_entry_id | BIGINT NULL | FK → `journal_entry` (asiento de regularización, SPEC-002) |
| cierre_entry_id | BIGINT NULL | FK → `journal_entry` (asiento de cierre, SPEC-002) |
| created_by / created_at | | auditoría; UTC |

**Validaciones/guarda**: al crear/asentar un asiento con `fecha` fuera de todo rango → HTTP 400; dentro de un ejercicio `is_closed` → HTTP 400 sin persistir nada (FR-007). No se crean ejercicios automáticamente.

**Transiciones de estado**: `abierto → cerrado` (cierre atómico) y, una vez cerrado, **permanece cerrado** (no hay reapertura en esta feature; SC-004: bloqueo definitivo).

## Factura (`invoice`)

Documento soporte de la contabilidad (emitida o recibida) con precisión exacta y numeración correlativa.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | BIGINT IDENTITY PK | |
| empresa_id | BIGINT NOT NULL | `UNIQUE (empresa_id, ejercicio, numero_seq)` |
| tipo | ENUM | `emitida`, `recibida` |
| ejercicio | INT NOT NULL | año del ejercicio de la factura |
| numero_seq | BIGINT | correlativo por (empresa, ejercicio) asignado atómicamente (patrón secuencia bloqueada de SPEC-002) |
| nif_tercero | VARCHAR(20) | identificación fiscal del tercero (validación fiscal FKI diferida al módulo de terceros) |
| fecha | DATE | fecha de emisión/recepción |
| base | NUMERIC(18,4) | base imponible; >= 0 |
| cuota_iva | NUMERIC(18,4) | cuota de IVA |
| total | NUMERIC(18,4) | `CHECK (total = base + cuota_iva)` |
| asiento_id | BIGINT NULL | FK → `journal_entry` (asiento que la soporta); **una vez fijado no cambia** |
| created_by / created_at | | auditoría; UTC |

**Validaciones**: `total == base + cuota_iva` (exacto, 4 decimales); número único por (empresa, ejercicio); sin `DELETE`; campos de contexto editables solo antes del vínculo con `asiento_id`.

**Transiciones**: `sin_asiento → con_asiento` (vinculación única e inmutable); sin borrado físico ni reinterpretación.

## Informes derivados (sin tabla)

- **Balance de Sumas y Saldos**: cálculo agregado sobre `journal_entry_line` + `account_plan` (ver research D1/D2). No se persiste; se regenera por consulta.
- **Libro Mayor**: secuencia de movimientos de una subcuenta con saldo acumulado (ver research D3). No se persiste.

## Registro de auditoría (`audit_log`)

Ver modelo de SPEC-001 (plan raíz §5.e). Acciones de esta feature: `CREATE_INVOICE`, `CLOSE_YEAR`, `REGULARIZATION`, `CLOSING_ENTRY`. Payload JSONB con importes como cadenas Decimal. Escritura en la misma transacción que la operación.

## Resumen de relaciones

```
fiscal_year 1 ── n journal_entry (SPEC-002: ejercicio derivado de la fecha, bloqueo is_closed)
fiscal_year 0..1 ── 1 journal_entry (regularizacion_entry_id / cierre_entry_id, SPEC-002)
invoice n ── 0..1 journal_entry (asiento_id que la soporta, SPEC-002)
invoice n ── account_plan indirecto (asientos de la factura sobre cuentas del plan)
empresa/tenant 1 ── n fiscal_year / invoice / audit_log  (aislamiento estricto)
```

El Balance y el Mayor se derivan de `journal_entry`/`journal_entry_line` + `account_plan` (SPEC-001/002) y no generan tablas propias.