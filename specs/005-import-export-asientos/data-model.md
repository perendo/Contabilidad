# Data Model: Importación y Exportación Masiva de Asientos Contables (SPEC-005)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda operación se ejecuta sobre la empresa activa derivada de sesión.
- Importes en `NUMERIC(18,4)` / `Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## Entidades consumidas (no crea tablas nuevas)

Esta feature no crea tablas propias. Consume las entidades existentes:

- **JournalEntry** (SPEC-002): cabecera de asiento con `empresa_id`, `numero_asiento`, `ejercicio`, `fecha`, `concepto`, `estado`.
- **JournalEntryLine** (SPEC-002): líneas del asiento con `journal_entry_id`, `cuenta`, `debe`, `haber`, `detalle`.
- **CuentaContable** (SPEC-001): plan de cuentas con `empresa_id`, `codigo`, `apuntable`.
- **EjercicioContable** (SPEC-004): ejercicio con `empresa_id`, `año`, `abierto`.

## ResultadoImportacion (objeto de respuesta, no persistido)

Resultado de la previsualización de importación; se devuelve al usuario y no se almacena como tabla.

| Campo | Tipo | Reglas |
|-------|------|--------|
| total_asientos | INT | suma de asientos detectados en el archivo |
| asientos_validos | INT | asientos que pasan todas las validaciones |
| asientos_con_error | INT | = total_asientos - asientos_validos |
| errores | ARRAY[ErrorImportacion] | detalle por fila con error |

## ErrorImportacion (objeto de respuesta, no persistido)

Detalle de un error en una fila del archivo importado.

| Campo | Tipo | Reglas |
|-------|------|--------|
| fila | INT | número de línea en el archivo (1-indexed) |
| grupo_asiento | INT | identificador del asiento al que pertenece la fila |
| cuenta | VARCHAR(20) NULL | código de cuenta implicada si aplica |
| tipo_error | ENUM | `formato`, `cuenta_no_encontrada`, `cuenta_no_apuntable`, `ejercicio_cerrado`, `desbalanceo`, `fecha_invalida`, `importe_invalido`, `lado_vacio` |
| mensaje | VARCHAR(255) | descripción legible del error |

## ResultadoImportacionDefinitiva (objeto de respuesta, no persistido)

Resultado de la confirmación de importación definitiva.

| Campo | Tipo | Reglas |
|-------|------|--------|
| asientos_importados | INT | asientos persistidos correctamente |
| asientos_omitidos | INT | asientos que fallaron en la ejecución |
| primer_numero_asiento | BIGINT | primer número de asiento asignado |
| ultimo_numero_asiento | BIGINT | último número de asiento asignado |
| omisiones | ARRAY[ErrorImportacion] | motivo de cada asiento omitido |

## ResultadoExportacion (objeto de respuesta, no persistido)

Resultado de la exportación del libro diario.

| Campo | Tipo | Reglas |
|-------|------|--------|
| total_asientos | INT | asientos exportados |
| formato | ENUM | `CSV` / `XLSX` |
| contenido | BYTEA / STREAM | el fichero descargable |

## Resumen de relaciones

```
Archivo importado (CSV/XLSX) → parseo → ResultadoImportacion → usuario confirma →
  JournalEntry (SPEC-002) 1 ── n JournalEntryLine (cada línea)
  CuentaContable (SPEC-001) n ── 1 JournalEntryLine.cuenta
  EjercicioContable (SPEC-004) n ── 1 JournalEntry.ejercicio

JournalEntry (SPEC-002) → exportación → CSV/XLSX (ResultadoExportacion)
```
