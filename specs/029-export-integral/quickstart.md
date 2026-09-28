# Quickstart Validation Guide: Export Integral del Tenant (SPEC-029)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa A y B, plan de cuentas con versiones, asientos, facturas, terceros, vencimientos, remesas, amortizaciones, cierres). Contratos en [contracts/api-contracts.md](contracts/api-contracts.md) y formato ZIP en [contracts/export-layout.md](contracts/export-layout.md); modelo en [data-model.md](data-model.md).

Convención: `$BASE=http://localhost:8000/api/v1`; `$TOK` = token de sesión; la empresa activa se envía como cabecera `X-Empresa-Id: <empresa_id>`.

## Scenario 1 — Exportar el tenant completo (portabilidad/backup)

```bash
# 1) Crear y generar la exportación integral
curl -X POST "$BASE/exportaciones" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -H "Content-Type: application/json" \
  -d '{"tipo":"INTEGRAL"}'
# Espera: 201, estado=lista, sha256, tamano_bytes, n_bloques=17, manifiesto con todos los bloques

# 2) Descargar el archivo
curl "$BASE/exportaciones/$EXPORT_ID/descarga" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -o export.zip
# Espera: 200 application/zip

# 3) Inspeccionar el contenido
# unzip -l export.zip   → lista bloques/001_..017_ + manifest.json
# El manifest.json interior refleja todos los bloques y conteos
```

Validación pytest:
- `backend/tests/integration/test_export_completo.py`: verifica inventario completo (todos los bloques presentes, conteos correctos).
- `backend/tests/unit/test_zip_layout.py`: verifica estructura determinista del ZIP.
- `backend/tests/unit/test_manifiesto.py`: verifica `manifest.json` interior.

## Scenario 2 — Verificar la integridad de la exportación

```bash
# 1) Verificar por API (recalcula SHA-256)
curl -X POST "$BASE/exportaciones/$EXPORT_ID/verificar" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP"
# Espera: 200, integro=true, sha256_calculado == sha256_manifiesto

# 2) Verificación local con el manifest
Get-FileHash export.zip -Algorithm SHA256   # debe coincidir con sha256_fichero del manifest.json interior
```

Validación pytest:
- `backend/tests/integration/test_verificar_integridad.py`: huella intacta → `integro=true`; alteración de un byte → `integro=false` con diferencias.
- `backend/tests/unit/test_hash_integridad.py`: comparación SHA-256 determinista.

## Scenario 3 — Exportación con filtro de rango de ejercicios

```bash
curl -X POST "$BASE/exportaciones" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -d '{"tipo":"INTEGRAL","ejercicio_desde":2025,"ejercicio_hasta":2025}'
# Espera: 201, estado=lista; bloques asientos/facturas/vencimientos con ejercicio_min==ejercicio_max==2025
# Bloques atemporales (plan_cuentas, terceros, configuracion) se exportan completos
```

Validación pytest: `backend/tests/integration/test_export_rango_ejercicio.py`.

## Scenario 4 — Aislamiento multi-empresa (constitución III)

```bash
# Empresa A genera su exportación
curl -X POST "$BASE/exportaciones" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP_A" -d '{"tipo":"INTEGRAL"}'
# Empresa B intenta descargar/ver los datos de A → 404 (nunca filtra datos de otra empresa)
curl "$BASE/exportaciones/$EXPORT_A/descarga" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP_B"   # 404
# El ZIP de A NO contiene ningún registro de B (verificado por test)
```

Validación pytest: `backend/tests/integration/test_export_tenant_isolation.py` — exportación A contiene 0 registros de B en TODOS los bloques.

## Scenario 5 — Bloque SII (opcional)

```bash
# 1) Configurar SII (previa creación de ConfigSii con obligado_sii=true)
curl -X POST "$BASE/exportaciones" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -d '{"tipo":"SII"}'
# Espera: 201; el ZIP incluye bloques/datos_sii/facturas_emitidas.json y facturas_recibidas.json

# 2) Consultar el bloque SII por API
curl "$BASE/exportaciones/$EXPORT_ID/sii" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP"
# Espera: 200, config + registros con campos AEAT (NIF, FechaOperacion, BaseImponible, CuotaRepercutida...)
```

Validación pytest: `backend/tests/integration/test_bloque_sii.py` — verifica campos AEAT, precisión decimal y consistencia con las facturas.

## Scenario 6 — Tenant con datos incompletos (manifiesto refleja el contenido real)

```bash
# Empresa sin remesas ni amortizaciones: la exportación se genera igualmente
curl -X POST "$BASE/exportaciones" -H "Authorization: Bearer $TOK" \
  -H "X-Empresa-Id: $EMP" -d '{"tipo":"INTEGRAL"}'
# Espera: 201; bloques remesas y amortizaciones presentes con conteo_registros=0
# El manifiesto refleja exactamente lo que contiene (edge case de la spec)
```

Validación pytest: `backend/tests/integration/test_export_completo.py` (caso tenant con bloques vacíos → conteos 0 y verificación `integro=true`).