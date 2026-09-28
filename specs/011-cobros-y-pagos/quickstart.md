# Quickstart Validation Guide: Vencimientos, Cobros y Pagos (SPEC-011)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed minimo (empresa, plan de cuentas con cuentas 430/400/572/570, factura de venta con vencimientos generados por SPEC-007).

## Scenario 1 — Cobrar un vencimiento total

```bash
# 1) Listar vencimientos pendientes
curl "$BASE/api/v1/vencimientos?estado=pendiente" -H "Authorization: Bearer $TOK"
# Espera: items con saldo_pendiente > 0

# 2) Cobrar el vencimiento
curl -X POST "$BASE/api/v1/vencimientos/$VENC_ID/cobrar" \
  -H "Authorization: Bearer $TOK" \
  -d '{"fecha": "2026-10-01", "importe": "1500.0000", "cuenta_tesoreria": "5720000"}'
# Espera: 200, estado=cobrado, saldo_pendiente=0.0000, journal_entry_id != null

# 3) Verificar asiento generado (Debe 572 | Haber 430)
curl "$BASE/api/v1/vencimientos/$VENC_ID/cobros" -H "Authorization: Bearer $TOK"
# Espera: cobro con journal_entry_id; balance Debe==Haber verificado en backend

# 4) Intentar cobrar de nuevo -> 409 vencimiento_saldado
```

Validacion pytest:
- `test_cobro_total_asiento_balance`: asiento Debe 572 == Haber 430 con Decimal exacto.
- `test_cobro_vencimiento_saldado`: segundo cobro -> 409.

## Scenario 2 — Parciales acumulados

```bash
# Vencimiento de 300.0000 en 3 parciales de 100.0000
curl -X POST "$BASE/api/v1/vencimientos/$VENC_ID/cobrar" \
  -H "Authorization: Bearer $TOK" -d '{"fecha":"2026-10-01","importe":"100.0000","cuenta_tesoreria":"5720000"}'
# Espera: estado=parcial, saldo_pendiente=200.0000

curl -X POST "$BASE/api/v1/vencimientos/$VENC_ID/cobrar" \
  -H "Authorization: Bearer $TOK" -d '{"fecha":"2026-10-02","importe":"100.0000","cuenta_tesoreria":"5720000"}'
# Espera: estado=parcial, saldo_pendiente=100.0000

curl -X POST "$BASE/api/v1/vencimientos/$VENC_ID/cobrar" \
  -H "Authorization: Bearer $TOK" -d '{"fecha":"2026-10-03","importe":"100.0000","cuenta_tesoreria":"5720000"}'
# Espera: estado=cobrado, saldo_pendiente=0.0000

# Exceso -> 422 exceso_importe
curl -X POST "$BASE/api/v1/vencimientos/$VENC_ID/cobrar" \
  -H "Authorization: Bearer $TOK" -d '{"fecha":"2026-10-03","importe":"300.0000","cuenta_tesoreria":"5720000"}'
# Espera: 422 exceso_importe
```

Validacion pytest:
- `test_parciales_no_exceden`: acumulado nunca supera importe; cierre exacto al igualar.
- `test_parciales_precision`: 1/3 de 1.0000 en 3 parciales suma exacta 1.0000 sin redondeo.

## Scenario 3 — Pago a proveedor

```bash
# Vencimiento de pago de 800.0000 (factura de compra)
curl -X POST "$BASE/api/v1/vencimientos/$VENC_PAGO_ID/pagar" \
  -H "Authorization: Bearer $TOK" \
  -d '{"fecha":"2026-10-05","importe":"800.0000","cuenta_tesoreria":"5700000"}'
# Espera: 200, estado=cobrado (saldado), asiento Debe 400 | Haber 570
```

Validacion pytest:
- `test_pago_caja_direccion`: asiento con cuenta de caja (570) cuando se configura.

## Scenario 4 — Remesa de agrupacion (borrador y emitida)

```bash
# 1) Crear remesa con 2 vencimientos pendientes
curl -X POST "$BASE/api/v1/remesas" -H "Authorization: Bearer $TOK" \
  -d '{"tipo":"cobro","fecha_cargo_prevista":"2026-11-01","vencimiento_ids":["<v1>","<v2>"]}'
# Espera: 201, numero_remesa=1, importe_total=suma de saldos, estado=borrador

# 2) Emitir la remesa (sin fichero; SEPA/CSB es SPEC-020)
curl -X POST "$BASE/api/v1/remesas/$REMESA_ID/emitir" \
  -H "Authorization: Bearer $TOK" -d '{"fecha_emision":"2026-10-15"}'
# Espera: 200, estado=emitida, n_vencimientos_remesados=2

# 3) Los vencimientos pasan a estado remesado
curl "$BASE/api/v1/vencimientos?estado=remesado" -H "Authorization: Bearer $TOK"
# Espera: items con los 2 vencimientos

# 4) Intentar crear remesa con vencimiento ya remesado -> 409
```

Validacion pytest:
- `test_remesa_agrupacion_estado`: vencimientos pasan a remesado y remesa calcula importe_total.
- `test_remesa_vencimiento_repetido`: vencimiento en dos remesas -> 409.

## Scenario 5 — Informe de antiguedad de saldos

```bash
# Con un vencimiento pendiente de hace 45 dias y otro de hace 95 dias:
curl "$BASE/api/v1/antiguedad" -H "Authorization: Bearer $TOK"
# Espera: items por tercero con rango_60 (para el de 45 dias) y rango_90mas (para el de 95 dias)
# Validacion: suma(rango_30+rango_60+rango_90+rango_90mas) == saldo_total_pendiente
```

Validacion pytest:
- `test_antiguedad_rangos`: clasifica correctamente 0-29/30-59/60-89/90+ segun fecha.
- `test_antiguedad_suma_rangos`: suma de rangos == saldo pendiente total.

## Scenario 6 — Aislamiento multi-empresa (constitucion III)

```bash
# Empresa A cobra su vencimiento
curl -X POST "$BASE/api/v1/vencimientos/$VENC_A/cobrar" \
  -H "Authorization: Bearer $TOK_A" -d '{"fecha":"2026-10-01","importe":"1500.0000","cuenta_tesoreria":"5720000"}'
# Espera: 200

# Empresa B intenta consultar/cobrar el vencimiento de A
curl "$BASE/api/v1/vencimientos/$VENC_A" -H "Authorization: Bearer $TOK_B"
# Espera: 404

curl -X POST "$BASE/api/v1/vencimientos/$VENC_A/cobrar" \
  -H "Authorization: Bearer $TOK_B" -d '{"fecha":"2026-10-01","importe":"1500.0000","cuenta_tesoreria":"5720000"}'
# Espera: 404 (recurso no visible en la empresa activa)
```

Validacion pytest:
- `test_tesoreria_aislamiento_total`: empress A no ve ni opera sobre vencimientos/cobros/remesas/antiguedad de B.