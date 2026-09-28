# Quickstart Validation Guide: Anticipos, Fondos a Cuenta y Cesión de Cobros (SPEC-022)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas, cuentas 438/407/430/572/662, tercero con facturas y vencimientos de SPEC-007/011).

## Scenario 1 — Anticipo de cliente y liquidación

```bash
# 1) Registrar anticipo de cliente
curl -X POST "$BASE/api/v1/anticipos" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"tercero_id":"<cli_uuid>","tipo":"CLIENTE","fecha":"2026-09-15","importe":"3000.0000","concepto":"Anticipo curso formación"}'
# Espera: 201, saldo_pendiente="3000.0000", asiento_id != null

# 2) Liquidar contra factura
curl -X POST "$BASE/api/v1/anticipos/$ANT_ID/liquidar" -H "Authorization: Bearer $TOK" \
  -d '{"aplicaciones":[{"factura_id":"<fact_uuid>","importe_aplicado":"2000.0000"}],"fecha_aplicacion":"2026-10-01"}'
# Espera: 200, saldo_pendiente="1000.0000"

# 3) Verificar asiento de liquidación
# Debe: 430 (2000.0000) | Haber: 438 (2000.0000)
# El anticipo queda con saldo 1000 pendiente
```

Validación pytest:
- `test_anticipo_cliente_balance`: Debe==Haber en asiento de anticipo (572 vs 438).
- `test_liquidacion_balance`: Debe==Haber en asiento de liquidación (430 vs 438).
- `test_anticipo_aislamiento`: empresa B no ve el anticipo de empresa A.

## Scenario 2 — Anticipo a proveedor y liquidación

```bash
# 1) Registrar anticipo a proveedor
curl -X POST "$BASE/api/v1/anticipos" -H "Authorization: Bearer $TOK" \
  -d '{"tercero_id":"<prov_uuid>","tipo":"PROVEEDOR","fecha":"2026-09-15","importe":"1500.0000","concepto":"Anticipo material"}'
# Espera: 201, saldo_pendiente="1500.0000"

# 2) Liquidar contra factura de compra
curl -X POST "$BASE/api/v1/anticipos/$ANT_ID/liquidar" -H "Authorization: Bearer $TOK" \
  -d '{"aplicaciones":[{"factura_id":"<fact_compra_uuid>","importe_aplicado":"1500.0000"}],"fecha_aplicacion":"2026-10-05"}'
# Espera: 200, saldo_pendiente="0.0000", estado="totalmente_aplicado"

# 3) Verificar asiento
# Debe: 407 (1500.0000) | Haber: 572 (1500.0000) al registrar
# Debe: 410 (1500.0000) | Haber: 407 (1500.0000) al liquidar
```

## Scenario 3 — Cesión de cobros (factoring) con comisión

```bash
# 1) Crear cesión con 2 vencimientos
curl -X POST "$BASE/api/v1/cesiones" -H "Authorization: Bearer $TOK" \
  -d '{"entidad_financiera":"Banco Factor S.A.","fecha_cesion":"2026-10-01","vencimiento_ids":["<venc1>","<venc2>"],"comision":"150.0000","tipo_comision":"IMPORTE_FIJO"}'
# Espera: 201, importe_total_cedido calculado, comision="150.0000", importe_neto_recibido calculado

# 2) Verificar asiento de cesión
# Debe: 572 (neto) + 662 (150.0000) | Haber: 430 (total cedido)
# Los vencimientos pasan a estado "cedido"

# 3) Registrar notificación al cliente
curl -X POST "$BASE/api/v1/cesiones/$CES_ID/notificar" -H "Authorization: Bearer $TOK" \
  -d '{"cliente_id":"<cli_uuid>","medio":"EMAIL","fecha_notificacion":"2026-10-01"}'
# 200: notificacion_id, estado=enviada
```

## Scenario 4 — Impedir doble cobro

```bash
# Intentar cobrar vencimiento ya cedido
curl -X POST "$BASE/api/v1/vencimientos/$VENC_CEDIDO/cobrar" -H "Authorization: Bearer $TOK" \
  -d '{"fecha_cobro":"2026-10-05","cuenta":"5720000"}'
# 409: vencimiento_ya_cedido
```

## Scenario 5 — Saldo excedente de anticipo

```bash
# Liquidar anticipo de 3000 contra factura de 2000
curl -X POST "$BASE/api/v1/anticipos/$ANT_ID/liquidar" -H "Authorization: Bearer $TOK" \
  -d '{"aplicaciones":[{"factura_id":"<fact_uuid>","importe_aplicado":"2000.0000"}],"fecha_aplicacion":"2026-10-01"}'
# 200, saldo_pendiente="1000.0000" (exceso a favor del cliente)

# Verificar saldo del anticipo
curl "$BASE/api/v1/anticipos/$ANT_ID" -H "Authorization: Bearer $TOK"
# saldo_pendiente="1000.0000"
```

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# Crear anticipo en empresa A
curl -X POST "$BASE/api/v1/anticipos" -H "Authorization: Bearer $TOK_A" \
  -d '{"tercero_id":"<terceroA>","tipo":"CLIENTE","fecha":"2026-09-15","importe":"1000.0000","concepto":"Test"}'

# Consultar desde empresa B → 404
curl "$BASE/api/v1/anticipos/$ANT_ID" -H "Authorization: Bearer $TOK_B"
# 404 — nunca filtrar datos de otra empresa
```
