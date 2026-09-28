# File Layouts: Importación y Exportación Masiva de Asientos Contables (SPEC-005)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

## 1. Archivo de importación (CSV)

Formato de texto plano, encoding UTF-8 (BOM aceptado) o ISO-8859-1 (detectado automáticamente).

- **Separador**: `;` (punto y coma) por defecto; auto-detectable si el archivo tiene `,` o `\t`.
- **Decimales**: punto (`.`) o coma (`,`) como separador decimal; auto-detectado por el parseador.
- **Cabecera obligatoria** (primera fila):

```
fecha;numero_asiento;concepto;cuenta;debe;haber
```

- **Filas de datos** (una línea por apunte/linha del asiento):

| Campo | Tipo | Formato | Reglas |
|-------|------|---------|--------|
| fecha | DATE | YYYY-MM-DD | Requerido; debe pertenecer a un ejercicio abierto de la empresa activa |
| numero_asiento | INT | numérico | Opcional; identifica el grupo de filas que forman un mismo asiento. Si se omite, todas las filas consecutivas sin número forman un solo asiento |
| concepto | VARCHAR(255) | texto libre | Requerido; se guarda como concepto de la cabecera si es la primera fila del grupo, o como detalle de la línea si es posteriores |
| cuenta | VARCHAR(20) | código del plan | Requerido; debe existir en el plan de cuentas de la empresa activa y ser apuntable |
| debe | VARCHAR(20) | string decimal | Importe al Debe en formato decimal (ej. "1250.00" o "1.250,00"); al menos uno de debe/haber debe ser > 0 |
| haber | VARCHAR(20) | string decimal | Importe al Haber; al menos uno de debe/haber debe ser > 0 |

**Agrupación de asientos multilínea**: Las filas con el mismo valor de `numero_asiento` forman un solo asiento. Si `numero_asiento` se omite, todas las filas consecutivas sin número (o con número vacío) se agrupan en un solo asiento hasta encontrar un nuevo número o fin de archivo.

**Ejemplo**:

```csv
fecha;numero_asiento;concepto;cuenta;debe;haber
2026-01-15;1;Compra material oficina;6200000;500.00;
2026-01-15;1;;4100000;;500.00
2026-01-16;2;Pago proveedor;4100000;1200.00;
2026-01-16;2;;5720000;;1200.00
2026-01-17;;Servicio consultoria;6260000;800.00;
2026-01-17;;4100000;;800.00
```

## 2. Archivo de importación (XLSX)

Hoja activa del libro Excel.

- **Cabecera obligatoria** (fila 1):

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| fecha | numero_asiento | concepto | cuenta | debe | haber |

- **Filas de datos** (fila 2 en adelante): mismos tipos y reglas que el CSV.
- **Formato de celdas de importe**: formato numérico o texto; el parser acepta ambos. Si es numérico, se convierte a `Decimal` sin pasar por `float` (mediante `str(valor_celda)` y `Decimal(str(...))`).
- **Encoding**: UTF-8 (estándar XLSX).

## 3. Archivo de exportación del libro diario (CSV)

Generado por el backend; el usuario descarga el fichero.

- **Encoding**: UTF-8 con BOM (`\xEF\xBB\xBF`).
- **Separador**: `;` (punto y coma).
- **Decimales**: punto como separador decimal; exactamente 4 decimales (ej. `1250.0000`).
- **Cabecera**:

```
fecha;numero_asiento;concepto;cuenta;detalle;debe;haber
```

- **Filas de datos**:

| Campo | Tipo | Formato | Reglas |
|-------|------|---------|--------|
| fecha | DATE | YYYY-MM-DD | Fecha del asiento |
| numero_asiento | BIGINT | numérico | Número correlativo del asiento |
| concepto | VARCHAR(255) | texto | Concepto de la cabecera del asiento |
| cuenta | VARCHAR(20) | código | Código de la cuenta del apunte |
| detalle | VARCHAR(255) | texto | Detalle de la línea (puede estar vacío) |
| debe | VARCHAR(20) | decimal 4d | Importe al Debe, exactamente 4 decimales; 0.0000 si no aplica |
| haber | VARCHAR(20) | decimal 4d | Importe al Haber, exactamente 4 decimales; 0.0000 si no aplica |

**Orden**: ordenados por `fecha`, luego `numero_asiento`, luego `cuenta`.

## 4. Archivo de exportación del libro diario (XLSX)

Generado por el backend.

- **Hoja única**: nombre "Diario".
- **Cabecera** (fila 1): mismas columnas que el CSV (`fecha`, `numero_asiento`, `concepto`, `cuenta`, `detalle`, `debe`, `haber`).
- **Formato de celdas de importe**: formato numérico con 4 decimales fijos.
- **Orden**: igual que CSV.

## Reglas comunes

- La previsualización de importación no escribe nada; la confirmación re-valida con las mismas reglas.
- El parseo de valores decimales acepta tanto punto como coma como separador decimal, y elimina separadores de miles (puntos o comas, detectados por contexto).
- Los valores vacíos en `debe` o `haber` se interpretan como `0.0000`.
- Se rechaza cualquier fila donde tanto `debe` como `haber` sean 0 o vacíos.
