# Quickstart Validation Guide: Contabilidad Habitual, Informes y Cierre (SPEC-004)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa con PGC sembrado, ejercicios provisionados 2026/2027 para la empresa, y el motor de asientos de SPEC-002 operativo). Referencias: [contracts](contracts/api-contracts.md), [data-model](data-model.md).

## Scenario 1 — Balance de Sumas y Saldos siempre cuadra

```bash
# Sembrar asientos balanceados: venta (4300/129…) y gasto (…)
# 1) Generar el balance de la empresa activa
curl "$BASE/api/v1/reports/trial-balance?date_from=2026-01-01&date_to=2026-12-31&level=4" \
  -H "Authorization: Bearer $TOK_A"
# Espera: 200; total_debe == total_haber; cuadra: true; items por cuenta al nivel 4
```

Validación pytest:
- `test_trial_balance_cuadra`: para varios rangos y niveles → `total_debe == total_haber` siempre (SC-001).
- `test_trial_balance_nivel_superior_al_plan`: pedir nivel 6 → agrega al mayor nivel disponible sin error.
- `test_trial_balance_aislamiento`: asientos de la empresa B en el mismo rango nunca aparecen (SC-003).

## Scenario 2 — Libro Mayor con saldo acumulado

```bash
curl "$BASE/api/v1/reports/ledger/$ACCOUNT_4300?date_from=2026-01-01&date_to=2026-12-31" \
  -H "Authorization: Bearer $TOK_A"
# Espera: 200; movimientos cronológicos de 4300 con saldo_acumulado exacto; saldo_final == saldo que cuadra con el balance

# Subcuenta inexistente o de otra empresa → 404; subcuenta sin movimientos → movimientos vacío
```

Validación pytest:
- `test_ledger_saldo_acumulado`: verifica la secuencia {debe, haber, saldo_acumulado} correcta en Decimal.
- `test_ledger_aislamiento`: mayor de subcuenta de B desde A → 404 sin datos.

## Scenario 3 — Cierre de ejercicio atómico

```bash
# 1) Cerrar el ejercicio 2026
curl -X POST "$BASE/api/v1/fiscal-years/2026/close" -H "Authorization: Bearer $TOK_A"
# Espera: 200; is_closed=true; regularizacion_entry_id/cierre_entry_id != null; suma_debe == suma_haber

# 2) Intentar registrar un asiento con fecha en 2026 (cerrado)
curl -X POST "$BASE/api/v1/journal/entries" \
  -H "Authorization: Bearer $TOK_A" -H "Content-Type: application/json" \
  -d '{"fecha":"2026-11-15","concepto":"X","lineas":[…]}'
# Espera: 400 — el ejercicio está cerrado, no persiste nada
```

Validación pytest:
- `test_cierre_atomico`: regularización + cierre + is_closed se aplican juntos; si se fuerza un fallo a mitad, el ejercicio queda abierto sin asientos de cierre (SC-004).
- `test_doble_cierre`: segundo cierre → 409 sin asientos duplicados.
- `test_cierre_con_borradores`: existe DRAFT en el rango → 422; asentar/anular antes de cerrar.
- `test_bloqueo_ejercicio_cerrado`: creación/asentado/anulación con fecha en cerrado → 400 sin cambios (SC-002).

## Scenario 4 — Correlatividad y cierre concurrente

```bash
# Dos cierres simultáneos sobre el mismo ejercicio → solo uno prospera (409 el otro)
```

Validación pytest:
- `test_cierre_concurrente`: lock `SELECT ... FOR UPDATE` → un 200 y un 409.

## Scenario 5 — Facturas con precisión exacta y numeración correlativa

```bash
# No hay API de facturas en esta feature (diferida); la validación se cubre por pytest:
#   - persistir factura emitida y recibida vía invoice_service
#   - verificar base/IVA/total con 4 decimales exactos (nunca float)
#   - verificar numero_seq correlativo por (empresa, ejercicio) sin saltos
```

Validación pytest:
- `test_invoice_precision_decimal`: base "100.0000" + IVA "21.0000" → total "121.0000" exacto; el CHECK `total = base + cuota` se cumple; >4 decimales → normalizado a 4.
- `test_invoice_correlatividad`: 3 facturas de 2026 → números 1,2,3; 2027 → reinicia (SC SC-005).
- `test_invoice_aislamiento`: factura de empresa B inaccesible desde A (sin endpoint, verificado a nivel de servicio).
- `test_invoice_inmutabilidad`: factura vinculada a asiento no se puede borrar ni re-vincular.

## Scenario 6 — Aislamiento multi-empresa en informes y cierre (constitución III)

```bash
# Empresa B intenta leer el balance/mayor de la empresa A o cerrar su ejercicio
curl "$BASE/api/v1/reports/trial-balance?... " -H "Authorization: Bearer $TOK_B"
curl -X POST "$BASE/api/v1/fiscal-years/2026/close" -H "Authorization: Bearer $TOK_B"
# Espera: 403/404 — ningún dato de A observable
```

Validación pytest:
- `test_informes_aislamiento_full`: balance, mayor, ejercicios y cierre de A ejecutados desde B → 403/404 sin efectos.