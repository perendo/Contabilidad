# Quickstart Validation Guide: Remesas SEPA y Soporte Magnético (SPEC-020)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas, cuentas 430/432/662/572/570).

## Scenario 1 — Crear y emitir una remesa CORE con cobro manual

```bash
# 1) Crear remesa (recibo_ids se obtienen de la API de vencimientos de SPEC-011)
curl -X POST "$BASE/api/v1/remesas" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"formato":"SEPA_DD","tipo_adeudo":"CORE","recibo_ids":["<uuid1>","<uuid2>"]}'
# Espera: 201, id, numero_remesa, importe_total, n_recibos=2

# 2) Emitir → genera el fichero
curl -X POST "$BASE/api/v1/remesas/$REMESA_ID/emitir" -H "Authorization: Bearer $TOK"
# Espera: 200, estado=emitida, fichero.sha256

# 3) Descargar fichero
curl "$BASE/api/v1/remesas/$REMESA_ID/fichero" -H "Authorization: Bearer $TOK" -o remesa.xml
# Espera: 200, application/xml; remesa.xml contiene PAIN.008 válidado

# 4) Marcar cobro manual (más tarde)
curl -X POST "$BASE/api/v1/remesas/$REMESA_ID/recibos/$REC_ID/cobrar" \
  -H "Authorization: Bearer $TOK" \
  -d '{"fecha_cobro":"2026-10-01","cuenta":"5720000"}'
# Espera: 200, estado=cobrado, asiento_cobro_id != null

# 5) Verificar balance del asiento generado (pytest o consulta)
# Debe: 572 (neto) = 430 (total) - 432/662 (descuento si procede)
```

Validación pytest:
- `test_crear_remesa_aislada`: crea dos empresas, una remesa en la empresa A, vuelve a consultar desde empresa B → 404.
- `test_emitir_sepa_core_valido`: parsea el XML generado con esquema PAIN.008 y verifica `NbOfTxs`, `CtrlSum` y `InstdAmt`.
- `test_correlatividad_remesa`: crea dos remesas en el mismo ejercicio, verifica `numero_remesa` correlativo sin saltos.
- `test_plazo_cargo_rechazado`: remesa con fecha_cargo=D0 (hoy) que no cumple D-2 → emisión rechaza con 422 `plazo_presentacion`.

## Scenario 2 — Remesa B2B con mandato

```bash
# 1) Registrar mandato B2B
curl -X POST "$BASE/api/v1/terceros/$TER_ID/mandatos" \
  -H "Authorization: Bearer $TOK" \
  -d '{"mandato_ref":"MAND-2026-001","fecha_firma":"2026-09-15","tipo":"B2B"}'

# 2) Crear y emitir remesa B2B
curl -X POST "$BASE/api/v1/remesas" -H "Authorization: Bearer $TOK" \
  -d '{"formato":"SEPA_DD","tipo_adeudo":"B2B","recibo_ids":["<uuid1>"]}'
# La fecha de cargo se toma del vencimiento; el emisor valida D-1 para cada grupo.

curl -X POST "$BASE/api/v1/remesas/$REMESA_ID/emitir" -H "Authorization: Bearer $TOK"
# 200, fichero contiene MndtRltdInf con mandato
```

## Scenario 3 — Devolución R19 con REVERSAL

```bash
# 1) Importar devolución
curl -X POST "$BASE/api/v1/devoluciones/import" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"devoluciones":[{"recibo_id":"<recibo_cobrado>","codigo":"R19","motivo":"MD06 - Mandato rechazado","importe":"150.0000","importe_gastos":"5.0000","fecha_registro":"2026-10-05"}]}'
# 200, procesadas=1

# 2) Verificar:
#   - ReciboRemesa.estado = devuelto
#   - Vencimiento (SPEC-011) vuelve a pendiente
#   - JournalEntry de tipo REVERSAL creado con Debe==Haber
#     Debe: 430 (150.00) + 626 (5.00) | Haber: 572 (155.00)
#   - Asiento original del cobro NO fue modificado
```

Validación pytest:
- `test_devolucion_reversal.balance`: verifica Debe==Haber en el asiento REVERSAL.
- `test_devolucion_reversal.aislamiento`: empresa B no ve la devolución de A.
- `test_devolucion_ejercicio_cerrado`: rechaza 409 si el vencimiento está en ejercicio cerrado.

## Scenario 4 — Liquidación con descuento por pronto pago

```bash
# 1) Configurar condición de pronto pago
curl -X POST "$BASE/api/v1/terceros/$TER_ID/condiciones" \
  -H "Authorization: Bearer $TOK" \
  -d '{"plazo_dias":10,"porcentaje":2.00,"vigente":true}'

# 2) Liquidar antes de vencer con pronto pago
curl -X POST "$BASE/api/v1/recibos/$REC_ID/liquidar" \
  -H "Authorization: Bearer $TOK" \
  -d '{"fecha_pago":"2026-10-05","cuenta":"5720000"}'
# 200, importe_neto="98.0000", descuento="2.0000", asiento_id != null
# Asiento: Debe 572 (98) + 432/662 (2) | Haber 430 (100)
```

## Scenario 5 — Generación CSB 19.19 (alternativa)

```bash
# Crear y emitir en formato CSB 19.19
curl -X POST "$BASE/api/v1/remesas" -H "Authorization: Bearer $TOK" \
  -d '{"formato":"CSB_19_19","tipo_adeudo":"CORE","recibo_ids":["<uuid1>"]}'
curl -X POST "$BASE/api/v1/remesas/$REMESA_ID/emitir" -H "Authorization: Bearer $TOK"
curl "$BASE/api/v1/remesas/$REMESA_ID/fichero" -o remesa.1919
# Verifica: texto plano ISO-8859-15, registro tipo 1/3/5, importes en céntimos
```

Validación pytest:
- `test_csb1919_campos`: parsea la salida y verifica longitud de campo 1919.
- `test_csb1919_importe_total`: verifica registro tipo 5 con suma en céntimos.

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# Crear remesa en empresa A
curl -X POST "$BASE/api/v1/remesas" ... 
# Consultar la misma remesa desde empresa B
curl -X GET "$BASE/api/v1/remesas/$REMESA_ID" 
# 404 — nunca filtrar datos de otra empresa
```

## Scenario 7 — Confirmación por conciliación sin duplicar cobro

```bash
# SPEC-013 notifica el movimiento conciliado
curl -X POST "$BASE/api/v1/remesas/$REMESA_ID/recibos/$REC_ID/conciliar" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"movimiento_id":"<movimiento-uuid>","fecha_cobro":"2026-10-01","cuenta":"5720000"}'
# Espera: 200, estado=cobrado, asiento_cobro_id != null

# Repetir el mismo evento devuelve el asiento original
curl -X POST "$BASE/api/v1/remesas/$REMESA_ID/recibos/$REC_ID/conciliar" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"movimiento_id":"<movimiento-uuid>","fecha_cobro":"2026-10-01","cuenta":"5720000"}'
# Espera: 200, idempotente=true y el mismo asiento_cobro_id
```

Validación pytest:
- `test_cobro_conciliado_idempotente`: repetir el movimiento no crea un segundo asiento.
- `test_cobro_manual_y_conciliado_no_duplican`: ambos caminos sobre el mismo recibo conservan un único cobro.