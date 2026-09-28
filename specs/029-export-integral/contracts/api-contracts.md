# API Contracts: Export Integral del Tenant (SPEC-029)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/exportaciones`. **El `empresa_id` activo se deriva exclusivamente de la cabecera de sesión `X-Empresa-Id` (o token de sesión): nunca viaja en el path ni en el body de la petición.** Respuestas JSON; importes como `Decimal` strings (p. ej. `"123.4500"`), nunca números de coma flotante. El backend es el único que ejecuta consultas con filtro `empresa_id`; el frontend nunca recibe ni envía `empresa_id`.

## Exportaciones

### POST `/api/v1/exportaciones`
Crear y generar una exportación del tenant de la empresa activa.
- Body: `{ "tipo": "INTEGRAL" | "SII", "ejercicio_desde"?: 2024, "ejercicio_hasta"?: 2026 }`
- Reglas: sin `empresa_id` en body; el rango es opcional (si no se envía, exporta todo); para `tipo=SII` la empresa debe tener `ConfigSii.obligado_sii=true` (si no, 422). Generación síncrona (MVP): el ZIP se construye, persiste y devuelve el resumen en el mismo request.
- 201: `{ "exportacion_id", "numero_exportacion", "tipos": "INTEGRAL", "estado": "lista", "ejercicio_desde", "ejercicio_hasta", "sha256", "tamano_bytes", "n_bloques", "manifiesto": { "formato_version", "fecha_generacion", "bloques": [ { "bloque", "conteo_registros" } ] } }`
- 401/403: autenticación/permisos.
- 422: `tipo` inválido | `ejercicio_desde > ejercicio_hasta` | `tipo=SII` sin configuración SII.

### GET `/api/v1/exportaciones`
Listado de exportaciones de la empresa activa, ordenado por fecha descendente, con paginación y filtro `tipo`, `estado`.
- 200: `{ "items": [ { "exportacion_id", "numero_exportacion", "tipo", "estado", "ejercicio_desde", "ejercicio_hasta", "created_at", "sha256", "tamano_bytes", "n_bloques" } ], "total" }`

### GET `/api/v1/exportaciones/{id}`
Detalle de una exportación con su manifiesto (inventario de bloques).
- 200: `{ "exportacion_id", "numero_exportacion", "tipo", "estado", "creado_por", "created_at", "manifiesto": { "formato_version", "fecha_generacion", "bloques": [ { "bloque", "entidades_exportadas", "conteo_registros", "ejercicio_min", "ejercicio_max" } ], "sha256_fichero" } }`
- 404: exportación inexistente o de otra empresa (aislamiento).

### GET `/api/v1/exportaciones/{id}/descarga`
Descarga del ZIP generado.
- 200: `application/zip`, `Content-Disposition: attachment; filename="export_{empresa}_{numero}_{ano}.zip"`, binario del fichero.
- 409: exportación no `lista` (aún en proceso o fallida).
- 404: exportación inexistente o de otra empresa (aislamiento).

### POST `/api/v1/exportaciones/{id}/verificar`
Verificar la integridad de la exportación (recalcula el SHA-256 del ZIP y lo compara con el manifiesto; valida que el conteo de registros por bloque coincide).
- 200: `{ "integro": true | false, "sha256_calculado", "sha256_manifiesto", "bloques": [ { "bloque", "esperados", "encontrados" } ], "diferencias": [] }`
- Reglas: si el ZIP fue manipulado, `integro=false` y `diferencias` enumera los bloques inconsistentes; la verificación es auditable (se crea audit log `VERIFICAR`).
- 404: exportación inexistente o de otra empresa.

### GET `/api/v1/exportaciones/{id}/sii` *(opcional, tipo SII)*
Extraer el bloque de datos SII preparado para la AEAT (subconjunto de `datos_sii/`).
- 200: `{ "config": { "obligado_sii", "sin_anexo", "clave_regimen" }, "bloques_sii": [ { "nombre": "facturas_emitidas", "conteo": n, "registros": [ { "NIF", "NombreRazon", "TipoFactura", "FechaOperacion", "FechaExpedicion", "NumeroFactura", "ClaveRegimen", "BaseImponible", "TipoImpositivo", "CuotaRepercutida", "ImporteTotal", "EstadoCuadre" } ] } ] }`
- 404: exportación inexistente o de otra empresa; 422: la exportación no es de tipo `SII`.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (exportación en `en_proceso`/`fallida` no descargable).
- `422`: validación de negocio (rangos, tipos, configuración SII).
- Importes siempre como strings decimales en el ZIP y en respuestas JSON; el backend es el único que serializa con precisión.

## Verificación manual (huella)

```bash
# Tras descargar export.zip, el SHA-256 del fichero completo debe coincidir
# con el campo sha256_fichero del manifest.json interior y con sha256 del detalle.
sha256sum export.zip   # Linux/macOS
Get-FileHash export.zip -Algorithm SHA256   # Windows PowerShell
```