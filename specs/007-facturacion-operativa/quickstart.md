# Quickstart Validation Guide: Facturación Operativa (SPEC-007)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas con cuentas 430/410/700/477/472/475/473/600, configuración de IVA/IRPF por empresa, ejercicio abierto 2026, un tercero cliente y un proveedor de SPEC-008).

## Scenario 1 — Crear factura de venta con IVA y emitir

```bash
# 1) Crear serie
SERIE_ID=$(curl -X POST "$BASE/api/v1/facturacion/series" \
  -H "Authorization: Bearer $TOK" \
  -d '{"codigo":"FV","nombre":"Facturas de venta","prefijo":"FV","sufijo":""}' | jq -r '.id')

# 2) Crear factura borrador con 2 líneas
FACT_ID=$(curl -X POST "$BASE/api/v1/facturacion/facturas" \
  -H "Authorization: Bearer $TOK" \
  -d '{
    "serie_id": "'"$SERIE_ID"'", "ejercicio": 2026, "fecha": "2026-01-20",
    "tipo": "VENTA", "tercero_id": "'"$CLIENTE_ID"'", "concepto_global": "Venta de material",
    "lineas": [
      {"descripcion":"Material A","cantidad":"2.0000","precio_unitario":"250.0000","porcentaje_descuento":"0.0000","tipo_iva":"21.00","tipo_recargo":"0.00","tipo_irpf":"0.00","base_irpf":"0.0000"},
      {"descripcion":"Material B","cantidad":"1.0000","precio_unitario":"100.0000","porcentaje_descuento":"5.00","tipo_iva":"21.00","tipo_recargo":"0.00","tipo_irpf":"0.00","base_irpf":"0.0000"}
    ]
  }' | jq -r '.id')

# 3) Emitir → número + asiento
curl -X POST "$BASE/api/v1/facturacion/facturas/$FACT_ID/emitir" \
  -H "Authorization: Bearer $TOK"
# Espera: 200, numero="FV1", estado=emitida, importe_base="595.0000" (2x250 + 95), 
#         importe_iva="124.9500", importe_total="719.9500", asiento_id != null
```

Validación pytest:
- `test_emitir_factura_numero_correlativo`: verifica numero FV1, correlativo en seguidas.
- `test_emitir_factura_asiento_balanceado`: asiento Debe==Haber, Debe 430 = base+IVA, Haber 700+477.
- `test_calculo_impuestos_decimal`: base/IVA/IRPF exactos a 4 decimales, sin error de redondeo.

## Scenario 2 — Factura con IRPF (retención)

```bash
# Emitir factura cuya línea tiene tipo_irpf=15 (actividad profesional)
curl -X POST "$BASE/api/v1/facturacion/facturas" \
  -H "Authorization: Bearer $TOK" \
  -d '{
    "serie_id": "'"$SERIE_ID"'", "ejercicio": 2026, "fecha": "2026-01-21",
    "tipo": "VENTA", "tercero_id": "'"$CLIENTE_ID"'", "concepto_global": "Servicio profesional",
    "lineas": [
      {"descripcion":"Servicio","cantidad":"1.0000","precio_unitario":"1000.0000","porcentaje_descuento":"0.0000","tipo_iva":"21.00","tipo_recargo":"0.00","tipo_irpf":"15.00","base_irpf":"1000.0000"}
    ]
  }'
# Emitir → importe_iva="210.0000", importe_irpf="150.0000", importe_total="1060.0000"
# Asiento: Debe 430 (1060) | Haber 700 (1000) + 477 (210) − 475 (150)... balanceado
```

Validación pytest:
- `test_factura_irpf_retencion`: verifica importe_irpf y asiento con 475.
- `test_cuadre_base_importes`: verifica que base+IVA−IRPF == importe_total exacto.

## Scenario 3 — Rectificativa (abono) especi 002/006

