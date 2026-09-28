# API Contracts: Catálogo Versionado del Plan de Cuentas (SPEC-025)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...`. El `empresa_id` (a.k.a. `tenant_id`) activo se deriva **exclusivamente de la cabecera de sesión autenticada** — nunca del path ni del body (constitución III). Respuestas JSON; importes como strings decimales (p. ej. `"1000.0000"`), nunca coma flotante.

## Versiones del catálogo

### GET `/api/v1/catalogo/versiones`
Listado de versiones de la empresa activa con filtros `estado`, `fecha_inicio[gte/lte]`, paginación.
- 200: `{ "items": [{ "id", "numero_version", "codigo", "fecha_inicio", "fecha_fin", "estado", "es_migracion" }], "total" }`

### POST `/api/v1/catalogo/versiones`
Registrar una nueva versión del catálogo (alta manual).
- Body: `{ "codigo": "PGC-2026", "fecha_inicio": "2026-01-01", "fecha_fin": null, "cuentas": [ { "operacion": "alta" | "renombrado" | "baja", "codigo": "430", "nombre": "...", "padre_codigo": "...", "destino_codigo": "..." } ] }`
- Reglas: `numero_version` correlativo por empresa asignado atómicamente; rechazo de solape de vigencia (FR-006); las versiones anteriores quedan intactas (FR-001).
- 201: `{ "id", "numero_version", "codigo", "estado": "borrador", "fecha_inicio" }`
- 422: solape de vigencia, códigos duplicados, operación inválida.

### GET `/api/v1/catalogo/versiones/{id}`
Detalle de versión con su árbol de cuentas (`CatalogoCuenta`) y mapeos.
- 404: versión inexistente en la empresa activa.

### POST `/api/v1/catalogo/versiones/{id}/activar`
Activar la versión (borrador → vigente). Valida mapeos completos y saldos pendientes.
- 200: `{ "id", "estado": "vigente", "n_mapeos": n, "pendientes": [...] }`
- 422: mapeo incompleto de cuentas suprimidas/renombradas con saldo (FR-004); saldo sin destino.

## Importación normativa

### POST `/api/v1/catalogo/importar`
Importar una actualización normativa (CSV o JSON) con altas/renombrados/bajas y mapeo.
- Multipart `file` (`text/csv` o `application/json`) o Body: `{ "codigo_version": "PGC-2026", "fecha_inicio": "2026-01-01", "operaciones": [ { "operacion", "codigo", "nombre", "padre_codigo", "destino_codigo" } ], "mapeo": [ { "origen_codigo": "430", "destino_codigo": "4310" } ] }`
- Reglas: crea versión en `borrador`, genera `CatalogoCuenta` (nuevas/renombradas/suprimidas) y `MapeoCuenta` (origen autogenerado para igualdad); advierte de suprimidas sin mapeo (422 `pendientes_mapeo`) sin cerrar la migración.
- 200: `{ "version_id", "nuevas": n, "renombradas": n, "suprimidas": n, "mapeos": n, "pendientes_mapeo": [{ "codigo", "motivo": "sin_destino" | "saldo_no_cero" }] }`
- 422: fichero mal formado, filas no parseables con motivo (validación Pydantic v2).

## Resolución histórica

### GET `/api/v1/catalogo/vigente?fecha=YYYY-MM-DD`
Versión del catálogo vigente en la fecha indicada (FR-003). Si ninguna versión cubre la fecha, usa la primera con `fecha_inicio` más antigua y lo marca como `fallback`.
- 200: `{ "version_id", "numero_version", "codigo", "fecha_inicio", "fecha_fin", "resolucion": "vigente" | "fallback" }`

### GET `/api/v1/catalogo/cuentas?version_id=&q=`
Autocompletar/búsqueda de cuentas dentro de una versión concreta (código o nombre del `CatalogoCuenta`), para UI de "cuenta vigente en fecha".
- 200: `{ "items": [{ "account_id", "codigo_version", "nombre_version", "estado" }] }`

## Reclasificación de saldos (apertura, SPEC-009)

### GET `/api/v1/catalogo/reclasificar/preview?version_id=&ejercicio=`
Previsualización de la reclasificación: para cada cuenta con saldo ≠ 0 propone el destino según `MapeoCuenta` y calcula importes (`Decimal`).
- 200: `{ "items": [{ "cuenta_origen_id", "codigo_origen", "importe", "cuenta_destino_id", "codigo_destino", "mapeo_id" }], "total_importe": "..." }`
- 422: cuentas sin destino en el mapeo.

### POST `/api/v1/catalogo/reclasificar/confirmar`
Confirmar la reclasificación: genera asientos `ADJUSTMENT` balanceados, registra `ReclasificacionSaldo` y vincula al asiento de apertura (SPEC-009).
- Body: `{ "version_id": "<id>", "ejercicio": 2026, "items": [ { "cuenta_origen_id", "importe", "cuenta_destino_id", "mapeo_id" } ] }`
- Reglas: suma origen == suma destino (cuadre); cada asiento cumple Debe==Haber (constitución I); NUNCA modifica asientos históricos.
- 200: `{ "reclasificaciones": n, "asientos": [{ "asiento_id", "cuadre": true }], "total_importe" }`
- 409: ejercicio ya abierto o versión no activable; 422: cuadre fallido o precisión > 4 decimales.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003); `403` si la empresa del contexto no pertenece al usuario.
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (ejercicio cerrado/abierto, activación no permitida).
- `422`: validación de negocio (solapes, mapeos incompletos, filas de importación inválidas, cuadre de reclasificación).
- El backend es el único que valida balance (constitución I); importes en precisión decimal.