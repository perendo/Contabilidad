# Quickstart Validation Guide: Retenciones IRPF y Modelos 111/115/190 (SPEC-024)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas, cuentas 4751/572, tercero con NIF, facturas con retención de SPEC-007).

## Scenario 1 — Acumular retenciones y generar modelo 111

```bash
# 1) Crear liquidación trimestral Q3
curl -X POST "$BASE/api/v1/fiscal/retenciones/liquidaciones" -H "Authorization: Bearer $TOK" \
  -d '{"ejercicio":2025,"trimestre":3}'
# 201: total_retenciones calculado, n_perceptores, estado=pendiente

# 2) Verificar retenciones por perceptor
curl "$BASE/api/v1/fiscal/retenciones/liquidaciones/$LIQ_ID/retenciones" -H "Authorization: Bearer $TOK"
# Lista de perceptores con NIF, base, tipo%, retención

# 3) Generar modelo 111
curl -X POST "$BASE/api/v1/fiscal/retenciones/modelos-111" -H "Authorization: Bearer $TOK" \
  -d '{"liquidacion_id":"<liq_uuid>"}'
# 201: id, hash_contenido

# 4) Descargar modelo 111
curl "$BASE/api/v1/fiscal/retenciones/modelos-111/$MOD_ID" -H "Authorization: Bearer $TOK" -o modelo111.pdf
```

Validación pytest:
- `test_acumulacion_retenciones`: verificar que la suma de retenciones coincide con las de las facturas del trimestre.
- `test_111_balance`: retenciones acumuladas = total del modelo.
- `test_retenciones_aislamiento`: empresa B no ve las retenciones de empresa A.

## Scenario 2 — Liquidar trimestre (asiento 4751 vs 572)

```bash
# 1) Contabilizar liquidación
curl -X POST "$BASE/api/v1/fiscal/retenciones/liquidaciones/$LIQ_ID/contabilizar" \
  -H "Authorization: Bearer $TOK" \
  -d '{"fecha_asiento":"2025-09-30","cuenta_banco":"5720000"}'
# 200: asiento_id, estado=liquidado

# 2) Verificar asiento
# Debe: 4751 (total_retenciones)
# Haber: 572 (total_retenciones)
# El saldo de 4751 queda a cero para Q3
```

## Scenario 3 — Modelo 115 (arrendamientos)

```bash
# Generar modelo 115 si hay retenciones de arrendamiento
curl -X POST "$BASE/api/v1/fiscal/retenciones/modelos-115" -H "Authorization: Bearer $TOK" \
  -d '{"liquidacion_id":"<liq_uuid>"}'
# 201: id, hash_contenido

# Si no hay retenciones de arrendamiento → 409 sin_retenciones_arrendamiento
```

## Scenario 4 — Modelo 190 anual

```bash
# 1) Validar NIF de perceptores
curl "$BASE/api/v1/fiscal/retenciones/modelo-190/validar?ejercicio=2025" -H "Authorization: Bearer $TOK"
# 200: { "valido": true } o { "valido": false, "perceptores_sin_nif": [...] }

# 2) Generar modelo 190
curl -X POST "$BASE/api/v1/fiscal/retenciones/modelo-190" -H "Authorization: Bearer $TOK" \
  -d '{"ejercicio":2025}'
# 201: id, n_perceptores, hash_contenido

# 3) Descargar modelo 190
curl "$BASE/api/v1/fiscal/retenciones/modelo-190/$MOD190_ID" -o modelo190.pdf
```

## Scenario 5 — Rechazo por perceptores sin NIF

```bash
# Intentar generar 190 sin NIF en algún perceptor
curl -X POST "$BASE/api/v1/fiscal/retenciones/modelo-190" -H "Authorization: Bearer $TOK" \
  -d '{"ejercicio":2025}'
# 422: perceptores_sin_nif con lista de los que faltan
```

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# Crear liquidación en empresa A
curl -X POST "$BASE/api/v1/fiscal/retenciones/liquidaciones" -H "Authorization: Bearer $TOK_A" \
  -d '{"ejercicio":2025,"trimestre":3}'

# Consultar desde empresa B → 404
curl "$BASE/api/v1/fiscal/retenciones/liquidaciones/$LIQ_ID" -H "Authorization: Bearer $TOK_B"
# 404 — nunca filtrar datos de otra empresa
```