```bash
# Rectificar la factura FV1
curl -X POST "$BASE/api/v1/facturacion/facturas/$FACT_ID/rectificar" \
  -H "Authorization: Bearer $TOK" \
  -d '{"serie_id":"'"$SERIE_ID"'","motivo":"Error en importe"}'
# Espera: 201, factura_rectificativa_id, numero="FV2", asiento_reversal_id != null

# Verificar:
# - Asiento original NO fue modificado
# - Nuevo asiento REVERSAL con líneas invertidas, balanceado (Debe==Haber)
# - factura_original_id en la RECTIFICATIVA apunta a la original
```

Validación pytest:
- `test_rectificativa_reversal_balanceado`: verifica REVERSAL balanceado e invertido.
- `test_rectificativa_original_intacto`: verifica que el asiento original no cambió.
- `test_rectificativa_sobre_rectificada`: se admite enlazando a la original.

## Scenario 4 — Recargo de equivalencia (FR-010)

```bash
# Empresa configurada en recargo de equivalencia (tipo_recargo=5.20 en líneas)
curl -X POST "$BASE/api/v1/facturacion/facturas" \
  -H "Authorization: Bearer $TOK" \
  -d '{
    "serie_id": "'"$SERIE_ID"'", "ejercicio": 2026, "fecha": "2026-01-22",
    "tipo": "VENTA", "tercero_id": "'"$CLIENTE_ID"'", "concepto_global": "Venta con recargo",
    "lineas": [
      {"descripcion":"Mercancía","cantidad":"1.0000","precio_unitario":"100.0000","porcentaje_descuento":"0.0000","tipo_iva":"21.00","tipo_recargo":"5.20","tipo_irpf":"0.00","base_irpf":"0.0000"}
    ]
  }'
# Emitir → importe_iva="21.0000", importe_recargo="5.2000", importe_total="126.2000"
# Asiento: Debe 430 (126.20) | Haber 700 (100) + 477 IVA (21) + 477 RECARGO (5.20) → balanceado
```

Validación pytest:
- `test_recargo_equivalencia_cuota_separada`: verifica importe_recargo en cuenta separada 477/472 recargo.
- `test_recargo_equivalencia_balanceado`: asiento balanceado con cuota recargo separada.

## Scenario 5 — Criterio de caja (FR-011)

```bash
# Empresa en régimen de criterio de caja (regimen_caja=true)
curl -X POST "$BASE/api/v1/facturacion/facturas" \
  -H "Authorization: Bearer $TOK" \
  -d '{
    "serie_id": "'"$SERIE_ID"'", "ejercicio": 2026, "fecha": "2026-01-23",
    "tipo": "VENTA", "tercero_id": "'"$CLIENTE_ID"'", "concepto_global": "Venta con criterio de caja",
    "lineas": [
      {"descripcion":"Mercancía","cantidad":"1.0000","precio_unitario":"100.0000","porcentaje_descuento":"0.0000","tipo_iva":"21.00","tipo_recargo":"0.00","tipo_irpf":"0.00","base_irpf":"0.0000"}
    ]
  }'
# Emitir → regimen_caja=true, iva_devengado=false, importe_total="121.0000"
# El IVA 21.00 queda en 477 como diferido; SPEC-012 lo devengará al cobro
```

Validación pytest:
- `test_criterio_caja_iva_diferido`: verifica regimen_caja=true, iva_devengado=false.
- `test_criterio_caja_iva_integro`: verifica que la factura lleva el IVA íntegro (no 0).

## Scenario 6 — Bloqueo de ejercicio cerrado y aislamiento

```bash
# Emitir factura con fecha en ejercicio cerrado (2025)
curl -X POST "$BASE/api/v1/facturacion/facturas" ... # fecha 2025-12-20
# Emitir → 400 "La fecha pertenece a un ejercicio cerrado"

# Aislamiento: empresa A emite factura, empresa B consulta
curl "$BASE/api/v1/facturacion/facturas/$FACT_A" -H "Authorization: Bearer $TOK_B"
# Espera: 404
```

Validación pytest:
- `test_ejercicio_cerrado_rechazado`: 400 al emitir en ejercicio cerrado.
- `test_aislamiento_empresa_factura`: B no ve factura de A (listado ni detalle).