# Quickstart Validation Guide: Libros de IVA y Modelos Fiscales (SPEC-012)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed minimo (empresa con NIF, plan de cuentas con cuentas 472/477 y de recargo, facturas emitidas/recibidas con IVA y sus asientos, vencimientos de SPEC-011 para criterio de caja).

## Scenario 1 — Consultar el libro de IVA emitidas del trimestre

```bash
# Con facturas emitidas en el 1T 2026:
curl "$BASE/api/v1/libros-iva/emitidas?ejercicio=2026&periodo=1&tipo_periodo=TRIMESTRE" \
  -H "Authorization: Bearer $TOK"
# Espera: 200, operaciones con base/cuota/tipo_iva, total_base y total_cuota
# Validacion: las bases/cuotas coinciden con las facturas contabilizadas (sin entrada manual)

# Aislamiento: la empresa B consulta el suyo y no ve el de A
curl "$BASE/api/v1/libros-iva/emitidas?ejercicio=2026&periodo=1&tipo_periodo=TRIMESTRE" \
  -H "Authorization: Bearer $TOK_B"
# Espera: 200, operaciones de B (distintas)
```

Validacion pytest:
- `test_libros_emitidas_derivan_facturas`: la suma de cuotas del libro == suma de lineas 477 de los asientos.
- `test_libros_no_cuadra_exclusion`: factura sin asiento no aparece en el libro.

## Scenario 2 — Calcular el modelo 303 con cuadre con libros

```bash
# Con ventas de 21% (base 10000, cuota 2100) y compras de 21% (base 5000, cuota 1050):
curl "$BASE/api/v1/modelos/303?ejercicio=2026&periodo=1&tipo_periodo=TRIMESTRE" \
  -H "Authorization: Bearer $TOK"
# Espera: 200, cuadre_libros=true
#   devengado.cuota.21 = 2100.0000, deducible.cuota.21 = 1050.0000
#   resultado.a_ingresar = 1050.0000 (o a_compensar si negativo)

# Si las cuotas de los libros difieren -> 422 descuadre_libros (defensivo)
```

Validacion pytest:
- `test_303_cuadre_con_libros`: resultado == devengado - deducible de los libros del periodo.
- `test_303_intracomunitarias`: las operaciones intracomunitarias quedan reflejadas (prepara 349).

## Scenario 3 — Exportar el modelo 303 con trazabilidad

```bash
# 1) Exportar el 303 del 1T 2026
curl -X POST "$BASE/api/v1/exportaciones" -H "Authorization: Bearer $TOK" \
  -d '{"modelo":"303","ejercicio":2026,"periodo":1,"tipo_periodo":"TRIMESTRE","formato":"csv"}'
# Espera: 201, exportacion_id, numero_exportacion=1, fichero con sha256

# 2) Descargar el fichero
curl "$BASE/api/v1/exportaciones/$EXP_ID/descargar" -H "Authorization: Bearer $TOK" -o 303.csv
# Espera: 200, adjunto con totales del trimestre

# 3) Re-exportar el mismo periodo -> advertencia y nuevo registro (trazabilidad)
curl -X POST "$BASE/api/v1/exportaciones" -H "Authorization: Bearer $TOK" \
  -d '{"modelo":"303","ejercicio":2026,"periodo":1,"tipo_periodo":"TRIMESTRE","formato":"csv"}'
# Espera: 201, numero_exportacion=2, advertencia="re-exportado"
```

Validacion pytest:
- `test_exportacion_303_identifica_periodo`: fichero contiene ejercicio/periodo y NIF de la empresa.
- `test_exportacion_trazabilidad`: multiples exportaciones del mismo periodo registran numeros correlativos y hashes.

## Scenario 4 — Recargo de equivalencia

