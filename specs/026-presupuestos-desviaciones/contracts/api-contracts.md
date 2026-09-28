# API Contracts: Presupuestos y Desviaciones (SPEC-026)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...`. El `empresa_id` (a.k.a. `tenant_id`) activo se deriva **exclusivamente de la cabecera de sesión autenticada** — nunca del path ni del body (constitución III). Respuestas JSON; importes como strings decimales (p. ej. `"5000.0000"`), nunca coma flotante.

## Presupuestos

### GET `/api/v1/presupuestos`
Listado de líneas de presupuesto con filtros `ejercicio`, `cuenta_id`, `centro_coste_id` y paginación.
- 200: `{ "items": [{ "id", "ejercicio", "cuenta_id", "codigo_cuenta", "centro_coste_id", "nombre_centro", "importe", "tipo" }], "total" }`

### POST `/api/v1/presupuestos`
Crear o actualizar presupuesto por combinación cuenta-centro-ejercicio.
- Body: `{ "ejercicio": 2026, "cuenta_id": "<uuid>", "centro_coste_id": "<uuid|null>", "importe": "5000.0000", "tipo": "gasto" | "ingreso" }`
- Reglas: la cuenta debe ser `is_selectable=true` de la empresa activa; el centro, si se provee, debe pertenecer a la empresa; rechazo de duplicado idéntico (FR-005/422); el periodo de seguimiento debe estar `abierto` (409 si cerrado).
- 200: `{ "id", "importe", "tipo", "cuenta_id", "centro_coste_id" }`
- 409: periodo cerrado o ejercicio cerrado.
- 422: cuenta o centro inválido, duplicado idéntico.

### POST `/api/v1/presupuestos/importar`
Importar líneas de presupuesto en lote (CSV o JSON).
- Multipart `file` (`text/csv` o `application/json`) o Body: `{ "ejercicio": 2026, "lineas": [ { "codigo_cuenta", "centro", "importe", "tipo" } ] }`
- Reglas: validación fila por fila (Pydantic v2); errores 422 por filas inválidas con motivo; rechazo si el periodo está cerrado.
- 200: `{ "importadas": n, "errores": [ { "fila", "motivo" } ] }`
- 409: periodo cerrado.

## Seguimiento (desviaciones)

### GET `/api/v1/presupuestos/seguimiento?ejercicio=&cuenta_id=&centro_coste_id=`
Consulta de desviación por cuenta y centro para el ejercicio.
- 200: `{ "items": [{ "cuenta_id", "codigo_cuenta", "centro_coste_id", "nombre_centro", "importe_presupuestado", "importe_real", "desviacion_absoluta", "desviacion_relativa", "sin_presupuesto" }], "total" }`
- Las desviaciones se calculan `real − presupuesto` (convención `research.md` D2); `desviacion_relativa` null si presupuesto = 0.

### GET `/api/v1/presupuestos/seguimiento/periodo?ejercicio=`
Estado del periodo de seguimiento: abierto/cerrado, fecha, último cierre.
- 200: `{ "periodo_id", "numero_periodo", "estado", "fecha_cierre", "cerrado_por" }`

## Informes

### GET `/api/v1/presupuestos/informes/desviacion?ejercicio=&centro_coste_id=&mes=`
Informe de desviación acumulada por centro y cuenta.
- `mes` opcional: si se provee, devuelve el acumulado del mes; sin parámetro devuelve el acumulado anual.
- 200: `{ "ejercicio", "total_presupuestado", "total_real", "items": [{ "centro_coste_id", "nombre_centro", "cuenta_id", "codigo_cuenta", "importe_presupuestado", "importe_real", "desviacion_absoluta", "desviacion_relativa", "sin_presupuesto" }] }`

### POST `/api/v1/presupuestos/informes/cerrar`
Cerrar el periodo de seguimiento: genera snapshot `Desviacion` (trazable) y bloquea futuras modificaciones de presupuesto.
- Body: `{ "ejercicio": 2026, "periodo_id": "<uuid>" }`
- Reglas: periodo debe estar `abierto` (409 si ya cerrado); si no hay datos de desviación para un periodo, se cierra igual con `total = 0`; el snapshot queda inmutable.
- 200: `{ "periodo_id", "estado": "cerrado", "desviaciones_registradas": n, "fecha_cierre" }`
- 409: periodo ya cerrado; 422: ejercicio inexistente.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003); `403` si la empresa del contexto no pertenece al usuario.
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (periodo cerrado, ejercicio cerrado, doble cierre).
- `422`: validación de negocio (cuenta inválida, centro de otra empresa, duplicado idéntico, filas de importación inválidas, precisión > 4 decimales).
- El backend calcula el real desde el diario (constitución I); importes en precisión decimal.