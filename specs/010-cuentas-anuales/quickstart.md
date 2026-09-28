# Quickstart Validation Guide: Cuentas Anuales (SPEC-010)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed minimo (empresa, plan de cuentas con grupos 1-7, ejercicio cerrado con asientos de gestion y regularizacion/cierre).

## Scenario 1 — Calcular Balance de Situacion provisional

```bash
# Calcular balance del ejercicio 2026 (provisional)
curl "$BASE/api/v1/cuentas-anuales/2026/balance" -H "Authorization: Bearer $TOK"
# Espera: 200, cuadre=true, total_activo == total_pasivo + total_patrimonio

# Verificar aislamiento: empresa B no ve el balance de A
curl "$BASE/api/v1/cuentas-anuales/2026/balance" -H "Authorization: Bearer $TOK_B"
# Espera: 200, cuadre=true, importes diferentes (empresa distinta)
```

Validacion pytest:
- `test_balance_cuadre`: verificar Activo == Pasivo + Patrimonio con Decimal exacto.
- `test_balance_solo_cuentas_1_3`: verificar que grupos 6-7 no aparecen en el balance.

## Scenario 2 — Calcular PyG y verificar resultado con cierre

```bash
# Calcular PyG del ejercicio 2026
curl "$BASE/api/v1/cuentas-anuales/2026/pyg" -H "Authorization: Bearer $TOK"
# Espera: 200, coincide_cierre=true (si el cierre esta hecho correctamente)

# Si coincide_cierre=false, la formulacion oficial se bloquea
```

Validacion pytest:
- `test_pyg_resultado_coincide_cierre`: resultado PyG == resultado del asiento de regularizacion.
- `test_pyg_aislamiento`: empresa B no ve la PyG de A.

## Scenario 3 — Formular oficialmente las cuentas anuales

```bash
# 1) Verificar que balance y PyG cuadran
curl "$BASE/api/v1/cuentas-anuales/2026/balance" -H "Authorization: Bearer $TOK"
# cuadre=true

curl "$BASE/api/v1/cuentas-anuales/2026/pyg" -H "Authorization: Bearer $TOK"
# coincide_cierre=true

# 2) Formular oficialmente
curl -X POST "$BASE/api/v1/cuentas-anuales/2026/formular" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"observaciones": "Formulacion anual 2026"}'
# Espera: 201, formulacion_id, numero_formulacion=1, contenido_hash (sha256)

# 3) Verificar historico de formulaciones
curl "$BASE/api/v1/cuentas-anuales/2026/formulaciones" -H "Authorization: Bearer $TOK"
# Espera: 200, items con 1 formulacion estado=formulada

# 4) Intentar reformular sin anular -> 409 ya_formulada
```

Validacion pytest:
- `test_formular_ejercicio_no_cerrado`: rechaza 409 si el ejercicio no esta cerrado.
- `test_formular_balance_descuadrado`: rechaza 422 si el balance no cuadra.
- `test_formular_bloqueo_duplicada`: segunda formulacion -> 409.

## Scenario 4 — Anulacion y reformulacion con trazabilidad

```bash
# 1) Anular la formulacion
curl -X POST "$BASE/api/v1/cuentas-anuales/2026/anular-formulacion" \
  -H "Authorization: Bearer $TOK" \
  -d '{"motivo": "Correccion de datos contables"}'
# Espera: 200, estado=anulada

# 2) Reformular
curl -X POST "$BASE/api/v1/cuentas-anuales/2026/formular" \
  -H "Authorization: Bearer $TOK" \
  -d '{"observaciones": "Reformulacion corregida"}'
# Espera: 201, numero_formulacion=2

# 3) Ver historico completo
curl "$BASE/api/v1/cuentas-anuales/2026/formulaciones" -H "Authorization: Bearer $TOK"
# Espera: 200, 2 items (una anulada, una formulada)
```

Validacion pytest:
- `test_anulacion_reformulacion`: verificar que la reformulacion genera nuevo numero y traza completa.
- `test_asientos_no_modificados`: los asientos del ejercicio permanecen inmutables tras formulacion/anulacion.

## Scenario 5 — EFE y cuadre con variacion de tesoreria

```bash
# 1) Calcular EFE
curl "$BASE/api/v1/cuentas-anuales/2026/efe" -H "Authorization: Bearer $TOK"
# Espera: 200, cuadre=true, saldo_final == saldo_inicial + movimientos

# 2) Clasificar un movimiento manualmente
curl -X PATCH "$BASE/api/v1/cuentas-anuales/2026/efe/clasificacion" \
  -H "Authorization: Bearer $TOK" \
  -d '{"movimiento_id": "<uuid>", "actividad": "inversion"}'
# Espera: 200

# 3) Recalcular EFE
curl "$BASE/api/v1/cuentas-anuales/2026/efe" -H "Authorization: Bearer $TOK"
# cuadre=true con la nueva clasificacion
```

Validacion pytest:
- `test_efe_cuadre_saldo_final`: saldo_final == saldo_inicial + cobros - pagos.
- `test_efe_variacion_balance`: variacion == diferencia tesoreria del Balance.

## Scenario 6 — Aislamiento multi-empresa (constitucion III)

```bash
# Crear asientos en empresa A y empresa B (con planes distintos)
# Formular cuentas anuales en A
curl -X POST "$BASE/api/v1/cuentas-anuales/2026/formular" \
  -H "Authorization: Bearer $TOK_A" -d '{"observaciones": "A"}'
# Espera: 201

# Consultar desde B -> no ve la formulacion de A
curl "$BASE/api/v1/cuentas-anuales/2026/formulaciones" -H "Authorization: Bearer $TOK_B"
# Espera: 200, items vacios

# Intentar anular la formulacion de A desde B -> 404
curl -X POST "$BASE/api/v1/cuentas-anuales/2026/anular-formulacion" \
  -H "Authorization: Bearer $TOK_B" -d '{"motivo": "test"}'
# Espera: 404 o 409 sin_formulacion
```
