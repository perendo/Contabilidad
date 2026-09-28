# Quickstart Validation Guide: Medios de Pago y Efectos (SPEC-021)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas, cuentas 431/430/572/626, tercero con vencimiento pendiente de SPEC-011).

## Scenario 1 — Registrar y cobrar un efecto (cheque)

```bash
# 1) Registrar efecto
curl -X POST "$BASE/api/v1/efectos" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"tercero_id":"<tercero_uuid>","tipo_efecto":"CHEQUE","numero_documento":"CHQ-001","fecha_emision":"2026-09-15","fecha_vencimiento":"2026-10-15","importe":"2500.0000"}'
# Espera: 201, id, estado=emitido

# 2) Cobrar el efecto
curl -X POST "$BASE/api/v1/efectos/$EFFECT_ID/cobrar" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"fecha_cobro":"2026-10-15","cuenta_banco":"5720000"}'
# Espera: 200, estado=cobrado, asiento_cobro_id != null

# 3) Verificar balance del asiento
# Debe: 572 (2500.0000) | Haber: 431 (2500.0000)
```

Validación pytest:
- `test_cobro_efecto_balance`: Debe==Haber en el asiento de cobro.
- `test_cobro_efecto_aislamiento`: empresa B no ve el efecto de empresa A.

## Scenario 2 — Registrar impago de una letra

```bash
# 1) Registrar efecto letra
curl -X POST "$BASE/api/v1/efectos" -H "Authorization: Bearer $TOK" \
  -d '{"tercero_id":"<tercero_uuid>","tipo_efecto":"LETRA","numero_documento":"LET-001","fecha_emision":"2026-09-01","fecha_vencimiento":"2026-10-01","importe":"1200.0000"}'

# 2) Registrar impago
curl -X POST "$BASE/api/v1/efectos/$EFFECT_ID/impago" -H "Authorization: Bearer $TOK" \
  -d '{"fecha_impago":"2026-10-02","motivo":"Fondos insuficientes","gastos_devolucion":"35.0000"}'
# Espera: 200, estado=impagado, asiento_impago_id != null

# 3) Verificar asiento REVERSAL
# Debe: 431 (1200.0000) + 626 (35.0000) | Haber: 572 (1235.0000)
# El vencimiento vuelve a pendiente (SPEC-011)
```

Validación pytest:
- `test_impago_reversal_balance`: Debe==Haber con gastos.
- `test_impago_reapertura_vencimiento`: vencimiento vuelve a pendiente.
- `test_impago_no_modifica_asiento_original`: asiento de cobro original intacto.

## Scenario 3 — Cobro por TPV con comisión

```bash
# 1) Registrar cobro por tarjeta con comisión
curl -X POST "$BASE/api/v1/cobros-medio" -H "Authorization: Bearer $TOK" \
  -d '{"vencimiento_id":"<venc_uuid>","medio_cobro":"TARJETA","fecha_cobro":"2026-10-05","cuenta_banco":"5720000","importe_comision":"25.0000"}'
# Espera: 201, importe_neto calculado, asiento_cobro_id != null

# 2) Verificar asiento
# Debe: 572 (neto = total - 25) + 626 (25.0000) | Haber: 430 (total)
```

## Scenario 4 — Cartera de efectos (consulta)

```bash
# Consultar cartera solo efectos pendientes
curl "$BASE/api/v1/efectos?estado=emitido" -H "Authorization: Bearer $TOK"
# 200: lista de efectos emitidos con tercero, vencimiento e importe

# Filtrar por tipo y rango de fechas
curl "$BASE/api/v1/efectos?tipo_efecto=LETRA&fecha_vencimiento[gte]=2026-10-01&fecha_vencimiento[lte]=2026-12-31" -H "Authorization: Bearer $TOK"
```

## Scenario 5 — Rechazo por ejercicio cerrado

```bash
# Intentar cobrar efecto en ejercicio cerrado
curl -X POST "$BASE/api/v1/efectos/$EFFECT_ID/cobrar" -H "Authorization: Bearer $TOK" \
  -d '{"fecha_cobro":"2025-12-31","cuenta_banco":"5720000"}'
# 409: ejercicio_cerrado
```

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# Crear efecto en empresa A
curl -X POST "$BASE/api/v1/efectos" -H "Authorization: Bearer $TOK_A" \
  -d '{"tercero_id":"<terceroA>","tipo_efecto":"PAGARE","numero_documento":"PAG-001","fecha_emision":"2026-09-15","fecha_vencimiento":"2026-11-15","importe":"800.0000"}'

# Consultar desde empresa B → 404
curl "$BASE/api/v1/efectos/$EFFECT_ID" -H "Authorization: Bearer $TOK_B"
# 404 — nunca filtrar datos de otra empresa
```
