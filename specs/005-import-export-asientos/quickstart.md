# Quickstart Validation Guide: Importación y Exportación Masiva de Asientos Contables (SPEC-005)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa, plan de cuentas con cuentas apuntables 430, 572, 6200000; ejercicio abierto 2026).

## Scenario 1 — Previsualizar archivo con asientos válidos y erróneos

```bash
# 1) Crear archivo mixto (3 asientos: 2 válidos, 1 desbalanceado)
cat > /tmp/asientos_test.csv << 'EOF'
fecha;numero_asiento;concepto;cuenta;debe;haber
2026-01-15;1;Compra material oficina;6200000;500.00;
2026-01-15;1;;4100000;;500.00
2026-01-16;2;Pago proveedor;4100000;1200.00;
2026-01-16;2;;5720000;;1200.00
2026-01-17;3;Servicio;6200000;800.00;
2026-01-17;3;;4100000;;750.00
EOF

# 2) Previsualizar
curl -X POST "$BASE/api/v1/asientos/importar/previsualizar" \
  -H "Authorization: Bearer $TOK" \
  -F "file=@/tmp/asientos_test.csv"
# Espera: 200, total_asientos=3, asientos_validos=2, asientos_con_error=1
# Errores: fila 6, grupo_asiento=3, tipo_error=desbalanceo (800 != 750)
```

Validación pytest:
- `test_previsualizacion_no_escribe_nada`: previsualiza, verifica que no se crea ningún JournalEntry.
- `test_previsualizacion_desbalanceo`: archivo con desbalanceo, verifica que se reporta tipo_error=desbalanceo.
- `test_previsualizacion_cuenta_inexistente`: archivo con cuenta inexistente, verifica tipo_error=cuenta_no_encontrada.

## Scenario 2 — Importar asientos válidos definitivamente

```bash
# 1) Confirmar importación con el mismo archivo (solo los 2 asientos válidos se importan)
curl -X POST "$BASE/api/v1/asientos/importar/confirmar" \
  -H "Authorization: Bearer $TOK" \
  -F "file=@/tmp/asientos_test.csv"
# Espera: 201, asientos_importados=2, asientos_omitidos=1

# 2) Verificar numeración correlativa
curl "$BASE/api/v1/asientos?fecha_desde=2026-01-01&fecha_hasta=2026-12-31" \
  -H "Authorization: Bearer $TOK"
# Espera: asientos con numero_asiento consecutivo (sin saltos)
```

Validación pytest:
- `test_importar_asientos_balanceados`: importar 2 asientos válidos, verificar que ambos existen y están balanceados.
- `test_importar_numeracion_correlativa`: importar 3 asientos, verificar numero_asiento secuencial.
- `test_importar_ejercicio_cerrado`: asiento con fecha en ejercicio cerrado → se omite en la importación.

## Scenario 3 — Exportar el libro diario a CSV

```bash
# 1) Exportar diario de enero 2026
curl "$BASE/api/v1/asientos/exportar?fecha_desde=2026-01-01&fecha_hasta=2026-01-31&formato=CSV" \
  -H "Authorization: Bearer $TOK" -o diario_enero.csv
# Espera: 200, fichero CSV con cabeceras y filas de los asientos importados

# 2) Verificar contenido del CSV
# - Encoding UTF-8 con BOM
# - Separador ;
# - Importes con exactamente 4 decimales (ej. 500.0000)
# - Solo asientos de la empresa activa
```

Validación pytest:
- `test_exportar_csv_formato`: exportar y verificar encoding, separador y decimales.
- `test_exportar_csv_solo_empresa_activa`: crear asientos en empresa A y B, exportar desde A, verificar que no aparecen los de B.

## Scenario 4 — Exportar a XLSX

```bash
# Exportar diario de enero 2026 en formato Excel
curl "$BASE/api/v1/asientos/exportar?fecha_desde=2026-01-01&fecha_hasta=2026-01-31&formato=XLSX" \
  -H "Authorization: Bearer $TOK" -o diario_enero.xlsx
# Espera: 200, fichero XLSX con hoja "Diario", formatos de celda correctos
```

Validación pytest:
- `test_exportar_xlsx_hoja_diario`: verificar que el XLSX tiene hoja "Diario" con columnas correctas.

## Scenario 5 — Aislamiento multi-empresa (constitución III)

```bash
# Crear asientos en empresa A
curl -X POST "$BASE/api/v1/asientos/importar/confirmar" \
  -H "Authorization: Bearer $TOK_A" \
  -F "file=@/tmp/asientos_test.csv"

# Exportar desde empresa B → no debe ver los asientos de A
curl "$BASE/api/v1/asientos/exportar?fecha_desde=2026-01-01&fecha_hasta=2026-01-31" \
  -H "Authorization: Bearer $TOK_B" -o diario_B.csv
# Espera: diario_B.csv vacío (sin filas de datos, solo cabecera)

# Previsualizar desde empresa B con el mismo archivo → cuentas no encontradas (sin revelar que existen en A)
curl -X POST "$BASE/api/v1/asientos/importar/previsualizar" \
  -H "Authorization: Bearer $TOK_B" \
  -F "file=@/tmp/asientos_test.csv"
# Espera: errores de tipo cuenta_no_encontrada para las cuentas de A
```

Validación pytest:
- `test_aislamiento_empresa_importacion`: importar en A, verificar que B no ve los asientos.
- `test_aislamiento_empresa_cuentas`: cuentas de A reportadas como no encontradas desde B.
