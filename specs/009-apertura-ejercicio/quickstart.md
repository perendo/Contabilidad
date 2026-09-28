# Quickstart Validation Guide: Apertura del Ejercicio (SPEC-009)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas con cuentas patrimoniales grupo 1-3, ejercicio anterior cerrado con saldos).

## Scenario 1 — Abrir ejercicio siguiente con asiento de apertura

```bash
# 1) Verificar que el ejercicio anterior (2026) está cerrado
curl "$BASE/api/v1/ciclo/apertura/estado?ejercicio=2026" -H "Authorization: Bearer $TOK"
# Espera: estado=cerrado, asiento_cierre_id != null

# 2) Abrir el ejercicio 2027
curl -X POST "$BASE/api/v1/ciclo/apertura" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio_destino": 2027}'
# Espera: 201, asiento_id, numero_asiento=1, n_lineas>0, importe_total_debe == importe_total_haber

# 3) Verificar estado del nuevo ejercicio
curl "$BASE/api/v1/ciclo/apertura/estado?ejercicio=2027" -H "Authorization: Bearer $TOK"
# Espera: estado=con_apertura, asiento_apertura_id != null
```

Validación pytest:
- `test_apertura_balance`: verificar que el asiento generado tiene Debe==Haber con `Decimal` exacto.
- `test_apertura_cuentas_patrimoniales`: verificar que solo aparecen cuentas de grupo 1-3.
- `test_apertura_numeracion`: el numero_asiento es 1 para el primer ejercicio.

## Scenario 2 — Rechazo de apertura duplicada

```bash
# Intentar abrir de nuevo el mismo ejercicio
curl -X POST "$BASE/api/v1/ciclo/apertura" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio_destino": 2027}'
# Espera: 409, error=ejercicio_ya_abierto
```

Validación pytest:
- `test_apertura_duplicada_rechazada`: crear apertura, intentar segunda → 409.
- `test_apertura_sin_cierre_rechazada`: ejercicio anterior sin cerrar → 409.

## Scenario 3 — Anulación de apertura errónea

```bash
# 1) Anular la apertura de 2027
curl -X POST "$BASE/api/v1/ciclo/apertura/anular" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio": 2027, "motivo": "Cierre anterior con errores"}'
# Espera: 200, asiento_reversal_id, estado=reversal_generado

# 2) Verificar que el asiento original NO fue modificado (inmutabilidad)
# Consultar JournalEntry OPENING → sigue con el mismo contenido
# Consultar JournalEntry OPENING_REVERSAL → nuevo asiento enlazado

# 3) Regenerar la apertura
curl -X POST "$BASE/api/v1/ciclo/apertura/regenerar" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio_destino": 2027}'
# Espera: 201, nuevo asiento_id, nuevo numero_asiento
```

Validación pytest:
- `test_anulacion_genera_reversal`: verificar que el REVERSAL tiene Debe==Haber y está enlazado.
- `test_asiento_original_inmutable`: el OPENING original no cambió tras la anulación.
- `test_regeneracion_tras_anulacion`: se puede regenerar y el nuevo OPENING es válido.

## Scenario 4 — Aislamiento multi-empresa (constitución III)

```bash
# Crear apertura en empresa A
curl -X POST "$BASE/api/v1/ciclo/apertura" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio_destino": 2027}'
# Espera: 201

# Consultar apertura desde empresa B → no debe aparecer
curl "$BASE/api/v1/ciclo/apertura/estado?ejercicio=2027" -H "Authorization: Bearer $TOK_B"
# Espera: estado=no_definido o 404

# Intentar anular la apertura de A desde B
curl -X POST "$BASE/api/v1/ciclo/apertura/anular" -H "Authorization: Bearer $TOK_B" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio": 2027, "motivo": "test"}'
# Espera: 409 sin_apertura o 404
```

Validación pytest:
- `test_aislamiento_multi_empresa`: empresa A crea apertura, empresa B no la ve ni puede anularla.

## Scenario 5 — Rechazo por ejercicio cerrado en anulación

```bash
# Intentar anular apertura de un ejercicio que ya está cerrado
curl -X POST "$BASE/api/v1/ciclo/apertura/anular" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio": 2026, "motivo": "test"}'
# Espera: 409, ejercicio_cerrado
```

Validación pytest:
- `test_anulacion_ejercicio_cerrado`: rechaza 409 si el ejercicio destino está cerrado.
