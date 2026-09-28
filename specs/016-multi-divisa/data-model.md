# Data Model: Multi-Divisa (SPEC-016)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; tipos de cambio en `NUMERIC(18,8)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.
- Los asientos in divisa amplían SPEC-002 sin tocar los asientos en moneda funcional; los `POSTED` son inmutables.

## Moneda

Catálogo de divisas y moneda funcional por empresa.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id) |
| codigo_iso | CHAR(3) | ISO 4217 (EUR, USD, GBP, ...) |
| es_funcional | BOOLEAN | una y solo una funcional por empresa |
| activa | BOOLEAN | divisa usable en los asientos |

**Validaciones**: único `es_funcional=true` por empresa; las divisas de trabajo se registran con `es_funcional=false`, `activa=true`.

## TipoCambio

Ratio divisa → funcional fechado, sellado cuando se usa en posteados.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| divisa_id | UUID FK → Moneda | |
| fecha | DATE | uso para asientos de esa fecha |
| ratio | NUMERIC(18,8) | 1 divisa = ratio funcional; CHECK > 0 |
| usos_posteados | INT DEFAULT 0 | contador de asientos posteados que lo usan |
| sellado | BOOLEAN DEFAULT false | true si `usos_posteados > 0` |

**Validaciones**: único por `(empresa_id, divisa_id, fecha)`; si `sellado=true` → prohibido UPDATE/DELETE (constitución II, enforced en base de datos y API 409); una divisa funcional no tiene tipo (ratio 1, no se almacena).

**Transición de estado**: `no_usado → sellado` (al postear el primer asiento en divisa con ese tipo, mismo transacción ACID).

## AsientoDivisa

Extensión del asiento (SPEC-002) que lo etiqueta como en divisa.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| asiento_id | UUID FK → SPEC-002 JournalEntry | uno a uno |
| divisa_id | UUID FK → Moneda | divisa de trabajo de la empresa |
| tipo_cambio_id | UUID FK → TipoCambio | tipo de la fecha del asiento (sellado tras postear) |
| fecha | DATE | fecha de transacción (tipo de la fecha) |
| importe_total_divisa | NUMERIC(18,4) | Σ líneas en divisa (por signo); cuadra con la divisa |
| importe_total_funcional | NUMERIC(18,4) | Σ líneas convertidas más ajuste de redondeo |

**Validaciones**: el asiento cuadra en divisa (Debe==Haber en importes de divisa) y en funcional (Debe==Haber en equivalentes + ajuste de redondeo); el tipo de la fecha existe (o se exige explícito, D9 research).

## LineaDivisa

Importes en divisa por línea funcional (amplía SPEC-002/006 sin alterar `JournalEntryLine`).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| asiento_divisa_id | UUID FK → AsientoDivisa | |
| linea_id | UUID FK → SPEC-002 JournalEntryLine | una línea base por línea divisa |
| importe_divisa | NUMERIC(18,4) | importe en divisa de la línea (0 para la línea de ajuste de redondeo) |
| importe_funcional | NUMERIC(18,4) | equivalente redondeado 4 decimales |
| es_linea_redondeo | BOOLEAN DEFAULT false | la línea que absorbe el remanente (cuenta 668/769) |

**Validación**: Σ importe_divisa de débito == Σ importe_divisa de crédito (cuadre en divisa); Σ importe_funcional (con línea de redondeo) == Σ equivalente exacto (cuadre en funcional).

## DiferenciaCambio

Valoración a cierre de saldos en divisa con su asiento.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio | INT | ejercicio del cierre |
| fecha_valoracion | DATE | fecha de cierre (tipo de cierre) |
| cuenta_id | UUID FK → SPEC-001 (cuenta en divisa) | |
| divisa_id | UUID FK → Moneda | |
| saldo_divisa | NUMERIC(18,4) | saldo vivo en divisa |
| saldo_funcional_previo | NUMERIC(18,4) | saldo funcional pendiente antes de valorar |
| tipo_cierre_id | UUID FK → TipoCambio | tipo de la fecha de valoración |
| saldo_funcional_valorado | NUMERIC(18,4) | saldo_divisa × tipo_cierre |
| diferencia | NUMERIC(18,4) | = valorado − previo (signo → pérdida/ganancia) |
| asiento_id | UUID FK → SPEC-002 JournalEntry | asiento de diferencia (balanced, POSTED) vinculado al cierre |
| estado | ENUM | `calculada`, `asentada` |

**Validaciones**: el asiento de diferencia cuadra (Debe 668 / Haber 769 o viceversa por signo); único por `(empresa_id, ejercicio, fecha_valoracion, cuenta_id, divisa_id)` antes de asentar; ejercicio cerrado → 409.

## Resumen de relaciones

```
Empresa (SPEC-003) 1 ── n Moneda (una funcional)
Moneda (divisa) 1 ── n TipoCambio
TipoCambio 1 ── 0..1 AsientoDivisa.tipo_cambio_id (sellado)
JournalEntry (SPEC-002) 1 ── 0..1 AsientoDivisa
AsientoDivisa 1 ── n LineaDivisa
JournalEntryLine (SPEC-002) 1 ── 0..1 LineaDivisa
Cuenta (SPEC-001) 1 ── n DiferenciaCambio (cuenta en divisa)
TipoCambio 1 ── 1 DiferenciaCambio.tipo_cierre_id
Cierre (SPEC-004) 1 ── n DiferenciaCambio (vinculado al cierre)
```