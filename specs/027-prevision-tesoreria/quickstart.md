# Quickstart Validation Guide: Previsión y Flujo de Caja (SPEC-027)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas con cuentas 570/572/6xx/7xx, vencimientos pendientes de SPEC-011: uno por cobrar a 30/09, uno por pagar a 15/10, un vencido ya cobrado; saldo de tesorería inicial registrado). Variable de entorno `BASE/api/v1`.

## Escenario 1 — Generar la previsión de tesorería por día (US1)

```bash
# 1) Generar previsión mensual a partir de vencimientos pendientes
curl -X POST "$BASE/api/v1/tesoreria/previsiones" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"desde_fecha":"2026-09-16","hasta_fecha":"2026-10-31","granularidad":"dia","movimientos_manuales":[{"tipo":"pago","importe":"1200.0000","fecha_prevista":"2026-10-01","frecuencia":"mensual","concepto":"Alquiler"}]}'
# Espera: 201, id, numero_prevision, saldo_inicial, saldo_final, n_movimientos

# 2) Detalle: buckets con cobros, pagos y saldo acumulado
curl "$BASE/api/v1/tesoreria/previsiones/$PREV_ID" -H "Authorization: Bearer $TOK_A"
# Espera: 200, buckets con fecha, cobros, pagos, saldo_acumulado; el vencido cobrado NO aparece
```

Validación pytest:
- `test_proyeccion_vencimientos`: cobro y pago esperados aparecen en su fecha de vencimiento (SC-001); saldo acumulado calculado con precisión exacta.
- `test_exclusion_vencidos`: vencimiento vencido/cobrado excluido de la proyección (FR-006); los `excluidos` se reportan con motivo.

## Escenario 2 — Proyección semanal/mensual y pagos recurrentes (US1)

```bash
curl -X POST "$BASE/api/v1/tesoreria/previsiones" -H "Authorization: Bearer $TOK_A" \
  -d '{"desde_fecha":"2026-10-01","hasta_fecha":"2026-12-31","granularidad":"mes","movimientos_manuales":[{"tipo":"pago","importe":"1200.0000","fecha_prevista":"2026-10-01","frecuencia":"mensual","concepto":"Alquiler"}]}'
# 201; el pago recurrente aparece en cada mes (octubre, noviembre, diciembre)
```

Validación pytest:
- `test_recurrente_mensual`: un pago `mensual` se replica en los meses del rango con saldo acumulado correcto.

## Escenario 3 — Alertas de liquidez por saldo negativo (US3)

```bash
# 1) Si la proyección tiene un día con saldo negativo...
curl "$BASE/api/v1/tesoreria/alertas?estado=abierta" -H "Authorization: Bearer $TOK_A"
# Espera: 200, items con fecha, saldo_proyectado negativo, importe_deficit, accion_sugerida

# 2) Atender la alerta reprogramando el pago
curl -X POST "$BASE/api/v1/tesoreria/alertas/$ALERTA_ID/atender" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"accion":"reprogramar_pago","movimiento_id":"<uuid>","nueva_fecha":"2026-10-15"}'
# 200, estado=atendida, movimiento_id

# 3) Regenerar la previsión: el bucket ya no es negativo
```

Validación pytest:
- `test_alerta_saldo_negativo`: día con saldo < 0 → alerta abierta (FR-003/SC-004).
- `test_saldo_cero_sin_alerta`: bucket con saldo exactamente 0 → visible como límite de solvencia, sin alerta.
- `test_reprogramar_pago`: atender con reprogramar actualiza fecha_prevista y la alerta pasa a atendida.

## Escenario 4 — Informe EFE consolidado (US2)

```bash
# 1) Generar el EFE del ejercicio (clasificación automática por grupo de cuenta)
curl "$BASE/api/v1/tesoreria/efe?ejercicio=2026" -H "Authorization: Bearer $TOK_A"
# Espera: 200, saldo_inicial + bloques (operativa/inversion/financiacion) = saldo_final, cuadre=true

# 2) Formular con override de clasificación
curl -X POST "$BASE/api/v1/tesoreria/efe/formular" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio":2026,"clasificaciones":[{"cuenta_id":"<uuid>","bloque":"inversion"}]}'
# 200, estado=formulado, cuadre=true, sin_conciliar=false
```

Validación pytest:
- `test_efe_tres_bloques`: aparecen los tres bloques (operativa/inversión/financiación) (US2 scenario 1).
- `test_efe_cuadre`: saldo_inicial + Σ bloques == saldo_final (FR-004/SC-003), siempre con Decimal.
- `test_efe_cruce_conciliacion`: si la conciliación (SPEC-013) difiere por movimientos no conciliados, el informe se marca `sin_conciliar` pero no bloquea (Assumptions).

## Escenario 5 — Aislamiento multi-empresa (constitución III)

```bash
# Empresa A genera previsión y EFE
curl -X POST "$BASE/api/v1/tesoreria/previsiones" -H "Authorization: Bearer $TOK_A" ...
# Empresa B consulta previsiones → no ve las de A
curl "$BASE/api/v1/tesoreria/previsiones" -H "Authorization: Bearer $TOK_B"
# 200, items=[] (aislamiento garantizado)

# Empresa B intenta consultar/atender alertas de A
curl "$BASE/api/v1/tesoreria/alertas?prevision_id=<uuid_id_A>" -H "Authorization: Bearer $TOK_B"
# 404
```

Validación pytest:
- `test_prevision_tenant_isolation`: previsiones y EFE de A invisibles para B (404/items vacíos) en listados, detalle y formulación.