# Quickstart Validation Guide: Multi-Divisa (SPEC-016)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa con moneda funcional EUR, divisa de trabajo USD, plan de cuentas con cuenta en divisa 4300 y cuentas 668/769, motor de asientos SPEC-002 operativo, ejercicio abierto). Contratos en [contracts/](contracts/), modelo en [data-model.md](data-model.md).

## Scenario 1 — Registrar divisa y tipos de cambio

```bash
# 1) Registrar USD como divisa de trabajo
curl -X POST "$BASE/api/v1/divisas" -H "Authorization: Bearer $TOK" \
  -d '{"codigo_iso":"USD","activa":true}'
# Espera: 201, es_funcional=false

# 2) Registrar un tipo para una fecha
curl -X POST "$BASE/api/v1/tipos-cambio" -H "Authorization: Bearer $TOK" \
  -d '{"divisa_id":"<usd_id>","fecha":"2026-10-01","ratio":"1.08500000"}'
# Espera: 201, sellado=false

# 3) Intentar registrar de nuevo la misma (divisa, fecha)
# Espera: 409 — único por (empresa, divisa, fecha)
```

Validación pytest:
- `test_tipo_cambio_unicidad`: (divisa, fecha) duplicado → 409.
- `test_tipo_aislamiento`: el tipo de A no aparece en la consulta de B; B no puede usarlo (404).

## Scenario 2 — Registrar un asiento en divisa cuadrando en ambas monedas

```bash
curl -X POST "$BASE/api/v1/asientos-divisa" -H "Authorization: Bearer $TOK" \
  -d '{"fecha":"2026-10-01","divisa_id":"<usd_id>",
       "lineas":[
         {"cuenta_id":"<cuenta_4300>","debe_divisa":"1000.0000","haber_divisa":"0.0000"},
         {"cuenta_id":"<cuenta_572>","debe_divisa":"0.0000","haber_divisa":"1000.0000"}
       ]}'
# Espera: 201; importe_total_divisa="1000.0000"
# Equivalente funcional de cada línea: 1000 × 1.085 = 1085.0000 → Debe==Haber en funcional también

# 2) Consultar el detalle
curl "$BASE/api/v1/asientos-divisa/$ASIENTO_ID" -H "Authorization: Bearer $TOK"
# Espera: líneas con debe/haber en divisa y en funcional; ratio y tipo sellado=true
```

Validación pytest:
- `test_cuadre_doble_moneda`: asiento con multas en divisa y funcional (Debe==Haber `Decimal` en ambas); fixture con cuadre a mano.
- `test_registro_sin_tipo`: sin tipo para la fecha ni tipo explícito → 422.
- `test_tipo_explicito_persiste`: el ratio explícito del body queda como tipo de la fecha y se sella al postear.

## Scenario 3 — Redondeo que nunca desequilibra

```bash
# Operación con dos líneas de débito en divisa contra un crédito funcional no divisible a 4 decimales
curl -X POST "$BASE/api/v1/asientos-divisa" ... # 3 líneas con equivalencias que dejan remanente
# Espera: 201 con linea_redondeo (cuenta 668/769, importe del remanente) — el asiento cuadra exacto en funcional
```

Validación pytest:
- `test_redondeo_half_even`: cada línea funcional usa ROUND_HALF_EVEN a 4 decimales.
- `test_remanente_imputado`: suma de líneas funcionales == total exacto cuando existe remanente; la diferencia va a la línea de redondeo.
- `test_redondeo_nunca_desequilibra`: invariante: Σ Debe funcional == Σ Haber funcional — probado con casuística de remanentes.

## Scenario 4 — Sellar el tipo de cambio (inmutabilidad)

```bash
# 1) Intentar corregir el tipo usado por el asiento posteado
curl -X PATCH "$BASE/api/v1/tipos-cambio/$TIPO_ID" -H "Authorization: Bearer $TOK" \
  -d '{"ratio":"1.20000000","motivo":"intento"}'
# Espera: 409 — sellado, no modificable (constitución II)

# 2) Consultar el histórico del asiento
curl "$BASE/api/v1/tipos-cambio/historial?asiento_id=$ASIENTO_ID" -H "Authorization: Bearer $TOK"
# Espera: el mismo ratio 1.08500000 — reproducible
```

Validación pytest:
- `test_tipo_sellado_bloqueado`: PATCH/DELETE de tipo con usos_posteados>0 → 409; DB rejection directo también.
- `test_historial_por_asiento`: el tipo consultado coincide con el usado (FR-003).
- `test_sellado_atomico`: si el asiento falla tras sellar, la transacción revierte el sello (misma ACID).

## Scenario 5 — Valoración a cierre y diferencias de cambio

```bash
# 1) Fijar el tipo de cierre
curl -X POST "$BASE/api/v1/tipos-cambio" -H "Authorization: Bearer $TOK" \
  -d '{"divisa_id":"<usd_id>","fecha":"2026-12-31","ratio":"1.10000000"}'

# 2) Valorar los saldos en divisa al cierre
curl -X POST "$BASE/api/v1/valoraciones" -H "Authorization: Bearer $TOK" \
  -d '{"ejercicio":2026,"fecha_valoracion":"2026-12-31"}'
# Espera: 200; por cuenta en divisa, diferencia = saldo_divisa × 1.10 − saldo_funcional_pendiente
# y asiento balanceado (Debe 668 pérdida / Haber 769 ganancia según signo)

# 3) Intentar valorar de nuevo el mismo período
# Espera: 409 (no duplica; única por ejercicio/fecha/cuenta/divisa)
```

Validación pytest:
- `test_diferencia_cambio_exacta`: cálculo con `Decimal`, signo correcto (pérdida/ganancia), asiento balanceado.
- `test_valoracion_vinculada_cierre`: el asiento referencia naturalmente sería SPEC-004; ejercicio cerrado → 409 (no se abre el cierre, Assumptions).
- `test_valoracion_duplicada`: segunda valoración del mismo (ejercicio, fecha, cuenta, divisa) → 409.

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# Empresa A registra tipo USD/1.085 y un asiento en divisa; empresa B consulta el mismo asiento/tipo
curl -X GET "$BASE/api/v1/asientos-divisa/$ASIENTO_A" -H "Authorization: Bearer $TOK_B"
# Espera: 404 — nunca filtra datos de otra empresa; B tiene su propia moneda funcional y tipos
```