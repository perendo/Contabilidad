# Data Model: Facturación Operativa (SPEC-007)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## SerieFactura

Serie de numeración configurable por empresa.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id) |
| codigo | VARCHAR(10) | identificador de serie (ej. "FV", "FC") |
| nombre | VARCHAR(100) | descripción de la serie |
| prefijo | VARCHAR(10) | prefijo del número (ej. "FV") |
| sufijo | VARCHAR(10) | sufijo (ej. año) |
| siguiente_numero | BIGINT | contador de numeración correlativa por (empresa_id, serie, ejercicio) — protegido con `SELECT ... FOR UPDATE` |
| estado | ENUM | `activa`, `inactiva` |

**Validaciones**: único (empresa_id, codigo); la numeración avanza por (empresa_id, serie_id, ejercicio) sin reutilizar números anulados.

## Factura

Cabecera de factura de venta o compra (cliente o proveedor).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| serie_id | UUID FK → SerieFactura | |
| numero | BIGINT | correlativo por (empresa_id, serie_id, ejercicio); asignado atómicamente |
| ejercicio | INT | año fiscal de la emisión |
| fecha | DATE | debe pertenecer a un ejercicio abierto (rechazo 400 si cerrado) |
| tipo | ENUM | `VENTA`, `COMPRA`, `RECTIFICATIVA` |
| tercero_id | UUID FK → SPEC-008 Tercero | cliente (venta) o proveedor (compra) |
| factura_original_id | UUID FK NULL → Factura | si es RECTIFICATIVA, la factura que rectifica |
| concepto_global | VARCHAR(255) | descripción |
| importe_base | NUMERIC(18,4) | suma de bases de líneas (derivada al confirmar) |
| importe_iva | NUMERIC(18,4) | total IVA |
| importe_recargo | NUMERIC(18,4) | total recargo de equivalencia (0 si no aplica) |
| importe_irpf | NUMERIC(18,4) | total IRPF (0 si no aplica) |
| importe_total | NUMERIC(18,4) | base + IVA + recargo - IRPF |
| regimen_caja | BOOLEAN | TRUE si criterio de caja (FR-011); deja IVA 477/472 diferido |
| iva_devengado | BOOLEAN | FALSE mientras el IVA está diferido (criterio de caja); SPEC-012 lo gestiona al cobro/pago |
| estado | ENUM | `borrador`, `emitida`, `anulada` |
| asiento_id | UUID FK NULL → SPEC-002 JournalEntry | asiento vinculado (nullable solo en borrador) |

**Transiciones de estado**: `borrador → emitida` (genera número + asiento, irreversible) | `emitida → anulada` (por rectificativa total) | `borrador → eliminada` (permitida).

**Cuota recargo** (FR-010): se calcula por línea y se totaliza en `importe_recargo`; se contabiliza en cuenta separada del IVA (477/472 recargo).

**Criterio de caja** (FR-011): la factura se emite con IVA íntegro; `iva_devengado=FALSE` marca el diferimiento; SPEC-012 revierte el estado al cobro/pago.

## FacturaLinea

Línea de factura con su base y tipos impositivos.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| factura_id | UUID FK → Factura | |
| descripcion | VARCHAR(255) | |
| cantidad | NUMERIC(18,4) | > 0 |
| precio_unitario | NUMERIC(18,4) | > 0 |
| porcentaje_descuento | NUMERIC(5,2) | 0 <= % <= 100; descuento propio de línea |
| base | NUMERIC(18,4) | cantidad × precio × (1 - descuento%); derivada |
| tipo_iva | NUMERIC(5,2) | 0, 4, 10, 21 según configuración de empresa |
| cuota_iva | NUMERIC(18,4) | base × tipo_iva (redondeo a 2 decimales a nivel de documento) |
| tipo_recargo | NUMERIC(5,2) | 0 si empresa no está en recargo de equivalencia; 5,2 / 1,4 / 0,5 en caso contrario |
| cuota_recargo | NUMERIC(18,4) | base × tipo_recargo si aplica |
| tipo_irpf | NUMERIC(5,2) | 0 si no aplica; 15/7/1 según configuración |
| base_irpf | NUMERIC(18,4) | base sobre la que aplica el IRPF |
| cuota_irpf | NUMERIC(18,4) | base_irpf × tipo_irpf |

**Validaciones**: `cantidad > 0`, `precio_unitario > 0`, tipos impositivos según configuración de empresa; `importe_total` nunca negativo; redondeo línea a línea a 2 decimales en la cuota.

## Resumen de relaciones

```
SerieFactura 1 ── n Factura
Factura 1 ── n FacturaLinea
Factura (rectificativa) FK factura_original_id ── 1 Factura (original)
Tercero (SPEC-008) 1 ── n Factura
JournalEntry (SPEC-002) 1 ── 0..1 Factura.asiento_id
EjercicioContable (SPEC-004) n ── 1 Factura.ejercicio

Asiento típico de venta con IVA:
  Debe: 430 (total) | Haber: 700 (base) + 477 (IVA) + 477 recargo (si aplica) - 475/473 (IRPF)
Asiento de compra con IVA:
  Debe: 600… (base) + 472 (IVA) + 472 recargo (si aplica) | Haber: 410 (total) - 475 (IRPF retenido)
Rectificativa: asiento REVERSAL con líneas invertidas (Debe↔Haber)
```