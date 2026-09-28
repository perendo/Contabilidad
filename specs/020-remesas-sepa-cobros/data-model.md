# Data Model: Remesas SEPA y Soporte Magnético (SPEC-020)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión.
- Toda entidad con UUID conserva su PK técnica y añade índice único `(empresa_id, id)`; toda referencia entre entidades tenant usa FK compuesta que incluye `empresa_id`.
- Los índices de unicidad funcional siempre empiezan por `empresa_id` (por ejemplo `(empresa_id, ejercicio, numero_remesa)`), y las relaciones activas usan índices parciales tenant-scoped.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## Remesa

Agrupación de recibos para domiciliación, con numeración correlativa por empresa + ejercicio.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id) |
| ejercicio | INT | año fiscal; con empresa_id forma la secuencia de numeración |
| numero_remesa | BIGINT | correlativo por (empresa_id, ejercicio), asignado atómicamente |
| fecha_emision | DATE | día de la emisión del fichero |
| fecha_cargo | DATE NULL | NULL en cabecera cuando hay varias fechas; cada línea conserva su fecha y cada grupo de fichero usa esa fecha |
| formato | ENUM | `SEPA_DD` (predeterminado) / `CSB_19_19` |
| tipo_adeudo | ENUM | `CORE` / `B2B` |
| importe_total | NUMERIC(18,4) | suma de importes de recibos; check > 0 |
| estado | ENUM | `borrador`, `emitida`, `cobrada`, `devuelta` (parcialmente devuelta) |
| fichero_id | UUID NULL | referencia al blob generado tras emitir; el fichero contiene grupos por fecha de cargo |
| creado_por / created_at | | auditoría |

**Validaciones**: número correlativo único por (empresa_id, ejercicio); índice único `(empresa_id, id)` para referencias compuestas; si hay un recibo sin IBAN o un B2B sin mandato → bloqueo de emisión; los recibos solo proceden de vencimientos pendientes de la empresa activa.

**Transiciones de estado**: `borrador → emitida` (genera fichero) | `emitida → cobrada` (por marcado/conciliación) | `emitida/cobrada → devuelta` (por R19/C19).

## ReciboRemesa

Línea de remesa que referencia el vencimiento a domiciliar.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| remesa_id | UUID FK → Remesa | |
| vencimiento_id | UUID FK → SPEC-011 Vencimiento | único por remesa |
| recibo_num | VARCHAR | identificador del recibo (gobernado por vencimiento) |
| tercero_id | UUID FK → SPEC-008 | |
| iban | VARCHAR(34) | IBAN del tercero en el momento de incluir |
| importe | NUMERIC(18,4) | > 0; neto si aplica descuento |
| fecha_cargo | DATE | fecha de vencimiento usada por el grupo del fichero |
| descuento_id | UUID FK NULL → CondicionProntoPago | si se aplica pronto pago |
| estado | ENUM | `pendiente`, `remesado`, `cobrado`, `devuelto` |
| asiento_cobro_id | UUID FK NULL → SPEC-002 JournalEntry | asiento del cobro (confirmado) |
| fecha_cobro | DATE NULL | |

**Validaciones**: índice único parcial `(empresa_id, vencimiento_id)` para remesas activas; FKs compuestas `(empresa_id, remesa_id)` y `(empresa_id, vencimiento_id)`; exclusión de recibos ya cobrados o sin IBAN.

**Transiciones**: `pendiente → remesado` (emisión) | `remesado → cobrado` (marcado/conciliación, genera/deja el asiento de SPEC-011) | `remesado/cobrado → devuelto` (devolución).

## DevolucionRecibo

Registro de rechazo/baja R19/C19 con su reversión contable.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| recibo_remesa_id | UUID FK → ReciboRemesa | |
| codigo | VARCHAR(10) | código bancario normalizado; admite `MD01`, `MD06`, `AC04`, `R-CUST` y equivalentes |
| motivo | VARCHAR(255) | descripción del código |
| fecha_registro | DATE | |
| fecha_cargo_original | DATE | la fecha de cargo que generó el abono |
| importe | NUMERIC(18,4) | importe revertido |
| importe_gastos | NUMERIC(18,4) DEFAULT 0 | gastos de devolución (opcionales) |
| asiento_reversal_id | UUID FK → SPEC-002 JournalEntry | asiento `REVERSAL` (no nulo) |
| estado_reclamacion | ENUM | `sin_reclamacion`, `reclamada`, `resuelta`, `desestimada` |

**Validaciones**: el importe a revertir <= importe del cobro; `importe_gastos >= 0`; el `REVERSAL` cuadra, incluye los gastos en 626 cuando proceda y enlaza al asiento original sin modificarlo. El identificador externo del retorno es único por empresa para evitar reprocesados.

**Transición**: al crear, `ReciboRemesa.estado → devuelto` y `Vencimiento` (SPEC-011) vuelve a `pendiente`.

## Reclamacion

Seguimiento posterior a la devolución (opcional).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| devolucion_id | UUID FK → DevolucionRecibo | FK compuesta con `empresa_id` |
| fecha_registro | DATE | |
| estado | ENUM | `abierta`, `en_curso`, `resuelta`, `desestimada` |
| observaciones | TEXT | |

**Validación**: una devolución tiene a lo sumo una reclamación activa.

## CondicionProntoPago

Condiciones de pronto pago del tercero (amplía SPEC-008, T-08).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| tercero_id | UUID FK → SPEC-008 Tercero | |
| plazo_dias | INT | > 0 |
| porcentaje | NUMERIC(5,2) | 0 < % <= 100 |
| vigente | BOOLEAN | |
| override_factura_id | UUID FK NULL → SPEC-007 Factura | override por factura si aplica |

**Validación**: un único registro vigente por (empresa_id, tercero_id); si `override_factura_id` no es nulo, la condición aplica solo a esa factura.

## MandatoSepa

Mandato de domiciliación (obligatorio para B2B; recomendable CORE).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| tercero_id | UUID FK → SPEC-008 | |
| mandato_ref | VARCHAR(35) | identificador único del mandato |
| fecha_firma | DATE | |
| tipo | ENUM | `CORE` / `B2B` |
| estado | ENUM | `firmado`, `caducado`, `revocado` |

**Validación**: para emitir un recibo **B2B**, el mandato debe estar `firmado` y `tipo=B2B`; para CORE se distingue primera domiciliación de recurrente y se exige el mandato/estado correspondiente.

## BlobFichero

Fichero de domiciliación generado (SEPA XML o CSB 19.19) y ficheros R19/C19 recibidos.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| tipo | ENUM | `remesa_sepa`, `remesa_csb1919`, `r19`, `c19` |
| contenido | BYTEA | el fichero crudo |
| sha256 | CHAR(64) | huella de integridad |
| created_at | TIMESTAMPTZ | |

**Validación**: la huella se calcula sobre el contenido; la regeneración de un fichero ya emitido exige estado `borrador` (la remesa emitida no regenera su blob salvo proceso de re-emisión explícita con trazabilidad).

## Resumen de relaciones

```
Tercero (SPEC-008/020) 1 ── n CondicionProntoPago
Tercero (SPEC-008/020) 1 ── n MandatoSepa
Vencimiento (SPEC-011) 1 ── 1 ReciboRemesa (activa)
Remesa 1 ── n ReciboRemesa
ReciboRemesa 1 ── 0..1 DevolucionRecibo
DevolucionRecibo 1 ── 0..1 Reclamacion
Asiento (SPEC-002) 1 ── 0..1 (asiento_cobro / asiento_reversal)
BlobFichero 1 ── 1 Remesa.fichero_id
```