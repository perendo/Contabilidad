# Quickstart Validation Guide: Catálogo Versionado del Plan de Cuentas (SPEC-025)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas base SPEC-001 con cuentas 430/431/472/570/572 y un asiento histórico de ejemplo). Variable de entorno `BASE/api/v1`.

## Escenario 1 — Registrar una nueva versión con vigencia (US1)

```bash
# 1) Alta de la versión (sin solape con versiones existentes)
curl -X POST "$BASE/api/v1/catalogo/versiones" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"codigo":"PGC-2026","fecha_inicio":"2026-01-01","fecha_fin":null,"cuentas":[{"operacion":"alta","codigo":"4310","nombre":"Clientes (pagos fraccionados)","padre_codigo":"431"}]}'
# Espera: 201, id, numero_version=2 (la 1 puede venir del seed), estado=borrador

# 2) Activar (mapeos completos)
curl -X POST "$BASE/api/v1/catalogo/versiones/$VER_ID/activar" -H "Authorization: Bearer $TOK_A"
# Espera: 200, estado=vigente

# 3) Comprobar que el asiento histórico sigue usando la versión de su fecha
curl "$BASE/api/v1/catalogo/vigente?fecha=2025-11-15" -H "Authorization: Bearer $TOK_A"
# Espera: 200, version del 2025 (resolucion=vigente), NO la nueva del 2026
```

Validación pytest:
- `test_solape_rechazado`: dos versiones con rangos solapados → 422 en la segunda (trigger + servicio).
- `test_resolucion_historica`: asiento de 2025 resuelve con versión de 2025; asiento de 2026 con la nueva; ningún asiento migra retroactivamente.
- `test_numero_version_correlativo`: tres versiones → numero_version 1, 2, 3 sin saltos.

## Escenario 2 — Cuenta eliminada visible en su contexto histórico (US1)

```bash
# 1) Baja de una cuenta con asientos: registrar versión 2026 con operacion "baja" de "4000"
# 2) Activar versión 2026
# 3) Consultar la cuenta en el contexto de 2025 (versión anterior)
curl "$BASE/api/v1/catalogo/vigente?fecha=2025-03-01" -H "Authorization: Bearer $TOK_A"
# La cuenta 4000 sigue disponible en el árbol de 2025
```

Validación pytest:
- `test_cuenta_baja_historica`: cuenta suprimida en 2026 sigue presente y apuntable en la versión de 2025; el asiento de 2025 que la usa no se rompe.

## Escenario 3 — Importar una actualización normativa con mapeo (US2)

```bash
# 1) Importar catálogo nuevo (CSV) con renombrado 4300 -> 4310 y una alta nueva
curl -X POST "$BASE/api/v1/catalogo/importar" -H "Authorization: Bearer $TOK_A" \
  -F "file=@catalogo_2026.csv" -F "codigo_version=PGC-2026-import"
# catalogo_2026.csv:
# operacion,codigo,nombre,padre_codigo,destino_codigo
# renombrado,4300,Clientes euros,430,4310
# alta,4310,Clientes pagos fraccionados,431,
# Espera: 200, nuevas=1, renombradas=1, suprimidas=0, mapeos=1, pendientes_mapeo=[]

# 2) Activar la versión importada
curl -X POST "$BASE/api/v1/catalogo/versiones/$VER_ID_IMPORT/activar" -H "Authorization: Bearer $TOK_A"
# Espera: 200, estado=vigente
```

Validación pytest:
- `test_import_mapeo`: la cuenta nueva 4310 se incorpora y la renombrada 4300 queda enlazada por `MapeoCuenta` a 4310.
- `test_suprimida_sin_mapeo`: import con baja sin destino → 200 con `pendientes_mapeo` y la activación bloqueada (422) hasta resolver.

## Escenario 4 — Reclasificar saldos para la apertura (US3)

```bash
# 1) Previsualización de la reclasificación (saldos de 2025 según mapeo)
curl "$BASE/api/v1/catalogo/reclasificar/preview?version_id=$VER_2026&ejercicio=2025" \
  -H "Authorization: Bearer $TOK_A"
# Espera: 200, items con cuenta_origen/importe/cuenta_destino

# 2) Confirmar reclasificación
curl -X POST "$BASE/api/v1/catalogo/reclasificar/confirmar" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"version_id":"<ver2026>","ejercicio":2025,"items":[{"cuenta_origen_id":"<acc4300>","importe":"12500.0000","cuenta_destino_id":"<cc4310>","mapeo_id":"<m1>"}]}'
# Espera: 200, reclasificaciones=1, asientos=[{asiento_id, cuadre:true}], total_importe="12500.0000"

# 3) Verificar cuadre de apertura (SPEC-009): Sum(saldos origen)==Sum(saldos destino)
```

Validación pytest:
- `test_reclasificacion_balance`: todo asiento ADJUSTMENT cumple Debe==Haber; suma origen == suma destino.
- `test_suprimida_saldo_sin_mapeo`: cuenta suprimida con saldo ≠ 0 y sin mapeo → preview 422 / activación bloqueada.
- `test_precision_reclasificacion`: importes con 4 decimales exactos, sin errores de redondeo.

## Escenario 5 — Aislamiento multi-empresa (constitución III)

```bash
# Versionar en empresa A
curl -X POST "$BASE/api/v1/catalogo/versiones" -H "Authorization: Bearer $TOK_A" ...
# Consultar la versión de A desde empresa B
curl -X GET "$BASE/api/v1/catalogo/versiones/$VER_A" -H "Authorization: Bearer $TOK_B"
# 404 — nunca filtrar datos de otra empresa; lo mismo para mapeos, reclasificaciones y resolución histórica
```

Validación pytest:
- `test_catalogo_tenant_isolation`: versión/mapeo/reclasificación de A invisible para B (404/403); intento de resolver cuenta vigente de B con contexto A → sin datos cruzados.