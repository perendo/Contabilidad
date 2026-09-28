# Data Model: Amortizaciones del Inmovilizado (SPEC-014)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`. Porcentajes en `NUMERIC(5,2)`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.
- Los asientos los crea el motor de SPEC-002 (balance Debe==Haber y numeración correlativa); los `POSTED` nunca se modifican.

## ActivoInmovilizado

Elemento del inmovilizado (cuenta 21x).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id) |
| numero_activo | VARCHAR(40) | identificador del activo legible; único por empresa |
| cuenta_id | UUID FK → SPEC-001 Cuenta (21x) | cuenta del activo; del plan de la empresa activa |
| descripcion | VARCHAR(255) | |
| fecha_alta | DATE | inicio del plan |
| coste_amortizable | NUMERIC(18,4) | > 0 |
| vida_util | INT | en períodos (meses por defecto); > 0 |
| metodo | ENUM | `lineal` / `regresivo` |
| porcentaje_regresivo | NUMERIC(5,2) NULL | requerido si `metodo = regresivo` |
| estado | ENUM | `en_uso`, `dado_de_baja` |
| fecha_baja | DATE NULL | si estado = dado_de_baja |
| cuenta_gasto_id | UUID FK → SPEC-001 (681 por defecto) | grupo configurado |
| cuenta_acumulada_id | UUID FK → SPEC-001 (281XXX según cuenta) | grupo configurado |

**Validaciones**: (coste, vida_util, método) coherentes — `coste > 0`, `vida_util > 0`, `porcentaje` en (0, 100) si regresivo; el plan nunca supera el coste (FR-006).

**Transición de estado**: `en_uso → dado_de_baja` (baja/venta, con fecha_baja).

## PlanAmortizacion

Detalle calculado del plan por período (vigente mientras el activo está en uso).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| activo_id | UUID FK → ActivoInmovilizado | |
| ejercicio | INT | |
| periodo | INT | 1..12 (o período definido); único por (empresa_id, activo_id, ejercicio, periodo) |
| cuota | NUMERIC(18,4) | cuota del período; última ajustada a `coste − Σ previas` |
| acumulado | NUMERIC(18,4) | amortización acumulada tras este período |
| estado | ENUM | `pendiente`, `amortizado` |

**Validaciones**: `acumulado <= coste_amortizable` (FR-006) — constraint CHECK y regla de servicio; la última cuota = `coste − Σ cuotas anteriores` (>= 0); a partir de ejercicios o períodos cerrados el plan se marca `pendiente` sin generarse.

**Transición**: `pendiente → amortizado` (al generar el asiento del período).

## AmortizacionGenerada

Registro de asiento de amortización generado por el motor. Garantiza la antidupilcación (FR-003).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| activo_id | UUID FK → ActivoInmovilizado | |
| ejercicio | INT | |
| periodo | INT | |
| asiento_id | UUID FK → SPEC-002 JournalEntry | asiento 681/281 generado (POSTED) |
| cuota | NUMERIC(18,4) | misma del plan |
| reapertura_de | UUID NULL → AmortizacionGenerada | si esta generación anula a una previa (REVERSAL) |

**Validaciones**: único por `(empresa_id, activo_id, ejercicio, periodo)` (constraint UNIQUE + índice) — segunda generación → 409 o flujo de reapertura; el asiento referenciado es balanceado (motor SPEC-002).

## BajaActivo

Registro de baja/venta con su asiento.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| activo_id | UUID FK → ActivoInmovilizado | único por activo |
| fecha_baja | DATE | |
| precio_venta | NUMERIC(18,4) | 0 en retirada |
| amortizacion_hasta_baja | NUMERIC(18,4) | cuota prorrateada hasta la baja (período parcial, D2 research) |
| amortizacion_acumulada | NUMERIC(18,4) | total acumulado a la fecha de baja |
| valor_neto_contable | NUMERIC(18,4) | = coste − amortización acumulada |
| resultado | NUMERIC(18,4) | = precio_venta − VNC (positivo 771 / negativo 671) |
| asiento_id | UUID FK → SPEC-002 JournalEntry | asiento de baja balanceado (POSTED) |
| tipo | ENUM | `venta`, `retirada` |

**Validaciones**: la amortización hasta la baja se prorratea (D5 research); `VNC`, `resultado` exactos con `Decimal`; asiento balanceado generado por SPEC-002 (Debe 281 + 572/570; Haber 21x; saldo → 671/771).

## Resumen de relaciones

```
Cuenta (SPEC-001, 21x) 1 ── n ActivoInmovilizado
ActivoInmovilizado 1 ── n PlanAmortizacion
ActivoInmovilizado 1 ── 0..1 BajaActivo
ActivoInmovilizado 1 ── n AmortizacionGenerada
Asiento (SPEC-002) 1 ── 0..1 AmortizacionGenerada.asiento_id
Asiento (SPEC-002) 1 ── 0..1 BajaActivo.asiento_id
```