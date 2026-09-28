# Quickstart Validation Guide: Amortizaciones del Inmovilizado (SPEC-014)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, ejercicio 2026 abierto, plan de cuentas con cuentas 21x, 281XXX y 681, motor de asientos SPEC-002 operativo). Contratos en [contracts/](contracts/), modelo en [data-model.md](data-model.md).

## Scenario 1 — Alta de un activo con plan lineal

```bash
# 1) Calcular plan sin persistir
curl -X POST "$BASE/api/v1/activos/plan/calcular" -H "Authorization: Bearer $TOK" \
  -d '{"cuenta_id":"<cuenta_218>","coste_amortizable":"15000.0000","vida_util":60,"metodo":"lineal","fecha_alta":"2026-10-01"}'
# Espera: plan 60 cuotas de "250.0000", acumulado final "15000.0000", sin exceder coste

# 2) Dar de alta
curl -X POST "$BASE/api/v1/activos" -H "Authorization: Bearer $TOK" \
  -d '{"numero_activo":"EQ-001","cuenta_id":"<cuenta_218>","descripcion":"Impresora","fecha_alta":"2026-10-01","coste_amortizable":"15000.0000","vida_util":60,"metodo":"lineal"}'
# Espera: 201, id, estado=en_uso, plan calculado y validado
```

Validación pytest:
- `test_plan_lineal`: 60 cuotas `Decimal("250.0000")`, acumulado final exacto, última cuota ajustada.
- `test_plan_no_excede_coste`: ninguna fila con `acumulado > coste` (FR-006).
- `test_activo_tenant`: empresa B no ve el activo de A; dar de alta desde B con su número → sin colisión Ni exposición.

## Scenario 2 — Alta de un activo con método regresivo

```bash
curl -X POST "$BASE/api/v1/activos" -H "Authorization: Bearer $TOK" \
  -d '{"numero_activo":"VEH-001","cuenta_id":"<cuenta_218>","coste_amortizable":"20000.0000","vida_util":48,"metodo":"regresivo","porcentaje_regresivo":25.00,"fecha_alta":"2026-10-01"}'
# Espera: 201; cuotas decrecientes conforme al % sobre valor residual; acumulado final == coste
```

Validación pytest:
- `test_plan_regresivo`: cuota(k) <= cuota(k-1), acumulado final == coste, ninguna cuota negativa.

## Scenario 3 — Generar los asientos de amortización del período

```bash
# 1) Generar período 10/2026 (ejercicio abierto)
curl -X POST "$BASE/api/v1/amortizaciones/generar" -H "Authorization: Bearer $TOK" \
  -d '{"ejercicio":2026,"periodo":10}'
# Espera: 200, generados con asiento_id por activo; n>0

# 2) Verificar balance consultando el asiento (SPEC-002):
#    Debe 681 (250.00) | Haber 281XXX (250.00)

# 3) Intentar regenerar el mismo período
curl -X POST "$BASE/api/v1/amortizaciones/generar" -H "Authorization: Bearer $TOK" \
  -d '{"ejercicio":2026,"periodo":10}'
# Espera: 409 — sin duplicados por (activo, ejercicio, periodo)

# 4) Intentar generar en ejercicio cerrado (SPEC-004)
# Espera: 409
```

Validación pytest:
- `test_asiento_amortizacion_balance`: cada asiento generado tiene Debe==Haber (681 vs 281) exacto en `Decimal`.
- `test_no_duplicados_periodo`: segunda llamada → 409; constraint UNIQUE no violable.
- `test_ejercicio_cerrado_rechazado`: generar para ejercicio cerrado → 409.
- `test_amortizacion_tenant`: generando en A, B no ve los asientos ni los registros `AmortizacionGenerada`.

## Scenario 4 — Reabrir un período ya amortizado (trazabilidad)

```bash
# 1) Reabrir período 10/2026 con motivo
curl -X POST "$BASE/api/v1/amortizaciones/$GENERADA_ID/reabrir" -H "Authorization: Bearer $TOK" \
  -d '{"motivo":"corrección"}'
# Espera: 200, reversal_asiento_id; el asiento previo NO fue modificado (constitución II)

# 2) Regenerar el período tras la corrección
curl -X POST "$BASE/api/v1/amortizaciones/generar" -d '{"ejercicio":2026,"periodo":10}'
# Espera: 200; nuevo AmortizacionGenerada.con reapertura_de = previo
```

Validación pytest:
- `test_reabrir_reversal`: se crea un `REVERSAL` balanceado enlazado; el asiento original queda intacto.
- `test_reabrir_ejercicio_cerrado`: reapertura en ejercicio cerrado → 409.

## Scenario 5 — Baja y venta de un activo

```bash
# 1) Amortizar hasta la fecha de baja (período parcial prorrateado)
curl -X POST "$BASE/api/v1/activos/$ACTIVO_ID/baja" -H "Authorization: Bearer $TOK" \
  -d '{"fecha_baja":"2027-03-15","precio_venta":"8000.0000","tipo":"venta"}'
# Espera: 201, amortizacion_hasta_baja, valor_neto_contable, resultado, asiento_id

# 2) Verificar asiento balanceado:
#    Debe 281 (acumulada) + 572 (8000) → Haber 21x (15000); saldo → 671 (pérdida) o 771 (beneficio)

# 3) El activo queda fuera del plan: GET activo → estado=dado_de_baja; ya no aparece en generar
```

Validación pytest:
- `test_baja_prorrateo`: amortización hasta baja según config mensual/días.
- `test_baja_asiento_balance`: asiento de baja Debe==Haber con resultado exacto (`precio - VNC`).
- `test_baja_sale_del_plan`: genera tras baja → el activo no se incluye.
- `test_baja_tenant`: B no puede dar de baja el activo de A (404).

## Scenario 6 — Corrección sin reabrir posteados

```bash
# Editar vida útil de un activo ya amortizado (2 cuotas generadas)
curl -X PATCH "$BASE/api/v1/activos/$ACTIVO_ID" -H "Authorization: Bearer $TOK" \
  -d '{"vida_util":48}'
# Espera: 200, plan_futuro recalculado desde el próximo período; las 2 cuotas pasadas intactas
# Verificar: acumulado posteado no cambia; cuotas futuras suman (coste - acumulado posteado)
```

Validación pytest:
- `test_correccion_plan_futuro`: el acumulado del período siguiente respeta el ya posteado; ninguna cuota excede el nuevo coste (FR-006).
- `test_correccion_no_toca_posteados`: los `JournalEntry` previos no se modifican (constitución II).