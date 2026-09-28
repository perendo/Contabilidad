# Quickstart Validation Guide: Motor de Asientos Contables (SPEC-002)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa A y B con PGC sembrado — SPEC-001/003 — e `is_selectable` en subcuentas de nivel ≥ 4, p. ej. 4300 y 5720). Referencias: [contracts](contracts/api-contracts.md), [data-model](data-model.md).

## Scenario 1 — Crear y asentar un asiento balanceado

```bash
# 1) Crear el asiento en borrador (Debe 4300 | Haber 5720)
curl -X POST "$BASE/api/v1/journal/entries" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"fecha":"2026-10-01","concepto":"Venta a crédito","lineas":[
        {"account_id":"<id_4300>","debit":"1000.0000","credit":"0.0000"},
        {"account_id":"<id_5720>","debit":"0.0000","credit":"1000.0000"}]}'
# Espera: 201, estado=DRAFT, suma_debe == suma_haber == "1000.0000"

# 2) Asentar → número correlativo
curl -X POST "$BASE/api/v1/journal/entries/$ENTRY_ID/post" -H "Authorization: Bearer $TOK_A"
# Espera: 200, estado=POSTED, numero=1, ejercicio=2026
```

Validación pytest:
- `test_balance_estricto`: asiento desbalanceado → 422 y **sin rastro parcial** (no hay cabecera huérfana).
- `test_asentado_atomico_numero`: crear + asentar → `numero` correlativo asignado en la misma transacción; asiento con `UNIQUE (empresa, ejercicio, numero)` intacto.
- `test_correlatividad`: 3 asientos en 2026 → números 1,2,3 sin saltos; ejercicio 2027 → reinicia.

## Scenario 2 — Rechazo de asiento desbalanceado (FR-002/SC-001)

```bash
curl -X POST "$BASE/api/v1/journal/entries" -H "Authorization: Bearer $TOK_A" \
  -d '{"fecha":"2026-10-01","concepto":"Mal","lineas":[
        {"account_id":"<id_4300>","debit":"100.0000","credit":"0.0000"},
        {"account_id":"<id_5720>","debit":"0.0000","credit":"99.0000"}]}'
# Espera: 422 { "detail": "...", "suma_debe": "100.0000", "suma_haber": "99.0000" }
# Base de datos: 0 cabeceras, 0 líneas nuevas
```

Validación pytest:
- `test_atomicidad_cabecera_lineas`: ante cualquier fallo de validación no queda fila en `journal_entry` ni `journal_entry_line` (FR-004).
- `test_cuenta_no_apuntable`: línea a cuenta de 1-3 dígitos (p. ej. 430) o inactiva → 422; a nivel DB el trigger `chk_journal_line_account_selectable` lanza EXCEPTION.

## Scenario 3 — Libro diario paginado con aislamiento

```bash
curl "$BASE/api/v1/journal/entries?date_from=2026-10-01&date_to=2026-10-31&page=1&page_size=20" \
  -H "Authorization: Bearer $TOK_A"
# Espera: 200; solo asientos de la EMPRESA A en el rango, ordenados por (fecha, numero)
# Sin rango de fechas → 422
```

Validación pytest:
- `test_libro_diario_paginacion`: 45 asientos → 3 páginas de 20 sin saltos de registros.
- `test_libro_diario_aislamiento`: la empresa B con asientos en el mismo rango no aparece en la consulta de A.

## Scenario 4 — Anulación con asiento REVERSAL (FR-008/FR-009/SC-004)

```bash
# Anular el asiento 1
curl -X POST "$BASE/api/v1/journal/entries/$ENTRY_ID/reverse" -H "Authorization: Bearer $TOK_A" \
  -d '{"fecha":"2026-10-05"}'
# Espera: 201; id_reversal asignado, numero_reversal=2, estado_original=CANCELLED

# Intentar anular de nuevo
curl -X POST "$BASE/api/v1/journal/entries/$ENTRY_ID/reverse" -H "Authorization: Bearer $TOK_A"
# Espera: 409 (doble anulación) — no se generan duplicados

# Intentar UPDATE/DELETE del original (no hay endpoints; a nivel DB el trigger lo deniega)
```

Validación pytest:
- `test_reversal_balance`: REVERSAL con importes invertidos, Debe==Haber, misma cantidad de líneas, suma neta 0; el asiento original **no se modifica** (payload intacto).
- `test_inmutabilidad_posted`: UPDATE/DELETE sobre un `POSTED`/`CANCELLED` → EXCEPTION DB y 409/405 en API.
- `test_doble_anulacion`: 409 sin efectos.

## Scenario 5 — Correlatividad bajo concurrencia (FR-005/SC-006)

```bash
# Lanzar en paralelo N peticiones de asentar asientos del mismo (empresa, ejercicio)
for i in $(seq 1 10); do curl -X POST "$BASE/api/v1/journal/entries/$E$i/post" \
  -H "Authorization: Bearer $TOK_A" & done; wait
# Espera: 10 números correlativos, sin duplicados ni omisiones (1..10)
```

Validación pytest:
- `test_correlatividad_concurrente`: 20 hilos asentando simultáneamente → única serie 1..20, `UNIQUE (empresa, ejercicio, numero)` jamás violado.

## Scenario 6 — Aislamiento multi-empresa (constitución III)

```bash
# La empresa B intenta ver/asentar/anular asientos de la empresa A
curl "$BASE/api/v1/journal/entries/$ENTRY_A" -H "Authorization: Bearer $TOK_B"
curl -X POST "$BASE/api/v1/journal/entries/$ENTRY_A/post" -H "Authorization: Bearer $TOK_B"
curl -X POST "$BASE/api/v1/journal/entries/$ENTRY_A/reverse" -H "Authorization: Bearer $TOK_B"
# Espera: 404 en los tres casos — ningún dato de A observable por B
```

Validación pytest:
- `test_asiento_aislamiento_full`: GET/asentar/anular de A desde B → 404 y sin efectos sobre datos de A.
- `test_ejercicio_cerrado`: asiento con fecha en ejercicio cerrado (SPEC-004) → 400 sin persistir.