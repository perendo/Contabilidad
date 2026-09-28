# Data Model: Libros de IVA y Modelos Fiscales (SPEC-012)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitucion):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` en PK/indices y filtros; se deriva de sesion.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoria en la misma transaccion ACID.
- Numeracion correlativa por (empresa_id, ejercicio) asignada atomicamente.

## Libro IVA (emitidas / recibidas / intracomunitarias)

Registro derivado (calculado bajo demanda, sin persistencia de estado). Cada linea deriva de una factura (SPEC-007) y de su asiento (SPEC-002).

| Campo (JSON) | Tipo | Reglas |
|-------|------|--------|
| empresa_id | BIGINT | |
| ejercicio | INT | |
| tipo_libro | ENUM | `emitidas` / `recibidas` / `intracomunitarias` |
| factura_id | UUID FK → SPEC-007 | |
| nif_tercero | VARCHAR(9) | especificado por tercero (SPEC-008) |
| fecha_expedicion | DATE | |
| fecha_operacion | DATE | (criterio de caja: fecha de devengo real) |
| numero_factura | VARCHAR(30) | |
| base | NUMERIC(18,4) | base imponible |
| cuota | NUMERIC(18,4) | cuota IVA |
| tipo_iva | VARCHAR(10) | tipo aplicado (21/10/5/0...) |
| recargo_cuota | NUMERIC(18,4) DEFAULT 0 | cuota de recargo de equivalencia (separada) |
| incluir_303 | BOOLEAN | false para IVA diferido de caja pendiente |
| sii_obligatoria | BOOLEAN | si la empresa tiene SII habilitado |

**Validacion**: `base * tipo / 100 == cuota` (con tolerancia decimal de centimo); para operaciones recibidas la cuota debe ser deducible o no segun configuracion de cuenta; las facturas sin asiento se excluyen de los libros hasta que su asiento exista (edge case).

## PeriodoFiscal

Periodo (trimestre o mes) del modelo 303 por empresa y ejercicio.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio | INT | |
| tipo_periodo | ENUM | `TRIMESTRE` / `MES` |
| numero_periodo | INT | 1-4 (trimestre) o 1-12 (mes) |
| fecha_inicio / fecha_fin | DATE | rangos no solapados dentro del ejercicio |
| estado | ENUM | `pendiente`, `libros_generados`, `303_calculado`, `exportado` |

**Validaciones**: unicidad (empresa_id, ejercicio, tipo_periodo, numero_periodo); el estado `exportado` impide recalcular el 303 sin trazar la regeneracion.

## ExportacionModelo

Registro de una exportacion de modelo (303/347/349) con trazabilidad.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio | INT | |
| modelo | ENUM | `303` / `347` / `349` |
| numero_exportacion | BIGINT | correlativo por (empresa_id, ejercicio, modelo) |
| periodo_id | UUID FK NULL → PeriodoFiscal | para 303/349 (347 es anual) |
| fecha_exportacion | TIMESTAMPTZ | UTC |
| usuario_id | UUID FK → SPEC-003 | |
| contenido_hash | CHAR(64) | sha256 del fichero generado |
| fichero_json | JSONB | los totales del modelo (para verificar cuadres) |
| estado | ENUM | `generado`, `regenerado`, `anulado` |

**Validaciones**: unicidad de numero_exportacion por (empresa, ejercicio, modelo); regenerar un periodo `exportado` exige trazabilidad (nueva ExportacionModelo con estado `regenerado`); el hash permite verificar integridad del fichero.

## ConfiguracionSII

Configuracion del enlace SII opcional por empresa.

| Campo | Tipo | Reglas |
|-------|------|--------|
| empresa_id | BIGINT PK | |
| habilitado | BOOLEAN DEFAULT false | |
| obligatorio | BOOLEAN | si la empresa esta obligada (mensualidad 303) |
| identificador_emisor | VARCHAR | NIF de la empresa (emitida) |
| endpoint_ejecucion | TEXT NULL | reservado para SPEC-029 (no se usa en esta feature) |
| updated_at | TIMESTAMPTZ | auditoria de configuracion |

**Validacion**: si `habilitado=true`, la periodicidad del 303 debe ser `MES` (regla SII); no hay envio en esta feature.

## IVADiferidoCaja

Trazabilidad del IVA diferido por criterio de caja hasta su liquidacion.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| factura_id | UUID FK → SPEC-007 | |
| vencimiento_id | UUID FK → SPEC-011 Vencimiento | vinculo a cobro/pago |
| cuota_diferida | NUMERIC(18,4) | IVA esperando cobro/pago |
| fecha_devengo_real | DATE NULL | fecha de cobro/pago que liquida |
| estado | ENUM | `diferido`, `liquidado` |

**Transicion**: `diferido → liquidado` cuando el vencimiento (SPEC-011) deja de tener saldo pendiente; en ese momento la cuota entra en el 303 del periodo del cobro/pago.

## Modelo 303 / 347 / 349 (calculado, no persistido salvo en ExportacionModelo.fichero_json)

- **303**: casillas de devengado (base/cuota por tipo, operaciones corrientes y intracomunitarias), deducible (por tipo), resultado (a ingresar/compensar) y recargo de equivalencia separado.
- **347**: agregacion por NIF y clave operacional (> 3.005,06 EUR anuales).
- **349**: agregacion por NIF del periodo (importe por clave de operacion).

Se exponen como JSON con `cuadre` verificado en backend contra los libros del periodo.

## Resumen de relaciones

```
PeriodoFiscal 1 ── n Libro IVA (derivado, no persistido directamente)
Factura (SPEC-007) 1 ── n LibroIVA (lineas derivadas)
LibroIVA ── derivados de asientos (SPEC-002) y cuentas 472/477 (SPEC-001)
ExportacionModelo 1 ── 1 PeriodoFiscal (para 303/349; NULL para 347)
ConfiguracionSII 1 ── 1 Empresa (SPEC-003)
Vencimiento (SPEC-011) 1 ── 0..1 IVADiferidoCaja
```