```bash
# Con recargo 5.2% sobre ventas al minorista (base 1000, recargo 52.00):
curl "$BASE/api/v1/libros-iva/emitidas?ejercicio=2026&periodo=1&tipo_periodo=TRIMESTRE" \
  -H "Authorization: Bearer $TOK"
# Espera: operaciones con cuota IVA y recargo_cuota separado

curl "$BASE/api/v1/modelos/303?ejercicio=2026&periodo=1&tipo_periodo=TRIMESTRE" \
  -H "Authorization: Bearer $TOK"
# Espera: recargo_equivalencia.cuota = 52.0000 (separado del IVA general)
```

Validacion pytest:
- `test_recargo_cuota_separada`: cuota de recargo nunca se mezcla con cuota IVA en libros ni 303.
- `test_recargo_cuenta_diferenciada`: usa la cuenta de recargo configurada por empresa.

## Scenario 5 — Criterio de caja (IVA diferido)

```bash
# Factura con criterio de caja de 2026 (base 1000, cuota 210) cuyo vencimiento aun no se ha cobrado:
curl "$BASE/api/v1/libros-iva/emitidas?ejercicio=2026&periodo=1&tipo_periodo=TRIMESTRE" \
  -H "Authorization: Bearer $TOK"
# Espera: operacion con incluir_303=false (diferida, trazada)

curl "$BASE/api/v1/modelos/303?ejercicio=2026&periodo=1&tipo_periodo=TRIMESTRE" \
  -H "Authorization: Bearer $TOK"
# Espera: la cuota 210 NO esta en devengado; iva_diferido.pendiente = 210.0000

# Al cobrar el vencimiento (SPEC-011) -> la cuota entra en el 303 del periodo del cobro
curl "$BASE/api/v1/modelos/303?ejercicio=2026&periodo=2&tipo_periodo=TRIMESTRE" \
  -H "Authorization: Bearer $TOK"
# (depende de la fecha del cobro; el IVA pasa a liquidado y entra en el devengado)
```

Validacion pytest:
- `test_criterio_caja_diferido`: cuota diferida no entra en el 303 hasta el cobro/pago.
- `test_criterio_caja_liquidacion`: al saldarse el vencimiento, la cuota pasa al periodo del devengo real y queda trazada.

## Scenario 6 — Preparar 347 y 349

```bash
# 347 anual con operaciones > 3005.06
curl "$BASE/api/v1/modelos/347?ejercicio=2026" -H "Authorization: Bearer $TOK"
# Espera: operaciones agregadas por NIF/clave con importe_acumulado (solo > 3005.06)

# 349 intracomunitarias del 1T
curl "$BASE/api/v1/modelos/349?ejercicio=2026&periodo=1&tipo_periodo=TRIMESTRE" \
  -H "Authorization: Bearer $TOK"
# Espera: operaciones intracomunitarias agregadas por NIF
```

Validacion pytest:
- `test_347_limite_legal`: terceros con importe <= 3005.06 quedan excluidos del 347.
- `test_349_intracomunitarias`: solo operaciones intracomunitarias, agregadas por NIF del periodo.

## Scenario 7 — Aislamiento multi-empresa y SII

```bash
# SII deshabilitado por defecto
curl "$BASE/api/v1/sii/configuracion" -H "Authorization: Bearer $TOK"
# Espera: habilitado=false, periodicidad_303=TRIMESTRE

# Habilitar SII -> periodicidad ajustada a MES (advertencia)
curl -X POST "$BASE/api/v1/sii/configuracion" -H "Authorization: Bearer $TOK" \
  -d '{"habilitado": true, "identificador_emisor": "B12345678"}'
# Espera: habilitado=true, periodicidad_303=MES, advertencia

# Aislamiento: configuracion y libros de A no visibles en B
curl "$BASE/api/v1/libros-iva/emitidas?ejercicio=2026&periodo=1&tipo_periodo=MES" \
  -H "Authorization: Bearer $TOK_B"
# Espera: solo operaciones de B
```

Validacion pytest:
- `test_sii_ajusta_periodicidad_mensual`: habilitar SII cambia el 303 a MES.
- `test_sii_deshabilitado_409`: pedir XML SII sin habilitar -> 409.
- `test_aislamiento_fiscal_total`: empresa B no ve libros, modelos ni configuracion SII de A.