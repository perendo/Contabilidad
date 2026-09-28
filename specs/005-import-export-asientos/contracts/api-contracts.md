# API Contracts: Importación y Exportación Masiva de Asientos Contables (SPEC-005)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1` (todos los endpoints exigen la cabecera de empresa activa derivada de sesión; la empresa activa se deriva exclusivamente de la sesión, nunca del path). Respuestas JSON; importes como strings decimales (p. ej. `"123.4500"`), nunca números de coma flotante.

**Nota de multi-tenancy**: la empresa activa se deriva exclusivamente de la sesión (token de Authorization). No se acepta `empresa_id` en el path ni en el body del request.

## Previsualización de importación

### POST `/api/v1/asientos/importar/previsualizar`

Recibe un archivo CSV o XLSX y devuelve el resultado de la pre-validación (dry-run) sin escribir nada en la base de datos.

- **Content-Type**: `multipart/form-data`
- **Body**: campo `file` con el archivo (CSV o XLSX), tamaño máximo configurable (default 10 MB).
- **200**: `{ "total_asientos": 120, "asientos_validos": 115, "asientos_con_error": 5, "errores": [{"fila": 3, "grupo_asiento": 12, "cuenta": "6100000", "tipo_error": "cuenta_no_apuntable", "mensaje": "Cuenta 6100000 no es apuntable"}] }`
- **422**: `{ "detail": "Formato de archivo no soportado" }` o `"Columnas requeridas faltantes: fecha, cuenta, debe, haber"` o `"Tamaño de archivo excedido (máx 10 MB)"`.
- **401/403**: autenticación/permisos (SPEC-003).
- **404**: nunca aplica (el endpoint siempre existe).

**Reglas**: no se escribe nada en la BD; se valida existencia y apuntabilidad de cuentas contra la empresa activa; se valida que la fecha no pertenezca a un ejercicio cerrado; se valida `Sum(Debe) == Sum(Haber)` por asiento en precisión decimal.

## Importación definitiva

### POST `/api/v1/asientos/importar/confirmar`

Re-valida y persiste los asientos válidos del archivo previamente previsualizado.

- **Content-Type**: `multipart/form-data`
- **Body**: campo `file` con el mismo archivo que se previsualizó (re-validación).
- **201**: `{ "asientos_importados": 115, "asientos_omitidos": 5, "primer_numero_asiento": 4501, "ultimo_numero_asiento": 4615, "omisiones": [{"fila": 3, "tipo_error": "ejercicio_cerrado", "mensaje": "..."}] }`
- **422**: `{ "detail": "El archivo no contiene asientos válidos para importar" }` o errores de validación globales.
- **409**: `{ "detail": "El ejercicio está cerrado" }` si todos los asientos caen en ejercicios cerrados.

**Reglas**: re-validación completa antes de escribir; cada asiento se persiste como transacción atómica (cabecera + líneas + incremento del contador correlativo + audit log) con `async with async_session.begin()`; numeración correlativa por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE` en secuencia bloqueada; asientos que fallen se omiten sin afectar a los demás; importes con `Decimal`/`NUMERIC(18,4)`.

## Exportación del libro diario

### GET `/api/v1/asientos/exportar`

Exporta el libro diario de la empresa activa a CSV o XLSX.

- **Query params**: `fecha_desde` (YYYY-MM-DD, requerido), `fecha_hasta` (YYYY-MM-DD, requerido), `formato` (CSV | XLSX, default CSV).
- **200**: archivo descargable con `Content-Disposition` (`attachment; filename="diario_{empresa}_{fecha_desde}_{fecha_hasta}.{csv|xlsx}"`).
  - CSV: encoding UTF-8 BOM, separador `;`, decimales con punto, 4 decimales exactos.
  - XLSX: hoja "Diario", formato de celda decimal para importes.
- **422**: `{ "detail": "Rango de fechas inválido" }` si `fecha_desde > fecha_hasta`.

**Reglas**: solo se exportan asientos `POSTED` de la empresa activa en el rango; importes con exactamente 4 decimales; solo asientos de la empresa activa (jamás de otra empresa).

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (ejercicio cerrado, datos modificados entre previsualización y confirmación).
- `422`: validación de negocio (formato, columnas, tamaño, validación de cuentas/balance).
- Errores de importes siempre en precisión decimal; el backend es el único que valida partida doble.
