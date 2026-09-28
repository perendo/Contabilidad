# Factura Format: Estructura de Factura y Cálculo de Impuestos (SPEC-007)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Descripción de la estructura canónica de una factura emitida y el cálculo de sus importes, incluyendo recargo de equivalencia (FR-010) y criterio de caja (FR-011). Este contrato define el formato de datos interno y los campos que se serializan en la API y en la exportación.

## 1. Estructura de la factura

### Cabecera (`Factura`)

| Campo | Formato | Reglas |
|-------|---------|--------|
| id | UUID | |
| empresa_id | BIGINT | aislamiento multi-tenant |
| serie_id | UUID | FK a SerieFactura |
| numero | VARCHAR(20) | `{prefijo}{correlativo}` (ej. `FV1`), sin saltos; un anulado no se reutiliza |
| ejercicio | INT | año fiscal |
| fecha | DATE | YYYY-MM-DD; dentro de un ejercicio abierto |
| tipo | ENUM | `VENTA` / `COMPRA` / `RECTIFICATIVA` |
| tercero_id | UUID | FK a SPEC-008 |
| factura_original_id | UUID NULL | solo en RECTIFICATIVA |
| importe_base | NUMERIC(18,4) | suma de bases → string decimal `"500.0000"` |
| importe_iva | NUMERIC(18,4) | suma de cuotas IVA |
| importe_recargo | NUMERIC(18,4) | suma de cuotas de recargo (0 si no aplica) |
| importe_irpf | NUMERIC(18,4) | suma de cuotas IRPF (0 si no aplica) |
| importe_total | NUMERIC(18,4) | base + IVA + recargo − IRPF; nunca negativo |
| regimen_caja | BOOLEAN | TRUE si criterio de caja (FR-011) |
| iva_devengado | BOOLEAN | FALSE si IVA diferido pendiente de SPEC-012 |
| estado | ENUM | `borrador` / `emitida` / `anulada` |
| asiento_id | UUID NULL | asiento vinculado (SPEC-002) |

### Línea (`FacturaLinea`)

| Campo | Formato | Reglas |
|-------|---------|--------|
| descripcion | VARCHAR(255) | |
| cantidad | NUMERIC(18,4) | > 0 |
| precio_unitario | NUMERIC(18,4) | > 0 |
| porcentaje_descuento | NUMERIC(5,2) | 0 ≤ % ≤ 100 |
| base | NUMERIC(18,4) | `cantidad × precio_unitario × (1 − descuento/100)` |
| tipo_iva | NUMERIC(5,2) | 0 / 4 / 10 / 21 según configuración de empresa |
| cuota_iva | NUMERIC(18,4) | `base × tipo_iva / 100`, redondeo a 2 decimales (nivel documento) |
| tipo_recargo | NUMERIC(5,2) | 0 / 5,20 / 1,40 / 0,50 según régimen de la empresa (FR-010) |
| cuota_recargo | NUMERIC(18,4) | `base × tipo_recargo / 100` |
| tipo_irpf | NUMERIC(5,2) | 0 / 15 / 7 / 1 según configuración |
| base_irpf | NUMERIC(18,4) | base sobre la que retiene |
| cuota_irpf | NUMERIC(18,4) | `base_irpf × tipo_irpf / 100` |

## 2. Cálculo de importes (todos en `Decimal`)

```text
por línea:
  base          = cantidad × precio_unitario × (1 − porcentaje_descuento/100)
  cuota_iva     = base × tipo_iva / 100           # redondeado a 2 decimales
  cuota_recargo = base × tipo_recargo / 100       # solo si empresa en recargo de equivalencia
  cuota_irpf    = base_irpf × tipo_irpf / 100

cabecera (suma de líneas):
  importe_base    = Σ base
  importe_iva     = Σ cuota_iva
  importe_recargo = Σ cuota_recargo
  importe_irpf    = Σ cuota_irpf
  importe_total   = importe_base + importe_iva + importe_recargo − importe_irpf
```

Reglas:
- Todo cálculo se hace con `Decimal`; `float` PROHIBIDO.
- El redondeo de cuotas es a 2 decimales (nivel fiscal). El asiento usa `NUMERIC(18,4)`.
- Si el cálculo del cliente no cuadra con el del backend (discrepancia > 0 en el 4º decimal), se rechaza con 422 (edge case "IVA/IRPF no cuadran con la base").
- `importe_recargo > 0` solo si la empresa está en régimen de recargo de equivalencia.

## 3. Recargo de equivalencia (FR-010)

- Se calcula por línea como `cuota_recargo = base × tipo_recargo / 100`, con tipos: **5,2 %** (general), **1,4 %** (reducido y superreducido), **0,5 %** (productos manufacturados).
- La cuota se contabiliza en **cuenta separada del IVA**: 477/472 cuota recargo.
- En el asiento, el IVA y el recargo aparecen desglosados (dos líneas o una con detalle separado), nunca fusionados.

## 4. Criterio de caja (FR-011)

- Régimen optativo por empresa. La factura se emite con **IVA íntegro** (`regimen_caja=true`, `iva_devengado=false`).
- El IVA queda en 477/472 con saldo **pendiente de liquidación**: el asiento de emisión contabiliza el IVA devengado formalmente, pero `iva_devengado=false` marca el diferimiento.
- **SPEC-012** (libros de IVA) gestiona la liquidación al producirse el cobro (ventas) o pago (compras), revirtiendo `iva_devengado` a `true`.
- Este contrato solo fija el marcado; el procesamiento del devengo es de SPEC-012.

## 5. Asiento vinculado (generado en la misma transacción)

Venta con recargo de equivalencia y sin IRPF:

```text
Debe:   43000xx (tercero cliente)   importe_total
Haber:  70000xx (ventas)            importe_base
Haber:  47700xx (IVA)               importe_iva
Haber:  47700xx (recargo)           importe_recargo
```

Compra con IVA e IRPF retenido:

```text
Debe:   60000xx (gasto)             importe_base
Debe:   47200xx (IVA)               importe_iva
Haber:  41000xx (tercero proveedor) importe_base + importe_iva − importe_irpf
Haber:  47500xx (IRPF retenido)     importe_irpf
```

Rectificativa: las líneas del asiento original se invierten (Debe↔Haber); el asiento generado es `REVERSAL` y enlaza vía `asiento_original_id`; el original no se modifica.

## 6. Estructura de descuentos

- **Descuento de línea** (`porcentaje_descuento`): se refleja en la base (precio × (1 − %)). No genera línea de asiento propia.
- **Descuento global / por pronto pago** (de tercero): gestionado en SPEC-008 (condición de pronto pago) y aplicado en la liquidación de SPEC-011/020, no en la factura.
- El descuento nunca produce `importe_total` negativo.