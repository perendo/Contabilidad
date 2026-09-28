# Quickstart Validation Guide: Presupuestos y Desviaciones (SPEC-026)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas con cuentas apuntables 6400 (sueldos, gasto) y 7000 (ventas, ingreso), asientos reales de ejemplo, periodo de seguimiento abierto). Variable de entorno `BASE/api/v1`.

## Escenario 1 — Definir el presupuesto anual por cuenta y centro (US1)

```bash
# 1) Alta de presupuesto por cuenta de gasto
curl -X POST "$BASE/api/v1/presupuestos" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio":2026,"cuenta_id":"<uuid_6400>","centro_coste_id":null,"importe":"48000.0000","tipo":"gasto"}'
# Espera: 200, id, importe="48000.0000", tipo=gasto

# 2) Duplicado idéntico → 422
curl -X POST "$BASE/api/v1/presupuestos" ... -d '{"cuenta_id":"<uuid_6400>","importe":"100.0000",...}'
# 422: duplicado idéntico (FR-005)

# 3) Listado por ejercicio
curl "$BASE/api/v1/presupuestos?ejercicio=2026" -H "Authorization: Bearer $TOK_A"
# 200: items con codigo_cuenta, importe, tipo
```

Validación pytest:
- `test_duplicado_rechazado`: insertar la misma combinación dos veces → la segunda rechaza con 422/unicidad.
- `test_cuenta_inapunteable_rechazado`: intentar presupuestar una cuenta nivel 2 (is_selectable=false) → 422.

## Escenario 2 — Seguimiento y desviación por cuenta (US2)

```bash
# 1) Consultar desviación por cuenta 6400 (sueldos) – suponer real del diario = 45000
curl "$BASE/api/v1/presupuestos/seguimiento?ejercicio=2026&cuenta_id=<uuid_6400>" \
  -H "Authorization: Bearer $TOK_A"
# 200: [{ "importe_presupuestado": "48000.0000", "importe_real": "45000.0000",
#         "desviacion_absoluta": "-3000.0000", "desviacion_relativa": null...
#         (si no hay cuenta con uuid centro, sin_presupuesto = false) }]
# Nota: real - presupuesto = 45000 - 48000 = -3000 (debajo del presupuesto)

# 2) Cuenta sin presupuesto (ejemplo 6800 con real del diario = 2000)
curl "$BASE/api/v1/presupuestos/seguimiento?ejercicio=2026&cuenta_id=<uuid_6800>" \
  -H "Authorization: Bearer $TOK_A"
# 200: [{ "sin_presupuesto": true, "importe_presupuestado": "0.0000",
#         "importe_real": "2000.0000", "desviacion_absoluta": "2000.0000" }]
```

Validación pytest:
- `test_desviacion_absoluta`: real = 45000, presupuesto = 48000 → desviación absoluta = -3000.0000 exacta.
- `test_desviacion_relativa`: presupuesto ≠ 0 → relativa calculada; presupuesto = 0 → null.
- `test_real_signo_gasto`: real sumando Debe para grupo 6.

## Escenario 3 — Informes y cierre de periodo (US3)

```bash
# 1) Informe de desviación acumulada anual
curl "$BASE/api/v1/presupuestos/informes/desviacion?ejercicio=2026" \
  -H "Authorization: Bearer $TOK_A"
# 200: total_presupuestado, total_real, items por centro/cuenta con desviaciones

# 2) Cerrar el periodo
curl -X POST "$BASE/api/v1/presupuestos/informes/cerrar" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"ejercicio":2026,"periodo_id":"<uuid_periodo>"}'
# 200: { "periodo_id", "estado": "cerrado", "desviaciones_registradas": 5,
#         "fecha_cierre": "2026-09-16T..." }

# 3) Intentar modificar presupuesto después del cierre → 409
curl -X POST "$BASE/api/v1/presupuestos" ... -d '{"cuenta_id":"<uuid_6400>","importe":"100.0000",...}'
# 409: periodo cerrado
```

Validación pytest:
- `test_cierre_snapshot_trazable`: al cerrar, la tabla `Desviacion` tiene filas exactas por combinación; el `sin_presupuesto` se registra correctamente.
- `test_modificacion_tras_cierre`: POST presupuesto tras cierre → 409 (FR-004).

## Escenario 4 — Importación masiva de presupuesto

```bash
curl -X POST "$BASE/api/v1/presupuestos/importar" -H "Authorization: Bearer $TOK_A" \
  -F "file=@presupuesto_2026.csv"
# CSV: codigo_cuenta,centro,importe,tipo
# 6400,,48000.0000,gasto
# 7000,,120000.0000,ingreso
# Espera: 200, importadas=2, errores=[]
```

## Escenario 5 — Aislamiento multi-empresa (constitución III)

```bash
# Empresa A crea presupuesto
curl -X POST "$BASE/api/v1/presupuestos" -H "Authorization: Bearer $TOK_A" ...
# Empresa B consulta presupuestos → vacío (no ve los de A)
curl "$BASE/api/v1/presupuestos?ejercicio=2026" -H "Authorization: Bearer $TOK_B"
# 200: items=[] (aislamiento garantizado)

# Empresa B intenta cerrar el periodo de A
curl -X POST "$BASE/api/v1/presupuestos/informes/cerrar" -H "Authorization: Bearer $TOK_B" \
  -d '{"ejercicio":2026,"periodo_id":"<uuid_periodo_A>"}'
# 404
```

Validación pytest:
- `test_presupuesto_tenant_isolation`: empresa A crea presupuesto y periodo, empresa B no los ve ni puede cerrarlos (404/403).