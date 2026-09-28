# Quickstart Validation Guide: Impuesto sobre Sociedades (Modelo 200) (SPEC-023)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa con ejercicio cerrado en SPEC-004, cuentas 630/473/4752/4709, configuración fiscal con tipo 25%).

## Scenario 1 — Calcular IS con ajustes y pagos a cuenta

```bash
# 1) Registrar ajustes extracontables
curl -X POST "$BASE/api/v1/fiscal/is/calculos/$CALC_ID/ajustes" -H "Authorization: Bearer $TOK" \
  -d '{"tipo":"AJUSTE_POSITIVO","descripcion":"Diferencias temporarias no deducibles","importe":"12000.0000"}'

curl -X POST "$BASE/api/v1/fiscal/is/calculos/$CALC_ID/ajustes" -H "Authorization: Bearer $TOK" \
  -d '{"tipo":"DEDUCCION","descripcion":"Deducción I+D","referencia_normativa":"Art 35 LIS","importe":"8000.0000"}'

# 2) Recalcular
curl -X POST "$BASE/api/v1/fiscal/is/calculos/$CALC_ID/recalcular" -H "Authorization: Bearer $TOK" \
  -d '{"ajustes":[],"deducciones":[]}'
# 200: base_imponible calculada, cuota_integra, cuota_diferencial

# 3) Verificar cálculo
curl "$BASE/api/v1/fiscal/is/calculos/$CALC_ID" -H "Authorization: Bearer $TOK"
# resultado_contable + 12000 = base_imponible
# base_imponible × 25% = cuota_integra
# cuota_integra - 8000 = cuota_liquida
# cuota_liquida - pagos_a_cuenta_473 = cuota_diferencial
```

Validación pytest:
- `test_calculo_is_balance`: cuota_integra = base × tipo / 100; cuota_diferencial = cuota_liquida - pagos.
- `test_calculo_is_aislamiento`: empresa B no ve el cálculo de empresa A.

## Scenario 2 — Contabilizar el IS (asiento 630/473/4752)

```bash
# 1) Contabilizar
curl -X POST "$BASE/api/v1/fiscal/is/calculos/$CALC_ID/contabilizar" -H "Authorization: Bearer $TOK" \
  -d '{"fecha_asiento":"2025-12-31"}'
# 200: asiento_id, estado=contabilizado

# 2) Verificar asiento
# Debe: 630 (cuota_liquida)
# Haber: 473 (pagos_a_cuenta) + 4752 (cuota_diferencial si > 0)
# Si cuota_diferencial < 0: Debe: 630 + 4709 | Haber: 473
```

## Scenario 3 — Generar modelo 200

```bash
# 1) Generar modelo
curl -X POST "$BASE/api/v1/fiscal/is/modelo-200" -H "Authorization: Bearer $TOK" \
  -d '{"calculo_is_id":"<calculo_uuid>"}'
# 201: id, hash_contenido, fecha_generacion

# 2) Descargar modelo
curl "$BASE/api/v1/fiscal/is/modelo-200/$MODELO_ID" -H "Authorization: Bearer $TOK" -o modelo200.pdf
# 200: fichero PDF/CSV con bloques del modelo
```

## Scenario 4 — Cálculo provisional (cierre intermedio)

```bash
# Crear cálculo provisional
curl -X POST "$BASE/api/v1/fiscal/is/calculos" -H "Authorization: Bearer $TOK" \
  -d '{"ejercicio":2025,"provisional":true}'
# 201: provisional=true

# Recalcular provisionalmismo
curl -X POST "$BASE/api/v1/fiscal/is/calculos/$CALC_ID/recalcular" -H "Authorization: Bearer $TOK" \
  -d '{"ajustes":[{"tipo":"AJUSTE_POSITIVO","descripcion":"Estimación","importe":"5000.0000"}],"deducciones":[]}'
# 200: valores recalculados, sigue siendo provisional
```

## Scenario 5 — Rechazo por cálculo ya definitivo

```bash
# Intentar crear segundo cálculo definitivo para el mismo ejercicio
curl -X POST "$BASE/api/v1/fiscal/is/calculos" -H "Authorization: Bearer $TOK" \
  -d '{"ejercicio":2025,"provisional":false}'
# 409: calculo_ya_definitivo
```

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# Crear cálculo en empresa A
curl -X POST "$BASE/api/v1/fiscal/is/calculos" -H "Authorization: Bearer $TOK_A" \
  -d '{"ejercicio":2025,"provisional":false}'

# Consultar desde empresa B → 404
curl "$BASE/api/v1/fiscal/is/calculos/$CALC_ID" -H "Authorization: Bearer $TOK_B"
# 404 — nunca filtrar datos de otra empresa
```
