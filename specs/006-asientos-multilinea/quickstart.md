# Quickstart Validation Guide: Asientos Contables Multilínea (SPEC-006)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas con cuentas apuntables 430, 572, 6200000, 6210000; ejercicio abierto 2026).

## Scenario 1 — Crear asiento multilínea con 3 débitos y 2 créditos

```bash
# Crear asiento con 3 líneas al Debe y 2 al Haber
curl -X POST "$BASE/api/v1/asientos" \
  -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{
    "fecha": "2026-01-15",
    "concepto": "Gasto compuesto parcialmente deducible",
    "lineas": [
      {"cuenta": "6200000", "debe": "300.0000", "haber": "0.0000", "detalle": "Material oficina"},
      {"cuenta": "6210000", "debe": "150.0000", "haber": "0.0000", "detalle": "Servicios externos"},
      {"cuenta": "6220000", "debe": "50.0000",  "haber": "0.0000", "detalle": "Transporte"},
      {"cuenta": "4100000", "debe": "0.0000",   "haber": "400.0000", "detalle": "Proveedor A"},
      {"cuenta": "4100001", "debe": "0.0000",   "haber": "100.0000", "detalle": "Proveedor B"}
    ]
  }'
# Espera: 201, total_debe="500.0000", total_haber="500.0000", n_lineas=5, estado=POSTED
```

Validación pytest:
- `test_multilinea_3debe_2haber_balanceado`: crear asiento 3:2, verificar Debe==Haber.
- `test_multilinea_lineas_persistidas`: verificar que todas las 5 líneas existen en la BD con las cuentas correctas.

## Scenario 2 — Rechazo por lado vacío

```bash
# Intentar crear asiento sin partidas al Haber
curl -X POST "$BASE/api/v1/asientos" \
  -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{
    "fecha": "2026-01-15",
    "concepto": "Asiento incompleto",
    "lineas": [
      {"cuenta": "6200000", "debe": "500.0000", "haber": "0.0000"},
      {"cuenta": "6210000", "debe": "200.0000", "haber": "0.0000"}
    ]
  }'
# Espera: 422, error: lado_vacio, mensaje: "Faltan partidas en el lado HABER"
```

Validación pytest:
- `test_rechazo_lado_vacio_haber`: asiento sin Haber → 422 lado_vacio.
- `test_rechazo_lado_vacio_debe`: asiento sin Debe → 422 lado_vacio.

## Scenario 3 — Rechazo por desbalanceo

```bash
# Intentar crear asiento desbalanceado
curl -X POST "$BASE/api/v1/asientos" \
  -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{
    "fecha": "2026-01-15",
    "concepto": "Desbalanceado",
    "lineas": [
      {"cuenta": "6200000", "debe": "500.0000", "haber": "0.0000"},
      {"cuenta": "4100000", "debe": "0.0000", "haber": "450.0000"}
    ]
  }'
# Espera: 422, error: desbalanceo, "Suma Debe (500.0000) != Suma Haber (450.0000)"
```

Validación pytest:
- `test_rechazo_desbalanceo_multilinea`: asiento N:M desbalanceado → 422, ninguna línea persistida.

## Scenario 4 — Anulación de asiento multilínea

```bash
# 1) Crear asiento multilínea
ASIENTO_ID=$(curl -X POST "$BASE/api/v1/asientos" ... | jq -r '.id')

# 2) Anular → genera rectificativo
curl -X POST "$BASE/api/v1/asientos/$ASIENTO_ID/anular" \
  -H "Authorization: Bearer $TOK"
# Espera: 201, asiento_rectificativo con tipo=REVERSAL, líneas invertidas

# 3) Verificar:
# - Asiento original NO fue modificado
# - Rectificativo tiene M débitos y N créditos (invertidos)
# - Rectificativo balanceado (Debe==Haber)
# - asiento_original_id apunta al original
```

Validación pytest:
- `test_anulacion_multilinea_invertido`: asiento 3:2 → rectificativo 2:3, verificar inversión.
- `test_anulacion_balanceado`: verificar Debe==Haber en rectificativo.
- `test_anulacion_original_intacto`: verificar que el asiento original no fue modificado.

## Scenario 5 — Caso clásico 1:1

```bash
# Crear asiento clásico con 1 línea al Debe y 1 al Haber
curl -X POST "$BASE/api/v1/asientos" \
  -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{
    "fecha": "2026-01-16",
    "concepto": "Pago proveedor",
    "lineas": [
      {"cuenta": "4100000", "debe": "1200.0000", "haber": "0.0000"},
      {"cuenta": "5720000", "debe": "0.0000", "haber": "1200.0000"}
    ]
  }'
# Espera: 201, n_lineas=2, total_debe=total_haber=1200.0000
```

Validación pytest:
- `test_caso_classico_1_1`: asiento 1:1 se acepta correctamente.
- `test_cuentas_repetidas_admitidas`: 2 líneas con la misma cuenta en el mismo asiento → aceptado.

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# Crear asiento en empresa A
ASIENTO_A=$(curl -X POST "$BASE/api/v1/asientos" ... | jq -r '.id')

# Consultar desde empresa B
curl "$BASE/api/v1/asientos/$ASIENTO_A" \
  -H "Authorization: Bearer $TOK_B"
# Espera: 404

# Anular desde empresa B
curl -X POST "$BASE/api/v1/asientos/$ASIENTO_A/anular" \
  -H "Authorization: Bearer $TOK_B"
# Espera: 404
```

Validación pytest:
- `test_aislamiento_empresa_asiento_multilinea`: empresa A crea, B no ve ni anula.
